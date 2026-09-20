"""Explicit local-version deployment with matched program/data rollback."""
import hashlib
import io
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import tarfile
import tempfile
import uuid
from pathlib import Path
from .backup import _replace_data, create_backup, inspect_database, unpack_verified
from .runtime import OpsError, atomic_json, event_log, health, now, own_runtime, program_info, read_json, selected_program, start, stop


def _git(root, *args):
    result = subprocess.run(["git", *args], cwd=root, capture_output=True, timeout=30)
    if result.returncode:
        raise OpsError("本地 Git 操作失败；目标版本可能不可用，未连接 GitHub，也未清理工作区")
    return result.stdout


def workspace_state(root):
    raw = _git(root, "status", "--porcelain=v1", "--untracked-files=all").decode()
    return {"clean": not raw.strip(), "entries": raw.splitlines()}


def database_fingerprint(path):
    db = sqlite3.connect(f"file:{Path(path)}?mode=ro", uri=True)
    digest = hashlib.sha256()
    try:
        db.execute("BEGIN")
        for table, columns, order in (("records", "kind,id,version,data", "kind,id"), ("versions", "kind,id,version,data", "kind,id,version")):
            for row in db.execute(f"SELECT {columns} FROM {table} ORDER BY {order}"):
                digest.update(json.dumps(list(row), ensure_ascii=False, separators=(",", ":")).encode())
        digest.update(str(db.execute("PRAGMA user_version").fetchone()[0]).encode())
        return digest.hexdigest()
    finally:
        db.close()


def prepare_release(config, target):
    root = config["root"]
    state = workspace_state(root)
    if not state["clean"]:
        raise OpsError("更新已暂停：工作区有已修改或未跟踪文件；请先自行提交/保存，或选择另一个干净代码目录。未重置、未清理任何文件")
    commit = _git(root, "rev-parse", "--verify", "--end-of-options", target + "^{commit}").decode().strip()
    archive_bytes = _git(root, "archive", "--format=tar", commit)
    programs = config["data_dir"].parent / "World Insight Programs"
    programs.mkdir(parents=True, exist_ok=True)
    release = programs / commit
    if release.exists():
        recorded = read_json(release / "release.json", {})
        if recorded.get("commit") != commit:
            raise OpsError("目标程序目录已有不同内容，拒绝覆盖")
        return release, program_info(release)
    stage = programs / (".prepare-" + uuid.uuid4().hex)
    stage.mkdir()
    try:
        with tarfile.open(fileobj=io.BytesIO(archive_bytes)) as archive:
            for member in archive.getmembers():
                target_path = (stage / member.name).resolve()
                if not target_path.is_relative_to(stage.resolve()) or member.issym() or member.islnk() or member.isdev():
                    raise OpsError("目标版本含不安全归档路径或链接，拒绝准备")
                if member.isdir():
                    target_path.mkdir(parents=True, exist_ok=True)
                elif member.isfile():
                    target_path.parent.mkdir(parents=True, exist_ok=True)
                    with archive.extractfile(member) as src, target_path.open("wb") as dest:
                        shutil.copyfileobj(src, dest)
                    target_path.chmod(member.mode & 0o777)
        lock = stage / "requirements.lock"
        if not lock.is_file() or any(line.strip() and not line.lstrip().startswith("#") for line in lock.read_text().splitlines()):
            raise OpsError("目标版本有未准备的第三方依赖；本版只接受标准库锁文件，研究数据未修改")
        info = program_info(stage)
        if not (stage / "server" / "app.py").is_file():
            raise OpsError("目标版本缺少本地服务入口")
        atomic_json(stage / "release.json", {"commit": commit, "prepared_at": now(), "schema_version": info["schema_version"]})
        os.replace(stage, release)
        return release, program_info(release)
    except BaseException:
        if stage.exists():
            shutil.rmtree(stage)
        raise


def _validate_running(config, expected_root):
    status = health(config["port"])
    if not status or status.get("status") != "ok" or status.get("data_dir") != str(config["data_dir"]):
        raise OpsError("目标程序健康检查失败")
    import urllib.request
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with opener.open(f'http://127.0.0.1:{config["port"]}/api/topics?limit=1', timeout=3) as response:
        value = json.load(response)
        if not isinstance(value.get("items"), list):
            raise OpsError("目标程序不能读取既有议题")
    info = program_info(expected_root)
    verified = inspect_database(config["db_path"], info["schema_version"])
    return {"health": status, "data": verified, "topic_count": value["total"]}


def _restore_exact(config, package, program_root):
    info = program_info(program_root)
    with tempfile.TemporaryDirectory(prefix="world-insight-update-rollback-", dir=config["data_dir"].parent) as tmp:
        stage = Path(tmp)
        unpack_verified(package, stage, info["schema_version"])
        point = _replace_data(config, stage)
    return str(point)


def update(config, target, dry_run=False):
    old_root = selected_program(config)
    old_program = program_info(old_root)
    release, new_program = prepare_release(config, target)
    initial = inspect_database(config["db_path"], old_program["schema_version"])
    plan = {"current": old_program, "target": new_program, "database": initial, "data_dir": str(config["data_dir"]), "release_directory": str(release), "workspace": workspace_state(config["root"]), "network_used": False}
    if dry_run:
        return {"status": "prepared", **plan}
    if new_program["schema_version"] < initial["schema_version"]:
        raise OpsError("目标版本不能读取现有数据库，拒绝仅回退程序")
    update_id = now().replace(":", "-") + "-" + uuid.uuid4().hex[:8]
    log_path = config["data_dir"] / "updates" / (update_id + ".json")
    maintenance = config["data_dir"] / "maintenance.json"
    if maintenance.exists():
        raise OpsError("发现未结束的维护状态；请先检查上次更新日志并显式恢复，未重复迁移")
    prior_selection = read_json(config["data_dir"] / "active-program.json")
    was_running = bool(own_runtime(config, require_health=False))
    record = {"id": update_id, "state": "preparing", "started_at": now(), "old_program": old_program, "new_program": new_program, "prior_selection": prior_selection, "was_running": was_running, "data_dir": str(config["data_dir"])}
    atomic_json(log_path, record)
    backup = None
    try:
        atomic_json(maintenance, {"operation": "update", "update_id": update_id, "at": now()})
        stop(config)
        backup = create_backup(config, label="before-update")
        record.update({"state": "backed_up", "backup": backup["package"]})
        atomic_json(log_path, record)
        # Starting target performs its real migration registry, then real HTTP health/read verification.
        start(config, program_root=release, open_browser=False)
        validation = _validate_running(config, release)
        if any(validation["data"]["counts"].get(kind, 0) < count for kind, count in initial["counts"].items()):
            raise OpsError("升级后关键记录数量减少，拒绝切换")
        atomic_json(config["data_dir"] / "active-program.json", {"root": str(release), "commit": new_program["commit"], "selected_at": now(), "update_id": update_id})
        record.update({"state": "complete", "completed_at": now(), "validation": validation, "post_update_fingerprint": database_fingerprint(config["db_path"])})
        atomic_json(log_path, record)
        maintenance.unlink(missing_ok=True)
        event_log(config, "update_complete", update_id=update_id, commit=new_program["commit"])
        return {"status": "updated", "update_id": update_id, "record": str(log_path), **plan, "validation": validation}
    except BaseException as error:
        failure = type(error).__name__
        record.update({"state": "failed", "failure_type": failure})
        atomic_json(log_path, record)
        try:
            stop(config)
            if backup:
                record["failed_state_restore_point"] = _restore_exact(config, backup["package"], old_root)
            if prior_selection:
                atomic_json(config["data_dir"] / "active-program.json", prior_selection)
            else:
                (config["data_dir"] / "active-program.json").unlink(missing_ok=True)
            maintenance.unlink(missing_ok=True)
            if was_running:
                start(config, program_root=old_root, open_browser=False)
                _validate_running(config, old_root)
            record.update({"state": "rolled_back", "rollback_at": now(), "rollback_program": str(old_root)})
            atomic_json(log_path, record)
            event_log(config, "update_rolled_back", update_id=update_id, failure_type=failure)
        except BaseException as rollback_error:
            record.update({"state": "rollback_requires_attention", "rollback_failure_type": type(rollback_error).__name__})
            atomic_json(log_path, record)
            raise OpsError(f"更新失败且自动回退需检查；保留维护状态、备份及日志：{log_path}")
        raise OpsError(f"更新失败（{failure}），已恢复兼容的旧程序及数据库/附件；日志：{log_path}")


def rollback(config, update_id):
    if Path(update_id).name != update_id:
        raise OpsError("回退 ID 无效")
    log_path = config["data_dir"] / "updates" / (update_id + ".json")
    record = read_json(log_path)
    if not record or record.get("state") != "complete":
        raise OpsError("没有对应的成功更新记录可回退")
    selection = read_json(config["data_dir"] / "active-program.json", {})
    if selection.get("update_id") != update_id:
        raise OpsError("该更新并非当前选定版本，拒绝跨版本盲目回退")
    # Always preserve the current state before deciding whether old data may be selected.
    preserved = create_backup(config, label="before-requested-rollback")
    if database_fingerprint(config["db_path"]) != record.get("post_update_fingerprint"):
        event_log(config, "rollback_refused_new_writes", update_id=update_id, current_backup=preserved["package"])
        raise OpsError(f"更新后存在新写入，已保留当前备份 {preserved['package']}；不自动用旧快照覆盖。需单独核对兼容性或导出新记录后人工迁移")
    maintenance = config["data_dir"] / "maintenance.json"
    atomic_json(maintenance, {"operation": "rollback", "update_id": update_id, "at": now()})
    stop(config)
    # Recheck after stopping closes the race with a new write during the online backup.
    if database_fingerprint(config["db_path"]) != record.get("post_update_fingerprint"):
        maintenance.unlink(missing_ok=True)
        start(config, open_browser=False)
        raise OpsError("回退前出现新写入，已停止回退且保留现状")
    old_root = Path(record["old_program"]["root"])
    recovery = _restore_exact(config, record["backup"], old_root)
    if record.get("prior_selection"):
        atomic_json(config["data_dir"] / "active-program.json", record["prior_selection"])
    else:
        (config["data_dir"] / "active-program.json").unlink(missing_ok=True)
    start(config, program_root=old_root, open_browser=False)
    _validate_running(config, old_root)
    maintenance.unlink(missing_ok=True)
    record.update({"state": "explicitly_rolled_back", "rollback_at": now(), "current_preserved_backup": preserved["package"], "restore_point": recovery})
    atomic_json(log_path, record)
    return {"status": "rolled_back", "update_id": update_id, "program_root": str(old_root), "preserved_current_backup": preserved["package"], "restore_point": recovery}


def recover(config, update_id):
    """Explicit recovery of an interrupted transaction while maintenance blocks new writes."""
    if Path(update_id).name != update_id:
        raise OpsError("恢复 ID 无效")
    path = config["data_dir"] / "updates" / (update_id + ".json")
    record = read_json(path)
    maintenance = config["data_dir"] / "maintenance.json"
    marker = read_json(maintenance, {})
    if not record or marker.get("update_id") != update_id:
        raise OpsError("未找到匹配的中断维护记录；不猜测需要恢复的版本")
    if record["state"] == "complete":
        _validate_running(config, Path(record["new_program"]["root"]))
        maintenance.unlink()
        return {"status": "completed_update_recovered", "update_id": update_id}
    if record["state"] not in {"preparing", "backed_up", "failed", "rollback_requires_attention"}:
        raise OpsError("该记录不处于可恢复的中断状态")
    stop(config)
    old_root = Path(record["old_program"]["root"])
    if record.get("backup"):
        record["failed_state_restore_point"] = _restore_exact(config, record["backup"], old_root)
    if record.get("prior_selection"):
        atomic_json(config["data_dir"] / "active-program.json", record["prior_selection"])
    else:
        (config["data_dir"] / "active-program.json").unlink(missing_ok=True)
    if record.get("was_running"):
        start(config, program_root=old_root, open_browser=False)
        _validate_running(config, old_root)
    maintenance.unlink(missing_ok=True)
    record.update({"state": "recovered_to_old", "recovered_at": now()})
    atomic_json(path, record)
    return {"status": "recovered_to_old", "update_id": update_id, "program_root": str(old_root)}
