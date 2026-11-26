#Requires -Version 5.1
# Local tool path/TEMP only. Does not run BAT, Codex, browser or login.
$ErrorActionPreference = 'Stop'
if ($PSVersionTable.PSVersion.Major -ne 5 -or $PSVersionTable.PSVersion.Minor -ne 1 -or
    -not [Environment]::Is64BitProcess) { throw 'Windows PowerShell 5.1 x64 required' }
$source = Split-Path -Parent $PSScriptRoot
. (Join-Path $source 'tool/automation/portable-automation.ps1')
$base = New-AutomationDirectory -Root $source -Path (Join-Path $source 'tmp')
$owned = New-AutomationDirectory -Root $source -Path (Join-Path $base ('native-tool-path-' + [Guid]::NewGuid().ToString('N')))
$oldPath = $env:PATH
try {
    $Root = New-AutomationDirectory -Root $owned -Path (Join-Path $owned ('Portable ' + [char]0x4e2d + [char]0x6587 + ' space'))
    foreach ($rel in @('tool/python/Lib/site-packages','tool/node','tool/automation','work','tmp','tests')) {
        [void](New-AutomationDirectory -Root $Root -Path (Join-Path $Root $rel))
    }
    function Copy-Verified([string]$Relative) {
        $from = Assert-AutomationPath -Root $source -Path (Join-Path $source $Relative)
        $to = Assert-AutomationPath -Root $Root -Path (Join-Path $Root $Relative) -MayNotExist
        if ([IO.File]::Exists($to)) { throw 'Fixture file already exists' }
        [IO.File]::Copy($from, $to, $false)
        if ((Get-FileHash -LiteralPath $from -Algorithm SHA256).Hash -cne
            (Get-FileHash -LiteralPath $to -Algorithm SHA256).Hash) { throw 'Fixture copy hash mismatch' }
    }
    foreach ($rel in @('tool/portable-process.ps1','tool/node/node.exe','tests/test_temp_consumer_encoding.py')) { Copy-Verified $rel }
    $runtime = Assert-AutomationPath -Root $source -Path (Join-Path $source 'tool/python') -Directory
    foreach ($file in @(Get-ChildItem -LiteralPath $runtime -File)) {
        if ($file.Extension -in @('.dll','.pyd') -or $file.Name -in @('python.exe','python314.zip','python314._pth')) {
            Copy-Verified ('tool/python/' + $file.Name)
        }
    }
    $probe = Join-Path $Root 'work/local_native_tool_consumer.py'
    $probeSource = Assert-AutomationPath -Root $source -Path (Join-Path $source 'tests/local_native_tool_consumer.py')
    [IO.File]::Copy($probeSource, $probe, $false)
    if ((Get-FileHash -LiteralPath $probeSource).Hash -cne (Get-FileHash -LiteralPath $probe).Hash) { throw 'Probe hash mismatch' }
    $python = Assert-AutomationPath -Root $Root -Path (Join-Path $Root 'tool/python/python.exe')
    $null = Assert-AutomationPath -Root $Root -Path (Join-Path $Root 'tool/node/node.exe')

    # Use the exact production function and its two list assignments, not a
    # copied approximation. Never run the rest of the launcher.
    $tokens=$null; $errors=$null
    $ast = [Management.Automation.Language.Parser]::ParseFile((Join-Path $source 'run-codex.ps1'),[ref]$tokens,[ref]$errors)
    if ($errors.Count -ne 0) { throw 'Launcher parse failed' }
    foreach ($name in @('Get-CodexTrustedWindowsRoot','Test-IsUnderDirectory','Assert-PortablePath','Set-PortableProcessPath')) {
        $found = @($ast.FindAll({param($n) $n -is [Management.Automation.Language.FunctionDefinitionAst] -and $n.Name -eq $name},$true))
        if ($found.Count -ne 1) { throw 'Unexpected launcher function contract' }
        . ([ScriptBlock]::Create($found[0].Extent.Text))
    }
    $PortableWindowsRoot = Get-CodexTrustedWindowsRoot
    $PortableTool = Join-Path $Root 'tool'
    $PortableCache = Join-Path $Root 'cache'
    # No Android SDK in this narrow synthetic fixture; optional prefix absent.
    foreach ($variable in @('$ToolPaths','$SystemPaths')) {
        $found = @($ast.FindAll({param($n) $n -is [Management.Automation.Language.AssignmentStatementAst] -and
            $n.Left.Extent.Text -ceq $variable -and $n.Right.Extent.Text.TrimStart().StartsWith('@(') -and
            ($n.Right.Extent.Text -match 'Join-Path \$Portable(?:Tool|WindowsRoot)')},$true))
        if ($found.Count -ne 1) { throw 'Unexpected launcher PATH assignment' }
        . ([ScriptBlock]::Create($found[0].Extent.Text))
    }
    Set-PortableProcessPath
    $selectedPath = $env:PATH
    $env:PATH = $oldPath
    foreach ($entry in ($selectedPath -split ';')) {
        if (-not $entry.StartsWith($Root + '\',[StringComparison]::OrdinalIgnoreCase) -and $entry -notin $SystemPaths) {
            throw 'Unexpected PATH entry'
        }
    }
    # Actual production automation supervisor. Its native environment is
    # intentionally different from the main launcher; inject only the actual
    # extracted PATH result for this targeted test, not a fake main launch.
    Initialize-AutomationSupervisor -Root $Root
    $work = Join-Path $Root 'work'
    $temp = Join-Path $Root 'tmp'
    $baseline = New-AutomationStartInfo -Root $Root -FilePath $python -WorkingDirectory $work -SessionDirectory $temp -CaptureOutput -Arguments @('-I','-B',(Join-Path $Root 'tests/test_temp_consumer_encoding.py'))
    $baseResult = Invoke-PortableProcess -StartInfo $baseline -PackageRoot $Root -TimeoutMs 120000
    if ($baseResult.ExitCode -ne 0 -or $baseResult.StdErr -notmatch 'Ran 6 tests' -or $baseResult.StdErr -notmatch '(?m)^OK\r?$') { throw 'Existing TEMP controls failed' }
    Write-Output 'TEMP_PRECEDENCE=PASS'
    $start = New-AutomationStartInfo -Root $Root -FilePath $python -WorkingDirectory $work -SessionDirectory $temp -CaptureOutput -Arguments @('-I','-B',$probe,$Root)
    $start.EnvironmentVariables['PATH'] = $selectedPath
    $result = Invoke-PortableProcess -StartInfo $start -PackageRoot $Root -TimeoutMs 120000
    if ($result.ExitCode -ne 0 -or $result.StdErr) { throw 'Native tool consumer failed' }
    $report = $result.StdOut | ConvertFrom-Json -ErrorAction Stop
    $fields = @('python_path','node_path','python_temp','node_temp','work_write','synthetic_denial_no_fallback','missing_path_rejected')
    foreach ($field in $fields) {
        if ($report.$field -isnot [bool] -or -not $report.$field) { throw 'Missing native probe result' }
    }
    if (@(Get-ChildItem -LiteralPath $temp -Force).Count -ne 0) { throw 'Temporary residue' }
} finally {
    $env:PATH = $oldPath
    Remove-AutomationSession -Root $source -Path $owned
}
Write-Output 'LOCAL_NATIVE_TOOL_BOUNDARY=PASS'
