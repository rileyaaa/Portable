#Requires -Version 5.1
[CmdletBinding()]
param(
    [Parameter(Mandatory=$true)][string]$State,
    [Parameter(Mandatory=$true)][ValidatePattern('^[A-Za-z0-9-]{2,35}$')][string]$Language,
    [string]$Image = '',
    [switch]$Check
)
$ErrorActionPreference = 'Stop'
$root = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\..\..'))
$python = Join-Path $root 'tool\python\python.exe'
$guard = Join-Path $PSScriptRoot 'path_guard.py'
if ($State -notmatch '(?i)\\work\\course-[a-z0-9_-]+\\[a-z0-9_-]+$') { throw 'Invalid course account directory.' }
$runtime = Join-Path $State 'runtime'
foreach ($key in @('TEMP','TMP','HOME','USERPROFILE','APPDATA','LOCALAPPDATA','PROGRAMDATA')) {
    if ([Environment]::GetEnvironmentVariable($key) -ine $runtime) { throw 'OCR requires the isolated course owner environment.' }
}
if (-not $Check) {
    if ([IO.Path]::GetDirectoryName($Image) -ine (Join-Path $State 'tmp') -or [IO.Path]::GetFileName($Image) -cnotmatch '^ocr-[0-9a-f]{32}\.png$') { throw 'Invalid OCR image path.' }
    & $python -I -B $guard file $Image
    if ($LASTEXITCODE) { throw 'Unsafe OCR image path.' }
}
Add-Type -AssemblyName System.Runtime.WindowsRuntime
[void][Windows.Media.Ocr.OcrEngine,Windows.Foundation,ContentType=WindowsRuntime]
[void][Windows.Globalization.Language,Windows.Globalization,ContentType=WindowsRuntime]
[void][Windows.Storage.StorageFile,Windows.Storage,ContentType=WindowsRuntime]
[void][Windows.Storage.Streams.IRandomAccessStream,Windows.Storage.Streams,ContentType=WindowsRuntime]
[void][Windows.Graphics.Imaging.BitmapDecoder,Windows.Graphics.Imaging,ContentType=WindowsRuntime]
[void][Windows.Graphics.Imaging.SoftwareBitmap,Windows.Graphics.Imaging,ContentType=WindowsRuntime]
[void][Windows.Media.Ocr.OcrResult,Windows.Foundation,ContentType=WindowsRuntime]
[void][Windows.Storage.FileAccessMode,Windows.Storage,ContentType=WindowsRuntime]
[void][Windows.Graphics.Imaging.BitmapPixelFormat,Windows.Graphics.Imaging,ContentType=WindowsRuntime]
[void][Windows.Graphics.Imaging.BitmapAlphaMode,Windows.Graphics.Imaging,ContentType=WindowsRuntime]
$engineType = [Windows.Media.Ocr.OcrEngine]
$requested = [Windows.Globalization.Language]::new($Language)
$zh = [Windows.Globalization.Language]::new('zh-Hans-CN')
$available = @($engineType::AvailableRecognizerLanguages | ForEach-Object {$_.LanguageTag})
$supported = $engineType::IsLanguageSupported($requested)
$engine = $null
if ($supported) { $engine = $engineType::TryCreateFromLanguage($requested) }
$result = [ordered]@{language=$Language; supported=($null -ne $engine); zhHansSupported=$engineType::IsLanguageSupported($zh); available=$available; actualLanguage=$null; text=$null; lines=@()}
if ($null -ne $engine) { $result.actualLanguage = $engine.RecognizerLanguage.LanguageTag }
[Console]::OutputEncoding = New-Object System.Text.UTF8Encoding($false)
if ($Check -or $null -eq $engine) {
    $result | ConvertTo-Json -Compress -Depth 5
    exit 0
}
$asTask = @([System.WindowsRuntimeSystemExtensions].GetMethods() | Where-Object {
    $_.Name -eq 'AsTask' -and $_.IsGenericMethodDefinition -and $_.GetGenericArguments().Count -eq 1 -and
    $_.GetParameters().Count -eq 1 -and $_.GetParameters()[0].ParameterType.Name -eq ('IAsyncOperation'+[char]96+'1')
})[0]
if ($null -eq $asTask) { throw 'WinRT async bridge missing.' }
function Wait-WinRT($operation,[type]$type) {
    $task = $asTask.MakeGenericMethod($type).Invoke($null,@($operation))
    $task.GetAwaiter().GetResult()
}
$stream = $null
$bitmap = $null
try {
    $file = Wait-WinRT ([Windows.Storage.StorageFile]::GetFileFromPathAsync($Image)) ([Windows.Storage.StorageFile])
    $stream = Wait-WinRT ($file.OpenAsync([Windows.Storage.FileAccessMode]::Read)) ([Windows.Storage.Streams.IRandomAccessStream])
    $decoder = Wait-WinRT ([Windows.Graphics.Imaging.BitmapDecoder]::CreateAsync($stream)) ([Windows.Graphics.Imaging.BitmapDecoder])
    if ($decoder.PixelWidth -gt $engineType::MaxImageDimension -or $decoder.PixelHeight -gt $engineType::MaxImageDimension) { throw 'Image exceeds Windows OCR engine dimensions.' }
    $bitmap = Wait-WinRT ($decoder.GetSoftwareBitmapAsync([Windows.Graphics.Imaging.BitmapPixelFormat]::Bgra8,[Windows.Graphics.Imaging.BitmapAlphaMode]::Premultiplied)) ([Windows.Graphics.Imaging.SoftwareBitmap])
    $ocr = Wait-WinRT ($engine.RecognizeAsync($bitmap)) ([Windows.Media.Ocr.OcrResult])
    $result.text = $ocr.Text
    $result.lines = @($ocr.Lines | ForEach-Object {
        $line = $_
        [ordered]@{text=$line.Text; words=@($line.Words | ForEach-Object {
            $box = $_.BoundingRect
            [ordered]@{text=$_.Text;x=$box.X;y=$box.Y;width=$box.Width;height=$box.Height}
        })}
    })
    $result | ConvertTo-Json -Compress -Depth 8
} finally {
    if ($null -ne $bitmap) { $bitmap.Dispose() }
    if ($null -ne $stream) { $stream.Dispose() }
}
