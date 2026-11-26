"""Test-only child for the local Windows tool-boundary probe, no services."""
import errno
import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import sys
import tempfile
from unittest import mock


def plain(path, directory):
    info = path.lstat()
    assert not getattr(info, "st_file_attributes", 0) & 0x400
    assert stat.S_ISDIR(info.st_mode) if directory else (
        stat.S_ISREG(info.st_mode) and info.st_nlink == 1)


def checked(root, path, directory=False):
    assert path.is_absolute() and path.is_relative_to(root)
    for parent in reversed(path.parents):
        plain(parent, True)
    plain(path, directory)
    assert path.resolve() == path
    return path


def resolved_program(root, name, relative):
    expected = checked(root, root / relative)
    search = os.environ.get("PATH", "")
    assert expected.parent in [Path(p) for p in search.split(os.pathsep) if p]
    found = shutil.which(name, path=search)
    assert found and Path(found).absolute() == expected
    return checked(root, Path(found).absolute())


def temp_lifecycle(root, expected):
    # Retain actual Python environment precedence; constrain only its fallback
    # list so an inaccessible test directory can never lead to a host write.
    checked(root, expected, directory=True)
    assert all(Path(os.environ[k]) == expected for k in ("TMPDIR", "TEMP", "TMP"))
    assert Path(tempfile._candidate_tempdir_list()[0]) == expected
    old = tempfile.tempdir
    try:
        tempfile.tempdir = None
        with mock.patch.object(tempfile, "_candidate_tempdir_list", return_value=[str(expected)]):
            assert Path(tempfile.gettempdir()) == expected
            with tempfile.NamedTemporaryFile() as f:
                actual = Path(f.name)
                assert actual.parent == expected and actual.is_file()
                assert f.write(b"owned") == 5
                f.flush()
                f.seek(0)
                assert f.read() == b"owned"
            assert not actual.exists()
            # Independent synthetic PermissionError: no actual ACL alteration.
            tempfile.tempdir = None
            attempts = []
            def deny(path, *args, **kwargs):
                assert Path(path).parent == expected
                attempts.append(True)
                raise PermissionError(errno.EACCES, "synthetic denial")
            with mock.patch.object(tempfile._os, "open", side_effect=deny):
                try:
                    tempfile.gettempdir()
                except FileNotFoundError:
                    assert attempts
                else:
                    raise AssertionError("Denied temp unexpectedly succeeded")
    finally:
        tempfile.tempdir = old
    assert not list(expected.iterdir())


NODE_PROBE = r'''
const fs = require('node:fs'), os = require('node:os'), p = require('node:path');
const [root, expectedExe, expectedTemp] = process.argv.slice(1);
const norm = x => p.resolve(x).toLowerCase();
if (norm(fs.realpathSync(process.execPath)) !== norm(expectedExe)) throw Error('identity');
if (norm(os.tmpdir()) !== norm(expectedTemp)) throw Error('temp');
const d = fs.mkdtempSync(p.join(expectedTemp, 'node-probe-'));
const f = p.join(d, 'owned');
try {
  fs.writeFileSync(f, 'owned', {flag:'wx'});
  if (fs.readFileSync(f, 'utf8') !== 'owned') throw Error('readback');
} finally {
  if (fs.existsSync(f)) fs.unlinkSync(f);
  fs.rmdirSync(d);
}
if (fs.existsSync(d)) throw Error('cleanup');
const relative = p.relative(root, fs.realpathSync(process.execPath)).split(p.sep).join('/');
process.stdout.write(JSON.stringify({exe:relative, temp:true}));
'''
PYTHON_ID = r'''
import json,sys
from pathlib import Path
root, expected = map(Path,sys.argv[1:])
actual = Path(sys.executable).resolve()
assert actual == expected
print(json.dumps(actual.relative_to(root).as_posix(),ensure_ascii=True))
'''


def main():
    assert os.name == "nt" and __debug__ and sys.flags.isolated and sys.dont_write_bytecode
    assert len(sys.argv) == 2
    root = Path(sys.argv[1]).absolute()
    work, tmp = root / "work", root / "tmp"
    checked(root, work, True)
    checked(root, tmp, True)
    python = resolved_program(root, "python.exe", "tool/python/python.exe")
    node = resolved_program(root, "node.exe", "tool/node/node.exe")
    assert Path(sys.executable).resolve() == python
    assert Path.cwd() == work
    assert not list(tmp.iterdir())
    def run(exe, args):
        result = subprocess.run([str(exe), *args], cwd=work,
                                stdin=subprocess.DEVNULL, capture_output=True, timeout=30)
        assert result.returncode == 0 and not result.stderr
        return json.loads(result.stdout.decode("ascii"))
    assert run(python, ["-I", "-B", "-c", PYTHON_ID, str(root), str(python)]) == "tool/python/python.exe"
    assert run(node, ["-e", NODE_PROBE, str(root), str(node), str(tmp)]) == {
        "exe": "tool/node/node.exe", "temp": True}
    temp_lifecycle(root, tmp)
    marker = work / "owned-write.txt"
    with marker.open("xb") as f:
        f.write(b"owned")
    assert marker.read_bytes() == b"owned"
    marker.unlink()
    assert not list(tmp.iterdir()) and not marker.exists()
    # The same strict test resolver must stop before any subprocess when the
    # package directory is absent from PATH; this is not a sandbox assertion.
    with mock.patch.dict(os.environ, {"PATH": str(work)}):
        try:
            resolved_program(root, "python.exe", "tool/python/python.exe")
        except AssertionError:
            pass
        else:
            raise AssertionError("Missing package PATH accepted")
    print(json.dumps({"python_path": True, "node_path": True, "python_temp": True,
                      "node_temp": True, "work_write": True,
                      "synthetic_denial_no_fallback": True,
                      "missing_path_rejected": True}, ensure_ascii=True))


if __name__ == "__main__":
    main()
