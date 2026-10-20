param([string]$Path)
$ErrorActionPreference = 'Stop'

function Test-ApkLabRootCandidate([string]$Candidate) {
    if ([string]::IsNullOrWhiteSpace($Candidate)) { return $null }
    try { $full = [IO.Path]::GetFullPath($Candidate).TrimEnd('\') } catch { return $null }
    if (-not ((Test-Path -LiteralPath (Join-Path $full 'codex.exe') -PathType Leaf) -and (Test-Path -LiteralPath (Join-Path $full 'env.ps1') -PathType Leaf))) { return $null }
    try { $rootItem = Get-Item -LiteralPath $full -Force -ErrorAction Stop } catch { return $null }
    if (($rootItem.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) { return $null }
    $scriptFull = [IO.Path]::GetFullPath($PSScriptRoot).TrimEnd('\')
    if (-not ($scriptFull.Equals($full,[StringComparison]::OrdinalIgnoreCase) -or $scriptFull.StartsWith($full + '\',[StringComparison]::OrdinalIgnoreCase))) { return $null }
    $cursor = $full
    $relativeScript = $scriptFull.Substring($full.Length).TrimStart('\')
    foreach ($part in @($relativeScript -split '\\')) {
        if ([string]::IsNullOrWhiteSpace($part)) { continue }
        $cursor = Join-Path $cursor $part
        if (Test-Path -LiteralPath $cursor) {
            $item = Get-Item -LiteralPath $cursor -Force -ErrorAction Stop
            if (($item.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) { return $null }
        }
    }
    return $full
}

function Find-ApkLabRoot([string]$StartDirectory) {
    $current = [IO.Path]::GetFullPath($StartDirectory).TrimEnd('\')
    for ($depth = 0; $depth -lt 8; $depth++) {
        $valid = Test-ApkLabRootCandidate $current
        if ($valid) { return $valid }
        $parent = Split-Path -Parent $current
        if ([string]::IsNullOrWhiteSpace($parent) -or $parent -eq $current) { break }
        $current = $parent
    }
    throw "Unable to locate Codex Portable root from: $StartDirectory"
}

function Get-ApkLabRoot {
    # 便携根只从当前 helper 自身位置向上解析；不接受宿主预先注入的根目录变量。
    return Find-ApkLabRoot $PSScriptRoot
}

function Resolve-ApkLabPath([string]$Candidate) {
    $root = Get-ApkLabRoot
    $full = [IO.Path]::GetFullPath($Candidate).TrimEnd('\')
    if ($full.Equals($root, [StringComparison]::OrdinalIgnoreCase)) { return $full }
    if (-not $full.StartsWith($root + '\', [StringComparison]::OrdinalIgnoreCase)) { throw "Path escapes portable package: $Candidate" }
    $current = $root
    $rel = $full.Substring(($root + '\').Length)
    foreach ($seg in @($rel -split '\\')) {
        if ([string]::IsNullOrWhiteSpace($seg)) { continue }
        $current = Join-Path $current $seg
        if (Test-Path -LiteralPath $current) {
            $item = Get-Item -LiteralPath $current -Force
            if (($item.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) { throw "Reparse point escape risk: $current" }
        }
    }
    return $full
}

# Dot-sourcing is used by the MCP launcher; do not emit a root path into MCP stdio in that case.
if ($MyInvocation.InvocationName -eq '.') { return }
if ($Path) { Resolve-ApkLabPath $Path } else { Get-ApkLabRoot }
