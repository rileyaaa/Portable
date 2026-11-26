#Requires -Version 5.1
# Developer-only, offline ZIP/TEMP preflight. Use a fresh hydrated checkout.
[CmdletBinding()]
param(
    [Parameter(Mandatory=$true)][string]$SourceRoot,
    [Parameter(Mandatory=$true)][ValidatePattern('^[0-9a-f]{40}$')][string]$ExpectedSourceCommit
)
$ErrorActionPreference = 'Stop'
if ([Environment]::OSVersion.Platform -ne [PlatformID]::Win32NT -or
    -not [Environment]::Is64BitOperatingSystem -or -not [Environment]::Is64BitProcess -or
    $PSVersionTable.PSEdition -ne 'Desktop' -or
    $PSVersionTable.PSVersion.Major -ne 5 -or $PSVersionTable.PSVersion.Minor -ne 1) {
    throw 'Requires Windows x64 and Windows PowerShell 5.1'
}
$Root = (Resolve-Path -LiteralPath $SourceRoot).ProviderPath
$Drive = [IO.DriveInfo]::new([IO.Path]::GetPathRoot($Root))
if ($Drive.DriveFormat -ne 'NTFS' -or $Drive.DriveType -ne [IO.DriveType]::Fixed) {
    throw 'Requires a local fixed NTFS volume'
}
$Python = Join-Path $Root 'tool\python\python.exe'
$Git = (Get-Command git.exe -CommandType Application | Select-Object -First 1).Source
$PSVersion = $PSVersionTable.PSVersion.ToString()
# No downloads, installation or publication. Git is a local build prerequisite.
# The Python payload orchestrates only the existing packager and fixed TEMP test.
@'
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import zipfile

BASE = 'bf1a75bd19e5f27eb9628025b0f18519d2dd8702'
SCRIPT = 'tests/run_candidate_temp_preflight.ps1'
TEST = 'tests/test_temp_consumer_encoding.py'
TEST_BLOB = '5f35b7f53d0934c17c5ed5c46ca087943e304444'
LABEL = 'v0.172.0-portable.2'  # Local filename only; no tag is created.
ARCHIVE = 'Codex-Portable-' + LABEL + '-windows-x64.zip'
NAMES = (ARCHIVE, 'release-manifest.json', 'SHA256SUMS')
CASES = {'test_tmpdir_consumption', 'test_temp_consumption', 'test_tmp_consumption',
         'test_unavailable_fixture_does_not_fall_back',
         'test_cp1252_reporting_fails_after_successful_consumption',
         'test_ascii_json_reporting_preserves_successful_consumption'}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def git_blob(data):
    return hashlib.sha1(b'blob ' + str(len(data)).encode('ascii') + b'\0' + data,
                        usedforsecurity=False).hexdigest()


def inventory(expected, parents, changes):
    # The review-only commit adds this one excluded test runner. Do not admit
    # a different product tree or the later workflow configuration as input.
    if expected == BASE:
        return (9343, 158, 9185)
    require(parents == [expected, BASE] and changes == ['A\t' + SCRIPT],
            'Source is not the reviewed base or its single-script child')
    return (9344, 159, 9185)


def check_counts(report, counts):
    require(tuple(report[k] for k in ('source_file_count', 'excluded_file_count', 'file_count')) == counts,
            'Candidate inventory mismatch')


def check_sums(directory, claimed):
    hashes = {name: sha(directory / name) for name in NAMES}
    lines = (directory / NAMES[2]).read_text(encoding='ascii').splitlines()
    expected = [hashes[name] + '  ' + name for name in NAMES[:2]]
    require(lines == expected and hashes[ARCHIVE] == claimed, 'Candidate checksum mismatch')
    return hashes


def test_passed(code, log):
    # unittest -v writes the individual results and summary to stderr.
    found = re.findall(r'^(test_\w+) \([^\r\n]*\) \.\.\. ok\s*$', log, re.M)
    return (code == 0 and len(found) == len(CASES) and set(found) == CASES and
            re.search(r'^Ran 6 tests in ', log, re.M) is not None and
            re.search(r'^OK\s*$', log, re.M) is not None)


def run(root, expected, git, ps_version):
    evidence = {'source_commit': expected, 'scope': 'Windows native file operations; synthetic TEMP only',
                'windows_version': sys.getwindowsversion().build, 'powershell_version': ps_version,
                'python_version': sys.version.split()[0], 'test_blob': TEST_BLOB,
                'zip_status': 'ZIP_UNVERIFIED', 'temp_status': 'TEMP_NOT_RUN',
                'temp_exit_code': None, 'cleanup_status': 'NOT_RUN', 'output_dir': None}
    out = owned = hashes = None
    # All objects and LFS payloads must already be local. Do not lazy-fetch.
    os.environ['GIT_NO_LAZY_FETCH'] = '1'
    os.environ['GIT_TERMINAL_PROMPT'] = '0'
    def local_git(*args):
        return subprocess.check_output([git, '-C', str(root), *args], timeout=120)
    def build(*args):
        result = subprocess.run([sys.executable, '-I', '-B', str(root/'tool/package-release.py'),
                                 *args, '--version', LABEL], cwd=root, capture_output=True, timeout=3600)
        require(result.returncode == 0, 'Packager failed: ' + ascii(result.stderr[-4000:]))
        return json.loads(result.stdout)
    try:
        require(sys.platform == 'win32' and sys.version_info[:3] == (3, 14, 10) and
                sys.maxsize > 2**32 and Path(sys.executable).resolve() == (root/'tool/python/python.exe').resolve(),
                'Fixed bundled Windows Python required')
        require(local_git('rev-parse', 'HEAD').decode().strip() == expected, 'Source commit mismatch')
        parents = local_git('rev-list', '--parents', '-n', '1', expected).decode().split()
        changes = [] if expected == BASE else local_git('diff', '--name-status', '--no-renames', BASE, expected).decode().splitlines()
        counts = inventory(expected, parents, changes)
        require(local_git('rev-parse', 'HEAD:' + TEST).decode().strip() == TEST_BLOB, 'TEMP test blob mismatch')
        data = local_git('cat-file', 'blob', TEST_BLOB)
        require(git_blob(data) == TEST_BLOB, 'TEMP test bytes mismatch')
        check = build('--check')
        check_counts(check, counts)
        require(check['source_commit'] == expected and check['codex_version'] == '0.172.0', 'Preflight source mismatch')
        built = build()
        check_counts(built, counts)
        candidate = Path(built['output_dir'])
        require(candidate.parent == root/'tmp' and re.fullmatch(r'release-[a-z0-9_]+', candidate.name),
                'Unexpected packager output directory')
        require(built['source_commit'] == expected and all(Path(built[key]) == candidate/name
                for key, name in zip(('archive', 'manifest', 'checksums'), NAMES)), 'Build report mismatch')
        out = candidate
        evidence['output_dir'] = str(out)
        hashes = check_sums(out, built['archive_sha256'])
        manifest = json.loads((out/NAMES[1]).read_bytes())
        check_counts(manifest, counts)
        require((manifest['source_commit'], manifest['release_version'], manifest['codex_version'],
                 manifest['target'], manifest['package_kind'], manifest['archive']) ==
                (expected, LABEL, '0.172.0', 'x86_64-pc-windows-msvc', 'customer', ARCHIVE),
                'Manifest identity mismatch')
        spec = importlib.util.spec_from_file_location('portable_release', root/'tool/package-release.py')
        release = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(release)
        names, excluded = release.customer_files(local_git('ls-tree', '-r', '--name-only', '-z', expected).decode('utf-8').rstrip('\0').split('\0'))
        require(list(manifest['files']) == names and manifest['excluded_files'] == excluded and
                len(names) == counts[2], 'Manifest member list mismatch')
        release.verify_zip(out/ARCHIVE, manifest['files'])
        evidence.update(zip_status='ZIP_VERIFIED', archive_sha256=hashes[ARCHIVE],
                        manifest_sha256=hashes[NAMES[1]], checksums_sha256=hashes[NAMES[2]],
                        file_count=counts[2], archive_bytes=(out/ARCHIVE).stat().st_size)
        for name in ('temp.stdout.log', 'temp.stderr.log'):
            with (out/name).open('xb'):
                pass
        owned = Path(tempfile.mkdtemp(prefix='extract-', dir=out))
        extraction = owned/'\u4e2d\u6587 \u7a7a\u683c'
        extraction.mkdir()
        with zipfile.ZipFile(out/ARCHIVE) as archive:
            archive.extractall(extraction)
        package = extraction/'Codex'
        actual = {p.relative_to(package).as_posix() for p in package.rglob('*') if p.is_file()}
        require(actual == set(names), 'Extracted member list mismatch')
        for name, item in manifest['files'].items():
            path = package/name
            require(path.stat().st_size == item['size'] and sha(path) == item['sha256'], 'Extracted bytes differ: ' + name)
        work = package/'work'
        work.mkdir(exist_ok=True)
        test = work/Path(TEST).name
        with test.open('xb') as stream:
            stream.write(data)
        python = package/'tool/python/python.exe'
        evidence.update(python_sha256=sha(python), test_sha256=sha(test), temp_status='TEMP_FAIL')
        with (out/'temp.stdout.log').open('wb') as stdout, (out/'temp.stderr.log').open('wb') as stderr:
            result = subprocess.run([str(python), '-I', '-B', str(test)], cwd=work,
                                    stdout=stdout, stderr=stderr, timeout=120)
        evidence['temp_exit_code'] = result.returncode
        require(test_passed(result.returncode, (out/'temp.stderr.log').read_text(encoding='ascii', errors='replace')),
                'TEMP test did not pass all six cases')
        require(not (package/'tmp/temp-encoding-probe').exists(), 'TEMP test left its fixture')
        evidence['temp_status'] = 'TEMP_PASS_NATIVE_SYNTHETIC'
    except Exception as error:
        evidence['failure'] = str(error)
    finally:
        if owned is not None:
            try:
                # Only the new extraction; retain the pristine candidate and logs.
                shutil.rmtree(owned)
                require(not owned.exists(), 'Extraction remains')
                evidence['cleanup_status'] = 'PASS'
            except Exception as error:
                evidence.update(cleanup_status='FAIL', cleanup_error=str(error))
        if evidence['zip_status'] == 'ZIP_VERIFIED':
            try:
                require(check_sums(out, hashes[ARCHIVE]) == hashes, 'Candidate bytes changed')
            except Exception as error:
                evidence.update(zip_status='ZIP_UNVERIFIED', verification_error=str(error))
        if out is not None:
            for name in ('temp.stdout.log', 'temp.stderr.log'):
                if (out/name).is_file():
                    evidence[name + '_sha256'] = sha(out/name)
            with (out/'preflight-evidence.json').open('x', encoding='utf-8') as report:
                json.dump(evidence, report, ensure_ascii=True, indent=2)
                report.write('\n')
        print(json.dumps(evidence, ensure_ascii=True))
    return 0 if (evidence['zip_status'], evidence['temp_status'], evidence['cleanup_status']) == (
        'ZIP_VERIFIED', 'TEMP_PASS_NATIVE_SYNTHETIC', 'PASS') else 1


if __name__ == '__main__':
    sys.exit(run(Path(sys.argv[1]), *sys.argv[2:]))
'@ | & $Python -I -B - $Root $ExpectedSourceCommit $Git $PSVersion
exit $LASTEXITCODE
