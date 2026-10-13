@echo off
cd /d "%~dp0"
REM Edit this explicit folder before use; existing database is preserved.
python scan_to_sqlite_v2.py --db file_index_v2.db --roots "%USERPROFILE%\Documents" --profile full --mode full
pause
