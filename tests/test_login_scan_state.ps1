#Requires -Version 5.1
# Actual Windows file metadata and atomic credential writes, with synthetic
# data only. Scheduler test doubles never launch a process or use a network.
param([string]$BaselineCommit = '')
$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path -Parent $PSScriptRoot
$tokens = $null; $errors = $null
if ($BaselineCommit) {
    if ($BaselineCommit -notmatch '^[a-f0-9]{40}$') { throw 'Invalid baseline commit.' }
    $oldLines = & git -C $repoRoot show ($BaselineCommit + ':login-json.ps1')
    if ($LASTEXITCODE -ne 0) { throw 'Could not read baseline source.' }
    $ast = [Management.Automation.Language.Parser]::ParseInput(($oldLines -join "`n"), [ref]$tokens, [ref]$errors)
} else {
    $ast = [Management.Automation.Language.Parser]::ParseFile((Join-Path $repoRoot 'login-json.ps1'), [ref]$tokens, [ref]$errors)
}
if ($errors.Count) { throw 'Login source failed to parse.' }
$definitions = @($ast.FindAll({ param($node) $node -is [Management.Automation.Language.FunctionDefinitionAst] }, $true))
$names = @('Test-IsUnderDirectory','Test-IsPortableSingleLinkRegularFile','ConvertTo-PortableJsonText',
    'Write-PortableNewUtf8File','Write-Utf8JsonFile','Get-ObjectProperty','Get-StringProperty','Set-ObjectProperty',
    'Save-CredentialFile','New-ScanResult','Get-ModelSlug','ConvertTo-ResultRecord','Get-RelativePathUnderRoot',
    'Test-IsInternalLoginJsonFile','Get-LoginCredentialFiles','Get-ScanFileState','Test-ScanCacheFileState',
    'Resolve-ScanCacheResultPaths','Read-ScanCache','Write-ScanCache','Invoke-ParallelCredentialChecks')
if (-not $BaselineCommit) { $names += 'Get-ScanCacheFileState' }
foreach ($name in $names) {
    $nodes = @($definitions | Where-Object { $_.Name -eq $name })
    if ($nodes.Count -ne 1) { throw ('Expected exactly one production function: ' + $name) }
    . ([scriptblock]::Create($nodes[0].Extent.Text))
}
function Assert-Case { param([bool]$Condition,[string]$Label) if (-not $Condition) { throw $Label } }
function Resolve-MaxFiles { return 0 }
function Resolve-MaxCredentials { return 0 }
$cursor = [IO.Path]::GetFullPath($repoRoot).TrimEnd('\')
while ($cursor) {
    $item=Get-Item -LiteralPath $cursor -Force
    if (-not $item.PSIsContainer -or ($item.Attributes -band [IO.FileAttributes]::ReparsePoint)) { throw 'Unsafe test ancestor.' }
    $cursor=[IO.Path]::GetDirectoryName($cursor)
}
$scratch=Join-Path $repoRoot 'tmp'
if (-not (Test-Path -LiteralPath $scratch)) { [void](New-Item -ItemType Directory -Path $scratch) }
$scratchItem=Get-Item -LiteralPath $scratch -Force
if (-not $scratchItem.PSIsContainer -or ($scratchItem.Attributes -band [IO.FileAttributes]::ReparsePoint)) { throw 'Unsafe test tmp.' }
$Root=Join-Path $scratch ('login-cache-state-test-'+[guid]::NewGuid().ToString('N'))
[void](New-Item -ItemType Directory -Path $Root)
try {
    $LoginDir=Join-Path $Root 'login_json'
    $TmpDir=Join-Path $Root 'tmp'
    [void](New-Item -ItemType Directory -Path $LoginDir)
    [void](New-Item -ItemType Directory -Path $TmpDir)
    $ScanCachePath=Join-Path $LoginDir 'login_json_report.cache.json'
    $ScanCacheVersion=4
    $a=Join-Path $LoginDir 'a.json'
    $b=Join-Path $LoginDir 'b.json'
    Write-PortableNewUtf8File -Path $a -Text '{"synthetic":"initial-a"}'
    Write-PortableNewUtf8File -Path $b -Text '{"synthetic":"initial-b"}'
    $files=@(Get-LoginCredentialFiles)
    Assert-Case ($files.Count -eq 2) 'Synthetic files not enumerated.'
    $initial=@(Get-ScanFileState -Files $files)
    $results=@()
    foreach ($i in 0,1) {
        $obj=[pscustomobject]@{synthetic=('a' * (100+100*$i))}
        $cred=[pscustomobject]@{Json=$obj;RootJson=$obj}
        Save-CredentialFile -Path $a -Credential $cred
        $r=New-ScanResult -Path $a
        $r.CredentialIndex=$i
        $r.Source=('accounts['+$i+']')
        $r.Status='VALID'
        $r.Credential=$cred
        $r.AccountId='synthetic-a'
        if ($BaselineCommit) {
            $results+=ConvertTo-ResultRecord $r
        } elseif ($i -eq 0) {
            $results+=$r
        } else {
            # Serialize the last save through the same production probe path.
            $probe=ConvertTo-ResultRecord $r -IncludeSavedFileState
            $recordJson=ConvertTo-PortableJsonText -InputObject $probe -Compress
            Assert-Case ($recordJson -notmatch '"Credential"\s*:|access_token|refresh_token') 'Probe exposed credential material.'
            $results+=($recordJson | ConvertFrom-Json)
            Assert-Case ($results[-1].SavedFileState.relative_path -eq 'login_json\a.json') 'Probe lost saved-file metadata.'
        }
    }
    $r=New-ScanResult -Path $b
    $r.CredentialIndex=0
    $r.Status='VALID'
    $r.AccountId='synthetic-b'
    $results+=$r
    $fresh=@(Get-LoginCredentialFiles)
    Assert-Case (-not (Test-ScanCacheFileState -CachedFiles $initial -CurrentFiles $fresh)) 'Fixture did not alter file metadata.'
    # Reverse order: cache state must follow same-file credential index, not
    # the parallel result arrival or lexicographic display order.
    [array]::Reverse($results)
    [void](Write-ScanCache -Results $results -ClientVersion '0.170.0' -ScannedFiles $files -ScanLimit 0 -CredentialLimit 0)
    $cache=[IO.File]::ReadAllText($ScanCachePath) | ConvertFrom-Json
    $valid=Test-ScanCacheFileState -CachedFiles $cache.files -CurrentFiles $fresh
    if ($BaselineCommit) {
        Assert-Case (-not $valid) 'Previous stale FileInfo cache miss did not reproduce.'
        Assert-Case ($cache.files[0].length -eq $initial[0].length) 'Previous cache did not retain enumeration length.'
        Write-Output 'REPRODUCED previous cache miss immediately after successful credential save'
        return
    }
    Assert-Case $valid 'Cache failed to describe own completed refresh.'
    Assert-Case (@(Read-ScanCache -ClientVersion '0.170.0').Count -eq 3) 'Existing cache reader rejected completed refresh.'
    Assert-Case (@($cache.results | Where-Object {$_.PSObject.Properties['SavedFileState'] -or $_.PSObject.Properties['Credential']}).Count -eq 0) 'Transient metadata or credentials leaked into persistent result rows.'
    Write-Output 'PASS real atomic writes, same-file latest save, probe roundtrip and cache reuse'
    Write-Utf8JsonFile -Path $b -InputObject @{synthetic=('b'*500)}
    [void](Write-ScanCache -Results $results -ClientVersion '0.170.0' -ScannedFiles $files -ScanLimit 0 -CredentialLimit 0)
    $cache=[IO.File]::ReadAllText($ScanCachePath) | ConvertFrom-Json
    Assert-Case (-not (Test-ScanCacheFileState -CachedFiles $cache.files -CurrentFiles @(Get-LoginCredentialFiles))) 'Unowned edit was certified by cache writer.'
    Assert-Case ($null -eq (Read-ScanCache -ClientVersion '0.170.0')) 'Unowned edit no longer invalidates cache.'
    Write-Output 'PASS unrelated file changes still invalidate the cache'
    $c=Join-Path $LoginDir 'c.json'
    Write-PortableNewUtf8File -Path $c -Text '{"synthetic":"new file"}'
    Assert-Case (-not (Test-ScanCacheFileState -CachedFiles $cache.files -CurrentFiles @(Get-LoginCredentialFiles))) 'New file was incorrectly accepted.'
    Write-Output 'PASS changed scan scope still invalidates cache'

    # Verify the unchanged scheduling policy using the actual scheduler and
    # controllable job doubles. No real process is launched.
    Write-PortableNewUtf8File -Path (Join-Path $Root 'login-json.ps1') -Text '# synthetic placeholder; never executed'
    $InternalMutexTokenName='CODEX_TEST_LOGIN_MUTEX_'+[guid]::NewGuid().ToString('N')
    $script:ActiveJobs=@{}
    $script:Queued=@()
    $script:Peak=0
    function Resolve-JobTimeoutSec { return 420 }
    function Start-Sleep { param([int]$Milliseconds) }
    function Start-Job {
        param([scriptblock]$ScriptBlock,[object[]]$ArgumentList)
        $p=[string]$ArgumentList[1]
        $i=[int]$ArgumentList[2]
        if ($script:ActiveJobs.ContainsKey($p)) { throw 'Two active writers for one file.' }
        $job=[pscustomobject]@{State='Running';Path=$p;Index=$i}
        $script:ActiveJobs[$p]=$job
        $script:Queued+=($p+'#'+$i)
        $script:Peak=[Math]::Max($script:Peak,$script:ActiveJobs.Count)
        return $job
    }
    function Receive-CompletedProbeJobs {
        param([Collections.ArrayList]$Jobs,[Collections.ArrayList]$Results,[switch]$OnlyFinished)
        if ($Jobs.Count -eq 0) { return }
        $item=$Jobs[0]
        $item.Job.State='Completed'
        $script:ActiveJobs.Remove($item.FilePath)
        [void]$Results.Add([pscustomobject]@{File=$item.Entry.File;CredentialIndex=$item.Entry.CredentialIndex})
        $Jobs.RemoveAt(0)
    }
    $targets=@()
    foreach ($p in @($a,$b)) {
        foreach ($i in 0,1,2) {
            $targets += [pscustomobject]@{Path=$p;File=([IO.Path]::GetFileName($p)+'#'+$i);CredentialIndex=$i;Source=('accounts['+$i+']');DeleteAllowed=$false}
        }
    }
    $scheduled=@(Invoke-ParallelCredentialChecks -Targets $targets -ClientVersion '0.170.0' -Limit 2)
    Assert-Case ($scheduled.Count -eq 6 -and $script:Peak -eq 2 -and $script:ActiveJobs.Count -eq 0) 'Existing scheduling concurrency changed.'
    foreach ($p in @($a,$b)) {
        $seq=@($script:Queued | Where-Object { $_.StartsWith($p+'#') })
        Assert-Case (($seq -join '|') -eq ((@($p+'#0',$p+'#1',$p+'#2')) -join '|')) 'Same-file credential order changed.'
    }
    Write-Output 'PASS actual scheduler with job doubles: same-file serialization and different-file concurrency'
} finally {
    if (Test-Path -LiteralPath $Root) {
        # This directory was created uniquely by this test; check before
        # recursive removal. Do not clean any pre-existing package state.
        $item=Get-Item -LiteralPath $Root -Force
        if ($item.Attributes -band [IO.FileAttributes]::ReparsePoint) { throw 'Unsafe owned fixture cleanup.' }
        foreach ($child in @(Get-ChildItem -LiteralPath $Root -Force -Recurse)) {
            if ($child.Attributes -band [IO.FileAttributes]::ReparsePoint) { throw 'Linked fixture cleanup refused.' }
        }
        Remove-Item -LiteralPath $Root -Recurse -Force
    }
}
