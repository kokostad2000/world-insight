"""Unified command-line entry points. All writes stay local to selected data/programs."""
import argparse
import json
import subprocess
import sys
from pathlib import Path
from server.platform.config import ROOT
from . import backup, runtime, update


def parser():
    result = argparse.ArgumentParser(description="World Insight 本地启动、备份、恢复与更新")
    result.add_argument("command", choices=("start", "stop", "check", "backup", "restore", "update", "status"))
    result.add_argument("package", nargs="?", help="恢复包路径")
    result.add_argument("--root", default=str(ROOT))
    result.add_argument("--data-dir")
    result.add_argument("--port", type=int)
    result.add_argument("--init", action="store_true", help="明确初始化新的数据目录，不覆盖既有配置")
    result.add_argument("--no-browser", action="store_true")
    result.add_argument("--no-scheduler", action="store_true", help="离线验收时禁用采集器，不改变保存的来源配置")
    result.add_argument("--output", help="新的备份输出路径；不会覆盖已存在文件")
    result.add_argument("--apply", action="store_true", help="预览验证后应用恢复到空目录")
    result.add_argument("--replace", action="store_true", help="明确替换已有数据，先建立恢复点；仍须 --apply")
    result.add_argument("--start-after", action="store_true")
    result.add_argument("--target", help="明确本地 Git ref 或提交；不隐式下载/推送")
    result.add_argument("--dry-run", action="store_true", help="准备目标程序并显示更新计划，不修改研究数据")
    result.add_argument("--rollback", metavar="UPDATE_ID")
    result.add_argument("--recover", metavar="UPDATE_ID")
    result.add_argument("--probe-network", action="store_true", help="单独探测免费源；本地检查默认不联网")
    result.add_argument("--probe-sources", default="rss,world_bank,gdelt")
    return result


def main(argv=None):
    args = parser().parse_args(argv)
    try:
        config = runtime.prepare_config(args.root, args.data_dir, args.port)
        config["no_scheduler"] = args.no_scheduler
        if args.command == "check":
            result = runtime.check(config, args.init)
            print(json.dumps(result, ensure_ascii=False, indent=2))
            code = 0 if result["ok"] else 1
            if args.probe_network:
                if any(item not in {"rss", "world_bank", "gdelt"} for item in args.probe_sources.split(",")):
                    raise runtime.OpsError("联网探测仅支持 rss,world_bank,gdelt 免费源")
                print("独立免费源联网探测（以上本地检查结果不受此探测替代）：", flush=True)
                process = subprocess.run([sys.executable, "-m", "server.modules.sources.probe", "--sources", args.probe_sources], cwd=config["root"])
                code = max(code, process.returncode)
            return code
        if args.command == "status":
            result = {"runtime": runtime.own_runtime(config), "selected_program": str(runtime.selected_program(config)), "data_dir": str(config["data_dir"]), "maintenance": runtime.read_json(config["data_dir"] / "maintenance.json")}
        elif args.command == "start":
            with runtime.operation_lock(config):
                result = runtime.start(config, args.init, not args.no_browser and config["open_browser"], no_scheduler=args.no_scheduler)
        elif args.command == "stop":
            with runtime.operation_lock(config):
                result = runtime.stop(config)
        elif args.command == "backup":
            with runtime.operation_lock(config):
                result = backup.create_backup(config, args.output)
        elif args.command == "restore":
            if not args.package:
                raise runtime.OpsError("恢复需要指定备份文件；默认仅验证与预览，--apply 执行，已有数据另加 --replace")
            if args.apply:
                with runtime.operation_lock(config):
                    result = backup.restore_backup(config, args.package, args.apply, args.replace, args.start_after)
            else:
                result = backup.restore_backup(config, args.package)
        elif args.command == "update":
            if sum(bool(value) for value in (args.target, args.rollback, args.recover)) != 1:
                raise runtime.OpsError("更新须指定一个 --target、--rollback 或 --recover")
            with runtime.operation_lock(config):
                if args.rollback:
                    result = update.rollback(config, args.rollback)
                elif args.recover:
                    result = update.recover(config, args.recover)
                else:
                    result = update.update(config, args.target, args.dry_run)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except runtime.OpsError as error:
        print(json.dumps({"status": "blocked", "message": str(error)}, ensure_ascii=False), file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("操作被中断；有效旧备份和数据保持。若处于更新维护状态，请用 --recover 和日志中的更新 ID 恢复。", file=sys.stderr)
        return 130
    except Exception as error:
        # No raw provider/system exception may leak secrets or credentials.
        print(json.dumps({"status": "failed", "error_type": type(error).__name__, "message": "本地操作失败；查看数据目录 logs/operations.jsonl。未将异常原文或配置值输出。"}, ensure_ascii=False), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
