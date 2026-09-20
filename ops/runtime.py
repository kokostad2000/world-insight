"""Local process ownership, preflight and persisted program selection."""
import contextlib
import fcntl
import json
import os
import platform
import shutil
import signal
import socket
import sqlite3
import subprocess
import sys
import time
import threading
import urllib.request
import uuid
from pathlib import Path
from server.platform.config import ROOT, load_config


class OpsError(RuntimeError):
    pass


def now():
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def read_json(path, default=None):
    try:
        return json.loads(Path(path).read_text())
    except FileNotFoundError:
        return default
    except (ValueError, UnicodeError):
        raise OpsError(f"本地状态文件格式损坏：{Path(path).name}；请恢复该文件，不自动重建空状态")


def atomic_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp-" + uuid.uuid4().hex)
    try:
        with temporary.open("w") as stream:
            json.dump(value, stream, ensure_ascii=False, indent=2)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def event_log(config, event, **details):
    # Callers only supply whitelisted operational fields, never exception strings or environment values.
    log = config["data_dir"] / "logs" / "operations.jsonl"
    log.parent.mkdir(parents=True, exist_ok=True)
    with log.open("a") as stream:
        stream.write(json.dumps({"at": now(), "event": event, **details}, ensure_ascii=False) + "\n")


def prepare_config(root=ROOT, data_dir=None, port=None):
    try:
        return load_config(root=Path(root), data_dir=data_dir, port=port)
    except (ValueError, TypeError, OSError):
        raise OpsError("配置格式、目录或端口无效；核对 .env 中的字段（配置值未输出）。端口范围为 1024—65535")


def create_env(root):
    path = Path(root) / ".env"
    if not path.exists():
        try:
            with path.open("x") as stream:
                stream.write((Path(root) / ".env.example").read_text())
        except FileExistsError:
            pass


def selected_program(config):
    selection = read_json(config["data_dir"] / "active-program.json")
    if not selection:
        return config["root"]
    root = Path(selection.get("root", "")).resolve()
    if not (root / "server" / "app.py").is_file():
        raise OpsError("已选程序目录不可用；保留现有数据，请修复 active-program.json 对应程序或执行明确回退")
    return root


def program_info(root):
    root = Path(root).resolve()
    try:
        result = subprocess.run([sys.executable, "-c", "import json; from server.platform.migrations import SCHEMA_VERSION; from pathlib import Path; print(json.dumps({'schema_version':SCHEMA_VERSION,'version':Path('VERSION').read_text().strip()}))"], cwd=root, capture_output=True, text=True, timeout=10)
        if result.returncode:
            raise OpsError("目标程序依赖或迁移定义不可加载；未修改研究数据")
        info = json.loads(result.stdout)
    except (OSError, ValueError, subprocess.TimeoutExpired):
        raise OpsError("程序元数据检查失败；请核对 Python 版本和完整代码目录")
    commit = subprocess.run(["git", "rev-parse", "HEAD"], cwd=root, capture_output=True, text=True).stdout.strip() if shutil.which("git") else ""
    release_info = read_json(root / "release.json", {})
    return {"root": str(root), "version": info["version"], "schema_version": info["schema_version"], "commit": release_info.get("commit") or commit or None}


def health(port):
    try:
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with opener.open(f"http://127.0.0.1:{port}/api/health", timeout=1) as response:
            if response.status == 200:
                return json.load(response)
    except (OSError, ValueError):
        pass
    return None


def is_alive(pid):
    if type(pid) is not int or pid <= 1:
        return False
    try:
        os.kill(pid, 0)
        state = subprocess.run(["/bin/ps", "-p", str(pid), "-o", "state="], capture_output=True, text=True)
        return state.returncode == 0 and not state.stdout.strip().startswith("Z")
    except ProcessLookupError:
        return False
    except PermissionError:
        return True


def own_runtime(config, require_health=True):
    runtime = read_json(config["data_dir"] / "runtime.json")
    identity = read_json(config["data_dir"] / "instance.json")
    if not runtime or not identity or runtime.get("instance_id") != identity.get("instance_id") or runtime.get("data_dir") != str(config["data_dir"]):
        return None
    if not is_alive(runtime.get("pid")):
        return None
    status = health(runtime.get("port"))
    if status and status.get("app") == "world-insight" and all(status.get(key) == runtime.get(key) for key in ("pid", "instance_id", "data_dir")):
        return runtime
    if require_health:
        return None
    process = subprocess.run(["/bin/ps", "-p", str(runtime["pid"]), "-o", "command="], capture_output=True, text=True)
    command = process.stdout
    if process.returncode == 0 and "-m server.app" in command and "--data-dir " + str(config["data_dir"]) in command:
        return runtime
    return None



def pending_runtime(config):
    pending = read_json(config["data_dir"] / "pending-start.json")
    if not pending or pending.get("data_dir") != str(config["data_dir"]) or not is_alive(pending.get("pid")):
        return None
    process = subprocess.run(["/bin/ps", "-p", str(pending["pid"]), "-o", "command="], capture_output=True, text=True)
    if process.returncode == 0 and "-m server.app" in process.stdout and "--data-dir " + str(config["data_dir"]) in process.stdout:
        return pending
    return None

def port_free(port):
    with socket.socket() as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sock.bind(("127.0.0.1", port))
            return True
        except PermissionError:
            raise OpsError("当前执行环境禁止绑定本机端口；请在获得本地服务权限的终端运行，未终止任何程序")
        except OSError:
            return False


def _writable(path):
    path = Path(path)
    current = path
    while not current.exists() and current != current.parent:
        current = current.parent
    if not current.is_dir() or not os.access(current, os.W_OK | os.X_OK):
        return False
    # Real create-and-remove probe catches read-only volumes/ACL failures.
    probe = current / (".world-insight-probe-" + uuid.uuid4().hex)
    try:
        with probe.open("x") as stream:
            stream.write("probe")
        probe.unlink()
        return True
    except OSError:
        probe.unlink(missing_ok=True)
        return False


def check(config, initialize=False, program_root=None):
    checks = []
    def add(level, name, message, fix=None):
        checks.append({"level": level, "name": name, "message": message, "fix": fix})
    if sys.version_info[:2] != (3, 11):
        add("block", "python", "需要 CPython 3.11.x", "安装 Python 3.11，并用 WORLD_INSIGHT_PYTHON 指定其可执行文件")
    else:
        add("pass", "python", f"CPython {platform.python_version()} / {platform.system()} {platform.machine()}")
    if not shutil.which("curl"):
        add("warning", "curl", "系统 curl 不可用，免费源联网采集不可用，核心人工研究仍可运行", "安装或恢复系统 curl")
    else:
        add("pass", "curl", "系统 curl 可用；本地检查不发出网络请求")
    if not shutil.which("git"):
        add("warning", "git", "Git 不可用，历史阅读可用，版本更新不可用", "更新前安装 Git")
    else:
        add("pass", "git", "Git 可用；本地检查未连接 GitHub")
    for key in ("data_dir", "backup_dir"):
        writable = _writable(config[key])
        add("pass" if writable else "block", key, "目录可读写" if writable else "目录不可写", "选择可写目录，不修改其他应用数据")
    existing = read_json(config["data_dir"] / "instance.json")
    if not existing:
        add("warning" if initialize and not config["db_path"].exists() else "block", "data_binding", "此目录尚未确认，未自动创建空库", "首次新建使用 --init；已有研究请指定原数据目录")
    elif not config["db_path"].is_file():
        add("block", "data_binding", "实例身份存在但数据库缺失", "先恢复备份，不在原目录创建空库")
    else:
        add("pass", "data_binding", "既有数据身份与数据库均存在")
    if config["data_dir"].is_relative_to(config["root"]):
        add("warning", "data_location", "数据位于程序目录内，更新前请迁往独立目录", "建议默认 ~/Library/Application Support/World Insight")
    root = Path(program_root or selected_program(config))
    try:
        info = program_info(root)
        if config["db_path"].exists():
            connection = sqlite3.connect(f'file:{config["db_path"]}?mode=ro', uri=True)
            try:
                schema = connection.execute("PRAGMA user_version").fetchone()[0]
                integrity = connection.execute("PRAGMA quick_check").fetchone()[0]
            finally:
                connection.close()
            if schema > info["schema_version"]:
                add("block", "schema", f"数据库版本 {schema} 高于目标程序支持 {info['schema_version']}", "选择兼容程序，禁止仅回退代码")
            elif integrity != "ok":
                add("block", "schema", "数据库快速完整性检查失败", "保留现状并恢复已验证备份")
            else:
                add("pass", "schema", f"数据库 {schema} / 程序支持 {info['schema_version']}")
        else:
            add("pass", "schema", f"新库使用数据库版本 {info['schema_version']}")
    except (OpsError, sqlite3.DatabaseError, OSError):
        add("block", "schema", "程序或数据库版本检查失败", "核对完整代码和数据目录，保留原始文件")
    owner = own_runtime(config)
    if owner and owner["port"] == config["port"]:
        add("pass", "port", "既有本项目实例可复用")
    elif not port_free(config["port"]):
        add("block", "port", "端口被其他实例或应用占用，未终止该程序", "在 .env 设置另一 WORLD_INSIGHT_PORT")
    else:
        add("pass", "port", "本机回环端口可用")
    parent = config["data_dir"]
    while not parent.exists():
        parent = parent.parent
    free = shutil.disk_usage(parent).free
    required = max(100 * 1024 * 1024, config["db_path"].stat().st_size * 3 if config["db_path"].exists() else 0)
    add("pass" if free >= required else "block", "disk", "可用空间满足本地启动要求" if free >= required else "空间不足以安全写入和保留恢复点", "释放明确可重建内容或更换数据目录")
    add("warning", "optional_providers", "AI、航空、船舶、行情默认未接入；无收费调用，不阻止人工研究")
    add("pass", "network_boundary", "以上仅本地检查，未向免费源或收费服务发送请求；联网状态须单独探测")
    return {"ok": not any(c["level"] == "block" for c in checks), "checked_at": now(), "checks": checks, "data_dir": str(config["data_dir"]), "port": config["port"], "program_root": str(root)}


@contextlib.contextmanager
def operation_lock(config):
    config["data_dir"].mkdir(parents=True, exist_ok=True)
    with (config["data_dir"] / "operations.lock").open("a+") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise OpsError("另一个备份/恢复/更新操作仍在执行，请等待该操作完成")
        try:
            yield
        finally:
            fcntl.flock(lock, fcntl.LOCK_UN)


def start(config, initialize=False, open_browser=True, program_root=None, no_scheduler=False):
    root = Path(program_root or selected_program(config)).resolve()
    if (config["data_dir"] / "maintenance.json").exists() and program_root is None:
        raise OpsError("上次维护尚未结束；核对 updates 日志后使用 update.sh --recover <更新ID>，不启动新的写入")
    create_env(config["root"])
    owner = own_runtime(config)
    if not owner and pending_runtime(config):
        raise OpsError("该数据目录已有尚未完成启动的本项目进程；请先停止或恢复中断更新，不启动第二份")
    if owner:
        if Path(owner["root"]).resolve() != root or owner["port"] != config["port"]:
            raise OpsError("该数据目录已有不同程序或端口的实例；先使用停止入口关闭现有实例，再重新启动")
        result = {"status": "reused", **owner, "url": f'http://127.0.0.1:{owner["port"]}'}
        if open_browser:
            import webbrowser
            webbrowser.open(result["url"])
        return result
    report = check(config, initialize, root)
    if not report["ok"]:
        blocks = [row["message"] + "；" + (row["fix"] or "") for row in report["checks"] if row["level"] == "block"]
        raise OpsError("启动检查未通过：" + " / ".join(blocks))
    config["data_dir"].mkdir(parents=True, exist_ok=True)
    (config["data_dir"] / "logs").mkdir(exist_ok=True)
    command = [sys.executable, "-m", "server.app", "--data-dir", str(config["data_dir"]), "--port", str(config["port"])]
    if initialize:
        command.append("--init")
    if no_scheduler or config.get("no_scheduler"):
        command.append("--no-scheduler")
    logfile = config["data_dir"] / "logs" / "server.log"
    with logfile.open("ab") as log:
        process = subprocess.Popen(command, cwd=root, stdin=subprocess.DEVNULL, stdout=log, stderr=log, start_new_session=True)
    atomic_json(config["data_dir"] / "pending-start.json", {"pid": process.pid, "root": str(root), "data_dir": str(config["data_dir"]), "port": config["port"], "started_at": now()})
    threading.Thread(target=process.wait, daemon=True, name="world-insight-child-reaper").start()
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        status = health(config["port"])
        if status and status.get("app") == "world-insight" and status.get("pid") == process.pid and status.get("data_dir") == str(config["data_dir"]):
            (config["data_dir"] / "pending-start.json").unlink(missing_ok=True)
            event_log(config, "started", pid=process.pid, root=str(root), port=config["port"])
            result = {"status": "started", **status, "root": str(root), "url": f'http://127.0.0.1:{config["port"]}'}
            if open_browser:
                import webbrowser
                webbrowser.open(result["url"])
            return result
        if process.poll() is not None:
            (config["data_dir"] / "pending-start.json").unlink(missing_ok=True)
            raise OpsError(f"本地服务在健康检查前退出（退出码 {process.returncode}）；查看脱敏日志 {logfile}")
        time.sleep(.15)
    process.terminate()
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        pass
    raise OpsError(f"启动健康检查超时，未报告成功；查看脱敏日志 {logfile}")


def stop(config):
    runtime = own_runtime(config, require_health=False)
    pending = pending_runtime(config) if not runtime else None
    runtime = runtime or pending
    if not runtime:
        stale = read_json(config["data_dir"] / "runtime.json")
        if stale and is_alive(stale.get("pid")):
            raise OpsError("运行身份无法确认；为保护其他程序，没有发送停止信号")
        return {"status": "already_stopped", "data_preserved": True}
    os.kill(runtime["pid"], signal.SIGTERM)
    deadline = time.monotonic() + 20
    while time.monotonic() < deadline:
        if (not pending and not (config["data_dir"] / "runtime.json").exists()) or not is_alive(runtime["pid"]):
            (config["data_dir"] / "pending-start.json").unlink(missing_ok=True)
            event_log(config, "stopped", pid=runtime["pid"])
            return {"status": "stopped", "pid": runtime["pid"], "data_preserved": True}
        time.sleep(.15)
    raise OpsError("本项目实例仍在安全停止写入，未强制终止；稍后重试停止入口")
