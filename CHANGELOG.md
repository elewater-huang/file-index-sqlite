# 2026-10-13 — public edition

- Replace internal server/share inventory with fictional configuration.
- Require explicit scan scope; batch launchers default to Documents and preserve databases.
- Preserve existing file state on partial/failed root traversal.
- Decode UTF-8 / CP950 share lists correctly.
- Skip shortcuts, links and active database companion files.
- Reject profile changes within one database.
- Fix deleted-only search; open search database read-only.
- Document metadata-only search, repeat enumeration, timestamps and storage limitations.

Validation: Linux / Python 3.12 temporary-directory integration checks for creation, modification, deletion, failed enumeration, deleted-only search, Chinese share-list encodings and shortcut exclusion. Windows 7 / Python 3.7 / live SMB not retested.
