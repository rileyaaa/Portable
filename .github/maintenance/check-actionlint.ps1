# Windows PowerShell 5.1. Validate all three manual production workflows with a pinned actionlint binary.
# This script runs offline after downloading a release ZIP whose digest was reviewed.
$ErrorActionPreference = 'Stop'
$version = '1.7.12'
$archiveName = "actionlint_${version}_windows_amd64.zip"
$expectedSha256 = '6e7241b51e6817ea6a047693d8e6fed13b31819c9a0dd6c5a726e1592d22f6e9'
$runFolder = Join-Path $env:RUNNER_TEMP ('codex-portable-actionlint-' + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Force -Path $runFolder | Out-Null
try {
    & gh release download ("v" + $version) --repo rhysd/actionlint --pattern $archiveName --dir $runFolder
    if ($LASTEXITCODE -ne 0) { throw 'Unable to download the pinned official actionlint archive.' }
    $archive = Join-Path $runFolder $archiveName
    if (-not (Test-Path -LiteralPath $archive -PathType Leaf)) { throw 'Actionlint ZIP is missing.' }
    $actual = (Get-FileHash -LiteralPath $archive -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($actual -cne $expectedSha256) { throw 'Actionlint archive SHA-256 does not match the reviewed pin.' }
    $bin = Join-Path $runFolder 'verified'
    Expand-Archive -LiteralPath $archive -DestinationPath $bin -Force
    $exe = Join-Path $bin 'actionlint.exe'
    if (-not (Test-Path -LiteralPath $exe -PathType Leaf)) { throw 'Pinned actionlint executable is missing.' }
    & $exe -oneline '.github/workflows/01-upgrade-codex-runtime.yml' '.github/workflows/02-verify-and-publish-portable.yml' '.github/workflows/03-update-tools.yml'
    if ($LASTEXITCODE -ne 0) { throw 'actionlint rejected a production GitHub Actions workflow.' }
    Write-Output 'ACTIONLINT_THREE_WORKFLOWS=PASS'
    if ($env:GITHUB_STEP_SUMMARY) {
        'ACTIONLINT_THREE_WORKFLOWS=PASS (pinned v1.7.12 SHA-256)' |
            Out-File -LiteralPath $env:GITHUB_STEP_SUMMARY -Encoding utf8 -Append
    }
} finally {
    if (Test-Path -LiteralPath $runFolder) {
        Remove-Item -LiteralPath $runFolder -Recurse -Force
    }
}
