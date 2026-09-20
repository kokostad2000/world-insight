"""Verified SQLite snapshots and atomic, reversible restoration."""
import hashlib
import json
import os
import shutil
import sqlite3
import tempfile
import uuid
import zipfile
from pathlib import Path, PurePosixPath
from .runtime import OpsError, atomic_json, event_log, now, own_runtime, program_info, read_json, selected_program, start, stop

FORMAT = 1
DB_NAME = "world-insight.sqlite"


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def inspect_database(path, maximum_schema=None):
    try:
        db = sqlite3.connect(f"file:{Path(path)}?mode=ro", uri=True)
        try:
            integrity = db.execute("PRAGMA integrity_check").fetchone()[0]
            schema = db.execute("PRAGMA user_version").fetchone()[0]
            if integrity != "ok" or schema < 1:
                raise OpsError("数据库完整性或版本无效")
            if maximum_schema is not None and schema > maximum_schema:
                raise OpsError("备份数据库版本高于当前程序支持，拒绝不兼容恢复")
            counts = {row[0]: row[1] for row in db.execute("SELECT kind,count(*) FROM records GROUP BY kind")}
            mismatches = db.execute("SELECT count(*) FROM records r LEFT JOIN versions v ON r.kind=v.kind AND r.id=v.id AND r.version=v.version WHERE v.id IS NULL OR v.data!=r.data").fetchone()[0]
            if mismatches or list(db.execute("PRAGMA foreign_key_check")):
                raise OpsError("数据库当前版本与历史版本不一致")
            versions = {(row[0], row[1], row[2]) for row in db.execute("SELECT kind,id,version FROM versions")}
            ids = {(row[0], row[1]) for row in db.execute("SELECT kind,id FROM records")}
            def walk(value):
                if isinstance(value, dict):
                    for key, child in value.items():
                        if key.endswith("evidence_version_ids") and isinstance(child, list):
                            for ref in child:
                                try:
                                    evidence_id, version = ref.rsplit("@", 1)
                                    if ("evidence", evidence_id, int(version)) not in versions:
                                        raise ValueError()
                                except (ValueError, TypeError, AttributeError):
                                    raise OpsError("备份存在无法恢复的材料版本引用")
                        elif key == "judgment_id" and child and ("judgment", child) not in ids:
                            raise OpsError("备份存在缺失的判断引用")
                        elif key == "claim_ids" and isinstance(child, list):
                            if any(("claim", item) not in ids for item in child):
                                raise OpsError("备份存在缺失的说法引用")
                        else:
                            walk(child)
                elif isinstance(value, list):
                    for child in value:
                        walk(child)
            for (raw,) in db.execute("SELECT data FROM versions"):
                record = json.loads(raw)
                walk(record)
                for field, kind in {"topic_id": "topic", "source_id": "source", "origin_evidence_id": "evidence", "evidence_id": "evidence", "judgment_id": "judgment", "change_id": "change"}.items():
                    ref = record.get(field)
                    if ref and not (field == "source_id" and ref == "manual") and (kind, ref) not in ids:
                        raise OpsError("备份存在缺失的领域引用：" + field)
                for field, kind in {"topic_ids": "topic", "source_ids": "source", "claim_ids": "claim", "judgment_ids": "judgment"}.items():
                    if any(ref and (kind, ref) not in ids for ref in record.get(field, [])):
                        raise OpsError("备份存在缺失的领域引用：" + field)
                for field, id_field, kind in (("judgment_version", "judgment_id", "judgment"), ("change_version", "change_id", "change")):
                    if record.get(field) is not None and (kind, record.get(id_field), record[field]) not in versions:
                        raise OpsError("备份存在缺失的精确版本引用：" + field)
                for ref in record.get("judgment_versions", []):
                    if ("judgment", ref.get("id"), ref.get("version")) not in versions:
                        raise OpsError("备份存在缺失的判断历史引用")
            return {"schema_version": schema, "counts": counts, "version_count": len(versions), "integrity": "ok"}
        finally:
            db.close()
    except (sqlite3.DatabaseError, ValueError, TypeError, OSError):
        raise OpsError("数据库验证失败，原数据未替换")


def _attachment_paths(data_dir):
    directory = Path(data_dir) / "attachments"
    if not directory.exists():
        return []
    paths = []
    for path in sorted(directory.rglob("*")):
        if path.is_symlink():
            raise OpsError("附件目录含符号链接，拒绝备份外部文件；请先核对附件")
        if path.is_file():
            paths.append(path)
    return paths


def _snapshot(source, target):
    src = sqlite3.connect(str(source), timeout=20)
    dest = sqlite3.connect(str(target))
    try:
        src.backup(dest, pages=128)
        dest.execute("PRAGMA journal_mode=DELETE")
    finally:
        dest.close()
        src.close()


def create_backup(config, output=None, label="manual"):
    if not config["db_path"].is_file() or not (config["data_dir"] / "instance.json").is_file():
        raise OpsError("没有已绑定的数据库可备份；未创建空库")
    program = program_info(selected_program(config))
    output = Path(output).expanduser().resolve() if output else config["backup_dir"] / (now().replace(":", "-") + "-" + label + ".wibackup")
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.exists():
        raise OpsError("目标备份已存在，拒绝覆盖有效备份")
    if output.is_relative_to(config["data_dir"] / "attachments"):
        raise OpsError("备份输出不可放进附件目录")
    partial = output.with_name(output.name + ".partial")
    if partial.exists():
        raise OpsError("发现同名未完成备份，请保留调查后选择新的输出文件名")
    # Creating the marker first ensures interrupted/disk-full attempts are never labeled successful.
    partial.touch(exist_ok=False)
    try:
        with tempfile.TemporaryDirectory(prefix="world-insight-backup-", dir=output.parent) as tmp:
            stage = Path(tmp)
            _snapshot(config["db_path"], stage / DB_NAME)
            verified = inspect_database(stage / DB_NAME, program["schema_version"])
            identity = read_json(config["data_dir"] / "instance.json")
            atomic_json(stage / "instance.json", identity)
            atomic_json(stage / "non-sensitive-config.json", {"port": config["port"], "open_browser": config["open_browser"], "paid_enabled": False, "ai_enabled": False, "note": "密钥和 .env 不包含在备份中"})
            before = {}
            for source in _attachment_paths(config["data_dir"]):
                relative = source.relative_to(config["data_dir"])
                before[str(relative)] = sha256(source)
                target = stage / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, target)
                if sha256(target) != before[str(relative)]:
                    raise OpsError("附件在备份期间变化，未生成有效备份")
            after = {str(p.relative_to(config["data_dir"])): sha256(p) for p in _attachment_paths(config["data_dir"])}
            if before != after:
                raise OpsError("附件在备份期间变化，未生成有效备份")
            entries = [{"path": str(path.relative_to(stage)), "size": path.stat().st_size, "sha256": sha256(path)} for path in sorted(stage.rglob("*")) if path.is_file()]
            manifest = {"format": FORMAT, "state": "complete", "created_at": now(), "label": label, "program": program, "database": verified, "instance_id": identity["instance_id"], "files": entries, "excluded": [".env", "credentials", "cache", "logs", "runtime.json", "active-program.json"]}
            atomic_json(stage / "manifest.json", manifest)
            with zipfile.ZipFile(partial, "w", compression=zipfile.ZIP_DEFLATED) as archive:
                for entry in entries:
                    archive.write(stage / entry["path"], entry["path"])
                archive.write(stage / "manifest.json", "manifest.json")
            with partial.open("rb") as stream:
                os.fsync(stream.fileno())
            validate_backup(partial, maximum_schema=program["schema_version"])
            os.replace(partial, output)
        event_log(config, "backup_complete", package=str(output), label=label)
        return {"status": "complete", "package": str(output), "manifest": manifest, "credentials_included": False}
    except BaseException:
        # Leave .partial for diagnosis; never replace or delete older valid packages.
        event_log(config, "backup_incomplete", package=str(partial), error="backup_failed")
        raise


def unpack_verified(package, destination, maximum_schema=None):
    destination = Path(destination)
    try:
        with zipfile.ZipFile(package) as archive:
            names = archive.namelist()
            if len(names) != len(set(names)) or "manifest.json" not in names:
                raise OpsError("备份清单缺失或成员名称重复")
            if sum(item.file_size for item in archive.infolist()) > 100 * 1024 ** 3:
                raise OpsError("备份解压大小超出本地安全上限")
            for item in archive.infolist():
                path = PurePosixPath(item.filename)
                if path.is_absolute() or ".." in path.parts or "\\" in item.filename or (item.external_attr >> 16) & 0o170000 == 0o120000:
                    raise OpsError("备份包含不安全路径或符号链接")
            manifest = json.loads(archive.read("manifest.json"))
            if manifest.get("format") != FORMAT or manifest.get("state") != "complete":
                raise OpsError("备份格式不兼容或尚未完成")
            entries = manifest.get("files", [])
            declared = {row["path"] for row in entries}
            if len(entries) != len(declared) or set(names) != declared | {"manifest.json"} or not {DB_NAME, "instance.json", "non-sensitive-config.json"}.issubset(declared):
                raise OpsError("备份文件与清单不一致")
            for entry in entries:
                relative = entry["path"]
                if relative not in {DB_NAME, "instance.json", "non-sensitive-config.json"} and not relative.startswith("attachments/"):
                    raise OpsError("备份包含非白名单文件，拒绝恢复")
                target = destination / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                with archive.open(relative) as source, target.open("wb") as out:
                    shutil.copyfileobj(source, out)
                if target.stat().st_size != entry["size"] or sha256(target) != entry["sha256"]:
                    raise OpsError("备份校验值不匹配，原数据未替换")
        database = inspect_database(destination / DB_NAME, maximum_schema)
        for key in ("schema_version", "counts", "version_count"):
            if database[key] != manifest["database"][key]:
                raise OpsError("恢复数据库与备份清单记录数或版本不匹配")
        identity = read_json(destination / "instance.json")
        if identity.get("instance_id") != manifest.get("instance_id"):
            raise OpsError("备份实例身份不一致")
        return manifest
    except (zipfile.BadZipFile, KeyError, TypeError, ValueError, OSError):
        raise OpsError("备份损坏或清单不完整，原数据未替换")


def validate_backup(package, maximum_schema=None):
    with tempfile.TemporaryDirectory(prefix="world-insight-verify-") as tmp:
        return unpack_verified(package, Path(tmp), maximum_schema)


def _replace_data(config, stage):
    """Stopped-instance replacement with a retained rollback directory."""
    data_dir = config["data_dir"]
    data_dir.mkdir(parents=True, exist_ok=True)
    rollback = data_dir.parent / (data_dir.name + "-restore-point-" + uuid.uuid4().hex)
    rollback.mkdir()
    moved, installed = [], []
    names = [DB_NAME, DB_NAME + "-wal", DB_NAME + "-shm", "attachments", "instance.json"]
    try:
        for name in names:
            original = data_dir / name
            if original.exists():
                os.replace(original, rollback / name)
                moved.append(name)
        for name in (DB_NAME, "attachments", "instance.json"):
            origin = Path(stage) / name
            if origin.exists():
                os.replace(origin, data_dir / name)
                installed.append(name)
        for name in ("attachments", "cache", "logs"):
            (data_dir / name).mkdir(exist_ok=True)
    except BaseException:
        for name in installed:
            target = data_dir / name
            if target.is_dir():
                shutil.rmtree(target)
            else:
                target.unlink(missing_ok=True)
        for name in moved:
            os.replace(rollback / name, data_dir / name)
        raise
    return rollback


def restore_backup(config, package, apply=False, replace=False, start_after=False):
    program = program_info(selected_program(config))
    package = Path(package).resolve()
    # Stage adjacent to data for atomic rename; validation never touches the target database.
    config["data_dir"].parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="world-insight-restore-stage-", dir=config["data_dir"].parent) as tmp:
        stage = Path(tmp)
        manifest = unpack_verified(package, stage, program["schema_version"])
        existing = config["db_path"].exists() or (config["data_dir"] / "instance.json").exists() or (config["data_dir"].exists() and any(child.name != "operations.lock" for child in config["data_dir"].iterdir()))
        preview = {"status": "preview", "target": str(config["data_dir"]), "package": str(package), "incoming": manifest["database"], "existing": inspect_database(config["db_path"]) if config["db_path"].exists() else None, "requires_replace": existing, "credentials_included": False}
        if not apply:
            return preview
        if existing and not replace:
            raise OpsError("目标已有数据，预览后必须显式 --replace；未替换任何记录")
        if own_runtime(config, require_health=False):
            raise OpsError("目标实例仍在运行；请先停止，再恢复（恢复不会暗中中断编辑）")
        if existing and (not config["db_path"].is_file() or not (config["data_dir"] / "instance.json").is_file()):
            raise OpsError("目标目录已有未绑定内容；请保留这些文件并选择空目录，不将其作为空实例覆盖")
        # A verified current package is retained in addition to the direct atomic restore point.
        recovery = create_backup(config, label="before-restore") if existing else None
        rollback = _replace_data(config, stage)
        verified = inspect_database(config["db_path"], program["schema_version"])
        result = {**preview, "status": "restored", "verification": verified, "recovery_package": recovery["package"] if recovery else None, "restore_point": str(rollback), "credentials_note": "未包含或覆盖 .env/密钥；可选来源凭据需自行重新填写"}
        event_log(config, "restore_complete", package=str(package), restore_point=str(rollback))
        if start_after:
            result["runtime"] = start(config, open_browser=False)
        return result
