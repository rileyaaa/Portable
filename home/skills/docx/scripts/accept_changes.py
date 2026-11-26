"""Accept all tracked changes in a DOCX file using LibreOffice.

Requires LibreOffice (soffice) to be installed.
"""

import argparse
import logging
import os
import sys
import zipfile
import shutil
import subprocess
from pathlib import Path


# The bundled isolated Python deliberately omits the script directory.
# Use only this entrypoint's verified package-local sibling modules.
if __name__ == "__main__" and sys.flags.safe_path:
    import stat
    from pathlib import Path
    _script = Path(__file__).absolute()
    _root = _script.parents[4]
    if _script.relative_to(_root).parts != ("home", "skills", "docx", "scripts", "accept_changes.py"):
        raise RuntimeError("Script is outside its bundled skill layout")
    _directory = _script.parent
    for _entry in (*reversed(_script.parents), _directory / "office", _directory / "office/helpers"):
        _info = _entry.lstat()
        if not stat.S_ISDIR(_info.st_mode) or getattr(_info, "st_file_attributes", 0) & 0x400:
            raise RuntimeError("Skill import path crosses a link or non-directory")
    for _entry in (_script, _root / "env.ps1", _root / "codex.exe", _directory / "office/helpers/__init__.py", _directory / "office/soffice.py"):
        _info = _entry.lstat()
        if not stat.S_ISREG(_info.st_mode) or _info.st_nlink != 1 or getattr(_info, "st_file_attributes", 0) & 0x400:
            raise RuntimeError("Skill import requires ordinary single-link package files")
    sys.path.insert(0, str(_directory))
    for _stream in (sys.stdout, sys.stderr):
        if _stream is not None and not _stream.isatty() and hasattr(_stream, "reconfigure"):
            _stream.reconfigure(encoding="utf-8", errors="backslashreplace")

from office.helpers import portable_temporary_directory, resolve_portable_path
from office.soffice import get_soffice_env, get_soffice_executable

logger = logging.getLogger(__name__)


ACCEPT_CHANGES_MACRO = """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE script:module PUBLIC "-//OpenOffice.org//DTD OfficeDocument 1.0//EN" "module.dtd">
<script:module xmlns:script="http://openoffice.org/2000/script" script:name="Module1" script:language="StarBasic">
    Sub AcceptAllTrackedChanges()
        Dim document As Object
        Dim dispatcher As Object

        document = ThisComponent.CurrentController.Frame
        dispatcher = createUnoService("com.sun.star.frame.DispatchHelper")

        dispatcher.executeDispatch(document, ".uno:AcceptAllTrackedChanges", "", 0, Array())
        ThisComponent.store()
        ThisComponent.close(True)
    End Sub
</script:module>"""


def accept_changes(
    input_file: str,
    output_file: str,
) -> tuple[None, str]:
    try:
        input_path = resolve_portable_path(input_file, must_exist=True, kind="file")
        output_path = resolve_portable_path(output_file, must_exist=False, kind="file")
    except (FileNotFoundError, RuntimeError) as e:
        return None, f"Error: {e}"

    if not input_path.exists():
        return None, f"Error: Input file not found: {input_file}"

    if not input_path.suffix.lower() == ".docx":
        return None, f"Error: Input file is not a DOCX file: {input_file}"

    # Do not create, overwrite, or modify the requested output until the
    # optional package-local tool has actually completed a staged document.
    try:
        executable = get_soffice_executable()
        environment = get_soffice_env()
        with portable_temporary_directory(prefix="libreoffice_docx_profile_") as scratch:
            scratch_path = Path(scratch)
            profile_path = scratch_path / "profile"
            profile_path.mkdir()
            staged = scratch_path / "document.docx"
            shutil.copy2(input_path, staged)
            if not _setup_libreoffice_macro(profile_path):
                return None, "Error: Failed to setup LibreOffice macro"

            cmd = [
                executable, "--headless",
                f"-env:UserInstallation={profile_path.as_uri()}",
                "--norestore",
                "vnd.sun.star.script:Standard.Module1.AcceptAllTrackedChanges?language=Basic&location=application",
                str(staged.absolute()),
            ]
            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=30,
                check=False, env=environment,
            )
            if result.returncode != 0:
                return None, f"Error: LibreOffice failed: {result.stderr}"
            # Do not publish a missing, linked, truncated or non-DOCX result.
            staged = resolve_portable_path(staged, must_exist=True, kind="file")
            with zipfile.ZipFile(staged) as document:
                if "word/document.xml" not in document.namelist() or document.testzip() is not None:
                    return None, "Error: LibreOffice did not produce an intact DOCX"
            output_path = resolve_portable_path(output_path, kind="file")
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path = resolve_portable_path(output_path, kind="file")
            os.replace(staged, output_path)
    except subprocess.TimeoutExpired:
        return None, "Error: LibreOffice timed out; requested output was not replaced"
    except (OSError, RuntimeError, ValueError, zipfile.BadZipFile) as e:
        return None, f"Error: {e}"

    return (
        None,
        f"Successfully accepted all tracked changes: {input_file} -> {output_file}",
    )


def _setup_libreoffice_macro(profile_path: Path) -> bool:
    macro_dir = profile_path / "user" / "basic" / "Standard"
    macro_file = macro_dir / "Module1.xba"

    if macro_file.exists() and "AcceptAllTrackedChanges" in macro_file.read_text():
        return True

    if not macro_dir.exists():
        result = subprocess.run(
            [
                get_soffice_executable(),
                "--headless",
                f"-env:UserInstallation={profile_path.as_uri()}",
                "--terminate_after_init",
            ],
            capture_output=True,
            timeout=10,
            check=False,
            env=get_soffice_env(),
        )
        if result.returncode != 0 or not macro_dir.is_dir():
            return False

    try:
        macro_file.write_text(ACCEPT_CHANGES_MACRO, encoding="utf-8")
        return True
    except Exception as e:
        logger.warning(f"Failed to setup LibreOffice macro: {e}")
        return False


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Accept all tracked changes in a DOCX file"
    )
    parser.add_argument("input_file", help="Input DOCX file with tracked changes")
    parser.add_argument(
        "output_file", help="Output DOCX file (clean, no tracked changes)"
    )
    args = parser.parse_args()

    _, message = accept_changes(args.input_file, args.output_file)
    print(message)

    if "Error" in message:
        raise SystemExit(1)
