# -*- coding: utf-8 -*-
r"""
scan_to_sqlite_v2.py

Python version:
    Compatible with Python 3.7.9 on Windows 7.

Purpose:
    Build and maintain a SQLite file index for:
    - server shares listed in server_shares.txt
    - C:\
    - D:\

Design:
    - current_files = current/latest file state, one row per path
    - file_changes  = optional change log: new / modified / deleted
    - scans, roots, scan_errors = scan metadata and errors

Configure explicit roots before scanning.
"""

from __future__ import print_function

import argparse
import datetime as _dt
import os
import re
import sqlite3
import sys

DEFAULT_DB = "file_index_v2.db"
DEFAULT_SHARE_FILE = "server_shares.txt"
DB_FILES = set()
FILE_ATTRIBUTE_REPARSE_POINT = 0x0400

USEFUL_EXTS = set("""
.doc .docx .xls .xlsx .xlsm .ppt .pptx .pdf .txt .csv .md .rtf
.jpg .jpeg .png .gif .bmp .tif .tiff .webp
.mp3 .wav .flac .aac .m4a .mp4 .mov .avi .mkv .wmv
.zip .rar .7z .tar .gz
.dwg .dxf
.db .sqlite .sqlite3 .mdb .accdb .sql
.html .htm .css .js .json .xml .php .py .bat .cmd .ps1 .ini .cfg .conf .log
.c .cpp .h .hpp .cs .java .vb .bas .frm .cls
.dll .exe .msi .inf .sys
""".split())

NOISY_DIR_NAMES = set(x.lower() for x in [
    "$Recycle.Bin",
    "System Volume Information",
    "Windows",
    "Program Files",
    "Program Files (x86)",
    "ProgramData",
    "AppData",
    "Temp",
    "Cache",
    "node_modules",
    ".git",
    ".svn",
    ".hg",
    "vendor",
    "build",
    "dist",
    "bin",
    "obj",
    "__pycache__",
])


def now_iso():
    return _dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def normalize_ext(name):
    root, ext = os.path.splitext(name)
    return ext.lower()


def dt_from_ts(ts):
    try:
        return _dt.datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        return None


def parse_server_shares(path):
    raw = None
    last_error = None
    for enc in ("utf-8-sig", "cp950"):
        try:
            with open(path, "r", encoding=enc) as f:
                raw = f.read()
            break
        except Exception as e:
            last_error = e

    if raw is None:
        raise RuntimeError("Cannot read share file: %s; %s" % (path, last_error))

    server_name = None
    shares = []

    for line in raw.splitlines():
        line = line.rstrip("\r\n")
        if not line.strip():
            continue

        m_server = re.search(r"\\\\([^\s\\]+)", line)
        if m_server and ("共用資源" in line or "Shared resources" in line):
            server_name = m_server.group(1)

        # Example: 文管中心                   Disk  Z:
        m = re.match(r"^(.*?)\s+Disk(?:\s|$)", line)
        if m:
            share = m.group(1).strip()
            if share and not share.startswith("-") and share not in shares:
                shares.append(share)

    if not server_name:
        m = re.search(r"\\\\([^\s\\]+)", raw)
        if m:
            server_name = m.group(1)

    if not server_name:
        raise RuntimeError("Cannot find server name in %s" % path)

    return server_name, shares


def remove_db_files(db_path):
    for suffix in ("", "-wal", "-shm", "-journal"):
        p = db_path + suffix
        if os.path.exists(p):
            os.remove(p)


def ensure_schema(conn):
    conn.executescript("""
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS scans (
    scan_id INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    mode TEXT NOT NULL,
    profile TEXT NOT NULL,
    note TEXT
);

CREATE TABLE IF NOT EXISTS roots (
    root_id INTEGER PRIMARY KEY AUTOINCREMENT,
    scan_id INTEGER NOT NULL,
    source_type TEXT NOT NULL,
    root_label TEXT NOT NULL,
    root_path TEXT NOT NULL,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    status TEXT,
    total_seen INTEGER DEFAULT 0,
    new_count INTEGER DEFAULT 0,
    modified_count INTEGER DEFAULT 0,
    unchanged_count INTEGER DEFAULT 0,
    deleted_count INTEGER DEFAULT 0,
    error_count INTEGER DEFAULT 0,
    error_message TEXT,
    FOREIGN KEY(scan_id) REFERENCES scans(scan_id)
);

CREATE TABLE IF NOT EXISTS current_files (
    full_path TEXT PRIMARY KEY,
    parent_path TEXT,
    name TEXT NOT NULL,
    ext TEXT,
    is_dir INTEGER NOT NULL,
    size_bytes INTEGER,
    mtime TEXT,
    ctime TEXT,
    atime TEXT,
    source_type TEXT NOT NULL,
    root_label TEXT NOT NULL,
    root_path TEXT NOT NULL,
    depth INTEGER,
    first_seen_at TEXT NOT NULL,
    last_seen_at TEXT NOT NULL,
    last_changed_at TEXT,
    last_scan_id INTEGER NOT NULL,
    is_deleted INTEGER NOT NULL DEFAULT 0,
    deleted_at TEXT
);

CREATE TABLE IF NOT EXISTS file_changes (
    change_id INTEGER PRIMARY KEY AUTOINCREMENT,
    scan_id INTEGER NOT NULL,
    root_id INTEGER,
    change_type TEXT NOT NULL,
    full_path TEXT NOT NULL,
    old_size_bytes INTEGER,
    new_size_bytes INTEGER,
    old_mtime TEXT,
    new_mtime TEXT,
    old_ext TEXT,
    new_ext TEXT,
    happened_at TEXT NOT NULL,
    FOREIGN KEY(scan_id) REFERENCES scans(scan_id),
    FOREIGN KEY(root_id) REFERENCES roots(root_id)
);

CREATE TABLE IF NOT EXISTS scan_errors (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    scan_id INTEGER NOT NULL,
    root_id INTEGER,
    source_type TEXT,
    root_label TEXT,
    path TEXT,
    error_type TEXT,
    error_message TEXT,
    happened_at TEXT NOT NULL,
    FOREIGN KEY(scan_id) REFERENCES scans(scan_id),
    FOREIGN KEY(root_id) REFERENCES roots(root_id)
);
""")
    conn.commit()


def create_indexes(conn):
    conn.executescript("""
CREATE INDEX IF NOT EXISTS idx_current_files_name ON current_files(name);
CREATE INDEX IF NOT EXISTS idx_current_files_ext ON current_files(ext);
CREATE INDEX IF NOT EXISTS idx_current_files_mtime ON current_files(mtime);
CREATE INDEX IF NOT EXISTS idx_current_files_ctime ON current_files(ctime);
CREATE INDEX IF NOT EXISTS idx_current_files_atime ON current_files(atime);
CREATE INDEX IF NOT EXISTS idx_current_files_root ON current_files(source_type, root_label);
CREATE INDEX IF NOT EXISTS idx_current_files_deleted ON current_files(is_deleted);
CREATE INDEX IF NOT EXISTS idx_file_changes_scan_type ON file_changes(scan_id, change_type);
CREATE INDEX IF NOT EXISTS idx_scan_errors_scan ON scan_errors(scan_id);
CREATE INDEX IF NOT EXISTS idx_scan_errors_path ON scan_errors(path);
""")
    conn.commit()


def is_reparse_point(stat_result):
    attrs = getattr(stat_result, "st_file_attributes", 0)
    return bool(attrs & FILE_ATTRIBUTE_REPARSE_POINT)


def should_skip_dir(name, profile):
    if profile == "full":
        return False
    return name.lower() in NOISY_DIR_NAMES


def should_keep_file(name, profile):
    if normalize_ext(name) == ".lnk":
        return False
    if profile == "full":
        return True
    return normalize_ext(name) in USEFUL_EXTS


def log_error(conn, scan_id, root_id, source_type, root_label, path, error_type, error_message):
    conn.execute("""
INSERT INTO scan_errors (
    scan_id, root_id, source_type, root_label, path,
    error_type, error_message, happened_at
) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
""", (
        scan_id, root_id, source_type, root_label, path,
        error_type, error_message, now_iso()
    ))


def log_change(conn, scan_id, root_id, change_type, full_path,
               old_size, new_size, old_mtime, new_mtime, old_ext, new_ext):
    conn.execute("""
INSERT INTO file_changes (
    scan_id, root_id, change_type, full_path,
    old_size_bytes, new_size_bytes,
    old_mtime, new_mtime,
    old_ext, new_ext,
    happened_at
) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
""", (
        scan_id, root_id, change_type, full_path,
        old_size, new_size, old_mtime, new_mtime, old_ext, new_ext,
        now_iso()
    ))


def upsert_current_file(conn, scan_id, root_id, row):
    """
    row tuple:
    full_path, parent_path, name, ext, is_dir, size_bytes,
    mtime, ctime, atime, source_type, root_label, root_path, depth

    Returns: new / modified / unchanged / revived
    """
    (full_path, parent_path, name, ext, is_dir, size_bytes,
     mtime, ctime, atime, source_type, root_label, root_path, depth) = row

    cur = conn.cursor()
    old = cur.execute("""
SELECT size_bytes, mtime, ext, is_dir, is_deleted
FROM current_files
WHERE full_path = ?
""", (full_path,)).fetchone()

    t = now_iso()

    if old is None:
        cur.execute("""
INSERT INTO current_files (
    full_path, parent_path, name, ext, is_dir, size_bytes,
    mtime, ctime, atime, source_type, root_label, root_path, depth,
    first_seen_at, last_seen_at, last_changed_at,
    last_scan_id, is_deleted, deleted_at
) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, NULL)
""", (
            full_path, parent_path, name, ext, is_dir, size_bytes,
            mtime, ctime, atime, source_type, root_label, root_path, depth,
            t, t, t, scan_id
        ))
        log_change(conn, scan_id, root_id, "new", full_path,
                   None, size_bytes, None, mtime, None, ext)
        return "new"

    old_size, old_mtime, old_ext, old_is_dir, old_is_deleted = old

    changed = (
        old_size != size_bytes or
        old_mtime != mtime or
        old_ext != ext or
        old_is_dir != is_dir or
        old_is_deleted != 0
    )

    if changed:
        change_type = "revived" if old_is_deleted else "modified"
        cur.execute("""
UPDATE current_files
SET parent_path=?, name=?, ext=?, is_dir=?, size_bytes=?,
    mtime=?, ctime=?, atime=?, source_type=?, root_label=?, root_path=?, depth=?,
    last_seen_at=?, last_changed_at=?, last_scan_id=?, is_deleted=0, deleted_at=NULL
WHERE full_path=?
""", (
            parent_path, name, ext, is_dir, size_bytes,
            mtime, ctime, atime, source_type, root_label, root_path, depth,
            t, t, scan_id, full_path
        ))
        log_change(conn, scan_id, root_id, change_type, full_path,
                   old_size, size_bytes, old_mtime, mtime, old_ext, ext)
        return change_type

    cur.execute("""
UPDATE current_files
SET atime=?, ctime=?, last_seen_at=?, last_scan_id=?, is_deleted=0, deleted_at=NULL
WHERE full_path=?
""", (atime, ctime, t, scan_id, full_path))
    return "unchanged"


def mark_deleted_for_root(conn, scan_id, root_id, source_type, root_label, root_path):
    t = now_iso()
    cur = conn.cursor()
    rows = cur.execute("""
SELECT full_path, size_bytes, mtime, ext
FROM current_files
WHERE source_type = ?
  AND root_label = ?
  AND root_path = ?
  AND is_deleted = 0
  AND last_scan_id <> ?
""", (source_type, root_label, root_path, scan_id)).fetchall()

    for full_path, old_size, old_mtime, old_ext in rows:
        cur.execute("""
UPDATE current_files
SET is_deleted = 1,
    deleted_at = ?,
    last_changed_at = ?
WHERE full_path = ?
""", (t, t, full_path))
        log_change(conn, scan_id, root_id, "deleted", full_path,
                   old_size, None, old_mtime, None, old_ext, None)

    conn.commit()
    return len(rows)


def scan_root(conn, scan_id, root_path, source_type, root_label, profile, commit_every=2000):
    started = now_iso()
    cur = conn.cursor()
    cur.execute("""
INSERT INTO roots (scan_id, source_type, root_label, root_path, started_at, status)
VALUES (?, ?, ?, ?, ?, ?)
""", (scan_id, source_type, root_label, root_path, started, "running"))
    root_id = cur.lastrowid
    conn.commit()

    stats = {
        "total_seen": 0,
        "new": 0,
        "modified": 0,
        "revived": 0,
        "unchanged": 0,
        "deleted": 0,
        "errors": 0,
    }

    stack = [(root_path, 0)]
    pending = 0

    while stack:
        current, depth = stack.pop()

        try:
            st_current = os.stat(current, follow_symlinks=False)
            if os.path.islink(current) or is_reparse_point(st_current):
                continue
        except Exception as e:
            stats["errors"] += 1
            log_error(conn, scan_id, root_id, source_type, root_label, current, type(e).__name__, str(e))
            if stats["errors"] % 100 == 0:
                conn.commit()
            continue

        try:
            with os.scandir(current) as it:
                for entry in it:
                    try:
                        full_path = entry.path
                        name = entry.name
                        parent_path = current

                        try:
                            st = entry.stat(follow_symlinks=False)
                        except Exception as e:
                            stats["errors"] += 1
                            log_error(conn, scan_id, root_id, source_type, root_label, full_path, type(e).__name__, str(e))
                            continue

                        if entry.is_symlink() or is_reparse_point(st):
                            continue

                        is_dir = entry.is_dir(follow_symlinks=False)
                        ext = "" if is_dir else normalize_ext(name)

                        if is_dir:
                            keep_this = True
                            enter_this = not should_skip_dir(name, profile)
                        else:
                            keep_this = should_keep_file(name, profile)
                            enter_this = False

                        if os.path.abspath(full_path) in DB_FILES:
                            keep_this = False

                        if keep_this:
                            row = (
                                full_path, parent_path, name, ext, 1 if is_dir else 0,
                                None if is_dir else int(getattr(st, "st_size", 0)),
                                dt_from_ts(getattr(st, "st_mtime", None)),
                                dt_from_ts(getattr(st, "st_ctime", None)),
                                dt_from_ts(getattr(st, "st_atime", None)),
                                source_type, root_label, root_path, depth
                            )
                            status = upsert_current_file(conn, scan_id, root_id, row)
                            if status in stats:
                                stats[status] += 1
                            stats["total_seen"] += 1
                            pending += 1

                        if is_dir and enter_this:
                            stack.append((full_path, depth + 1))

                        if pending >= commit_every:
                            conn.commit()
                            pending = 0
                            print("[%s] %s seen=%s new=%s modified=%s unchanged=%s errors=%s" % (
                                now_iso(), root_label, stats["total_seen"],
                                stats["new"], stats["modified"] + stats["revived"],
                                stats["unchanged"], stats["errors"]
                            ))

                    except KeyboardInterrupt:
                        raise
                    except Exception as e:
                        stats["errors"] += 1
                        log_error(conn, scan_id, root_id, source_type, root_label,
                                  getattr(entry, "path", current), type(e).__name__, str(e))

        except KeyboardInterrupt:
            raise
        except Exception as e:
            stats["errors"] += 1
            log_error(conn, scan_id, root_id, source_type, root_label, current, type(e).__name__, str(e))
            conn.commit()

    conn.commit()

    # After this root has been fully walked, mark previously-known but not seen items as deleted.
    if stats["errors"] == 0:
        stats["deleted"] = mark_deleted_for_root(conn, scan_id, root_id, source_type, root_label, root_path)

    finished = now_iso()
    cur.execute("""
UPDATE roots
SET finished_at=?, status=?, total_seen=?, new_count=?, modified_count=?,
    unchanged_count=?, deleted_count=?, error_count=?, error_message=?
WHERE root_id=?
""", (
        finished, "partial" if stats["errors"] else "done", stats["total_seen"], stats["new"], stats["modified"] + stats["revived"],
        stats["unchanged"], stats["deleted"], stats["errors"], "", root_id
    ))
    conn.commit()
    return stats


def build_targets(args):
    targets = [("local", os.path.abspath(p), os.path.abspath(p)) for p in args.roots]

    if args.include_server:
        share_file = os.path.abspath(args.share_file)
        server_name, shares = parse_server_shares(share_file)
        for share in shares:
            root_path = r"\\%s\%s" % (server_name, share)
            targets.append(("server", share, root_path))

    if args.include_local:
        for drive in args.local_drives:
            d = drive.rstrip("\\/")
            root_path = d + "\\"
            label = d.upper()
            targets.append(("local", label, root_path))

    return targets


def main(argv=None):
    parser = argparse.ArgumentParser(description="Maintain SQLite current file index.")
    parser.add_argument("--roots", nargs="+", default=[], help="Explicit directories to scan")
    parser.add_argument("--db", default=DEFAULT_DB, help="SQLite DB path. Default: file_index_v2.db")
    parser.add_argument("--share-file", default=DEFAULT_SHARE_FILE, help="net view output file. Default: server_shares.txt")
    parser.add_argument("--mode", choices=["full", "incremental"], default="incremental")
    parser.add_argument("--profile", choices=["full", "useful"], default="full")
    parser.add_argument("--include-server", action="store_true", default=False)
    parser.add_argument("--include-local", action="store_true", default=False)
    parser.add_argument("--local-drives", nargs="*", default=["C:", "D:"], help="Default: C: D:")
    parser.add_argument("--reset-db", action="store_true", help="Delete existing db before scan. Recommended for full scan only.")
    parser.add_argument("--no-indexes", action="store_true", help="Skip index creation at the end.")
    parser.add_argument("--note", default="")
    args = parser.parse_args(argv)

    if not args.roots and not args.include_server and not args.include_local:
        parser.error("Specify --roots, --include-server or --include-local")
    targets = build_targets(args)
    if not targets:
        parser.error("No scan targets configured")

    db_path = os.path.abspath(args.db)
    global DB_FILES
    DB_FILES = set(db_path + suffix for suffix in ("", "-wal", "-shm", "-journal"))

    if args.reset_db:
        print("Reset DB:", db_path)
        remove_db_files(db_path)

    print("Python:", sys.version)
    print("DB:", db_path)
    print("Mode:", args.mode)
    print("Profile:", args.profile)

    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA synchronous=NORMAL;")
    conn.execute("PRAGMA temp_store=MEMORY;")
    ensure_schema(conn)

    cur = conn.cursor()
    previous = cur.execute("SELECT profile FROM scans ORDER BY scan_id DESC LIMIT 1").fetchone()
    if previous and previous[0] != args.profile:
        conn.close()
        parser.error("Use a separate database for a different profile")
    cur.execute("INSERT INTO scans (started_at, mode, profile, note) VALUES (?, ?, ?, ?)",
                (now_iso(), args.mode, args.profile, args.note))
    scan_id = cur.lastrowid
    conn.commit()

    targets = build_targets(args)
    print("Targets:", len(targets))
    for source_type, label, path in targets:
        print(" -", source_type, label, path)

    total = {
        "total_seen": 0,
        "new": 0,
        "modified": 0,
        "revived": 0,
        "unchanged": 0,
        "deleted": 0,
        "errors": 0,
    }

    try:
        for source_type, label, root_path in targets:
            print("\n=== Scanning %s ===" % root_path)
            stats = scan_root(conn, scan_id, root_path, source_type, label, args.profile)
            for k in total:
                total[k] += stats.get(k, 0)
            print("Done: %s seen=%s new=%s modified=%s deleted=%s errors=%s" % (
                root_path, stats["total_seen"], stats["new"],
                stats["modified"] + stats["revived"], stats["deleted"], stats["errors"]
            ))

    except KeyboardInterrupt:
        print("\nInterrupted by user.")
        conn.execute("UPDATE scans SET finished_at=?, note=? WHERE scan_id=?",
                     (now_iso(), (args.note + " INTERRUPTED").strip(), scan_id))
        conn.commit()
        raise

    finally:
        conn.execute("UPDATE scans SET finished_at=? WHERE scan_id=?", (now_iso(), scan_id))
        conn.commit()

    if not args.no_indexes:
        print("\nCreating indexes. This may take a while on large DB...")
        create_indexes(conn)

    conn.close()

    print("\nFinished.")
    print("Scan ID:", scan_id)
    print("Total seen:", total["total_seen"])
    print("New:", total["new"])
    print("Modified/revived:", total["modified"] + total["revived"])
    print("Unchanged:", total["unchanged"])
    print("Deleted/missing:", total["deleted"])
    print("Errors:", total["errors"])
    print("DB:", db_path)


if __name__ == "__main__":
    main()
