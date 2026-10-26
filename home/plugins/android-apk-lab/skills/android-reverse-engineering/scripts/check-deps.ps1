# Portable dependency check for Android reverse engineering.
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

function Resolve-PortablePath {
    param([Parameter(Mandatory=$true)][string]$Path)
    $full = [IO.Path]::GetFullPath($Path).TrimEnd('\')
    if (-not ($full.Equals($Root,[StringComparison]::OrdinalIgnoreCase) -or $full.StartsWith($Root + '\',[StringComparison]::OrdinalIgnoreCase))) {
        throw "Path escapes portable package: $Path"
    }
    if (-not $full.Equals($Root,[StringComparison]::OrdinalIgnoreCase)) {
        $relative = $full.Substring($Root.Length).TrimStart('\')
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
    return $full
}

function Get-PortableAndroidBuildToolsPath {
    param([string]$SdkRoot)
    $buildToolsRoot = Resolve-PortablePath (Join-Path $SdkRoot 'build-tools')
    if (-not (Test-Path -LiteralPath $buildToolsRoot -PathType Container)) { return '' }
    $candidates = @()
    foreach ($dir in @(Get-ChildItem -LiteralPath $buildToolsRoot -Directory -Force -ErrorAction SilentlyContinue)) {
        $safe = Resolve-PortablePath $dir.FullName
        $baseVersion = ([string]$dir.Name -replace '-.*$','')
        try { $version = [Version]$baseVersion } catch { $version = [Version]'0.0' }
        $expected = @('aapt.exe','aapt2.exe','apksigner.bat','zipalign.exe') | ForEach-Object { Join-Path $safe $_ }
        $safeExpected = @()
        $unsafeExpected = $false
        foreach ($toolPath in $expected) {
            if (-not (Test-Path -LiteralPath $toolPath -PathType Leaf)) { continue }
            try { $safeExpected += (Resolve-PortablePath $toolPath) } catch { $unsafeExpected = $true; break }
        }
        if ($unsafeExpected) { continue }
        $present = @($safeExpected | Where-Object { (Get-Item -LiteralPath $_ -Force).Length -gt 0 }).Count
        $isPrerelease = $(if ([string]$dir.Name -match '-') { 1 } else { 0 })
        $candidates += [pscustomobject]@{ Path=$safe; Version=$version; IsPrerelease=$isPrerelease; Name=[string]$dir.Name; Present=$present }
    }
    if ($candidates.Count -eq 0) { return '' }
    $ordered = @($candidates | Sort-Object @{Expression='Version';Descending=$true}, @{Expression='IsPrerelease';Descending=$false}, @{Expression='Name';Descending=$true})
    $complete = @($ordered | Where-Object { $_.Present -eq 4 } | Select-Object -First 1)
    if ($complete.Count -gt 0) { return [string]$complete[0].Path }
    $partial = @($ordered | Where-Object { $_.Present -gt 0 } | Select-Object -First 1)
    if ($partial.Count -gt 0) { return [string]$partial[0].Path }
    return ''
}

$Root = Find-ApkLabRoot
$env:CODEX_INSTALL_DIR = $Root
$env:JAVA_HOME = Resolve-PortablePath (Join-Path $Root 'tool\android\jdk')
$env:ANDROID_HOME = Resolve-PortablePath (Join-Path $Root 'tool\android\sdk')
$env:APKTOOL_FRAMEWORK_DIR = Resolve-PortablePath (Join-Path $Root 'cache\android\apktool-framework')
$env:FRIDA_CACHE_DIR = Resolve-PortablePath (Join-Path $Root 'cache\android\frida')
$env:MITMPROXY_HOME = Resolve-PortablePath (Join-Path $Root 'cache\android\mitmproxy')
$env:APPIUM_HOME = Resolve-PortablePath (Join-Path $Root 'cache\android\appium')
$AndroidBuildToolsPath = Get-PortableAndroidBuildToolsPath -SdkRoot $env:ANDROID_HOME

$portableParts = @(
    (Resolve-PortablePath (Join-Path $Root 'tool\android\jdk\bin')),
    (Resolve-PortablePath (Join-Path $Root 'tool\android\jadx\bin')),
    (Resolve-PortablePath (Join-Path $Root 'tool\android\apktool')),
    (Resolve-PortablePath (Join-Path $Root 'tool\android\dex2jar')),
    (Resolve-PortablePath (Join-Path $Root 'tool\android\sdk\platform-tools')),
    (Resolve-PortablePath (Join-Path $Root 'tool\bin')),
    (Resolve-PortablePath (Join-Path $Root 'tool\python')),
    (Resolve-PortablePath (Join-Path $Root 'tool\python\Scripts')),
    (Resolve-PortablePath (Join-Path $Root 'cache\python-userbase\Scripts')),
    (Resolve-PortablePath (Join-Path $Root 'cache\npm-prefix')),
    (Resolve-PortablePath (Join-Path $Root 'cache\npm-prefix\node_modules\.bin')),
    (Resolve-PortablePath (Join-Path $Root 'cache\pnpm')),
    (Resolve-PortablePath (Join-Path $Root 'tool\android\maestro\bin'))
)
if (-not [string]::IsNullOrWhiteSpace($AndroidBuildToolsPath)) { $portableParts = @($AndroidBuildToolsPath) + $portableParts }
$parts = @(
    $portableParts + @(
        (Join-Path $env:SystemRoot 'System32'),
        $env:SystemRoot,
        (Join-Path $env:SystemRoot 'System32\WindowsPowerShell\v1.0'),
        (Join-Path $env:SystemRoot 'System32\Wbem')
    )
)
# Dependency discovery is intentionally package-only; never let an inherited host opt-in change the result.
$env:CODEX_PORTABLE_ALLOW_HOST_PATH = 'false'
$env:PATH = ($parts | Where-Object { -not [string]::IsNullOrWhiteSpace($_) } | Select-Object -Unique) -join ';'

$checks = @(
    @{name='java';    cmd='java';        required=$true;  portable=(Join-Path $Root 'tool\android\jdk')},
    @{name='jadx';    cmd='jadx';        required=$true;  portable=(Join-Path $Root 'tool\android\jadx')},
    @{name='apktool'; cmd='apktool';     required=$false; portable=(Join-Path $Root 'tool\android\apktool')},
    @{name='adb';     cmd='adb';         required=$false; portable=(Join-Path $Root 'tool\android\sdk\platform-tools')},
    @{name='dex2jar';  cmd='d2j-dex2jar'; required=$false; portable=(Join-Path $Root 'tool\android\dex2jar')},
    @{name='aapt';     cmd='aapt';       required=$false; portable=$AndroidBuildToolsPath},
    @{name='aapt2';    cmd='aapt2';      required=$false; portable=$AndroidBuildToolsPath},
    @{name='apksigner';cmd='apksigner';  required=$false; portable=$AndroidBuildToolsPath},
    @{name='zipalign'; cmd='zipalign';    required=$false; portable=$AndroidBuildToolsPath},
    @{name='frida';    cmd='frida';       required=$false; portable=(Join-Path $Root 'tool\bin')},
    @{name='mitmproxy';cmd='mitmproxy';   required=$false; portable=(Join-Path $Root 'tool\bin')},
    @{name='objection';cmd='objection';   required=$false; portable=(Join-Path $Root 'tool\bin')},
    @{name='appium';   cmd='appium';      required=$false; portable=(Join-Path $Root 'cache\npm-prefix')},
    @{name='maestro';  cmd='maestro';     required=$false; portable=(Join-Path $Root 'tool\android\maestro\bin')}
)
$result = foreach ($c in $checks) {
    $cmd = Get-Command $c.cmd -ErrorAction SilentlyContinue
    if ($cmd) {
        try {
            $resolved = Resolve-PortablePath $cmd.Source
            $cmd = Get-Item -LiteralPath $resolved -ErrorAction Stop
        } catch {
            $cmd = $null
        }
    }
    [pscustomobject]@{ name=$c.name; found=[bool]$cmd; command=if($cmd){$cmd.FullName}else{$null}; required=$c.required; portablePath=$c.portable }
}
$result | ConvertTo-Json -Depth 4
$missingRequired = @($result | Where-Object { $_.required -and -not $_.found })
if ($missingRequired.Count -gt 0) { exit 1 }
exit 0
