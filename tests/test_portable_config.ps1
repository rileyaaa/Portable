#Requires -Version 5.1
param(
    # Optional JSON captured with the pinned client's: debug models --bundled
    [string]$BundledModelsPath = ""
)

$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $PSScriptRoot
$LauncherPath = Join-Path $Root 'run-codex.ps1'
$Tokens = $null
$ParseErrors = $null
$LauncherAst = [System.Management.Automation.Language.Parser]::ParseFile(
    $LauncherPath, [ref]$Tokens, [ref]$ParseErrors
)
if ($ParseErrors.Count -gt 0) {
    throw "Launcher parse failed: $($ParseErrors[0].Message)"
}

# Import definitions only. Never execute the Windows launcher, inspect credentials,
# start a client, or write package state from this platform-independent test.
$FunctionNames = @(
    'Convert-ToTomlBool',
    'Normalize-ReasoningEffortValue',
    'Get-ModelReasoningMenuInfo',
    'Get-BundledModelsResponse',
    'Find-BundledModelSource',
    'Get-PortableGenericBaseInstructions',
    'Ensure-ModelCatalog',
    'ConvertTo-PortableJsonText'
)
foreach ($FunctionName in $FunctionNames) {
    $Definitions = @($LauncherAst.FindAll({
        param($Node)
        $Node -is [System.Management.Automation.Language.FunctionDefinitionAst]
    }, $true) | Where-Object { $_.Name -eq $FunctionName })
    if ($Definitions.Count -ne 1) { throw "Expected one definition of $FunctionName" }
    . ([scriptblock]::Create($Definitions[0].Extent.Text))
}

# Replace only the process and file boundaries. Catalog selection, cloning,
# overrides, and JSON serialization execute the production functions above.
function Invoke-CodexChildCapture {
    param([object[]]$LaunchArgs)
    if ($null -eq $script:ModelResponse) {
        return [pscustomobject]@{ ExitCode = 1; StdOut = '' }
    }
    return [pscustomobject]@{
        ExitCode = 0
        StdOut = ConvertTo-Json -InputObject $script:ModelResponse -Depth 64
    }
}

function Write-Utf8TextAtomic {
    param([string]$Path, [string]$Text)
    $script:CatalogText = $Text
}

function Assert-Equal {
    param($Actual, $Expected, [string]$Because)
    if ($Actual -cne $Expected) {
        throw "$Because -- expected '$Expected', got '$Actual'"
    }
}

function Assert-True {
    param([bool]$Condition, [string]$Because)
    if (-not $Condition) { throw $Because }
}

function Test-Case {
    param([string]$Name, [scriptblock]$Body)
    & $Body
    $script:Passed += 1
    Write-Output "PASS $Name"
}

function Set-TestModels {
    param($Models)
    $script:ModelResponse = $Models
    $script:BundledModelsCache = $null
    $script:CatalogText = $null
}

function Invoke-HostGuardCase {
    param([string]$ResourceVariant)
    $FixtureBase = Join-Path $Root 'tmp'
    # Do not inherit a host TEMP path or follow a pre-existing linked tmp directory.
    $FixtureAncestor = $FixtureBase
    while (-not [string]::IsNullOrWhiteSpace($FixtureAncestor)) {
        $FixtureItem = Get-Item -LiteralPath $FixtureAncestor -Force -ErrorAction SilentlyContinue
        if ($null -ne $FixtureItem -and (
            -not $FixtureItem.PSIsContainer -or
            ($FixtureItem.Attributes -band [System.IO.FileAttributes]::ReparsePoint) -ne 0)) {
            throw "Unsafe test fixture directory: $FixtureAncestor"
        }
        $FixtureAncestor = Split-Path -Parent $FixtureAncestor
    }
    $null = New-Item -ItemType Directory -Path $FixtureBase -Force
    $FixtureRoot = Join-Path $FixtureBase ('codex-host-guard-' + [guid]::NewGuid().ToString('N'))
    $null = New-Item -ItemType Directory -Path $FixtureRoot
    try {
        $FixtureHost = Join-Path $FixtureRoot 'codex-code-mode-host.exe'
        [System.IO.File]::WriteAllBytes($FixtureHost, [byte[]](1, 3, 5, 7))
        $ExpectedHash = (Get-FileHash -LiteralPath $FixtureHost -Algorithm SHA256).Hash
        if ($ResourceVariant -ne 'absent') {
            $ResourceDirectory = Join-Path $FixtureRoot 'codex-resources'
            $null = New-Item -ItemType Directory -Path $ResourceDirectory
            $ResourceHost = Join-Path $ResourceDirectory 'codex-code-mode-host.exe'
            $Bytes = if ($ResourceVariant -eq 'same') { [byte[]](1, 3, 5, 7) } else { [byte[]](2, 4, 6, 8) }
            [System.IO.File]::WriteAllBytes($ResourceHost, $Bytes)
        }
        $WorkerPath = Join-Path $FixtureRoot 'check-host.ps1'
        $WorkerSource = @'
param([string]$LauncherPath, [string]$FixtureRoot, [string]$ExpectedHash)
$ErrorActionPreference = 'Stop'
$Tokens = $null
$ParseErrors = $null
$Ast = [System.Management.Automation.Language.Parser]::ParseFile(
    $LauncherPath, [ref]$Tokens, [ref]$ParseErrors
)
if ($ParseErrors.Count -gt 0) { throw 'Launcher parse failed' }
$Definitions = @($Ast.FindAll({
    param($Node)
    $Node -is [System.Management.Automation.Language.FunctionDefinitionAst] -and
    $Node.Name -eq 'Assert-PinnedCodeModeHost'
}, $true))
if ($Definitions.Count -ne 1) { throw 'Expected one host guard definition' }
. ([scriptblock]::Create($Definitions[0].Extent.Text))
# Fixtures are ordinary local files. Windows reparse/ACL validation has its own
# platform boundary; the production candidate selection and SHA checks run here.
function Assert-PortableRegularInputFile { param($Name, $Path) }
function Assert-PortablePinnedExecutableAcl { param($Name, $Path) }
$Root = $FixtureRoot
$CodeModeHost = Join-Path $Root 'codex-code-mode-host.exe'
$ExpectedCodeModeHostSha256 = $ExpectedHash
$ExpectedCodexVersion = 'test-fixture'
Assert-PinnedCodeModeHost
exit 0
'@
        [System.IO.File]::WriteAllText($WorkerPath, $WorkerSource, (New-Object System.Text.UTF8Encoding($true)))
        # A separate engine preserves the production function's "exit 3" without
        # terminating this runner or rewriting exit statements in the source.
        $EnginePath = [System.Diagnostics.Process]::GetCurrentProcess().MainModule.FileName
        $WorkerRuntime = Join-Path $FixtureRoot 'runtime'
        $null = New-Item -ItemType Directory -Path $WorkerRuntime
        $Start = New-Object System.Diagnostics.ProcessStartInfo
        $Start.FileName = $EnginePath
        $Start.Arguments = '-NoLogo -NoProfile -NonInteractive -File "' + $WorkerPath +
            '" "' + $LauncherPath + '" "' + $FixtureRoot + '" "' + $ExpectedHash + '"'
        $Start.UseShellExecute = $false
        $Start.CreateNoWindow = $true
        $Start.RedirectStandardOutput = $true
        $Start.RedirectStandardError = $true
        $Start.WorkingDirectory = $FixtureRoot
        foreach ($Name in @('TEMP', 'TMP', 'TMPDIR', 'HOME', 'USERPROFILE',
                            'APPDATA', 'LOCALAPPDATA', 'XDG_CONFIG_HOME',
                            'XDG_CACHE_HOME', 'XDG_DATA_HOME')) {
            $Start.EnvironmentVariables[$Name] = $WorkerRuntime
        }
        $Start.EnvironmentVariables['POWERSHELL_TELEMETRY_OPTOUT'] = '1'
        $Start.EnvironmentVariables['PSModuleAnalysisCachePath'] = Join-Path $WorkerRuntime 'ModuleAnalysisCache'
        $Process = New-Object System.Diagnostics.Process
        $Process.StartInfo = $Start
        try {
            [void]$Process.Start()
            $StdoutTask = $Process.StandardOutput.ReadToEndAsync()
            $StderrTask = $Process.StandardError.ReadToEndAsync()
            if (-not $Process.WaitForExit(60000)) {
                $Process.Kill()
                $Process.WaitForExit()
                throw 'Host guard fixture exceeded 60 seconds.'
            }
            return [pscustomobject]@{
                ExitCode = $Process.ExitCode
                Output = $StdoutTask.GetAwaiter().GetResult() + $StderrTask.GetAwaiter().GetResult()
            }
        } finally {
            $Process.Dispose()
        }
    } finally {
        Remove-Item -LiteralPath $FixtureRoot -Recurse -Force
    }
}

$script:Passed = 0
$UseAccountJsonLogin = $false
$UseBrowserLogin = $false
$SavedProviderMode = $env:CODEX_PROVIDER_MODE
$SavedCatalogPath = $env:CODEX_MODEL_CATALOG_JSON
try {
    $env:CODEX_MODEL_CATALOG_JSON = ''

    Test-Case 'boolean true spellings and surrounding whitespace' {
        foreach ($Value in @('1', 'TRUE', 'Yes', 'y', ' ON ')) {
            Assert-Equal (Convert-ToTomlBool $Value $false) 'true' $Value
        }
    }
    Test-Case 'boolean false spellings and defaults' {
        foreach ($Value in @('0', 'FALSE', 'No', 'n', ' OFF ')) {
            Assert-Equal (Convert-ToTomlBool $Value $true) 'false' $Value
        }
        Assert-Equal (Convert-ToTomlBool '' $true) 'true' 'Empty true default'
        Assert-Equal (Convert-ToTomlBool ' ' $false) 'false' 'Blank false default'
    }
    Test-Case 'invalid booleans fail instead of silently changing permissions' {
        foreach ($Value in @('2', 'tru', 'enabled', 'false;true')) {
            $Rejected = $false
            try { $null = Convert-ToTomlBool $Value $false } catch { $Rejected = $true }
            Assert-True $Rejected "Invalid boolean accepted: $Value"
        }
    }
    Test-Case 'reasoning normalization preserves custom provider values' {
        Assert-Equal (Normalize-ReasoningEffortValue ' ') '' 'Unspecified effort'
        foreach ($Value in @('minimal', 'low', 'medium', 'high', 'xhigh', 'max', 'ultra')) {
            Assert-Equal (Normalize-ReasoningEffortValue $Value.ToUpperInvariant()) $Value $Value
        }
        Assert-Equal (Normalize-ReasoningEffortValue ' ProviderEffort ') 'ProviderEffort' 'Custom effort'
    }
    Test-Case 'third-party reasoning remains unspecified by default' {
        Set-TestModels $null
        $env:CODEX_PROVIDER_MODE = 'custom_provider'
        $Menu = Get-ModelReasoningMenuInfo 'gpt-6-luna'
        Assert-Equal $Menu.Default '' 'Third-party provider must control its default'
    }
    Test-Case 'official Luna fallback agrees with 0.164.0 medium default' {
        Set-TestModels $null
        $env:CODEX_PROVIDER_MODE = 'official_chatgpt'
        $Menu = Get-ModelReasoningMenuInfo 'gpt-6-luna'
        Assert-Equal $Menu.Default 'medium' 'Luna fallback'
        Assert-True ($Menu.Levels -contains $Menu.Default) 'Fallback default must be selectable'
    }

    $Fixture = [pscustomobject]@{
        models = @(
            [pscustomobject]@{ slug = 'gpt'; priority = 5 },
            [pscustomobject]@{
                slug = 'gpt-5.2'
                display_name = 'GPT-5.2'
                priority = 1
                base_instructions = "You are Codex, based on GPT-5.2.`nPreserve user files."
                input_modalities = @('text', 'image')
                context_window = 272000
                max_context_window = 272000
                future_metadata = [pscustomobject]@{ enabled = $true }
            }
        )
    }

    Test-Case 'model lookup selects longest prefix and one provider namespace' {
        Assert-Equal (Find-BundledModelSource $Fixture 'gpt-5.2-snapshot').slug 'gpt-5.2' 'Longest prefix'
        Assert-Equal (Find-BundledModelSource $Fixture 'vendor/gpt-5.2-snapshot').slug 'gpt-5.2' 'Provider namespace'
        Assert-True ($null -eq (Find-BundledModelSource $Fixture 'vendor/team/gpt-5.2')) 'Nested namespace must not match'
        Assert-True ($null -eq (Find-BundledModelSource $Fixture 'GPT-5.2')) 'Model matching is case sensitive'
        Assert-True ($null -eq (Find-BundledModelSource $Fixture 'unknown-model')) 'Unknown model must not match'
    }
    Test-Case 'known model overrides preserve metadata without mutating the source' {
        Set-TestModels $Fixture
        $Success = Ensure-ModelCatalog -CatalogPath 'memory-only.json' -ModelSlug 'vendor/gpt-5.2' -InputModalities @('text') -ContextWindow 524288
        Assert-True $Success 'Known catalog generation failed'
        $Entry = ($script:CatalogText | ConvertFrom-Json).models[0]
        Assert-Equal $Entry.slug 'vendor/gpt-5.2' 'Requested slug'
        Assert-Equal (@($Entry.input_modalities) -join ',') 'text' 'Explicit text-only override'
        Assert-Equal $Entry.context_window 524288 'Context override'
        Assert-Equal $Entry.max_context_window 524288 'Maximum must allow the requested context'
        Assert-True $Entry.future_metadata.enabled 'Unrecognized future metadata must survive cloning'
        Assert-Equal $Fixture.models[1].context_window 272000 'Source context must remain unchanged'
        Assert-Equal (@($Fixture.models[1].input_modalities) -join ',') 'text,image' 'Source modalities must remain unchanged'
    }
    Test-Case 'unknown model catalog receives overrides and neutral instructions' {
        Set-TestModels $Fixture
        $Success = Ensure-ModelCatalog -CatalogPath 'memory-only.json' -ModelSlug 'portable-test-unknown-model' -InputModalities @('text', 'image') -ContextWindow 131072
        Assert-True $Success 'Unknown catalog generation failed'
        $Entry = ($script:CatalogText | ConvertFrom-Json).models[0]
        Assert-Equal $Entry.slug 'portable-test-unknown-model' 'Unknown slug'
        Assert-Equal $Entry.context_window 131072 'Unknown model context'
        Assert-Equal $Entry.max_context_window 131072 'Unknown model maximum context'
        Assert-Equal (@($Entry.input_modalities) -join ',') 'text,image' 'Unknown model modalities'
        Assert-Equal $Entry.base_instructions 'Preserve user files.' 'Cloned model identity must be removed'
    }
    Test-Case 'catalog generation reports unavailable metadata without writing output' {
        Set-TestModels $null
        $Success = Ensure-ModelCatalog -CatalogPath 'memory-only.json' -ModelSlug 'unknown-model' -InputModalities @('text')
        Assert-True (-not $Success) 'Unavailable bundled catalog must fail'
        Assert-True ($null -eq $script:CatalogText) 'Failure must not write a partial catalog'
    }
    Test-Case 'host identity guard accepts the pinned root host' {
        $Result = Invoke-HostGuardCase 'absent'
        Assert-Equal $Result.ExitCode 0 "Root host verification: $($Result.Output)"
    }
    Test-Case 'host identity guard accepts an identical resource host' {
        $Result = Invoke-HostGuardCase 'same'
        Assert-Equal $Result.ExitCode 0 "Matching resource host verification: $($Result.Output)"
    }
    Test-Case 'host identity guard rejects a substituted resource host with exit 3' {
        $Result = Invoke-HostGuardCase 'different'
        Assert-Equal $Result.ExitCode 3 "Resource host substitution must be rejected: $($Result.Output)"
    }

    if (-not [string]::IsNullOrWhiteSpace($BundledModelsPath)) {
        $RealModels = [System.IO.File]::ReadAllText(
            (Resolve-Path -LiteralPath $BundledModelsPath).Path,
            [System.Text.Encoding]::UTF8
        ) | ConvertFrom-Json
        Test-Case 'pinned client export supports known and unknown model overrides' {
            Assert-True (@($RealModels.models).Count -gt 0) 'Bundled export is empty'
            foreach ($Slug in @([string]$RealModels.models[0].slug, 'portable-test-unknown-model')) {
                Set-TestModels $RealModels
                $Success = Ensure-ModelCatalog -CatalogPath 'memory-only.json' -ModelSlug $Slug -InputModalities @('text') -ContextWindow 524288
                Assert-True $Success "Real bundled export failed for $Slug"
                $Entry = ($script:CatalogText | ConvertFrom-Json).models[0]
                Assert-Equal $Entry.slug $Slug 'Real export slug'
                Assert-Equal $Entry.max_context_window 524288 'Real export context override'
                Assert-Equal (@($Entry.input_modalities) -join ',') 'text' 'Real export modality override'
                Assert-True (-not [string]::IsNullOrWhiteSpace($Entry.base_instructions)) 'Real export must retain usable instructions'
            }
        }
        Test-Case 'official reasoning menu uses the pinned client export' {
            Set-TestModels $RealModels
            $env:CODEX_PROVIDER_MODE = 'official_chatgpt'
            $Luna = @($RealModels.models | Where-Object { $_.slug -eq 'gpt-6-luna' })[0]
            Assert-True ($null -ne $Luna) 'Pinned export must contain Luna'
            $Menu = Get-ModelReasoningMenuInfo 'gpt-6-luna'
            Assert-Equal $Menu.Default $Luna.default_reasoning_level 'Use catalog reasoning default'
            Assert-Equal ($Menu.Levels -join ',') ((@($Luna.supported_reasoning_levels | ForEach-Object { $_.effort })) -join ',') 'Use catalog supported levels'
        }
    } else {
        Write-Output 'SKIP 2 pinned-client export cases: pass -BundledModelsPath to enable them.'
    }
    Write-Output ("Passed {0} configuration cases. Windows runtime behavior is not exercised." -f $script:Passed)
} finally {
    $env:CODEX_PROVIDER_MODE = $SavedProviderMode
    $env:CODEX_MODEL_CATALOG_JSON = $SavedCatalogPath
}
