# Portable dependency locator for Android reverse engineering.
# Usage: install-dep.ps1 <java|jadx|vineflower|dex2jar|apktool|adb>
param([Parameter(Position=0)][string]$Dep)
$ErrorActionPreference = 'Stop'

function Find-ApkLabRoot {
    # 便携根只从当前脚本位置向上寻找最近匹配项，不信任外部 CODEX_INSTALL_DIR/CODEX_HOME。
    $cursor = [IO.Path]::GetFullPath($PSScriptRoot).TrimEnd('\')
    for ($i = 0; $i -lt 8 -and -not [string]::IsNullOrWhiteSpace($cursor); $i++) {
        if ((Test-Path -LiteralPath (Join-Path $cursor 'codex.exe') -PathType Leaf) -and
            (Test-Path -LiteralPath (Join-Path $cursor 'env.ps1') -PathType Leaf)) {
            $rootItem = Get-Item -LiteralPath $cursor -Force -ErrorAction Stop
            if (($rootItem.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) { throw "Refusing reparse-point portable root: $cursor" }
            $scriptFull = [IO.Path]::GetFullPath($PSScriptRoot).TrimEnd('\')
            $walk = $cursor
            foreach ($part in @($scriptFull.Substring($cursor.Length).TrimStart('\') -split '\\')) {
                if ([string]::IsNullOrWhiteSpace($part)) { continue }
                $walk = Join-Path $walk $part
                if (Test-Path -LiteralPath $walk) {
                    $item = Get-Item -LiteralPath $walk -Force -ErrorAction Stop
                    if (($item.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) { throw "Refusing reparse-point script path: $walk" }
                }
            }
            return $cursor
        }
        $parent = Split-Path -Parent $cursor
        if ([string]::IsNullOrWhiteSpace($parent) -or $parent -eq $cursor) { break }
        $cursor = $parent
    }
    throw 'Cannot locate Codex portable root.'
}

$Root = Find-ApkLabRoot
$env:CODEX_INSTALL_DIR = $Root
function UnderRoot([string]$Path) {
    $p = [IO.Path]::GetFullPath($Path).TrimEnd('\')
    if (-not ($p.Equals($Root,[StringComparison]::OrdinalIgnoreCase) -or $p.StartsWith($Root + '\',[StringComparison]::OrdinalIgnoreCase))) { throw "Path escapes portable package: $Path" }
    if (-not $p.Equals($Root,[StringComparison]::OrdinalIgnoreCase)) {
        $relative = $p.Substring($Root.Length).TrimStart('\')
        $cursor = $Root
        foreach ($part in @($relative -split '\\')) {
            if ([string]::IsNullOrWhiteSpace($part)) { continue }
            $cursor = Join-Path $cursor $part
            if (Test-Path -LiteralPath $cursor) {
                $item = Get-Item -LiteralPath $cursor -Force
                if (($item.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) { throw "Refusing reparse-point path: $cursor" }
            }
        }
    }
    return $p
}
$ToolAndroid = UnderRoot (Join-Path $Root 'tool\android')
$CacheAndroid = UnderRoot (Join-Path $Root 'cache\android')
foreach ($d in @($ToolAndroid,$CacheAndroid,(UnderRoot (Join-Path $Root 'tmp\android')))) { New-Item -ItemType Directory -Force -Path $d | Out-Null }
$targets = @{
  java = @{ Dir='tool\android\jdk'; Url='https://adoptium.net/temurin/releases/'; Note='Use Windows x64 ZIP and extract here.' }
  jadx = @{ Dir='tool\android\jadx'; Url='https://github.com/skylot/jadx/releases'; Note='Use jadx ZIP and extract here.' }
  vineflower = @{ Dir='tool\android\vineflower'; Url='https://github.com/Vineflower/vineflower/releases'; Note='Place vineflower.jar here.' }
  fernflower = @{ Dir='tool\android\vineflower'; Url='https://github.com/Vineflower/vineflower/releases'; Note='Place vineflower.jar here.' }
  dex2jar = @{ Dir='tool\android\dex2jar'; Url='https://github.com/pxb1988/dex2jar/releases'; Note='Extract dex-tools ZIP here.' }
  apktool = @{ Dir='tool\android\apktool'; Url='https://apktool.org/docs/install/'; Note='Place apktool.jar and wrapper here; set APKTOOL_FRAMEWORK_DIR to cache\android\apktool-framework.' }
  adb = @{ Dir='tool\android\sdk\platform-tools'; Url='https://developer.android.com/tools/releases/platform-tools'; Note='Extract platform-tools here.' }
}
if (-not $Dep -or $Dep -in @('-h','--help')) {
  'Portable APK Lab dependency layout:'
  $targets.GetEnumerator() | Sort-Object Name | ForEach-Object { "  {0,-12} {1}" -f $_.Name,(Join-Path $Root $_.Value.Dir) }
  exit 0
}
if (-not $targets.ContainsKey($Dep)) { throw "Unknown dependency: $Dep" }
$t=$targets[$Dep]
$dir=UnderRoot (Join-Path $Root $t.Dir)
New-Item -ItemType Directory -Force -Path $dir | Out-Null
[pscustomobject]@{ dependency=$Dep; installDir=$dir; download=$t.Url; note=$t.Note; portableRoot=$Root } | ConvertTo-Json -Depth 4
exit 0
