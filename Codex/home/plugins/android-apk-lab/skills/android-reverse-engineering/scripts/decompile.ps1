# decompile.ps1 — Decompile APK/XAPK/JAR/AAR using jadx, fernflower, or both
param(
    [Alias('o')]
    [string]$Output,
    [switch]$Deobf,
    [switch]$NoRes,
    [string]$Engine = 'jadx',
    [Parameter(Position=0)]
    [string]$InputFile,
    [Alias('h')]
    [switch]$Help
)

$ErrorActionPreference = 'Stop'

# APK Lab portable guard: inputs/outputs stay under the Codex package root.
function Test-CodexPortableRootCandidate([string]$Candidate) {
    if ([string]::IsNullOrWhiteSpace($Candidate)) { return $null }
    try { $full = [IO.Path]::GetFullPath($Candidate).TrimEnd('\') } catch { return $null }
    if (-not ((Test-Path -LiteralPath (Join-Path $full 'codex.exe') -PathType Leaf) -and
        (Test-Path -LiteralPath (Join-Path $full 'env.ps1') -PathType Leaf))) { return $null }
    try { $rootItem = Get-Item -LiteralPath $full -Force -ErrorAction Stop } catch { return $null }
    if (($rootItem.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) { return $null }
    $scriptFull = [IO.Path]::GetFullPath($PSScriptRoot).TrimEnd('\')
    if (-not ($scriptFull.Equals($full,[StringComparison]::OrdinalIgnoreCase) -or
        $scriptFull.StartsWith($full + '\',[StringComparison]::OrdinalIgnoreCase))) { return $null }
    $walk = $full
    foreach ($part in @($scriptFull.Substring($full.Length).TrimStart('\') -split '\\')) {
        if ([string]::IsNullOrWhiteSpace($part)) { continue }
        $walk = Join-Path $walk $part
        if (Test-Path -LiteralPath $walk) {
            $item = Get-Item -LiteralPath $walk -Force -ErrorAction Stop
            if (($item.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) { return $null }
        }
    }
    return $full
}
function Find-CodexPortableRoot([string]$StartDirectory) {
    $current = [IO.Path]::GetFullPath($StartDirectory).TrimEnd('\')
    for ($depth = 0; $depth -lt 8; $depth++) {
        $valid = Test-CodexPortableRootCandidate $current
        if ($valid) { return $valid }
        $parent = Split-Path -Parent $current
        if ([string]::IsNullOrWhiteSpace($parent) -or $parent -eq $current) { break }
        $current = $parent
    }
    throw "Unable to locate Codex Portable root from: $StartDirectory"
}

# 便携根只从当前脚本位置向上寻找最近匹配项，不信任外部 CODEX_INSTALL_DIR/CODEX_HOME。
$Root = Find-CodexPortableRoot $PSScriptRoot
$env:CODEX_INSTALL_DIR = $Root

function Resolve-ApkLabPortablePath([string]$Path) {
    if ([string]::IsNullOrWhiteSpace($Path)) { throw 'Path is required.' }
    $full = [IO.Path]::GetFullPath($Path).TrimEnd('\')
    if ($full.Equals($Root, [StringComparison]::OrdinalIgnoreCase)) { return $full }
    if (-not $full.StartsWith($Root + '\', [StringComparison]::OrdinalIgnoreCase)) { throw "Path escapes portable package: $Path" }
    $current = $Root
    $relative = $full.Substring(($Root + '\').Length)
    foreach ($segment in @($relative -split '\\')) {
        if ([string]::IsNullOrWhiteSpace($segment)) { continue }
        $current = Join-Path $current $segment
        if (Test-Path -LiteralPath $current) {
            $item = Get-Item -LiteralPath $current -Force
            if (($item.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) { throw "Reparse point escape risk: $current" }
        }
    }
    return $full
}

function Assert-ApkLabSingleLinkRegularFile([string]$Path,[string]$Label) {
    $full = Resolve-ApkLabPortablePath $Path
    if (-not (Test-Path -LiteralPath $full -PathType Leaf)) { throw "Missing $Label: $full" }
    $item = Get-Item -LiteralPath $full -Force -ErrorAction Stop
    if (($item.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) { throw "Refusing reparse-point $Label: $full" }
    $linkTypeProperty = $item.PSObject.Properties['LinkType']
    $linkType = if ($null -ne $linkTypeProperty) { [string]$linkTypeProperty.Value } else { '' }
    if ($linkType -eq 'HardLink' -or ([string]$item.Mode).Contains('l')) { throw "Refusing hardlink/link $Label: $full" }
    return $full
}

function Get-ApkLabTreeEntries([string]$TreePath) {
    $tree = Resolve-ApkLabPortablePath $TreePath
    if (-not (Test-Path -LiteralPath $tree -PathType Container)) { return @() }
    $result = New-Object 'System.Collections.Generic.List[object]'
    $pending = New-Object 'System.Collections.Generic.Stack[string]'
    $pending.Push($tree)
    while ($pending.Count -gt 0) {
        $dir = $pending.Pop()
        $dirItem = Get-Item -LiteralPath $dir -Force -ErrorAction Stop
        if (($dirItem.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) { throw "Refusing reparse point in APK Lab tree: $dir" }
        foreach ($entry in @(Get-ChildItem -LiteralPath $dir -Force -ErrorAction Stop)) {
            if (($entry.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) { throw "Refusing reparse point in APK Lab tree: $($entry.FullName)" }
            $linkTypeProperty = $entry.PSObject.Properties['LinkType']
            if ($null -ne $linkTypeProperty -and [string]$linkTypeProperty.Value -eq 'HardLink') { throw "Refusing hard link in APK Lab tree: $($entry.FullName)" }
            [void](Resolve-ApkLabPortablePath $entry.FullName)
            [void]$result.Add($entry)
            if ($entry.PSIsContainer) { $pending.Push($entry.FullName) }
        }
    }
    return @($result)
}
function Get-ApkLabTreeFiles([string]$TreePath) {
    return @(Get-ApkLabTreeEntries $TreePath | Where-Object { -not $_.PSIsContainer })
}
function Get-ApkLabTreeDirectories([string]$TreePath) {
    return @(Get-ApkLabTreeEntries $TreePath | Where-Object { $_.PSIsContainer })
}
function Remove-ApkLabTree([string]$TreePath) {
    $tree = Resolve-ApkLabPortablePath $TreePath
    if (-not (Test-Path -LiteralPath $tree)) { return }
    $rootItem = Get-Item -LiteralPath $tree -Force -ErrorAction Stop
    if (($rootItem.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) { throw "Refusing to delete reparse point: $tree" }
    if (-not $rootItem.PSIsContainer) { Remove-Item -LiteralPath $tree -Force -ErrorAction Stop; return }
    $entries = @(Get-ApkLabTreeEntries $tree)
    foreach ($file in @($entries | Where-Object { -not $_.PSIsContainer })) { Remove-Item -LiteralPath $file.FullName -Force -ErrorAction Stop }
    foreach ($dir in @($entries | Where-Object { $_.PSIsContainer } | Sort-Object { $_.FullName.Length } -Descending)) { Remove-Item -LiteralPath $dir.FullName -Force -ErrorAction Stop }
    Remove-Item -LiteralPath $tree -Force -ErrorAction Stop
}

function Copy-ApkLabFileCreateNew([string]$SourcePath, [string]$DestinationPath) {
    $source = Resolve-ApkLabPortablePath $SourcePath
    if (-not (Test-Path -LiteralPath $source -PathType Leaf)) { throw "Source file is missing: $source" }
    $dest = Resolve-ApkLabPortablePath $DestinationPath
    $parent = Resolve-ApkLabPortablePath (Split-Path -Parent $dest)
    New-Item -ItemType Directory -Force -Path $parent | Out-Null
    [void](Resolve-ApkLabPortablePath $parent)
    if (Test-Path -LiteralPath $dest) { throw "Refusing pre-existing copy target: $dest" }
    $input = $null; $output = $null
    try {
        $input = [IO.File]::Open($source, [IO.FileMode]::Open, [IO.FileAccess]::Read, [IO.FileShare]::Read)
        $output = [IO.File]::Open($dest, [IO.FileMode]::CreateNew, [IO.FileAccess]::Write, [IO.FileShare]::None)
        $input.CopyTo($output)
    } finally {
        if ($null -ne $output) { $output.Dispose() }
        if ($null -ne $input) { $input.Dispose() }
    }
    return $dest
}

function Install-ApkLabStagedTree([string]$StagePath, [string]$DestinationPath) {
    $stage = Resolve-ApkLabPortablePath $StagePath
    if (-not (Test-Path -LiteralPath $stage -PathType Container)) { throw "Staging directory is missing: $stage" }
    [void](Get-ApkLabTreeEntries $stage)

    $dest = Resolve-ApkLabPortablePath $DestinationPath
    $parent = Split-Path -Parent $dest
    if ([string]::IsNullOrWhiteSpace($parent)) { throw "Invalid output parent: $DestinationPath" }
    $parent = Resolve-ApkLabPortablePath $parent
    New-Item -ItemType Directory -Force -Path $parent | Out-Null
    [void](Resolve-ApkLabPortablePath $parent)

    if (Test-Path -LiteralPath $dest) { Remove-ApkLabTree $dest }
    Move-Item -LiteralPath $stage -Destination $dest -ErrorAction Stop
    [void](Resolve-ApkLabPortablePath $dest)
    [void](Get-ApkLabTreeEntries $dest)
    return $dest
}

$PortableHome = Resolve-ApkLabPortablePath (Join-Path $Root 'home-runtime')
$PortableAppData = Resolve-ApkLabPortablePath (Join-Path $Root 'appdata')
$PortableLocalAppData = Resolve-ApkLabPortablePath (Join-Path $Root 'localappdata')
$env:TEMP = Resolve-ApkLabPortablePath (Join-Path $Root 'tmp')
$env:TMP = $env:TEMP
$env:TMPDIR = $env:TEMP
$env:HOME = $PortableHome
$env:USERPROFILE = $PortableHome
$env:APPDATA = $PortableAppData
$env:LOCALAPPDATA = $PortableLocalAppData
$env:JAVA_HOME = Resolve-ApkLabPortablePath (Join-Path $Root 'tool\android\jdk')
# Decompilation is offline and must not inherit host credentials, proxies, code-loading or Git/Java injection.
$apkScrub = @(
    'OPENAI_API_KEY','CODEX_API_KEY','ANTHROPIC_API_KEY','AZURE_OPENAI_API_KEY','GOOGLE_API_KEY','GEMINI_API_KEY','GOOGLE_APPLICATION_CREDENTIALS',
    'AWS_ACCESS_KEY_ID','AWS_SECRET_ACCESS_KEY','AWS_SESSION_TOKEN','AWS_SECURITY_TOKEN','AWS_WEB_IDENTITY_TOKEN_FILE',
    'AZURE_CLIENT_ID','AZURE_CLIENT_SECRET','AZURE_TENANT_ID','AZURE_FEDERATED_TOKEN_FILE','GITHUB_TOKEN','GH_TOKEN','NPM_TOKEN','NODE_AUTH_TOKEN','PYPI_TOKEN','TWINE_PASSWORD','HF_TOKEN','HUGGINGFACEHUB_API_TOKEN','CLOUDFLARE_API_TOKEN',
    'PYTHONPATH','PYTHONHOME','PYTHONSTARTUP','NODE_OPTIONS','NODE_PATH','NODE_EXTRA_CA_CERTS','JAVA_TOOL_OPTIONS','JDK_JAVA_OPTIONS','_JAVA_OPTIONS','CLASSPATH',
    'BASH_ENV','ENV','CDPATH','RUBYOPT','RUBYLIB','PERL5OPT','PERL5LIB','LD_PRELOAD','LD_LIBRARY_PATH','DYLD_INSERT_LIBRARIES','DYLD_LIBRARY_PATH',
    'SSL_CERT_FILE','SSL_CERT_DIR','REQUESTS_CA_BUNDLE','CURL_CA_BUNDLE','HTTP_PROXY','HTTPS_PROXY','ALL_PROXY','NO_PROXY','http_proxy','https_proxy','all_proxy','no_proxy',
    'SSH_AUTH_SOCK','SSH_AGENT_PID','GPG_AGENT_INFO'
)
foreach ($name in $apkScrub) { Remove-Item ("Env:" + $name) -ErrorAction SilentlyContinue }
Get-ChildItem Env: | Where-Object { $_.Name -match '^(?i:GIT_)' -or $_.Name -match '(?i)(^|_)(API_?KEY|ACCESS_?TOKEN|AUTH_?TOKEN|SECRET|PASSWORD|CREDENTIALS?)($|_)' } | ForEach-Object { Remove-Item ("Env:" + $_.Name) -ErrorAction SilentlyContinue }
$env:GIT_CONFIG_NOSYSTEM = '1'
$portableToolPathParts = @(
    (Resolve-ApkLabPortablePath (Join-Path $Root 'tool\bin')),
    (Resolve-ApkLabPortablePath (Join-Path $Root 'tool\python')),
    (Resolve-ApkLabPortablePath (Join-Path $Root 'tool\python\Scripts')),
    (Resolve-ApkLabPortablePath (Join-Path $Root 'tool\android\jdk\bin')),
    (Resolve-ApkLabPortablePath (Join-Path $Root 'tool\android\jadx\bin')),
    (Resolve-ApkLabPortablePath (Join-Path $Root 'tool\android\dex2jar')),
    (Resolve-ApkLabPortablePath (Join-Path $Root 'tool\android\apktool'))
)
$portablePathParts = @(
    $portableToolPathParts + @(
        (Join-Path $env:SystemRoot 'System32'),
        $env:SystemRoot,
        (Join-Path $env:SystemRoot 'System32\WindowsPowerShell\v1.0'),
        (Join-Path $env:SystemRoot 'System32\Wbem')
    )
)
# Android reverse-engineering helpers never append the host PATH; provision dependencies under tool\android.
$env:CODEX_PORTABLE_ALLOW_HOST_PATH = 'false'
$env:PATH = ($portablePathParts | Where-Object { -not [string]::IsNullOrWhiteSpace($_) } | Select-Object -Unique) -join ';'
foreach ($dir in @($env:TEMP,$PortableHome,$PortableAppData,$PortableLocalAppData)) { New-Item -ItemType Directory -Force -Path $dir | Out-Null }

Add-Type -AssemblyName System.IO.Compression

function Expand-ZipArchiveSafe {
    param(
        [Parameter(Mandatory=$true)][string]$ArchivePath,
        [Parameter(Mandatory=$true)][string]$DestinationPath,
        [int]$MaxEntries = 50000,
        [long]$MaxEntryBytes = 2GB,
        [long]$MaxTotalBytes = 4GB
    )
    $archiveFull = Assert-ApkLabSingleLinkRegularFile $ArchivePath 'archive input'
    $destRoot = Resolve-ApkLabPortablePath $DestinationPath
    New-Item -ItemType Directory -Force -Path $destRoot | Out-Null
    $destRoot = Resolve-ApkLabPortablePath $destRoot
    [void](Get-ApkLabTreeEntries $destRoot)
    $stream = $null
    $archive = $null
    try {
        $stream = [IO.File]::Open($archiveFull, [IO.FileMode]::Open, [IO.FileAccess]::Read, [IO.FileShare]::Read)
        $archive = New-Object IO.Compression.ZipArchive($stream, [IO.Compression.ZipArchiveMode]::Read, $false)
        if ($archive.Entries.Count -gt $MaxEntries) { throw "Archive has too many entries: $($archive.Entries.Count)" }
        [long]$total = 0
        $seenArchiveTargets = @{}
        foreach ($entry in $archive.Entries) {
            $rawEntryName = [string]$entry.FullName
            if ([string]::IsNullOrWhiteSpace($rawEntryName)) { continue }
            if ($rawEntryName.Contains('\') -or $rawEntryName.StartsWith('/') -or $rawEntryName -match '^[A-Za-z]:') { throw "Unsafe archive entry: $rawEntryName" }
            $nameParts = @($rawEntryName -split '/')
            foreach ($namePart in $nameParts) {
                if ([string]::IsNullOrWhiteSpace($namePart)) { continue }
                if ($namePart -eq '..' -or $namePart.Contains(':') -or $namePart -match '[\x00-\x1F]' -or $namePart -match '[. ]$') { throw "Windows-unsafe archive entry: $rawEntryName" }
                $baseName = (($namePart -split '\.')[0]).ToUpperInvariant()
                if ($baseName -in @('CON','PRN','AUX','NUL','COM1','COM2','COM3','COM4','COM5','COM6','COM7','COM8','COM9','LPT1','LPT2','LPT3','LPT4','LPT5','LPT6','LPT7','LPT8','LPT9','CLOCK$','CONIN$','CONOUT$')) { throw "Windows-reserved archive entry: $rawEntryName" }
            }
            $unixType = (($entry.ExternalAttributes -shr 16) -band 0xF000)
            if ($unixType -eq 0xA000) { throw "Symlink archive entry is not allowed: $rawEntryName" }
            $entryName = $rawEntryName.Replace('/', '\')
            if ($rawEntryName.Length -gt 4096) { throw "Archive entry name is too long" }
            $entryKey = $entryName.TrimEnd('\').Normalize([Text.NormalizationForm]::FormC).ToLowerInvariant()
            if ($seenArchiveTargets.ContainsKey($entryKey)) { throw "Case-insensitive/Unicode archive path collision: $rawEntryName" }
            $seenArchiveTargets[$entryKey] = $true
            if ([long]$entry.Length -gt $MaxEntryBytes) { throw "Archive entry too large: $rawEntryName" }
            if ([long]$entry.Length -gt 16MB -and [long]$entry.CompressedLength -gt 0 -and [long]$entry.Length -gt ([long]$entry.CompressedLength * 250L)) { throw "Archive entry compression ratio is unsafe: $rawEntryName" }
            $total += [long]$entry.Length
            if ($total -gt $MaxTotalBytes) { throw "Archive expanded size exceeds limit." }
            $dest = [IO.Path]::GetFullPath((Join-Path $destRoot $entryName)).TrimEnd('\')
            if (-not ($dest.Equals($destRoot, [StringComparison]::OrdinalIgnoreCase) -or $dest.StartsWith($destRoot + '\', [StringComparison]::OrdinalIgnoreCase))) {
                throw "Archive entry escapes destination: $($entry.FullName)"
            }
            if ([string]::IsNullOrEmpty($entry.Name)) {
                $destParent = Resolve-ApkLabPortablePath (Split-Path -Parent $dest)
                New-Item -ItemType Directory -Force -Path $destParent | Out-Null
                [void](Resolve-ApkLabPortablePath $destParent)
                if (Test-Path -LiteralPath $dest) {
                    $existingDir = Get-Item -LiteralPath $dest -Force -ErrorAction Stop
                    if (-not $existingDir.PSIsContainer -or (($existingDir.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0)) { throw "Unsafe pre-existing archive directory target: $dest" }
                } else {
                    New-Item -ItemType Directory -Path $dest | Out-Null
                }
                [void](Resolve-ApkLabPortablePath $dest)
                continue
            }
            $destParent = Resolve-ApkLabPortablePath (Split-Path -Parent $dest)
            New-Item -ItemType Directory -Force -Path $destParent | Out-Null
            [void](Resolve-ApkLabPortablePath $destParent)
            if (Test-Path -LiteralPath $dest) { throw "Refusing to overwrite pre-existing archive target: $dest" }
            $input = $null
            $output = $null
            try {
                $input = $entry.Open()
                $output = [IO.File]::Open($dest, [IO.FileMode]::CreateNew, [IO.FileAccess]::Write, [IO.FileShare]::None)
                $buffer = New-Object byte[] (1024 * 1024)
                [long]$copied = 0
                while (($read = $input.Read($buffer, 0, $buffer.Length)) -gt 0) {
                    $copied += [long]$read
                    if ($copied -gt $MaxEntryBytes -or $copied -gt ([long]$entry.Length + 1MB)) { throw "Archive entry expanded beyond declared safe size: $rawEntryName" }
                    $output.Write($buffer, 0, $read)
                }
            } finally {
                if ($null -ne $output) { $output.Dispose() }
                if ($null -ne $input) { $input.Dispose() }
            }
        }
    } finally {
        if ($null -ne $archive) { $archive.Dispose() }
        if ($null -ne $stream) { $stream.Dispose() }
    }
}

function Show-Usage {
    Write-Host @"
Usage: decompile.ps1 [OPTIONS] <file>

Decompile an Android APK, XAPK, JAR, or AAR file.

Arguments:
  <file>            Path to the .apk, .xapk, .jar, or .aar file

Options:
  -Output DIR       Output directory (default: <filename>-decompiled)
  -Deobf            Enable deobfuscation of names
  -NoRes            Skip resource decoding (faster, code-only)
  -Engine ENGINE    Decompiler engine: jadx, fernflower, or both (default: jadx)
  -Help             Show this help message

Engines:
  jadx        Use jadx (default). Handles APK/JAR/AAR natively, decodes resources.
  fernflower  Use Fernflower/Vineflower. Better on complex Java, lambdas, generics.
              For APK files, requires dex2jar as intermediate step.
  both        Run both decompilers side by side for comparison.
              jadx output  -> <output>/jadx/
              fernflower   -> <output>/fernflower/

Environment:
  FERNFLOWER_JAR_PATH   Path to fernflower.jar or vineflower.jar

Examples:
  .\decompile.ps1 app-release.apk
  .\decompile.ps1 app-bundle.xapk
  .\decompile.ps1 -Engine both -Deobf app-release.apk
  .\decompile.ps1 -Engine fernflower library.jar
"@
    exit 0
}

if ($Help) { Show-Usage }

# --- Validate input ---
if (-not $InputFile) {
    Write-Host "Error: No input file specified." -ForegroundColor Red
    Show-Usage
}

if (-not (Test-Path -LiteralPath $InputFile)) {
    Write-Host "Error: File not found: $InputFile" -ForegroundColor Red
    exit 1
}

$extLower = [IO.Path]::GetExtension($InputFile).TrimStart('.').ToLower()
if ($extLower -notin @('apk', 'xapk', 'jar', 'aar')) {
    Write-Host "Error: Unsupported file type '.$extLower'. Expected .apk, .xapk, .jar, or .aar" -ForegroundColor Red
    exit 1
}

if ($Engine -notin @('jadx', 'fernflower', 'both')) {
    Write-Host "Error: Unknown engine '$Engine'. Use jadx, fernflower, or both." -ForegroundColor Red
    exit 1
}

$baseName = [IO.Path]::GetFileNameWithoutExtension($InputFile)
$inputFileAbs = Assert-ApkLabSingleLinkRegularFile ((Resolve-Path -LiteralPath $InputFile).Path) 'decompile input'

if (-not $Output) {
    $Output = Join-Path (Join-Path $Root 'work\apk-jobs\manual') "$baseName-decompiled"
}

# --- XAPK handling ---
$xapkExtractedDir = $null
$xapkApkFiles = @()

if ($extLower -eq 'xapk') {
    $xapkExtractedDir = Join-Path $env:TEMP ("xapk-extract-{0}" -f ([Guid]::NewGuid().ToString("N")))
    Write-Host "=== Extracting XAPK archive ==="
    New-Item -ItemType Directory -Path $xapkExtractedDir -Force | Out-Null
    Expand-ZipArchiveSafe -ArchivePath $inputFileAbs -DestinationPath $xapkExtractedDir

    # Show manifest.json if present
    $manifestPath = Join-Path $xapkExtractedDir 'manifest.json'
    if (Test-Path -LiteralPath $manifestPath) {
        Write-Host "XAPK manifest found:"
        Get-Content $manifestPath
        Write-Host ""
    }

    # Find all APK files inside
    $xapkApkFiles = @(Get-ApkLabTreeFiles $xapkExtractedDir | Where-Object { $_.Extension -ieq '.apk' } | Sort-Object Name)

    if ($xapkApkFiles.Count -eq 0) {
        Write-Host "Error: No APK files found inside XAPK archive." -ForegroundColor Red
        Remove-ApkLabTree $xapkExtractedDir
        exit 1
    }

    Write-Host "Found $($xapkApkFiles.Count) APK(s) inside XAPK:"
    foreach ($f in $xapkApkFiles) {
        Write-Host "  - $($f.Name)"
    }
    Write-Host ""
}

# --- Locate fernflower JAR ---
function Find-FernflowerJar {
    if ($env:FERNFLOWER_JAR_PATH) {
        try {
            $configured = Resolve-ApkLabPortablePath $env:FERNFLOWER_JAR_PATH
            if (Test-Path -LiteralPath $configured -PathType Leaf) { return $configured }
        } catch {
            Write-Host "Ignoring FERNFLOWER_JAR_PATH outside portable package." -ForegroundColor Yellow
        }
    }
    $candidates = @(
        (Join-Path $Root 'tool\android\vineflower\vineflower.jar'),
        (Join-Path $Root 'tool\android\vineflower\fernflower.jar'),
        (Join-Path $Root 'tool\android\fernflower\fernflower.jar'),
        (Join-Path $Root 'tool\android\fernflower\vineflower.jar')
    )
    foreach ($candidate in $candidates) {
        try { $candidate = Resolve-ApkLabPortablePath $candidate } catch { continue }
        if (Test-Path -LiteralPath $candidate -PathType Leaf) { return $candidate }
    }
    return $null
}

# --- Locate dex2jar ---
function Find-Dex2Jar {
    foreach ($candidate in @(
        (Join-Path $Root 'tool\android\dex2jar\d2j-dex2jar.bat'),
        (Join-Path $Root 'tool\android\dex2jar\d2j-dex2jar.cmd'),
        (Join-Path $Root 'tool\android\dex2jar\d2j-dex2jar')
    )) {
        try { $candidate = Resolve-ApkLabPortablePath $candidate } catch { continue }
        if (Test-Path -LiteralPath $candidate -PathType Leaf) { return $candidate }
    }
    $cmd = Get-Command d2j-dex2jar -ErrorAction SilentlyContinue
    if ($cmd) {
        try { return Resolve-ApkLabPortablePath $cmd.Source } catch {}
    }
    $cmd = Get-Command d2j-dex2jar.bat -ErrorAction SilentlyContinue
    if ($cmd) {
        try { return Resolve-ApkLabPortablePath $cmd.Source } catch {}
    }
    return $null
}

# --- jadx decompilation ---
function Invoke-Jadx {
    param([string]$OutDir, [string]$FileAbs, [string]$FileExt)

    $jadxCommand = Get-Command jadx -ErrorAction SilentlyContinue
    if (-not $jadxCommand) {
        Write-Host "Error: portable jadx is not installed or not in PATH." -ForegroundColor Red
        return $false
    }
    try { $jadxExecutable = Assert-ApkLabSingleLinkRegularFile $jadxCommand.Source 'jadx launcher' } catch {
        Write-Host "Error: refusing unsafe/non-portable jadx: $($jadxCommand.Source)" -ForegroundColor Red
        return $false
    }

    $OutDir = Resolve-ApkLabPortablePath $OutDir
    $outParent = Resolve-ApkLabPortablePath (Split-Path -Parent $OutDir)
    New-Item -ItemType Directory -Force -Path $outParent | Out-Null
    [void](Resolve-ApkLabPortablePath $outParent)
    $stageOut = Resolve-ApkLabPortablePath (Join-Path $env:TEMP ("jadx-output-{0}" -f ([Guid]::NewGuid().ToString('N'))))
    New-Item -ItemType Directory -Path $stageOut | Out-Null
    try {
        $jadxArgs = @('-d', $stageOut)
        if ($Deobf) { $jadxArgs += '--deobf' }
        if ($NoRes) { $jadxArgs += '--no-res' }
        $jadxArgs += '--show-bad-code'
        $jadxArgs += $FileAbs

        Write-Host "Running: jadx $($jadxArgs -join ' ')"
        & $jadxExecutable @jadxArgs
        $jadxExit = $LASTEXITCODE
        if ($jadxExit -ne 0) {
            Write-Host "Error: jadx failed with exit code $jadxExit." -ForegroundColor Red
            return $false
        }

        # The decompiler is an external process. Never let it write into an
        # attacker-prepopulated final tree: validate its fresh staging tree first.
        [void](Get-ApkLabTreeEntries $stageOut)
        [void](Install-ApkLabStagedTree -StagePath $stageOut -DestinationPath $OutDir)
        $stageOut = $null

        $sourcesDir = Join-Path $OutDir 'sources'
        if (Test-Path -LiteralPath $sourcesDir) {
            $count = @(Get-ApkLabTreeFiles $sourcesDir | Where-Object { $_.Extension -ieq '.java' }).Count
            Write-Host "jadx output: $sourcesDir\"
            Write-Host "Java files decompiled by jadx: $count"
        }
        return $true
    } finally {
        if ($stageOut -and (Test-Path -LiteralPath $stageOut)) { Remove-ApkLabTree $stageOut }
    }
}

# --- Fernflower decompilation ---
function Invoke-Fernflower {
    param([string]$OutDir, [string]$FileAbs, [string]$FileExt)

    $ffJar = Find-FernflowerJar
    if (-not $ffJar) {
        Write-Host "Error: portable Fernflower/Vineflower JAR not found." -ForegroundColor Red
        Write-Host "Place it under tool\android\vineflower or tool\android\fernflower."
        return $false
    }
    try { $ffJar = Assert-ApkLabSingleLinkRegularFile $ffJar 'Fernflower/Vineflower JAR' } catch {
        Write-Host "Error: refusing unsafe Fernflower/Vineflower JAR: $($_.Exception.Message)" -ForegroundColor Red
        return $false
    }

    $java = Resolve-ApkLabPortablePath (Join-Path $Root 'tool\android\jdk\bin\java.exe')
    try { $java = Assert-ApkLabSingleLinkRegularFile $java 'portable Java' } catch {
        Write-Host "Error: refusing missing/unsafe portable Java: $($_.Exception.Message)" -ForegroundColor Red
        return $false
    }

    $OutDir = Resolve-ApkLabPortablePath $OutDir
    $outParent = Resolve-ApkLabPortablePath (Split-Path -Parent $OutDir)
    New-Item -ItemType Directory -Force -Path $outParent | Out-Null
    [void](Resolve-ApkLabPortablePath $outParent)

    $stageDir = Resolve-ApkLabPortablePath (Join-Path $env:TEMP ("fernflower-stage-{0}" -f ([Guid]::NewGuid().ToString('N'))))
    New-Item -ItemType Directory -Path $stageDir | Out-Null
    $stageOut = Resolve-ApkLabPortablePath (Join-Path $stageDir 'output')
    New-Item -ItemType Directory -Path $stageOut | Out-Null
    try {
        $jarToDecompile = $FileAbs

        if ($FileExt -eq 'apk') {
            $d2j = Find-Dex2Jar
            if (-not $d2j) {
                Write-Host "Error: portable dex2jar is required to use Fernflower on APK files." -ForegroundColor Red
                return $false
            }
            try { $d2j = Assert-ApkLabSingleLinkRegularFile $d2j 'dex2jar launcher' } catch {
                Write-Host "Error: refusing unsafe dex2jar launcher: $($_.Exception.Message)" -ForegroundColor Red
                return $false
            }
            Write-Host "Converting APK to JAR with dex2jar..."
            $jarToDecompile = Join-Path $stageDir "$baseName-dex2jar.jar"
            & $d2j -f -o $jarToDecompile $FileAbs 2>&1 | Write-Host
            $d2jExit = $LASTEXITCODE
            if ($d2jExit -ne 0 -or -not (Test-Path -LiteralPath $jarToDecompile -PathType Leaf)) {
                Write-Host "Error: dex2jar conversion failed with exit code $d2jExit." -ForegroundColor Red
                return $false
            }
            $jarToDecompile = Resolve-ApkLabPortablePath $jarToDecompile
        } elseif ($FileExt -eq 'aar') {
            $aarStage = Join-Path $stageDir 'aar'
            New-Item -ItemType Directory -Path $aarStage | Out-Null
            Expand-ZipArchiveSafe -ArchivePath $FileAbs -DestinationPath $aarStage -MaxTotalBytes 4GB
            $classesJar = Resolve-ApkLabPortablePath (Join-Path $aarStage 'classes.jar')
            if (-not (Test-Path -LiteralPath $classesJar -PathType Leaf)) {
                Write-Host "Error: AAR does not contain classes.jar." -ForegroundColor Red
                return $false
            }
            $jarToDecompile = $classesJar
        }

        $ffArgs = @('-dgs=1', '-mpm=60')
        if ($Deobf) { $ffArgs += '-ren=1' }
        $ffArgs += $jarToDecompile
        $ffArgs += $stageOut

        Write-Host "Running: java -jar $ffJar $($ffArgs -join ' ')"
        & $java -jar $ffJar @ffArgs
        $ffExit = $LASTEXITCODE
        if ($ffExit -ne 0) {
            Write-Host "Error: Fernflower/Vineflower failed with exit code $ffExit." -ForegroundColor Red
            return $false
        }

        # Fernflower/Vineflower often writes a JAR with the input basename. Extract
        # that archive only inside the fresh staging tree.
        [void](Get-ApkLabTreeEntries $stageOut)
        $resultJar = Resolve-ApkLabPortablePath (Join-Path $stageOut ([IO.Path]::GetFileName($jarToDecompile)))
        $sourcesDir = Join-Path $stageOut 'sources'
        if (Test-Path -LiteralPath $resultJar -PathType Leaf) {
            New-Item -ItemType Directory -Path $sourcesDir -Force | Out-Null
            Expand-ZipArchiveSafe -ArchivePath $resultJar -DestinationPath $sourcesDir -MaxTotalBytes 4GB
            Remove-Item -LiteralPath $resultJar -Force
        } elseif (-not (Test-Path -LiteralPath $sourcesDir)) {
            $directJava = @(Get-ApkLabTreeFiles $stageOut | Where-Object { $_.Extension -ieq '.java' })
            if ($directJava.Count -eq 0) {
                Write-Host "Error: decompiler exited successfully but produced no Java sources." -ForegroundColor Red
                return $false
            }
            $sourcesDir = $stageOut
        }

        [void](Get-ApkLabTreeEntries $stageOut)
        $count = @(Get-ApkLabTreeFiles $sourcesDir | Where-Object { $_.Extension -ieq '.java' }).Count
        $sourcesWasRoot = ([IO.Path]::GetFullPath($sourcesDir).TrimEnd('\') -eq [IO.Path]::GetFullPath($stageOut).TrimEnd('\'))
        [void](Install-ApkLabStagedTree -StagePath $stageOut -DestinationPath $OutDir)
        $stageOut = $null
        $finalSourcesDir = if ($sourcesWasRoot) { $OutDir } else { Join-Path $OutDir 'sources' }
        Write-Host "Fernflower output: $finalSourcesDir\"
        Write-Host "Java files decompiled by Fernflower: $count"
        return $true
    } finally {
        if (Test-Path -LiteralPath $stageDir) { Remove-ApkLabTree $stageDir }
    }
}

# --- Summary helper ---
function Show-Structure {
    param([string]$SrcDir, [string]$Label)
    if (Test-Path -LiteralPath $SrcDir) {
        Write-Host ""
        Write-Host "Top-level packages ($Label):"
        @(Get-ApkLabTreeDirectories $SrcDir | Where-Object {
            $relative = $_.FullName.Substring(([IO.Path]::GetFullPath($SrcDir).TrimEnd('\') + '\').Length)
            @($relative -split '\\').Count -le 3
        }) | Select-Object -First 20 |
            ForEach-Object { $_.FullName.Replace("$SrcDir\", '') } |
            Sort-Object
    }
}

# --- Decompile a single file ---
function Invoke-DecompileSingle {
    param([string]$FileAbs, [string]$OutDir, [string]$Label)

    $fileExt = [IO.Path]::GetExtension($FileAbs).TrimStart('.').ToLower()

    if ($Label) {
        Write-Host "=== Decompiling $Label (engine: $Engine) ==="
    }

    switch ($Engine) {
        'jadx' {
            if (-not (Invoke-Jadx -OutDir $OutDir -FileAbs $FileAbs -FileExt $fileExt)) { throw 'jadx decompilation failed.' }
            Show-Structure (Join-Path $OutDir 'sources') 'jadx'
        }
        'fernflower' {
            if (-not (Invoke-Fernflower -OutDir $OutDir -FileAbs $FileAbs -FileExt $fileExt)) { throw 'Fernflower/Vineflower decompilation failed.' }
            Show-Structure (Join-Path $OutDir 'sources') 'fernflower'
        }
        'both' {
            Write-Host "--- Pass 1: jadx ---"
            if (-not (Invoke-Jadx -OutDir (Join-Path $OutDir 'jadx') -FileAbs $FileAbs -FileExt $fileExt)) { throw 'jadx decompilation failed.' }
            Write-Host ""
            Write-Host "--- Pass 2: Fernflower ---"
            if (-not (Invoke-Fernflower -OutDir (Join-Path $OutDir 'fernflower') -FileAbs $FileAbs -FileExt $fileExt)) { throw 'Fernflower/Vineflower decompilation failed.' }

            Show-Structure (Join-Path $OutDir 'jadx\sources') 'jadx'
            Show-Structure (Join-Path $OutDir 'fernflower\sources') 'fernflower'

            Write-Host ""
            Write-Host "=== Comparison ==="
            $jadxCount = 0; $ffCount = 0
            $jadxSources = Join-Path $OutDir 'jadx\sources'
            $ffSources   = Join-Path $OutDir 'fernflower\sources'
            if (Test-Path -LiteralPath $jadxSources) {
                $jadxCount = @(Get-ApkLabTreeFiles $jadxSources | Where-Object { $_.Extension -ieq '.java' }).Count
            }
            if (Test-Path -LiteralPath $ffSources) {
                $ffCount = @(Get-ApkLabTreeFiles $ffSources | Where-Object { $_.Extension -ieq '.java' }).Count
            }
            Write-Host "jadx:        $jadxCount Java files"
            Write-Host "Fernflower:  $ffCount Java files"

            if (Test-Path -LiteralPath $jadxSources) {
                $jadxErrors = @(Get-ApkLabTreeFiles $jadxSources | Where-Object { $_.Extension -ieq '.java' } |
                    Select-String -Pattern 'JADX WARNING|JADX WARN|JADX ERROR|Code decompiled incorrectly' -SimpleMatch -ErrorAction SilentlyContinue |
                    Select-Object -ExpandProperty Path -Unique).Count
                Write-Host "jadx files with warnings/errors: $jadxErrors"
            }
            Write-Host ""
            Write-Host "Tip: compare specific classes between jadx/ and fernflower/ to pick the better output."
        }
    }
}

# --- Run ---
Write-Host "=== Decompiling $InputFile (engine: $Engine) ==="
$Output = Resolve-ApkLabPortablePath $Output
Write-Host "Output directory: $Output"
Write-Host ""

# Never reuse an attacker-prepopulated output tree. Reparse/junction and hard-link
# entries are rejected by the explicit tree walk before any staged output is installed.
if (Test-Path -LiteralPath $Output) { Remove-ApkLabTree $Output }

if ($extLower -eq 'xapk') {
    try {
        New-Item -ItemType Directory -Path $Output -Force | Out-Null

        # Copy XAPK manifest for reference
    $manifestSrc = Join-Path $xapkExtractedDir 'manifest.json'
    if (Test-Path -LiteralPath $manifestSrc) {
        [void](Copy-ApkLabFileCreateNew -SourcePath $manifestSrc -DestinationPath (Join-Path $Output 'xapk-manifest.json'))
    }

    # List OBB files
    $obbFiles = @(Get-ApkLabTreeFiles $xapkExtractedDir | Where-Object { $_.Extension -ieq '.obb' })
    if ($obbFiles) {
        Write-Host "OBB files found (not decompiled, data-only):"
        foreach ($obb in $obbFiles) {
            $size = '{0:N1} MB' -f ($obb.Length / 1MB)
            Write-Host "  - $($obb.Name) ($size)"
        }
        Write-Host ""
    }

    foreach ($apkFile in $xapkApkFiles) {
        $apkName = [IO.Path]::GetFileNameWithoutExtension($apkFile.Name)
        Write-Host ""
        Write-Host "======================================================"
        Invoke-DecompileSingle -FileAbs $apkFile.FullName -OutDir (Join-Path $Output $apkName) -Label "$($apkFile.Name)"
    }

        Write-Host ""
        Write-Host "=== XAPK decompilation complete ==="
        Write-Host "Subdirectories in ${Output}\"
        Get-ChildItem -LiteralPath $Output -Directory | ForEach-Object { Write-Host $_.Name }
    } finally {
        if ($xapkExtractedDir -and (Test-Path -LiteralPath $xapkExtractedDir)) {
            Remove-ApkLabTree $xapkExtractedDir
        }
    }
} else {
    Invoke-DecompileSingle -FileAbs $inputFileAbs -OutDir $Output -Label ''

    # --- Split/bundled APK detection ---
    # Some APKs are bundles: the outer APK contains
    # base.apk + split_config.*.apk inside the resources directory. jadx will
    # decompile the thin outer wrapper and produce very few Java files.
    # Detect this and automatically decompile the inner base.apk.
    $sourcesDir = Join-Path $Output 'sources'
    $resourcesDir = Join-Path $Output 'resources'
    if ((Test-Path -LiteralPath $sourcesDir) -and (Test-Path -LiteralPath $resourcesDir)) {
        $javaCount = @(Get-ApkLabTreeFiles $sourcesDir | Where-Object { $_.Extension -ieq '.java' }).Count
        # resources 目录本身也必须先过 reparse/包内链校验，再做非递归的直接子项枚举。
        [void](Resolve-ApkLabPortablePath $resourcesDir)
        $innerApks = Get-ChildItem -LiteralPath $resourcesDir -Filter '*.apk' -File -ErrorAction SilentlyContinue
        $baseApk = $innerApks | Where-Object { $_.Name -eq 'base.apk' }

        if ($javaCount -le 10 -and $baseApk) {
            Write-Host ""
            Write-Host "=== Split/bundled APK detected ==="
            Write-Host "Outer APK produced only $javaCount Java file(s) but contains $($innerApks.Count) inner APK(s):"
            foreach ($inner in $innerApks) {
                Write-Host "  - $($inner.Name)"
            }
            Write-Host ""
            Write-Host "Decompiling base.apk (contains the actual app code)..."
            $baseOutput = Join-Path $Output 'base'
            Invoke-DecompileSingle -FileAbs $baseApk.FullName -OutDir $baseOutput -Label 'base.apk'

            # Decompile any split APKs that aren't just config splits
            $splitApks = $innerApks | Where-Object { $_.Name -ne 'base.apk' -and $_.Name -notmatch 'split_config\.' }
            foreach ($split in $splitApks) {
                $splitName = [IO.Path]::GetFileNameWithoutExtension($split.Name)
                Write-Host ""
                Write-Host "Decompiling $($split.Name)..."
                Invoke-DecompileSingle -FileAbs $split.FullName -OutDir (Join-Path $Output $splitName) -Label $split.Name
            }

            if ($innerApks | Where-Object { $_.Name -match 'split_config\.' }) {
                Write-Host ""
                Write-Host "Skipped config splits (resource/ABI only):"
                $innerApks | Where-Object { $_.Name -match 'split_config\.' } | ForEach-Object { Write-Host "  - $($_.Name)" }
            }

            Write-Host ""
            Write-Host "NOTE: The main decompiled source is in: $(Join-Path $Output 'base\sources')"
        }
    }

    Write-Host ""
    Write-Host "=== Decompilation complete ==="
}
