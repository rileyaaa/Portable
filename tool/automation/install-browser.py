"""Install exactly the pinned Chrome for Testing ZIP inside this package."""
import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import struct
import urllib.request
from urllib.parse import urlsplit
import zipfile


def checked(root, path, *, directory=False, missing=False):
    if ".." in Path(path).parts:
        raise ValueError("Parent traversal is not allowed")
    root, path = Path(root).absolute(), Path(path).absolute()
    if not path.is_relative_to(root):
        raise ValueError("Browser path must remain inside the package")
    if os.name == "nt" and (str(path).startswith("\\\\") or ":" in str(path)[2:]):
        raise ValueError("Device and stream paths are not allowed")
    for part in reversed((path, *path.parents)):
        try:
            entry = part.lstat()
        except FileNotFoundError:
            continue
        if (stat.S_ISLNK(entry.st_mode) or
                getattr(entry, "st_file_attributes", 0) & 0x400 or
                (stat.S_ISREG(entry.st_mode) and entry.st_nlink != 1)):
            raise ValueError("Browser paths must not contain links")
    try:
        entry = path.lstat()
    except FileNotFoundError:
        if missing:
            return path
        raise
    if not (stat.S_ISDIR(entry.st_mode) if directory else stat.S_ISREG(entry.st_mode)):
        raise ValueError("Unexpected browser path type")
    return path


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def archive_name(name):
    parts = PurePosixPath(name).parts
    if (not name or "\\" in name or name.startswith("/") or len(parts) < 2 or
            parts[0] != "chrome-win64" or "/".join(parts) != name or
            any(part in (".", "..") or part.endswith((" ", ".")) or
                re.search(r'[\x00-\x1f<>:"|?*]', part) or
                re.match(r"^(?:CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\.|$)", part, re.I)
                for part in parts)):
        raise ValueError("Unsafe browser archive member")
    return parts


def load_manifest(root):
    automation = root / "tool/automation"
    versions = json.loads(checked(root, automation / "versions.json").read_text(encoding="utf-8"))
    manifest = json.loads(checked(root, automation / "browser-manifest.json").read_text(encoding="utf-8"))
    browser = versions["browser"]
    version, revision = browser["version"], browser["revision"]
    if (not re.fullmatch(r"\d+\.\d+\.\d+\.\d+", version) or
            not re.fullmatch(r"\d+", revision) or
            manifest["schemaVersion"] != 1 or manifest["platform"] != "win32-x64" or
            manifest["browserVersion"] != version or manifest["revision"] != revision):
        raise ValueError("Browser version lock mismatch")
    archive = manifest["archive"]
    official = f"https://storage.googleapis.com/chrome-for-testing-public/{version}/win64/chrome-win64.zip"
    source = f"https://cdn.playwright.dev/builds/cft/{version}/win64/chrome-win64.zip"
    if browser.get("revisionSource") == "chrome-for-testing":
        if browser.get("channel") != "stable" or browser.get("downloadUrl") != official:
            raise ValueError("Invalid stable Chrome for Testing identity")
        source = official
    elif browser.get("revisionSource") is not None or browser.get("channel") is not None:
        raise ValueError("Unknown browser revision source")
    if (archive["resolvedUrl"] != official or
            archive["sourceUrl"] != source or
            not re.fullmatch(r"[a-f0-9]{64}", archive["sha256"]) or
            not isinstance(archive["size"], int) or not 0 < archive["size"] <= 1024**3):
        raise ValueError("Invalid pinned browser archive")
    prefix = f"tool/automation/browsers/chromium-{revision}/"
    if browser["executable"] != f"browsers/chromium-{revision}/chrome-win64/chrome.exe":
        raise ValueError("Unexpected browser executable")
    entries = {}
    for name, item in manifest["files"].items():
        if not name.startswith(prefix):
            raise ValueError("Browser inventory outside pinned revision")
        relative = name[len(prefix):]
        archive_name(relative)
        if (relative.casefold() in entries or not re.fullmatch(r"[a-f0-9]{64}", item["sha256"]) or
                not isinstance(item["size"], int) or item["size"] < 0):
            raise ValueError("Invalid browser inventory entry")
        entries[relative.casefold()] = relative
    if (manifest["fileCount"] != len(entries) or
            manifest["uncompressedBytes"] != sum(x["size"] for x in manifest["files"].values()) or
            prefix + "chrome-win64/chrome.exe" not in manifest["files"]):
        raise ValueError("Invalid browser inventory totals")
    return manifest, prefix


def verify_payload(root, manifest):
    root = Path(root).absolute()
    revision = checked(root, root / f"tool/automation/browsers/chromium-{manifest['revision']}", directory=True)
    actual = set()
    pending = [revision]
    while pending:
        directory = checked(root, pending.pop(), directory=True)
        for entry in directory.iterdir():
            # Reuse the existing link/reparse and single-link file guards.
            info = entry.lstat()
            if stat.S_ISDIR(info.st_mode):
                pending.append(checked(root, entry, directory=True))
            else:
                actual.add(checked(root, entry).relative_to(root).as_posix())
    if actual != set(manifest["files"]):
        raise ValueError("Pinned browser payload inventory differs")
    for name, item in manifest["files"].items():
        target = checked(root, root / name)
        if target.stat().st_size != item["size"] or digest(target) != item["sha256"]:
            raise ValueError("Pinned browser payload has changed: " + name)
    executable = root / f"tool/automation/browsers/chromium-{manifest['revision']}/chrome-win64/chrome.exe"
    with executable.open("rb") as stream:
        if stream.read(2) != b"MZ":
            raise ValueError("Browser is not a Windows executable")
        stream.seek(0x3C)
        stream.seek(struct.unpack("<I", stream.read(4))[0])
        if stream.read(6) != b"PE\0\0\x64\x86":
            raise ValueError("Browser is not Windows x64")


def payload_state(root, manifest, prefix):
    destination = checked(root, root / prefix, directory=True, missing=True)
    if not destination.exists():
        return "missing"
    try:
        verify_payload(root, manifest)
    except (FileNotFoundError, ValueError, struct.error):
        # Never install over an existing revision, even when only the EXE is missing.
        return "incomplete"
    return "verified"


def report_payload_state(manifest, state):
    revision_path = f"tool/automation/browsers/chromium-{manifest['revision']}"
    actions = {
        "missing": f"Pinned revision directory {revision_path} is missing; rerun with -Install.",
        "incomplete": f"Existing pinned revision {revision_path} is incomplete or changed; restore the same version from a verified package. Do not remove the browser profile.",
        "verified": f"Pinned browser files verified in {revision_path}.",
    }
    print(json.dumps({"verified": state == "verified", "state": state,
                      "version": manifest["browserVersion"], "files": manifest["fileCount"],
                      "action": actions[state]}))
    return 0 if state == "verified" else 1


def extract_archive(root, archive, stage, manifest, prefix):
    checked(root, archive)
    checked(root, stage, directory=True)
    if archive.stat().st_size != manifest["archive"]["size"] or digest(archive) != manifest["archive"]["sha256"]:
        raise ValueError("Pinned browser archive digest differs")
    expected = {name[len(prefix):]: item for name, item in manifest["files"].items()}
    with zipfile.ZipFile(archive) as source:
        seen = set()
        for item in source.infolist():
            archive_name(item.filename)
            if (item.filename.casefold() in seen or item.is_dir() or
                    stat.S_IFMT(item.external_attr >> 16) == stat.S_IFLNK or
                    item.filename not in expected or item.file_size != expected[item.filename]["size"]):
                raise ValueError("Unexpected browser archive inventory")
            seen.add(item.filename.casefold())
        if seen != {name.casefold() for name in expected}:
            raise ValueError("Browser archive is incomplete")
        for item in source.infolist():
            target = checked(root, stage.joinpath(*archive_name(item.filename)), missing=True)
            checked(root, target.parent, directory=True, missing=True).mkdir(parents=True, exist_ok=True)
            checked(root, target, missing=True)
            checksum = hashlib.sha256()
            with source.open(item) as incoming, target.open("xb") as outgoing:
                while block := incoming.read(1024 * 1024):
                    checksum.update(block)
                    outgoing.write(block)
            if checksum.hexdigest() != expected[item.filename]["sha256"]:
                raise ValueError("Extracted browser file digest differs")


class _RejectBrowserDownloadRedirect(urllib.request.HTTPRedirectHandler):
    # The manifest pins the exact resolved Google Storage URL, not a release
    # page requiring a CDN handoff. Refuse any 3xx *before* making a second
    # HTTP request to an unreviewed host.
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ValueError("Pinned browser download must not redirect")


def download_archive(root, session, manifest):
    target = checked(root, session / "chrome-win64.zip", missing=True)
    # Explicit proxy mapping prevents urllib from consulting the host Windows registry.
    proxies = {name: os.environ.get(name + "_proxy") or os.environ.get(name.upper() + "_PROXY")
               for name in ("http", "https", "no")}
    all_proxy = os.environ.get("all_proxy") or os.environ.get("ALL_PROXY")
    if proxies["http"] or proxies["https"] or all_proxy:
        # The launcher already supplies an HTTP CONNECT bridge for SOCKS.
        # urllib does not honor ALL_PROXY; without HTTPS_PROXY it would go
        # direct. Never silently replace the explicitly selected transport.
        proxy = urlsplit(proxies["https"] or "")
        if proxy.scheme != "http" or not proxy.hostname:
            raise ValueError("Pinned browser download requires the configured HTTP proxy/bridge")
    opener = urllib.request.build_opener(
        urllib.request.ProxyHandler({k: v for k, v in proxies.items() if v}),
        _RejectBrowserDownloadRedirect())
    metadata = manifest["archive"]
    with opener.open(metadata["resolvedUrl"], timeout=60) as response:
        # Check the exact locked response location before creating any file.
        # _RejectBrowserDownloadRedirect already blocked each real 3xx hop.
        if response.url != metadata["resolvedUrl"]:
            raise ValueError("Unexpected browser download redirect")
        with target.open("xb") as outgoing:
            total = 0
            while block := response.read(1024 * 1024):
                total += len(block)
                if total > metadata["size"]:
                    raise ValueError("Browser archive exceeds pinned size")
                outgoing.write(block)
    return target


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--install", action="store_true")
    parser.add_argument("--session", type=Path)
    options = parser.parse_args()
    root = Path(__file__).absolute().parents[2]
    checked(root, Path(__file__).absolute())
    checked(root, root / "env.ps1")
    manifest, prefix = load_manifest(root)
    destination = checked(root, root / prefix, directory=True, missing=True)
    if options.check or not options.install or destination.exists():
        return report_payload_state(manifest, payload_state(root, manifest, prefix))
    if os.name != "nt":
        raise ValueError("Install the Windows x64 browser from Windows x64")
    if options.session is None:
        raise ValueError("Use the portable PowerShell installer")
    session = checked(root, options.session, directory=True)
    if session.parent != root / "tmp" or not re.fullmatch(r"browser-install-[a-f0-9]{32}", session.name):
        raise ValueError("Use an owned browser installation session")
    archive = download_archive(root, session, manifest)
    stage = checked(root, session / "payload", directory=True, missing=True)
    stage.mkdir()
    extract_archive(root, archive, stage, manifest, prefix)
    checked(root, destination.parent, directory=True, missing=True).mkdir(parents=True, exist_ok=True)
    checked(root, destination, directory=True, missing=True)
    if destination.exists():
        raise ValueError("Browser destination appeared during installation")
    stage.rename(destination)
    verify_payload(root, manifest)
    print(json.dumps({"installed": True, "version": manifest["browserVersion"], "files": manifest["fileCount"]}))


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as error:
        # Network exceptions may contain proxy credentials; callers receive a bounded error.
        raise SystemExit("Pinned browser installation/check failed (" + type(error).__name__ + ").")
