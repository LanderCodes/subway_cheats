#!/usr/bin/env python3
"""Read and write Subway Surfers profile files inside unencrypted iOS backups.

This module never talks to the phone directly. It manipulates a local iOS
backup created with Finder or ``idevicebackup2``; applying the edited backup is
a separate step handled by ``restore()``.

Only unencrypted backups are supported. In an encrypted backup ``Manifest.db``
is itself encrypted and cannot be queried with SQLite.
"""
import hashlib
import os
import plistlib
import shutil
import sqlite3
import subprocess
import sys
from datetime import datetime
from pathlib import Path

BUNDLE_ID = "com.kiloo.subwaysurf"
APP_DOMAIN = f"AppDomain-{BUNDLE_ID}"
PROFILE_REL = "Documents/profile"


class IosBackupError(Exception):
    pass


def backup_root():
    override = os.environ.get("IOS_BACKUP_ROOT")
    if override:
        return Path(override).expanduser()
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "MobileSync" / "Backup"
    if os.name == "nt":
        appdata = os.environ.get("APPDATA")
        if appdata:
            return Path(appdata) / "Apple Computer" / "MobileSync" / "Backup"
    return Path.home() / ".local" / "share" / "MobileSync" / "Backup"


def find_backups(root=None):
    root = Path(root).expanduser() if root else backup_root()
    if not root.is_dir():
        return []
    backups = [p for p in root.iterdir() if (p / "Manifest.db").is_file()]
    backups.sort(key=lambda p: (p / "Manifest.db").stat().st_mtime, reverse=True)
    return backups


def resolve_backup(path=None):
    if path:
        candidate = Path(path).expanduser()
        if (candidate / "Manifest.db").is_file():
            return candidate
        alternate = backup_root() / path
        if (alternate / "Manifest.db").is_file():
            return alternate
        raise IosBackupError(f"not an iOS backup folder: {candidate}")

    backups = find_backups()
    if not backups:
        raise IosBackupError(
            "no iOS backups found. Create one with Finder, or run: "
            "idevicebackup2 backup --full <folder>"
        )
    return backups[0]


def _connect(backup):
    db = Path(backup) / "Manifest.db"
    try:
        conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
        conn.execute("SELECT count(*) FROM Files")
        return conn
    except sqlite3.DatabaseError as exc:
        raise IosBackupError(
            "Manifest.db is unreadable. The backup is probably encrypted; disable "
            "backup encryption in Finder and create a new unencrypted backup."
        ) from exc


def file_id(relative_path):
    return hashlib.sha1(f"{APP_DOMAIN}-{relative_path}".encode("utf-8")).hexdigest()


def _blob_path(backup, fid):
    return Path(backup) / fid[:2] / fid


def list_profile_entries(backup):
    conn = _connect(backup)
    try:
        rows = conn.execute(
            "SELECT fileID, relativePath FROM Files "
            "WHERE domain = ? AND flags = 1 AND relativePath LIKE ? "
            "ORDER BY relativePath",
            (APP_DOMAIN, f"{PROFILE_REL}/%"),
        ).fetchall()
    finally:
        conn.close()
    return [{"fileID": fid, "relativePath": rel} for fid, rel in rows]


def describe(backup):
    backup = Path(backup)
    device = ""
    info = backup / "Info.plist"
    if info.is_file():
        try:
            data = plistlib.loads(info.read_bytes())
            device = data.get("Device Name") or data.get("Product Name") or ""
        except Exception:
            device = ""
    entries = list_profile_entries(backup)
    modified = datetime.fromtimestamp((backup / "Manifest.db").stat().st_mtime).strftime("%Y-%m-%d %H:%M")
    label = f"{backup.name} ({device or 'unknown device'})"
    return f"{label}: {len(entries)} profile files, modified {modified}"


def pull(backup, dest):
    backup = Path(backup)
    dest = Path(dest).expanduser()
    entries = list_profile_entries(backup)
    if not entries:
        raise IosBackupError(f"no {PROFILE_REL} files found in this backup")
    dest.mkdir(parents=True, exist_ok=True)
    count = 0
    for entry in entries:
        source = _blob_path(backup, entry["fileID"])
        if not source.is_file():
            continue
        name = Path(entry["relativePath"]).name
        (dest / name).write_bytes(source.read_bytes())
        count += 1
    if not count:
        raise IosBackupError("profile files are listed in Manifest.db but missing on disk")
    return dest, count


def _ensure_parent_rows(conn, relative_paths):
    for rel in relative_paths:
        parts = rel.split("/")
        for index in range(1, len(parts)):
            parent = "/".join(parts[:index])
            conn.execute(
                "INSERT OR IGNORE INTO Files (fileID, domain, relativePath, flags, file) "
                "VALUES (?, ?, ?, 2, NULL)",
                (file_id(parent), APP_DOMAIN, parent),
            )


def push(backup, profile_dir, undo_dir=None):
    backup = Path(backup)
    profile_dir = Path(profile_dir).expanduser()
    if not profile_dir.is_dir():
        raise IosBackupError(f"profile folder not found: {profile_dir}")

    files = sorted(
        p for p in profile_dir.iterdir()
        if p.is_file() and p.suffix == ".json" and not p.name.startswith(".")
    )
    if not files:
        raise IosBackupError(f"no .json profile files in {profile_dir}")

    db = backup / "Manifest.db"
    if undo_dir:
        undo_dir = Path(undo_dir)
        undo_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(db, undo_dir / "Manifest.db")

    relative_paths = [f"{PROFILE_REL}/{p.name}" for p in files]
    conn = sqlite3.connect(db)
    try:
        _ensure_parent_rows(conn, relative_paths)
        for path, rel in zip(files, relative_paths):
            fid = file_id(rel)
            target = _blob_path(backup, fid)
            target.parent.mkdir(parents=True, exist_ok=True)
            if undo_dir and target.is_file():
                saved = undo_dir / fid[:2] / fid
                saved.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(target, saved)
            target.write_bytes(path.read_bytes())
            row = conn.execute("SELECT file FROM Files WHERE fileID = ?", (fid,)).fetchone()
            if row is None:
                conn.execute(
                    "INSERT INTO Files (fileID, domain, relativePath, flags, file) "
                    "VALUES (?, ?, ?, 1, NULL)",
                    (fid, APP_DOMAIN, rel),
                )
        conn.commit()
    finally:
        conn.close()
    return len(files)


def idevicebackup2_path():
    return shutil.which("idevicebackup2")


def restore(backup, udid=None):
    exe = idevicebackup2_path()
    if not exe:
        raise IosBackupError(
            "idevicebackup2 not found. Install it with: brew install libimobiledevice"
        )
    cmd = [exe]
    if udid:
        cmd += ["-u", udid]
    cmd += ["restore", "--system", "--settings", "--remove", str(Path(backup))]
    print("running:", " ".join(cmd))
    proc = subprocess.run(cmd)
    if proc.returncode != 0:
        raise IosBackupError(f"idevicebackup2 exited with code {proc.returncode}")
    return proc.returncode
