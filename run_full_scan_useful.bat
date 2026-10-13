@echo off
cd /d "%~dp0"
REM Edit this explicit folder before use; existing database is preserved.
python scan_to_sqlite_v2.py --db file_index_v2_useful.db --roots "%USERPROFILE%\Documents" --profile useful --mode full
pause
