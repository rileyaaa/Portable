# find-api-calls.ps1 — Search decompiled source for API calls and HTTP endpoints
param(
    [Parameter(Position=0)]
    [string]$SourceDir,
    [switch]$Retrofit,
    [switch]$OkHttp,
    [switch]$Volley,
    [switch]$Urls,
    [switch]$Auth,
    [switch]$All,
    [Alias('h')]
    [switch]$Help
)

$ErrorActionPreference = 'Stop'

# Portable guard: this scanner may read many source files, so it must never
# recurse outside the Codex package (including through a junction/reparse point).
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
            $item = Get-Item -LiteralPath $current -Force -ErrorAction Stop
            if (($item.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) { throw "Reparse point escape risk: $current" }
        }
    }
    return $full
}

function Get-ApkLabSafeSourceFiles([string]$TreePath) {
    $tree = Resolve-ApkLabPortablePath $TreePath
    $result = New-Object 'System.Collections.Generic.List[object]'
    $pending = New-Object 'System.Collections.Generic.Stack[string]'
    $pending.Push($tree)
    while ($pending.Count -gt 0) {
        $dir = $pending.Pop()
        $dirItem = Get-Item -LiteralPath $dir -Force -ErrorAction Stop
        if (($dirItem.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) { throw "Refusing source-tree reparse point: $dir" }
        foreach ($entry in @(Get-ChildItem -LiteralPath $dir -Force -ErrorAction Stop)) {
            if (($entry.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) { throw "Refusing source-tree reparse point: $($entry.FullName)" }
            [void](Resolve-ApkLabPortablePath $entry.FullName)
            if ($entry.PSIsContainer) { $pending.Push($entry.FullName) }
            else {
                $linkTypeProperty = $entry.PSObject.Properties['LinkType']
                $linkType = if ($null -ne $linkTypeProperty) { [string]$linkTypeProperty.Value } else { '' }
                if ($linkType -eq 'HardLink' -or ([string]$entry.Mode).Contains('l')) { throw "Refusing hardlink/link source file: $($entry.FullName)" }
                if ($entry.Extension -in @('.java','.kt')) { [void]$result.Add($entry) }
            }
        }
    }
    return @($result)
}

$Root = Find-CodexPortableRoot $PSScriptRoot
$env:CODEX_INSTALL_DIR = $Root
$env:TEMP = Resolve-ApkLabPortablePath (Join-Path $Root 'tmp')
$env:TMP = $env:TEMP
$env:TMPDIR = $env:TEMP
New-Item -ItemType Directory -Force -Path $env:TEMP | Out-Null

function Show-Usage {
    Write-Host @"
Usage: find-api-calls.ps1 <source-dir> [OPTIONS]

Search decompiled Java/Kotlin source for HTTP API calls and endpoints.

Arguments:
  <source-dir>    Path to the decompiled sources directory

Options:
  -Retrofit       Search only for Retrofit annotations
  -OkHttp         Search only for OkHttp patterns
  -Volley         Search only for Volley patterns
  -Urls           Search only for hardcoded URLs
  -Auth           Search only for auth-related patterns
  -All            Search all patterns (default)
  -Help           Show this help message

Output:
  Results are printed as file:line:match for easy navigation.
"@
    exit 0
}

if ($Help) { Show-Usage }

if (-not $SourceDir) {
    Write-Host "Error: No source directory specified." -ForegroundColor Red
    Show-Usage
}

try { $SourceDir = Resolve-ApkLabPortablePath $SourceDir } catch {
    Write-Host ("Error: " + $_.Exception.Message) -ForegroundColor Red
    exit 1
}
if (-not (Test-Path -LiteralPath $SourceDir -PathType Container)) {
    Write-Host "Error: Directory not found: $SourceDir" -ForegroundColor Red
    exit 1
}
try { $SourceFiles = @(Get-ApkLabSafeSourceFiles $SourceDir) } catch {
    Write-Host ("Error: " + $_.Exception.Message) -ForegroundColor Red
    exit 1
}

# Default to all if no specific flag set
$searchAll = (-not $Retrofit -and -not $OkHttp -and -not $Volley -and -not $Urls -and -not $Auth) -or $All

function Write-Section {
    param([string]$Title)
    Write-Host ""
    Write-Host "==== $Title ===="
    Write-Host ""
}

function Search-Sources {
    param([string]$Pattern)
    $SourceFiles |
        Select-String -Pattern $Pattern -ErrorAction SilentlyContinue |
        ForEach-Object {
            "$($_.Path):$($_.LineNumber):$($_.Line.Trim())"
        }
}

# --- Retrofit ---
if ($searchAll -or $Retrofit) {
    Write-Section "Retrofit Annotations"
    Search-Sources '@(GET|POST|PUT|DELETE|PATCH|HEAD|OPTIONS|HTTP)\s*\('

    Write-Section "Retrofit Headers & Parameters"
    Search-Sources '@(Headers|Header|Query|QueryMap|Path|Body|Field|FieldMap|Part|PartMap|Url)\s*\('

    Write-Section "Retrofit Base URL"
    Search-Sources '(baseUrl|base_url)\s*\('
}

# --- OkHttp ---
if ($searchAll -or $OkHttp) {
    Write-Section "OkHttp Request Building"
    Search-Sources '(Request\.Builder|HttpUrl|\.newCall|\.enqueue|addInterceptor|addNetworkInterceptor)'

    Write-Section "OkHttp URL Construction"
    Search-Sources '(\.url\s*\(|\.addQueryParameter|\.addPathSegment|\.scheme\s*\(|\.host\s*\()'
}

# --- Volley ---
if ($searchAll -or $Volley) {
    Write-Section "Volley Requests"
    Search-Sources '(StringRequest|JsonObjectRequest|JsonArrayRequest|ImageRequest|RequestQueue|Volley\.newRequestQueue)'
}

# --- Hardcoded URLs ---
if ($searchAll -or $Urls) {
    Write-Section "Hardcoded URLs (http:// and https://)"
    Search-Sources '"https?://[^"]+'

    Write-Section "HttpURLConnection"
    Search-Sources '(openConnection|setRequestMethod|HttpURLConnection|HttpsURLConnection)'

    Write-Section "WebView URLs"
    Search-Sources '(loadUrl|loadData|evaluateJavascript|addJavascriptInterface|WebViewClient|WebChromeClient)'
}

# --- Auth patterns ---
if ($searchAll -or $Auth) {
    Write-Section "Authentication & API Keys"
    Search-Sources '(?i)(api[_\-]?key|auth[_\-]?token|bearer|authorization|x-api-key|client[_\-]?secret|access[_\-]?token)'

    Write-Section "Base URLs and Constants"
    Search-Sources '(?i)(BASE_URL|API_URL|SERVER_URL|ENDPOINT|API_BASE|HOST_NAME)'
}

Write-Host ""
Write-Host "=== Search complete ==="
