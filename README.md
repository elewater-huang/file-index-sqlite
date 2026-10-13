# File Index SQLite

把散落的檔案整理成可離線搜尋的地圖。A local, offline-searchable file metadata index.

為剛加入團隊、接手舊電腦或整理多年共享資料夾的人，提供一個小型 Python / SQLite 工具。依指定範圍走訪檔案與資料夾，記錄檔名、副檔名、完整路徑、大小及時間，再於本機查詢。

**不讀取文件內容、不複製原始文件、不繞過權限，也沒有資料上傳功能。** 搜尋只比對檔名與路徑，不是全文、語音或影片內容搜尋。找到路徑後，仍須透過原有權限存取原始檔案。

## Quick start / 快速開始

僅使用 Python 標準函式庫，不需 pip 安裝。程式保留 Python 3.7 相容語法，原始使用環境為 Windows 7 / Python 3.7.9；本次驗證於 Linux / Python 3.12，尚未重新實測 Windows / SMB。舊環境相容不等於建議使用舊作業系統。

先從小目錄試跑，資料庫放本機：

```bat
python scan_to_sqlite_v2.py --roots "C:\Users\YourName\Documents" --db file_index_v2.db
python search_current_files.py CEO --db file_index_v2.db --files
python search_current_files.py --ext .ppt .pptx --after 2026-01-01 --files
```

指定已獲准的共享目錄：

```bat
python scan_to_sqlite_v2.py --roots "\\example-server\Documents" --db team_index.db
```

多個目錄可以接在 `--roots` 後面。同一資料庫固定使用相同根目錄與 profile；避免重疊根目錄。移除掃描目錄不會自動清除它的舊索引。

### 在 CMD 建立 server_shares.txt

`server_shares.example.txt` 是虛構範例；實際設定檔可直接用 Windows 的 `net view` 指令產生，不必逐項手打。

開啟 **命令提示字元（CMD，不是 PowerShell）**，切換到放置程式的資料夾。以下路徑與伺服器名稱請換成自己的：

```bat
cd /d "D:\Tools\file-index-sqlite"
chcp 950
net view \\YOUR-SERVER
```

先確認畫面正常列出共享目錄，再將相同結果輸出成檔案：

```bat
net view \\YOUR-SERVER > server_shares.txt
notepad server_shares.txt
```

- `YOUR-SERVER` 是伺服器名稱；前面要保留兩個反斜線 `\\`。
- `>` 將輸出寫到目前資料夾的 `server_shares.txt`；若檔案已存在會覆寫。請先備份自己調整過的設定。
- `chcp 950` 配合繁體中文 Windows 的 CP950 輸出；程式也接受 UTF-8 設定檔。本步驟以繁體中文 Windows CMD 為例。
- 記事本內應看到包含 `\\YOUR-SERVER` 的標頭與 `Disk` 共用項目。保留伺服器標頭，刪除不打算或未獲准索引的共用項目整行；不要改掉保留項目的名稱與 `Disk` 欄位。
- 若顯示拒絕存取、找不到網路路徑或其他錯誤，先確認公司網路／VPN、伺服器名稱與既有權限，修正後重新產生檔案。錯誤訊息不能當作共享清單使用。

完成設定後，執行：

```bat
python scan_to_sqlite_v2.py --include-server --share-file server_shares.txt --db team_index.db
```

`net view` 這一步只列出共享名稱；上述 Python 指令才會走訪保留項目下的檔案與資料夾。工具不會自動列出所有隱藏共用，也不會自動掃描其他伺服器。

範例伺服器與共享名稱皆為虛構。實際 `server_shares.txt` 已列入 `.gitignore`，不應提交至公開 repository。

## 更新與搜尋

再次執行相同掃描命令會更新索引及變更紀錄。增量更新仍會重新走訪目錄，並非只存取改過的檔案。`--mode` 是掃描紀錄標籤，真正重建須明確使用 `--reset-db`（會刪除指定資料庫，先備份）。批次檔均保留既有資料庫，預設 Documents，請先編輯範圍。

```bat
python search_current_files.py "會議" --ext .pdf .pptx --files
python search_current_files.py --recent 100 --files
python search_current_files.py --deleted-only
python search_current_files.py --changes latest --limit 50
```

`--changes latest` 顯示最近的變更紀錄，可能跨多次掃描。`--profile useful` 排除常見系統/開發目錄並保留特定副檔名；請使用另一個資料庫。同一資料庫切換 profile 會遭拒絕。兩種 profile 都略過 .lnk、符號連結與 Windows reparse points。自動排除目前資料庫及 SQLite 暫存伴隨檔。

## 資料表與限制

- `current_files`：每個完整路徑一筆最新觀測狀態。
- `file_changes`：new / modified / revived / deleted；變更依大小、修改時間、類型與原有缺失狀態判定，不使用內容雜湊。
- `scans`、`roots`：掃描紀錄。遇錯誤的根目錄標為 partial。
- `scan_errors`：存取失敗紀錄。

只有整個根目錄無錯誤走訪完成才標記未再看到的項目為缺失；若有任一錯誤，該根目錄保留原有存在狀態。`is_deleted` 表示索引未再看到，不保證原檔被人刪除。搜尋結果是最後掃描快照，不是即時存在或權限檢查。

Windows 的 `ctime` 通常是建立時間，Unix 的 `ctime` 是狀態變更時間；網路共享視伺服器實作而定，不能當作文件最初創作日期。`atime` 可能未更新。檔案時間以執行端本地時區呈現，精度為秒。

## 使用範圍與資料保護

技術上可列出不代表公司政策允許批次索引。先確認允許的目錄、掃描時段與資料庫保存方式；不建議以系統管理員權限擴大掃描。

目錄列舉及 metadata 查詢仍會造成 SMB / 伺服器負載，也可能觸發稽核。先試小範圍，避免忙碌時段。工具沒有自動限流或可恢復斷點。

資料庫雖不含文件內容，檔名與路徑仍可能揭露客戶、專案及人員資訊。資料庫、共享設定與錯誤紀錄應依公司規定保存，不提交 GitHub、不任意放公開或個人同步目錄。SQLite 檔案沒有內建加密。

容量取決於項目數、路徑長度、索引與變更歷史，可能達數 GB；不是複製全部文件的容量。重複更新仍會累積變更與掃描紀錄。預留資料庫、WAL 及建立索引的空間；工具沒有自動容量上限。長路徑與大型資料量在舊版 Windows / 32 位元 Python 可能遇限制。

## English summary

Index explicitly selected local folders and authorized network shares into SQLite, then search filenames, paths, extensions and timestamps offline. Original document contents are neither read nor copied. Incremental scans still enumerate every configured directory. Existing permissions apply; organizational approval and secure handling of metadata remain necessary. Reopen original files through their original access controls.

## License

MIT — Copyright (c) 2026 Elewater Huang.
