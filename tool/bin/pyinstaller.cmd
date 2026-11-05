@echo off
setlocal DisableDelayedExpansion
set "__APPDIR__="
set "_CODEX_SYSTEM_BIN=%__APPDIR__%"
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
set "POWERSHELL_TELEMETRY_OPTOUT=1"
set "PSModuleAnalysisCachePath=NUL"
rem R19 preflight: executable and code file are independently checked.
set "_CODEX_BOOTSTRAP_ROOT=%~dp0..\.."
set "_CODEX_BOOTSTRAP_ENTRYDIR=%~dp0."
set "_CODEX_BOOTSTRAP_CODE1=%~dp0..\python\python.exe"
set "_CODEX_BOOTSTRAP_CODE2=%~dp0portable-python-cli.py"
"%_CODEX_NATIVE_POWERSHELL%" -NoLogo -NoProfile -NonInteractive -ExecutionPolicy Bypass -Command "$ErrorActionPreference='Stop'; try { function Check([string]$p,[bool]$file) { $p=[IO.Path]::GetFullPath($p); if($p -notmatch '^[A-Za-z]:\\' -or $p.Substring(2).Contains(':')){throw 'path'}; $leaf=$true; $c=$p; while($c){$i=Get-Item -LiteralPath $c -Force -ErrorAction Stop; if(($i.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0){throw 'reparse'}; if($leaf -and $file){if($i.PSIsContainer -or $null -eq $i.PSObject.Properties['LinkType'] -or [string]$i.LinkType -eq 'HardLink' -or ([string]$i.Mode).Contains('l')){throw 'file'}}elseif(-not $i.PSIsContainer){throw 'parent'}; $leaf=$false; $c=[IO.Path]::GetDirectoryName($c.TrimEnd('\'))}; return $p }; $r=Check $env:_CODEX_BOOTSTRAP_ROOT $false; $r=$r.TrimEnd('\'); $e=Check $env:_CODEX_BOOTSTRAP_ENTRYDIR $false; $cwd=Check ([Environment]::CurrentDirectory) $false; if(-not ($cwd.Equals($r,[StringComparison]::OrdinalIgnoreCase) -or $cwd.StartsWith($r+'\',[StringComparison]::OrdinalIgnoreCase))){throw 'cwd'}; foreach($raw in @($env:_CODEX_BOOTSTRAP_CODE1,$env:_CODEX_BOOTSTRAP_CODE2)){if($raw){$p=Check $raw $true; if(-not $p.StartsWith($r+'\',[StringComparison]::OrdinalIgnoreCase)){throw 'boundary'}}}; exit 0 } catch { [Console]::Error.WriteLine('Safety stop: unsafe package/code/cwd; target NOT EXECUTED.'); exit 3 }"
if errorlevel 1 exit /b 3
"%~dp0..\python\python.exe" -E -s -B "%~dp0portable-python-cli.py" "pyinstaller" %*
exit /b %errorlevel%
