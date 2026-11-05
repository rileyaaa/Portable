@echo off
setlocal DisableDelayedExpansion
set "__APPDIR__="
set "_CODEX_SYSTEM_BIN=%__APPDIR__%"
if not "%_CODEX_SYSTEM_BIN:~1,2%"==":\" exit /b 3
if /i not "%_CODEX_SYSTEM_BIN:~-10%"=="\System32\" exit /b 3
set "_CODEX_NATIVE_POWERSHELL=%_CODEX_SYSTEM_BIN%WindowsPowerShell\v1.0\powershell.exe"
if not exist "%_CODEX_NATIVE_POWERSHELL%" exit /b 3
for %%I in ("%_CODEX_SYSTEM_BIN%..") do set "SystemRoot=%%~fI"
set "WINDIR=%SystemRoot%"
set "SystemDrive=%SystemRoot:~0,2%"
set "ComSpec=%_CODEX_SYSTEM_BIN%cmd.exe"
set "PATHEXT=.COM;.EXE;.BAT;.CMD"
set "PATH=%_CODEX_SYSTEM_BIN%;%_CODEX_SYSTEM_BIN%WindowsPowerShell\v1.0"
set "PSModulePath=%_CODEX_SYSTEM_BIN%WindowsPowerShell\v1.0\Modules"
set "COR_ENABLE_PROFILING=0"
set "COR_PROFILER="
set "COR_PROFILER_PATH="
set "COR_PROFILER_PATH_32="
set "COR_PROFILER_PATH_64="
set "CORECLR_ENABLE_PROFILING=0"
set "CORECLR_PROFILER="
set "CORECLR_PROFILER_PATH="
set "CORECLR_PROFILER_PATH_32="
set "CORECLR_PROFILER_PATH_64="
set "DOTNET_ENABLE_PROFILING=0"
set "DOTNET_PROFILER="
set "DOTNET_PROFILER_PATH="
set "DOTNET_STARTUP_HOOKS="
set "DOTNET_ADDITIONAL_DEPS="
set "DOTNET_SHARED_STORE="
rem Disable PowerShell caches before bootstrap validates any package directory.
set "POWERSHELL_TELEMETRY_OPTOUT=1"
set "PSModuleAnalysisCachePath=NUL"
rem Portable npm entrypoint: never resolve a host Node or global npm installation.
set "_CODEX_BOOTSTRAP_ROOT=%~dp0..\.."
set "_CODEX_BOOTSTRAP_ENTRYDIR=%~dp0."
set "_CODEX_BOOTSTRAP_CODE1=%~dp0node.exe"
set "_CODEX_BOOTSTRAP_CODE2=%~dp0portable-npm.js"
"%_CODEX_NATIVE_POWERSHELL%" -NoLogo -NoProfile -NonInteractive -ExecutionPolicy Bypass -Command "$ErrorActionPreference='Stop'; try { function Check([string]$p,[bool]$file) { $p=[IO.Path]::GetFullPath($p); if($p -notmatch '^[A-Za-z]:\\' -or $p.Substring(2).Contains(':')){throw 'path'}; $chain=New-Object 'System.Collections.Generic.Stack[string]'; $c=$p; while($c){$chain.Push($c); $c=[IO.Path]::GetDirectoryName($c)}; while($chain.Count){$c=$chain.Pop(); $i=Get-Item -LiteralPath $c -Force -ErrorAction Stop; if(($i.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0){throw 'reparse'}; if($c -eq $p -and $file){if($i.PSIsContainer -or $null -eq $i.PSObject.Properties['LinkType'] -or [string]$i.LinkType -eq 'HardLink' -or ([string]$i.Mode).Contains('l')){throw 'file'}}elseif(-not $i.PSIsContainer){throw 'parent'}}; return $p }; $r=Check $env:_CODEX_BOOTSTRAP_ROOT $false; $r=$r.TrimEnd('\'); $e=Check $env:_CODEX_BOOTSTRAP_ENTRYDIR $false; $cwd=[IO.Path]::GetFullPath([Environment]::CurrentDirectory); if(-not ($cwd.Equals($r,[StringComparison]::OrdinalIgnoreCase) -or $cwd.StartsWith($r+'\',[StringComparison]::OrdinalIgnoreCase))){throw 'cwd'}; $null=Check $cwd $false; foreach($raw in @($env:_CODEX_BOOTSTRAP_CODE1,$env:_CODEX_BOOTSTRAP_CODE2)){if($raw){$p=[IO.Path]::GetFullPath($raw); if(-not $p.StartsWith($r+'\',[StringComparison]::OrdinalIgnoreCase)){throw 'boundary'}; $null=Check $p $true}}; exit 0 } catch { [Console]::Error.WriteLine('Safety stop: unsafe package/code/cwd; target NOT EXECUTED.'); exit 3 }"
if errorlevel 1 exit /b 3
set "NODE_OPTIONS="
set "NODE_PATH="
set "NODE_EXTRA_CA_CERTS="
set "NODE_COMPILE_CACHE="
set "NODE_V8_COVERAGE="
set "NODE_REDIRECT_WARNINGS="
set "OPENSSL_CONF="
set "SSL_CERT_FILE="
set "SSL_CERT_DIR="
"%~dp0node.exe" "%~dp0portable-npm.js" npm %*
exit /b %errorlevel%
