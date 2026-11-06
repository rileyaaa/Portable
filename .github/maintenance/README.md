# Main 分支的 Actions 入口與維護腳本

本目錄專門存放維護來源、舊工作流備份和開發分支同步副本。主程式 `codex.exe`、Tool 執行檔、實際正式 Release 完全不因這些檔案改動。

## 執行入口

GitHub Actions 的 `workflow_dispatch` 必須先出現在預設分支 `main` 才能從網頁執行。

- `01-upgrade-codex-runtime.yml`：在 main 點選 Run workflow，僅以 `actions: write` 將開發工作流派發到 `development/latest-codex-portable-20261106`，不執行 main 的舊程式。
- `02-verify-and-publish-portable.yml`：需填完整版本標籤；僅派發 development 的唯讀驗證，禁止 `publish_release=true`。
- `03-update-tools.yml`：只派發 development 的官方 Tool 版本檢查，尚不能更新全部 Tool。
- `04-cleanup-branches.yml`：只在 PR 已合併到 main 後，自動清理由更新工作流產生的 `maintenance/tools-數字`、`maintenance/full-tools-數字` 分支；保護 main、development、未合併及其他名稱分支。

路由 run 返回成功 **僅代表派發請求已受理**，實際測試結果見被派發的 development run。若使用者直接選 development 分支執行，則以 development 中的真實工作流內容為準。

## 同步原始碼與備份

- `.github/maintenance/01-upgrade-runtime.py`、`02-compatibility.py`、`02-tool-compatibility.ps1`、`03-update-route.py`、`check-actionlint.ps1` 為 development 維護程式鏡像，僅供追溯審閱。
- `development-workflows/` 備份 development 完整的 01～04 YAML。放在 `.github/workflows/` 外，不是有效的工作流。
- `tooling-sources/` 備份 development 的 Tool 升級 Python 程式碼；不寫入 main 的 `tool/` 目錄，亦不能單獨在舊 runtime 上執行。
- `legacy-main-workflows/` 完整備份本次整理前的四份 main YAML，包括舊發布、一次性 r1/r2 和瀏覽器下載流程。

## 當前限制

01 如果發現 Tool 也需更新，會安全中止，避免只更新 Codex 而假稱整包完成。03 是唯讀更新需求偵測；完整 Tool 更新和正式發布需另行整合與 Windows 驗證。**main 上的路由與鏡像不表示這些功能已經通過驗證或獲准發布。**

舊 0.166.0 正式 Release、標籤與可執行檔不變。需要恢復舊 Actions 時，從 `legacy-main-workflows/` 還原到 `.github/workflows/` 並審核後提交。
