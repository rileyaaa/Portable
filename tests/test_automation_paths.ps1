# Offline production-helper tests; never launch Windows or browser processes.
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
. (Join-Path $root 'tool/automation/portable-automation.ps1')
$scratch = New-AutomationDirectory -Root $root -Path (Join-Path $root 'tmp')
$fixture = New-AutomationDirectory -Root $root -Path (Join-Path $scratch ('automation-ps-' + [Guid]::NewGuid().ToString('N')))
function Assert-Test([bool]$Condition, [string]$Message) { if (-not $Condition) { throw $Message } }
try {
    $session = New-AutomationDirectory -Root $root -Path (Join-Path $fixture 'session')
    $executable = Join-Path $fixture 'synthetic.exe'
    [IO.File]::WriteAllText($executable, 'Fixture only; never executable.')
    $start = New-AutomationStartInfo -Root $root -FilePath $executable -WorkingDirectory $fixture -Arguments @('space and 中文', 'quote"slash\', '') -SessionDirectory $session
    foreach ($name in @('HOME','USERPROFILE','APPDATA','LOCALAPPDATA','TEMP','TMP','TMPDIR','PROGRAMDATA','ALLUSERSPROFILE','PUBLIC','XDG_CONFIG_HOME','XDG_CACHE_HOME','XDG_DATA_HOME','XDG_STATE_HOME')) {
        Assert-Test ($start.EnvironmentVariables[$name] -ceq $session) "Child $name must use owned package state."
    }
    Assert-Test (-not $start.UseShellExecute) 'Shell execution must be disabled.'
    Assert-Test (-not $start.EnvironmentVariables.ContainsKey('NODE_OPTIONS')) 'Host code injection must not be inherited.'
    Assert-Test ($start.Arguments.Contains('""')) 'Empty CRT argument must be retained.'
    Write-Output 'PASS isolated child environment and quoted arguments'
    foreach ($bad in @((Join-Path $fixture '../escape'), (Split-Path -Parent $root))) {
        $threw = $false
        try { $null = Assert-AutomationPath -Root $fixture -Path $bad -Directory -MayNotExist } catch { $threw = $true }
        Assert-Test $threw 'Traversal/outside paths must be refused.'
    }
    Write-Output 'PASS lexical package boundary'
    $hard = Join-Path $fixture 'hard.exe'
    $null = New-Item -ItemType HardLink -Path $hard -Target $executable
    $threw = $false
    try { $null = Assert-AutomationPath -Root $root -Path $hard } catch { $threw = $true }
    Assert-Test $threw 'Hardlinked code input must be refused.'
    Write-Output 'PASS hardlinked executable rejection'
    $tree = New-AutomationDirectory -Root $root -Path (Join-Path $fixture 'browser-tree')
    $subtree = New-AutomationDirectory -Root $root -Path (Join-Path $tree 'ordinary')
    [IO.File]::WriteAllText((Join-Path $subtree 'payload.txt'), 'synthetic')
    Assert-AutomationTree -Root $root -Path $tree
    $linked = Join-Path $tree 'linked'
    $linkType = 'SymbolicLink'
    if ([Environment]::OSVersion.Platform -eq [PlatformID]::Win32NT) { $linkType = 'Junction' }
    $null = New-Item -ItemType $linkType -Path $linked -Target $session
    $script:enumeratedLinkedDirectory = $false
    function Get-ChildItem {
        param([string]$LiteralPath, [switch]$Force)
        if ($LiteralPath -eq $linked) { $script:enumeratedLinkedDirectory = $true }
        Microsoft.PowerShell.Management\Get-ChildItem -LiteralPath $LiteralPath -Force:$Force
    }
    try {
        $threw = $false
        try { Assert-AutomationTree -Root $root -Path $tree } catch { $threw = $true }
        Assert-Test $threw 'Existing browser links must be refused.'
        Assert-Test (-not $script:enumeratedLinkedDirectory) 'Do not enumerate a linked target before refusing it.'
    } finally {
        Remove-Item Function:Get-ChildItem
        Remove-Item -LiteralPath $linked -Force
    }
    Write-Output 'PASS browser tree checked before linked subtree enumeration'
    $owned = New-AutomationDirectory -Root $root -Path (Join-Path $fixture 'cleanup')
    [IO.File]::WriteAllText((Join-Path $owned 'owned.txt'), 'synthetic')
    Remove-AutomationSession -Root $root -Path $owned
    Assert-Test (-not [IO.Directory]::Exists($owned)) 'Owned session must be removed.'
    Assert-Test ([IO.File]::Exists($executable)) 'Cleanup must preserve other fixture data.'
    $threw = $false
    try { Remove-AutomationSession -Root $root -Path $scratch } catch { $threw = $true }
    Assert-Test $threw 'Shared temporary root must never be deleted.'
    Write-Output 'PASS owned session cleanup and shared-root protection'
    # Reuse state across tasks, but never share it with a simultaneous browser or cleaner.
    $browserLock = Open-AutomationBrowserLock -Root $fixture
    try {
        $state = Initialize-AutomationBrowserState -Root $fixture
        $stateFile = Join-Path $state.profile 'synthetic-state.txt'
        [IO.File]::WriteAllText($stateFile, 'retained between tasks')
        $second = Initialize-AutomationBrowserState -Root $fixture
        Assert-Test ($state.profile -ceq $second.profile) 'Sequential browser tasks must reuse one profile.'
        Assert-Test ([IO.File]::ReadAllText($stateFile) -ceq 'retained between tasks') 'Initializing the next task must retain data.'
        foreach ($name in @('profile','cache','crashes','downloads','runtime')) {
            Assert-Test ([IO.Directory]::Exists($state.$name)) "Persistent browser $name must be under cache/browser."
        }
        $threw = $false
        try { $unexpected = Open-AutomationBrowserLock -Root $fixture; $unexpected.Dispose() } catch { $threw = $true }
        Assert-Test $threw 'A second browser must not open an active profile.'
        # Execute the actual cache-cleaner lock acquisition, without running deletion
        # or inspecting real package user data. Its helper is copied into this fixture.
        $helperDirectory = New-AutomationDirectory -Root $fixture -Path (Join-Path $fixture 'tool/automation')
        Copy-Item -LiteralPath (Join-Path $root 'tool/automation/portable-automation.ps1') -Destination $helperDirectory
        $tokens=$null; $errors=$null
        $cleanupAst = [Management.Automation.Language.Parser]::ParseFile((Join-Path $root '清理缓存.ps1'),[ref]$tokens,[ref]$errors)
        Assert-Test ($errors.Count -eq 0) 'Cache cleaner must parse.'
        $acquisition = $cleanupAst.Find({
            param($node)
            $node -is [Management.Automation.Language.AssignmentStatementAst] -and
            $node.Left.Extent.Text -eq '$CleanupBrowserFileLock' -and $node.Right.Extent.Text.StartsWith('& {')
        }, $true)
        Assert-Test ($null -ne $acquisition) 'Cache cleaner must acquire the browser lock before clearing state.'
        $acquireForCleanup = [ScriptBlock]::Create('param([string]$Root)' + "`n" + $acquisition.Extent.Text + "`n" + '$CleanupBrowserFileLock')
        $threw = $false
        try { $unexpected = & $acquireForCleanup $fixture; $unexpected.Dispose() } catch { $threw = $true }
        Assert-Test $threw 'Actual cleanup guard must refuse an active browser session.'
        Assert-Test ([IO.File]::Exists($stateFile)) 'A rejected cleanup must retain the profile.'
    } finally { $browserLock.Dispose() }
    $cleanupLock = & $acquireForCleanup $fixture
    try {
        $threw = $false
        try { $unexpected = Open-AutomationBrowserLock -Root $fixture; $unexpected.Dispose() } catch { $threw = $true }
        Assert-Test $threw 'A browser must not start during cache cleanup.'
    } finally { $cleanupLock.Dispose() }
    $stateLockPath = Join-Path $fixture '.codex-browser.instance.lock'
    Remove-Item -LiteralPath $stateLockPath -Force
    $null = New-Item -ItemType HardLink -Path $stateLockPath -Target $stateFile
    $threw = $false
    try { $unexpected = Open-AutomationBrowserLock -Root $fixture; $unexpected.Dispose() } catch { $threw = $true }
    Assert-Test $threw 'Hardlinked browser lock files must be refused before opening.'
    Remove-Item -LiteralPath $stateLockPath -Force
    $unsafeRoot = New-AutomationDirectory -Root $fixture -Path (Join-Path $fixture 'unsafe-root')
    $unsafeCache = Join-Path $unsafeRoot 'cache'
    $null = New-Item -ItemType $linkType -Path $unsafeCache -Target $session
    try {
        $threw = $false
        try { $null = Initialize-AutomationBrowserState -Root $unsafeRoot } catch { $threw = $true }
        Assert-Test $threw 'Linked browser state ancestors must be refused before creating children.'
        Assert-Test (-not [IO.Directory]::Exists((Join-Path $session 'browser'))) 'State initialization must not follow a linked ancestor.'
    } finally { Remove-Item -LiteralPath $unsafeCache -Force }
    Write-Output 'PASS persistent browser data, browser/cleanup mutual exclusion and unsafe state rejection'
    if ([Environment]::OSVersion.Platform -eq [PlatformID]::Win32NT) {
        # Run the complete real cache cleaner only against synthetic Windows state.
        foreach ($marker in @('codex.exe','run-codex.ps1','env.ps1')) {
            [IO.File]::WriteAllText((Join-Path $fixture $marker), 'synthetic fixture')
        }
        $fixtureWork = New-AutomationDirectory -Root $fixture -Path (Join-Path $fixture 'work')
        $fixtureHome = New-AutomationDirectory -Root $fixture -Path (Join-Path $fixture 'home')
        [IO.File]::WriteAllText((Join-Path $fixtureWork 'keep.txt'), 'synthetic work')
        [IO.File]::WriteAllText((Join-Path $fixtureHome 'auth.json'), '{"synthetic":true}')
        $cleaner = Join-Path $fixture '清理缓存.ps1'
        Copy-Item -LiteralPath (Join-Path $root '清理缓存.ps1') -Destination $cleaner
        $shell = (Get-Process -Id $PID).Path
        $browserLock = Open-AutomationBrowserLock -Root $fixture
        try {
            & $shell -NoProfile -NonInteractive -File $cleaner -Yes | Out-Null
            Assert-Test ($LASTEXITCODE -eq 2) 'Full cache cleaner must reject an active browser.'
            Assert-Test ([IO.File]::Exists($stateFile)) 'Rejected full cleanup must retain browser state.'
        } finally { $browserLock.Dispose() }
        & $shell -NoProfile -NonInteractive -File $cleaner -Yes | Out-Null
        Assert-Test ($LASTEXITCODE -eq 0) 'Full cache cleaner must succeed when the browser exits.'
        Assert-Test (-not [IO.Directory]::Exists($state.Root)) 'Manual cache cleanup must remove persistent browser data.'
        Assert-Test ([IO.File]::Exists((Join-Path $fixtureWork 'keep.txt'))) 'Default cleanup must preserve work.'
        Assert-Test ([IO.File]::Exists((Join-Path $fixtureHome 'auth.json'))) 'Default cleanup must preserve Codex authentication.'
        Write-Output 'PASS complete Windows cache cleanup and protected user state'
    } else { Write-Output 'SKIP complete cache-cleaner execution: requires Windows path semantics' }
    foreach ($name in @('desktop.ps1','desktop-worker.ps1','start-browser.ps1')) {
        $callArguments = @{}
        if ($name -ne 'start-browser.ps1') { $callArguments['TargetProcessId'] = 123456 }
        $threw = $false
        try { & (Join-Path $root ('tool/automation/' + $name)) @callArguments }
        catch { $threw = $_.Exception.Message -match 'task|TaskAuthorized' }
        Assert-Test $threw "Unselected entry must reject before UI/process work: $name"
    }
    Write-Output 'PASS task selection gates before process work'
    foreach ($name in @('desktop.ps1','desktop-worker.ps1','start-browser.ps1','install-browser.ps1','portable-automation.ps1')) {
        $tokens=$null; $errors=$null
        $null = [Management.Automation.Language.Parser]::ParseFile((Join-Path $root ('tool/automation/' + $name)),[ref]$tokens,[ref]$errors)
        Assert-Test ($errors.Count -eq 0) "Production script must parse: $name"
    }
    Write-Output 'PASS all automation PowerShell scripts parse'
} finally {
    Remove-Item -LiteralPath $fixture -Recurse -Force
}
