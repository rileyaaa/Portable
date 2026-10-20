@echo off
setlocal DisableDelayedExpansion
set "CODEX_PORTABLE_MAINTENANCE_LAUNCHER=1"
set "CODEX_REPARSE_TARGET=%~dp0."
call :RejectReparse
if errorlevel 1 (
  echo [Codex] Safety stop: package root is a reparse point: "%~dp0"
  exit /b 3
)
cd /d "%~dp0"
if not exist "%~dp0run-codex.ps1" (
  echo [Codex] Safety stop: required script is missing: "%~dp0run-codex.ps1"
  exit /b 3
)
set "CODEX_REPARSE_TARGET=%~dp0run-codex.ps1"
call :RejectReparse
if errorlevel 1 (
  echo [Codex] Safety stop: target script is a reparse point: "%~dp0run-codex.ps1"
  exit /b 3
)
for %%D in ("home" "sqlite" "tmp" "home-runtime" "appdata" "localappdata" "programdata" "cache" "login_json" "tool") do (
  if exist "%~dp0%%~D" (
    set "CODEX_REPARSE_TARGET=%~dp0%%~D"
    call :RejectReparse
    if errorlevel 1 (
      echo [Codex] Safety stop: package directory is a reparse point: "%~dp0%%~D"
      exit /b 3
    )
  )
)
for %%D in ("home" "sqlite" "tmp" "home-runtime" "appdata" "localappdata" "programdata" "cache" "login_json") do if not exist "%~dp0%%~D" mkdir "%~dp0%%~D" >nul 2>nul
set "CODEX_HOME=%~dp0home"
set "CODEX_SQLITE_HOME=%~dp0sqlite"
set "HOME=%~dp0home-runtime"
set "USERPROFILE=%~dp0home-runtime"
set "HOMEDRIVE=%~d0"
set "HOMEPATH=%~p0home-runtime"
set "APPDATA=%~dp0appdata"
set "LOCALAPPDATA=%~dp0localappdata"
set "PROGRAMDATA=%~dp0programdata"
set "ALLUSERSPROFILE=%~dp0programdata"
set "TEMP=%~dp0tmp"
set "TMP=%~dp0tmp"
set "TMPDIR=%~dp0tmp"
set "POWERSHELL_TELEMETRY_OPTOUT=1"
set "PSModuleAnalysisCachePath=%~dp0localappdata\Microsoft\Windows\PowerShell\ModuleAnalysisCache"
set "PSModulePath=%~dp0cache\powershell\modules;%SystemRoot%\System32\WindowsPowerShell\v1.0\Modules"
set "XDG_CACHE_HOME=%~dp0cache"
set "XDG_CONFIG_HOME=%~dp0appdata"
set "XDG_DATA_HOME=%~dp0localappdata"
set "XDG_STATE_HOME=%~dp0localappdata\state"
set "PIP_CACHE_DIR=%~dp0cache\pip"
set "PYTHONUSERBASE=%~dp0cache\python-userbase"
set "PYTHONPYCACHEPREFIX=%~dp0cache\pycache"
set "PYTHONDONTWRITEBYTECODE=1"
set "NPM_CONFIG_CACHE=%~dp0cache\npm"
set "NPM_CONFIG_PREFIX=%~dp0cache\npm-prefix"
set "NPM_CONFIG_GLOBALCONFIG=%~dp0cache\npm\global.npmrc"
set "NPM_CONFIG_USERCONFIG=%~dp0home-runtime\.npmrc"
set "NODE_REPL_HISTORY=%~dp0home-runtime\.node_repl_history"
set "YARN_CACHE_FOLDER=%~dp0cache\yarn"
set "PNPM_HOME=%~dp0cache\pnpm"
set "PNPM_STORE_DIR=%~dp0cache\pnpm-store"
set "GOPATH=%~dp0cache\go"
set "GOCACHE=%~dp0cache\go-build"
set "GOMODCACHE=%~dp0cache\gomod"
set "GOROOT=%~dp0tool\go"
set "GOTOOLCHAIN=local"
set "GRADLE_USER_HOME=%~dp0cache\gradle"
set "MAVEN_OPTS=-Dmaven.repo.local=%~dp0cache\maven"
set "UV_CACHE_DIR=%~dp0cache\uv"
set "UV_PYTHON_INSTALL_DIR=%~dp0tool\python"
set "UV_TOOL_DIR=%~dp0tool\uv-tools"
set "UV_TOOL_BIN_DIR=%~dp0tool\bin"
set "CODEX_INSTALL_DIR=%~dp0"
set "PATH=%~dp0tool\bin;%~dp0tool\python;%~dp0tool\python\Scripts;%~dp0tool\python\Lib\site-packages\bin;%~dp0cache\python-userbase\Scripts;%~dp0tool\node;%~dp0cache\npm-prefix;%~dp0cache\npm-prefix\node_modules\.bin;%~dp0cache\pnpm;%~dp0tool\go\bin;%~dp0tool\android\jdk\bin;%~dp0tool\android\sdk\platform-tools;%~dp0tool\android\sdk\emulator;%~dp0tool\android\sdk\cmdline-tools\latest\bin;%~dp0tool\android\jadx\bin;%~dp0tool\android\dex2jar;%~dp0tool\android\apktool;%~dp0tool\android\maestro\bin;%~dp0tool\android\cli;%~dp0tool\android\cli\bin;%~dp0tool\android\bundletool;%~dp0tool\office\libreoffice\program;%~dp0tool\office\pandoc;%~dp0tool\pdf\poppler\Library\bin;%~dp0tool\pdf\poppler\bin;%~dp0tool\pdf\qpdf\bin;%~dp0tool\media\ffmpeg\bin;%~dp0tool\ocr\tesseract;%SystemRoot%\System32;%SystemRoot%;%SystemRoot%\System32\WindowsPowerShell\v1.0;%SystemRoot%\System32\Wbem"
rem R19 preflight: executable and code file are independently checked.
set "_CODEX_BOOTSTRAP_ROOT=%~dp0."
set "_CODEX_BOOTSTRAP_ENTRYDIR=%~dp0."
set "_CODEX_BOOTSTRAP_CODE1=%~dp0run-codex.ps1"
set "_CODEX_BOOTSTRAP_CODE2="
"%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe" -NoLogo -NoProfile -NonInteractive -ExecutionPolicy Bypass -Command "$ErrorActionPreference='Stop'; try { function Check([string]$p,[bool]$file) { $p=[IO.Path]::GetFullPath($p); if($p -notmatch '^[A-Za-z]:\\' -or $p.Substring(2).Contains(':')){throw 'path'}; $leaf=$true; $c=$p; while($c){$i=Get-Item -LiteralPath $c -Force -ErrorAction Stop; if(($i.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0){throw 'reparse'}; if($leaf -and $file){if($i.PSIsContainer -or $null -eq $i.PSObject.Properties['LinkType'] -or [string]$i.LinkType -eq 'HardLink' -or ([string]$i.Mode).Contains('l')){throw 'file'}}elseif(-not $i.PSIsContainer){throw 'parent'}; $leaf=$false; $c=[IO.Path]::GetDirectoryName($c.TrimEnd('\'))}; return $p }; $r=Check $env:_CODEX_BOOTSTRAP_ROOT $false; $r=$r.TrimEnd('\'); $e=Check $env:_CODEX_BOOTSTRAP_ENTRYDIR $false; $cwd=Check ([Environment]::CurrentDirectory) $false; if(-not ($cwd.Equals($r,[StringComparison]::OrdinalIgnoreCase) -or $cwd.StartsWith($r+'\',[StringComparison]::OrdinalIgnoreCase))){throw 'cwd'}; foreach($raw in @($env:_CODEX_BOOTSTRAP_CODE1,$env:_CODEX_BOOTSTRAP_CODE2)){if($raw){$p=Check $raw $true; if(-not $p.StartsWith($r+'\',[StringComparison]::OrdinalIgnoreCase)){throw 'boundary'}}}; exit 0 } catch { [Console]::Error.WriteLine('Safety stop: unsafe package/code/cwd; target NOT EXECUTED.'); exit 3 }"
if errorlevel 1 exit /b 3
echo [Codex] MAINTENANCE MODE: package scripts/plugins/skills/tools are writable by Codex tools.
echo [Codex] Use this mode only for intentional package maintenance; do not open untrusted projects.
"%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe" -NoProfile -ExecutionPolicy Bypass -File "%~dp0run-codex.ps1" --portable-maintenance %*
set "CODEX_EXIT_CODE=%ERRORLEVEL%"
if not "%CODEX_EXIT_CODE%"=="0" (
  echo.
  echo [Codex] Failed to start. Please check env.ps1 and codex.exe.
  if "%~1"=="" pause
)
exit /b %CODEX_EXIT_CODE%
:RejectReparse
setlocal
set "CODEX_REPARSE_ATTR="
for %%A in ("%CODEX_REPARSE_TARGET%") do set "CODEX_REPARSE_ATTR=%%~aA"
if /i "%CODEX_REPARSE_ATTR:~-1%"=="l" (
  endlocal
  exit /b 1
)
endlocal
exit /b 0
