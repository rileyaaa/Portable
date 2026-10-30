#!/usr/bin/env python3
"""One-time, fail-closed upgrade of pinned Windows Codex Portable runtime.

Invoked only by the owner's Windows GitHub Actions runner. Does not push or
publish; the workflow validates and commits the resulting checked-out files.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
from pathlib import Path, PurePosixPath
import re
import shutil
import struct
import tarfile
import tempfile

VERSION = "0.166.0"
OLD = "0.164.0"
TARGET = "x86_64-pc-windows-msvc"
ARCHIVE = "codex-package-x86_64-pc-windows-msvc.tar.gz"
SOURCE = f"https://github.com/openai/codex/releases/download/rust-v{VERSION}/{ARCHIVE}"
SOURCE_SHA256 = "d559bb88e74d471265857b93b7f19bc250dae527673b9191b33534478093f6bc"
UPSTREAM = {
    "codex.exe": "bin/codex.exe",
    "codex-code-mode-host.exe": "bin/codex-code-mode-host.exe",
    "codex-exec-server.exe": "bin/codex-exec-server.exe",
    "codex-command-runner.exe": "codex-resources/codex-command-runner.exe",
    "codex-windows-sandbox-setup.exe": "codex-resources/codex-windows-sandbox-setup.exe",
    "codex-path/rg.exe": "codex-path/rg.exe",
}
# Independent raw assets from the same pinned official GitHub release.
PUBLISHED_BIN_SHA256 = {
    "codex.exe": "9d563ee4e0441ff9d59d612013e0460ddf8e5709735c2d9f6b98b7ef8ca4eb42",
    "codex-code-mode-host.exe": "977c1f01c9efac0bfe1b9032717c95f92e1c965c8441a8dacbfe824c5c79a527",
    "codex-exec-server.exe": "eda5263b31e0354347e7bcdc434aff82f5c630ddba69f13449742a64e1836a37",
    "codex-command-runner.exe": "5e68e3f5b4640af55db2873a0d0dc038907145708f9e735870d9279a8074c2df",
    "codex-windows-sandbox-setup.exe": "3995c4f57199eb8023a0f3a585f6e9fdc4d5174c22a51837aaeb15beb52954f0",
}


# The audited output scope is also enforced against the Git index by Actions.
EXPECTED_UPGRADE_PATHS = frozenset({
    '.gitattributes',
    'codex.exe',
    'codex-code-mode-host.exe',
    'codex-exec-server.exe',
    'codex-command-runner.exe',
    'codex-windows-sandbox-setup.exe',
    'codex-package.json',
    'codex-path/rg.exe',
    'tool/runtime-manifest.json',
    'run-codex.ps1',
    'env.ps1',
    'login-json.ps1',
    'README.md',
    'DEVELOPMENT.md',
    'tool/工具更新说明.md',
    'tool/package-release.py',
    'Version_History/常用模式专用包-run-codex.ps1',
    'Version_History/常用模式专用包-env.ps1',
    'Version_History/YOLO mode专用包-run-codex.ps1',
    'Version_History/YOLO mode专用包-env.ps1',
    'tests/test_runtime_package.py',
    'tests/test_release_package.py',
    'tests/test_runtime_preflight.ps1',
})


def require(condition: bool, description: str) -> None:
    if not condition:
        raise ValueError(description)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1048576), b""):
            digest.update(chunk)
    return digest.hexdigest()


def replace_once(data: bytes, before: bytes, after: bytes, what: str) -> bytes:
    require(data.count(before) == 1, "Expected unique patch anchor: " + what)
    return data.replace(before, after, 1)


def put(changes: dict[str, bytes], root: Path, relative: str, data: bytes) -> None:
    path = root / relative
    require(path.is_file(), "Expected source file: " + relative)
    changes[relative] = data


def patch_run(data: bytes, manifest_sha: str, hashes: dict[str, str]) -> bytes:
    require(data.count(OLD.encode()) >= 4, "Old launcher version not recognized")
    data = data.replace(OLD.encode(), VERSION.encode())
    for variable, value in (
        ("ExpectedRuntimeManifestSha256", manifest_sha),
        ("ExpectedCodexSha256", hashes["codex.exe"]),
        ("ExpectedCodeModeHostSha256", hashes["codex-code-mode-host.exe"]),
    ):
        before = re.search(rb'\$' + variable.encode() + rb' = "[A-Fa-f0-9]{64}"', data)
        require(before is not None, "Missing launcher identity: " + variable)
        data = replace_once(data, before.group(), (f'${variable} = "{value.upper()}"').encode(), variable)
    return data


def validate_pe(name: str, data: bytes) -> None:
    require(len(data) > 65536 and data[:2] == b"MZ", "Invalid Windows executable: " + name)
    pos = struct.unpack_from("<I", data, 0x3C)[0]
    require(pos < len(data) - 6 and data[pos:pos+6] == b"PE\0\0\x64\x86", "Not Windows x64: " + name)


def safe_member(name: str) -> None:
    require(name and not name.startswith("/") and "\\" not in name and ":" not in name,
            "Unsafe upstream archive path")
    require(all(part not in ("", ".", "..") for part in name.rstrip("/").split("/")),
            "Unsafe path segments")


def collect(archive: Path, *, fixture: bool = False) -> tuple[dict[str, bytes], dict, int]:
    require(archive.is_file(), "Missing pinned upstream archive")
    if not fixture:
        require(sha256(archive) == SOURCE_SHA256, "Official archive SHA256 mismatch")
    result = {}
    voice_count = 0
    with tarfile.open(archive, "r:gz") as tar:
        members = tar.getmembers()
        require(len(members) < 256, "Unexpectedly large archive index")
        for item in members:
            safe_member(item.name)
            require(item.isdir() or item.isfile(), "Links/special nodes forbidden in upstream archive")
        metas = [m for m in members if m.isfile() and m.name.endswith("codex-package.json")]
        require(len(metas) == 1, "Exactly one upstream codex-package.json is required")
        full = metas[0].name
        prefix = full[:-len("codex-package.json")]
        require(prefix == "" or prefix.endswith("/"), "Invalid upstream package prefix")
        files = {}
        seen = set()
        for item in members:
            require(item.name.startswith(prefix), "Archive escaped its package root")
            rel = item.name[len(prefix):].rstrip("/")
            if not rel:
                require(item.isdir(), "Archive root is not a directory")
                continue
            safe_member(rel)
            if item.isdir():
                continue
            case = rel.casefold()
            require(case not in seen, "Duplicate archive filename")
            seen.add(case)
            require(0 <= item.size <= 500_000_000, "Unexpected upstream file size")
            if rel.startswith("codex-resources/voice/"):
                voice_count += 1
                continue  # Existing text-only product explicitly excludes voice.
            require(rel in set(UPSTREAM.values()) | {"codex-package.json"},
                    "New upstream component needs explicit review: " + rel)
            f = tar.extractfile(item)
            require(f is not None, "Missing regular tar member payload")
            with f:
                data = f.read(item.size + 1)
            require(len(data) == item.size, "Truncated upstream member: " + rel)
            files[rel] = data
        require(set(files) == set(UPSTREAM.values()) | {"codex-package.json"},
                "Incomplete upstream runtime closure")
        original = json.loads(files["codex-package.json"].decode("utf-8"))
        for key, value in {
            "layoutVersion": 1, "version": VERSION, "target": TARGET, "variant": "codex",
            "entrypoint": "bin/codex.exe", "execServer": "bin/codex-exec-server.exe",
            "resourcesDir": "codex-resources", "pathDir": "codex-path",
        }.items():
            require(original.get(key) == value, "Unexpected upstream metadata " + key)
        for local, upstream in UPSTREAM.items():
            data = files[upstream]
            validate_pe(local, data)
            if not fixture and local in PUBLISHED_BIN_SHA256:
                require(hashlib.sha256(data).hexdigest() == PUBLISHED_BIN_SHA256[local],
                        "Raw official EXE digest mismatch: " + local)
            result[local] = data
    # Preserve the upstream fields but adapt entrypoint/executor paths to the root launcher.
    original["entrypoint"] = "codex.exe"
    original["execServer"] = "codex-exec-server.exe"
    result["codex-package.json"] = (json.dumps(original, indent=2, ensure_ascii=False) + "\n").encode("utf-8")
    return result, original, voice_count


def prepare(root: Path, archive: Path, fixture: bool = False) -> dict[str, bytes]:
    require(root.is_dir() and (root / ".git").exists(), "Must run in a checked-out repository")
    results, metadata, voice_count = collect(archive, fixture=fixture)
    changes = dict(results)
    path = root / "tool/runtime-manifest.json"
    current = json.loads(path.read_bytes())
    require(current["version"] == OLD and current["target"] == TARGET, "Unexpected baseline runtime version")
    current["version"] = VERSION
    current["release"] = f"https://github.com/openai/codex/releases/tag/rust-v{VERSION}"
    current["archive"] = SOURCE
    current["archive_sha256"] = SOURCE_SHA256
    record = {}
    for name, data in sorted(results.items()):
        record[name] = {"upstream_path": "codex-package.json" if name == "codex-package.json" else UPSTREAM[name],
                        "sha256": hashlib.sha256(data).hexdigest()}
        if name == "codex-package.json":
            record[name]["adaptation"] = "entrypoint and execServer adapted to the package-root portable launcher"
    current["files"] = record
    current["excluded_components"]["voice"]["upstream_file_count"] = voice_count
    current["excluded_components"]["duplicate_sandbox_resources"]["upstream_paths"] = [
        "codex-resources/codex-command-runner.exe", "codex-resources/codex-windows-sandbox-setup.exe",
    ]
    manifest = (json.dumps(current, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    changes["tool/runtime-manifest.json"] = manifest
    manifest_sha = hashlib.sha256(manifest).hexdigest()

    root_run = (root / "run-codex.ps1").read_bytes()
    target_run = patch_run(root_run, manifest_sha, {k:hashlib.sha256(v).hexdigest() for k,v in results.items()})
    for name in ("run-codex.ps1", "Version_History/常用模式专用包-run-codex.ps1", "Version_History/YOLO mode专用包-run-codex.ps1"):
        require((root/name).read_bytes() == root_run, "Launcher mode copy diverged before upgrade: " + name)
        changes[name] = target_run
    root_env = (root / "env.ps1").read_bytes()
    yolo_env = (root / "Version_History/YOLO mode专用包-env.ps1").read_bytes()
    require((root/"Version_History/常用模式专用包-env.ps1").read_bytes() == root_env,
            "Default env copy diverged before upgrade")
    env_updated = root_env.replace(OLD.encode(), VERSION.encode())
    changes["env.ps1"] = env_updated
    changes["Version_History/常用模式专用包-env.ps1"] = env_updated
    changes["Version_History/YOLO mode专用包-env.ps1"] = yolo_env.replace(OLD.encode(), VERSION.encode())

    # Keep original README structure; historical DEVELOPMENT records stay intact.
    for name in ("README.md", "tool/工具更新说明.md"):
        data = (root / name).read_bytes()
        require(OLD.encode() in data, "Missing expected README/tool documentation version: " + name)
        data = data.replace(OLD.encode(), VERSION.encode())
        if name == "README.md":
            data = replace_once(data, "保留清单中的六个运行文件".encode(),
                                "保留清单中的七个运行文件".encode(), "README runtime count")
            data = replace_once(data, "当前保留六个运行文件，约 **464.5 MB**".encode(),
                                "当前保留七个运行文件（新增执行器，体积及摘要以清单为准）".encode(),
                                "README outdated runtime bytes")
            row = ("| `codex-exec-server.exe` | 0.166.0 新增独立执行器，保留官方校验字节并使用包根同目录路径；"
                   "不自动改变沙箱权限。 |\n")
            anchor = b'| `codex-code-mode-host.exe` |'
            require(data.count(anchor) == 1, "README EXE table changed")
            start = data.index(anchor)
            end = data.index(b'\n', start) + 1
            data = data[:end] + row.encode() + data[end:]
            data = replace_once(data,
                                '`codex.exe` 和配套浏览器文件使用 Git LFS 管理'.encode(),
                                '新版官方 EXE、搜索程序和配套浏览器使用 Git LFS 管理'.encode(),
                                "README LFS scope")
        else:
            data = replace_once(data, "当前六个运行文件约 464.5 MB".encode(),
                                "当前七个运行文件（含新增独立执行器）以运行清单为准".encode(),
                                "tool doc outdated runtime bytes")
            data = replace_once(data, "只适配 `codex-package.json` 的 `entrypoint`".encode(),
                                "仅适配 `codex-package.json` 的 `entrypoint` 和 `execServer` 路径".encode(),
                                "tool doc metadata adaptation")
        changes[name] = data
    development = (root/"DEVELOPMENT.md").read_bytes()
    block = ("## 2026-10-30：Codex 0.166.0 官方运行时升级（自动化候选）\n\n"
             "本次使用 GitHub Actions 从官方固定 release 下载 Windows x64 canonical package，校验归档与独立 EXE 摘要，"
             "同步主程序、Code Mode Host、执行器、沙箱助手、搜索工具及 manifest，保留包根启动和全部便携隔离策略。"
             "新版新增 codex-exec-server.exe 并适配 package metadata 的 execServer 字段；"
             "语音继续不打包，重复沙箱助手继续精简。\n\n"
             "启动器 `CODEX_TUI_FULLSCREEN_TRANSCRIPT` 默认 false、可在受控 env.local.ps1 覆盖；"
             "继续使用 `--no-daemon` 防止共享 daemon 把状态迁到包外。"
             "本提交只有经 runner 验证的文件；真正的 Windows 全量发行门禁由单独 release workflow 执行。"
             "账号登录、真实网络代理、付费模型及用户终端重绘不以合成测试冒充实测。\n\n")
    require(b"## " in development, "Cannot identify maintenance record section")
    index = development.index(b"## ")
    changes["DEVELOPMENT.md"] = development[:index] + block.encode("utf-8") + development[index:]
    preflight = (root/"tests/test_runtime_preflight.ps1").read_bytes()
    require(OLD.encode() in preflight, "Synthetic runtime preflight baseline moved")
    changes["tests/test_runtime_preflight.ps1"] = preflight.replace(OLD.encode(), VERSION.encode())
    login = (root / "login-json.ps1").read_bytes()
    previous = b"'6f267830b029ee25d9339864aa867cd45de9f8fd4c5ea007d2e63c13a0c66d36' = '0.164.0'"
    newer = ("'" + PUBLISHED_BIN_SHA256["codex.exe"] + "' = '" + VERSION + "'").encode()
    changes["login-json.ps1"] = replace_once(login, previous, newer, "login client version mapping")
    runtime_test = (root/"tests/test_runtime_package.py").read_bytes()
    runtime_test = replace_once(runtime_test,
                                b'"codex.exe", "codex-code-mode-host.exe", "codex-package.json",',
                                b'"codex.exe", "codex-code-mode-host.exe", "codex-exec-server.exe", "codex-package.json",',
                                "runtime test complete inventory")
    runtime_test = replace_once(runtime_test,
                                b'self.assertEqual(metadata["entrypoint"], "codex.exe")',
                                b'self.assertEqual(metadata["entrypoint"], "codex.exe")\n        self.assertEqual(metadata["execServer"], "codex-exec-server.exe")',
                                "runtime test executor metadata")
    changes["tests/test_runtime_package.py"] = runtime_test
    attrs = (root/".gitattributes").read_bytes()
    require(b"codex.exe filter=lfs diff=lfs merge=lfs -text" in attrs,
            "Existing Codex LFS attributes missing")
    additions = ("codex-code-mode-host.exe filter=lfs diff=lfs merge=lfs -text\n"
                 "codex-exec-server.exe filter=lfs diff=lfs merge=lfs -text\n"
                 "codex-command-runner.exe filter=lfs diff=lfs merge=lfs -text\n"
                 "codex-windows-sandbox-setup.exe filter=lfs diff=lfs merge=lfs -text\n"
                 "codex-path/rg.exe filter=lfs diff=lfs merge=lfs -text\n")
    require(b"codex-exec-server.exe filter=lfs" not in attrs,
            "LFS executor already configured")
    changes[".gitattributes"] = attrs + additions.encode("ascii")
    release_script = (root/"tool/package-release.py").read_bytes()
    release_script = replace_once(release_script, b'"codex.exe", "codex-code-mode-host.exe", "codex-command-runner.exe",',
                                  b'"codex.exe", "codex-code-mode-host.exe", "codex-exec-server.exe", "codex-command-runner.exe",',
                                  "release runtime inventory")
    release_script = replace_once(release_script, b'"entrypoint": "codex.exe", "resourcesDir": "codex-resources", "pathDir": "codex-path",',
                                  b'"entrypoint": "codex.exe", "execServer": "codex-exec-server.exe", "resourcesDir": "codex-resources", "pathDir": "codex-path",',
                                  "release metadata executor")
    changes["tool/package-release.py"] = release_script
    release_test = (root/"tests/test_release_package.py").read_bytes()
    release_test = replace_once(release_test, b'"resourcesDir": "codex-resources", "pathDir": "codex-path",',
                                b'"execServer": "codex-exec-server.exe", "resourcesDir": "codex-resources", "pathDir": "codex-path",',
                                "release synthetic fixture metadata")
    changes["tests/test_release_package.py"] = release_test
    require(set(changes) == EXPECTED_UPGRADE_PATHS,
            "Unexpected adapted change set: " + repr(set(changes) ^ EXPECTED_UPGRADE_PATHS))
    return changes


def apply(root: Path, archive: Path) -> None:
    changes = prepare(root, archive)
    for relative in changes:
        path = root / relative
        if relative not in UPSTREAM and relative != "codex-package.json":
            require(path.is_file(), "Refuse to create unexpected file: " + relative)
        else:
            require(path.parent.is_dir(), "Missing expected runtime parent: " + relative)
    for relative, data in changes.items():
        path = root / relative
        if relative.endswith(".exe"):
            validate_pe(relative, data)
        path.write_bytes(data)
    print("UPGRADE=APPLIED version=" + VERSION + " changed_files=" + str(len(changes)))
    print("RUNTIME_FILES=" + ",".join(sorted(UPSTREAM) + ["codex-package.json"]))
    print("PINNED_ARCHIVE_SHA256=" + SOURCE_SHA256)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--archive", type=Path, required=True)
    args = parser.parse_args()
    apply(args.repo.absolute(), args.archive.absolute())


if __name__ == "__main__":
    main()
