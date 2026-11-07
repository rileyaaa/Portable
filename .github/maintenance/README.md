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

- `.github/maintenance/01-upgrade-runtime.py`、`01-check-codex-stable.py`、`01-combined-candidate.py`、`02-compatibility.py`、`02-tool-compatibility.ps1`、`03-update-route.py`、`check-actionlint.ps1` 為 development 維護程式鏡像，僅供追溯審閱。
- `development-workflows/` 備份 development 完整的 01～04 YAML。放在 `.github/workflows/` 外，不是有效的工作流。
- `tooling-sources/` 備份 development 的 Tool 升級 Python 程式碼；不寫入 main 的 `tool/` 目錄，亦不能單獨在舊 runtime 上執行。
- `legacy-main-workflows/` 完整備份本次整理前的四份 main YAML，包括舊發布、一次性 r1/r2 和瀏覽器下載流程。

## 當前限制

01 的開發流程可在同一個 Windows 候選中整合官方 Codex 穩定版與受限的 Node（原主版本內）、ripgrep、fd、jq Tool 更新：依序校驗 Runtime LFS 指標、Tool 官方 SHA-256、個別變更範圍及合併 SHA-256；獨立 Writer 必須重建相同合併摘要，且只能提交 development。**這仍是未驗證的整合候選，尚未經 Windows Actions 驗收，請勿視為已可發佈。** 其他 Python、npm、Playwright、瀏覽器等完整 Tool 升級仍依獨立已審核計畫處理，計畫變更時 01 會拒絕部分更新。版本皆已最新時，01 的 Ubuntu metadata-only 預檢會跳過 Windows Runner。03 繼續只讀檢查，不單獨更新。正式 Release 始終關閉。

舊 0.166.0 正式 Release、標籤與可執行檔不變。需要恢復舊 Actions 時，從 `legacy-main-workflows/` 還原到 `.github/workflows/` 並審核後提交。
