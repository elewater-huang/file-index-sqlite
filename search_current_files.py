# -*- coding: utf-8 -*-
r"""
search_current_files.py

Python version:
    Compatible with Python 3.7.9 on Windows 7.

Examples:
    python search_current_files.py 編碼原則
    python search_current_files.py 編碼原則 --exclude-ext .lnk
    python search_current_files.py --ext .pptx --after 2026-06-01
    python search_current_files.py --time-field ctime --ext .pptx --after 2026-06-01
    python search_current_files.py --recent 100
    python search_current_files.py --changes latest
"""

from __future__ import print_function

import argparse
import os
import sqlite3


def fix_ext(ext):
    ext = ext.lower().strip()
    if ext and not ext.startswith("."):
        ext = "." + ext
    return ext


def main(argv=None):
    parser = argparse.ArgumentParser(description="Search file_index_v2.db current_files.")
    parser.add_argument("keyword", nargs="?", default="", help="Keyword in file name or full path")
    parser.add_argument("--db", default="file_index_v2.db")
    parser.add_argument("--ext", nargs="*", default=[], help="Extensions to include, e.g. .xlsx .pptx")
    parser.add_argument("--exclude-ext", nargs="*", default=[], help="Extensions to exclude, e.g. .lnk .tmp")
    parser.add_argument("--limit", type=int, default=200)
    parser.add_argument("--after", default="", help="time field >= YYYY-MM-DD")
    parser.add_argument("--before", default="", help="time field <= YYYY-MM-DD")
    parser.add_argument("--time-field", choices=["mtime", "ctime", "atime", "last_seen_at", "last_changed_at"], default="mtime")
    parser.add_argument("--dirs", action="store_true", help="Folders only")
    parser.add_argument("--files", action="store_true", help="Files only")
    parser.add_argument("--include-deleted", action="store_true", help="Include deleted/missing records")
    parser.add_argument("--deleted-only", action="store_true", help="Only deleted/missing records")
    parser.add_argument("--recent", type=int, default=0, help="Show latest N records ordered by selected time field")
    parser.add_argument("--changes", default="", help="Use --changes latest to show latest change log")
    args = parser.parse_args(argv)

    db = os.path.abspath(args.db)
    if not os.path.isfile(db):
        parser.error("Database does not exist: %s" % db)
    conn = sqlite3.connect("file:" + __import__("urllib.parse", fromlist=["quote"]).quote(db.replace(os.sep, "/"), safe="/:") + "?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row

    if args.changes:
        sql = """
SELECT
    fc.happened_at,
    fc.change_type,
    fc.old_mtime,
    fc.new_mtime,
    fc.old_size_bytes,
    fc.new_size_bytes,
    fc.full_path
FROM file_changes fc
ORDER BY fc.change_id DESC
LIMIT ?
"""
        for row in conn.execute(sql, (args.limit,)):
            print("%s\t%s\told_mtime=%s\tnew_mtime=%s\told_size=%s\tnew_size=%s\t%s" % (
                row["happened_at"] or "",
                row["change_type"] or "",
                row["old_mtime"] or "",
                row["new_mtime"] or "",
                row["old_size_bytes"] if row["old_size_bytes"] is not None else "",
                row["new_size_bytes"] if row["new_size_bytes"] is not None else "",
                row["full_path"] or ""
            ))
        conn.close()
        return

    where = []
    params = []

    if not args.include_deleted and not args.deleted_only:
        where.append("is_deleted = 0")
    if args.deleted_only:
        where.append("is_deleted = 1")

    if args.keyword:
        where.append("(name LIKE ? OR full_path LIKE ?)")
        kw = "%" + args.keyword + "%"
        params.extend([kw, kw])

    if args.ext:
        exts = [fix_ext(e) for e in args.ext if fix_ext(e)]
        if exts:
            where.append("ext IN (%s)" % ",".join(["?"] * len(exts)))
            params.extend(exts)

    if args.exclude_ext:
        exts = [fix_ext(e) for e in args.exclude_ext if fix_ext(e)]
        if exts:
            where.append("ext NOT IN (%s)" % ",".join(["?"] * len(exts)))
            params.extend(exts)

    tf = args.time_field
    if args.after:
        where.append(tf + " >= ?")
        params.append(args.after)

    if args.before:
        before = args.before + " 23:59:59" if len(args.before) == 10 else args.before
        where.append(tf + " <= ?")
        params.append(before)

    if args.dirs and not args.files:
        where.append("is_dir = 1")
    elif args.files and not args.dirs:
        where.append("is_dir = 0")

    sql = """
SELECT
    mtime, ctime, atime, last_seen_at, last_changed_at,
    size_bytes, ext, source_type, root_label, is_deleted, full_path
FROM current_files
"""
    if where:
        sql += " WHERE " + " AND ".join(where)

    limit = args.recent if args.recent > 0 else args.limit
    sql += " ORDER BY " + tf + " DESC, full_path LIMIT ?"
    params.append(limit)

    for row in conn.execute(sql, params):
        print("mtime=%s\tctime=%s\tatime=%s\tlast_seen=%s\tchanged=%s\tsize=%s\text=%s\t%s\t%s\tdeleted=%s\t%s" % (
            row["mtime"] or "",
            row["ctime"] or "",
            row["atime"] or "",
            row["last_seen_at"] or "",
            row["last_changed_at"] or "",
            row["size_bytes"] if row["size_bytes"] is not None else "",
            row["ext"] or "",
            row["source_type"] or "",
            row["root_label"] or "",
            row["is_deleted"],
            row["full_path"] or "",
        ))

    conn.close()


if __name__ == "__main__":
    main()
