#!/usr/bin/env python3
"""Bounded APK/XAPK fingerprinting for the Windows portable package."""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import re
import shutil
import stat
import sys
import tempfile
import unicodedata
import zipfile

from portable_guard import PortablePathError, WINDOWS_RESERVED, find_portable_root, resolve_inside

MAX_OUTER_ENTRIES = 50_000
MAX_OUTER_ENTRY_BYTES = 2 * 1024 * 1024 * 1024
MAX_OUTER_TOTAL_BYTES = 4 * 1024 * 1024 * 1024
MAX_APK_ENTRIES = 100_000
MAX_DEX_ENTRY_BYTES = 768 * 1024 * 1024
MAX_DEX_TOTAL_BYTES = 2 * 1024 * 1024 * 1024
MAX_DESCRIPTORS = 750_000
MAX_ZIP_NAME_CHARS = 4096
MAX_ZIP_NAME_TOTAL_CHARS = 16 * 1024 * 1024
MAX_COMPRESSION_RATIO = 250
DEX_DESCRIPTOR = re.compile(rb"L[a-z][A-Za-z0-9_]*(?:/[A-Za-z0-9_$]+)+;")


def validate_extract_name(name: str) -> list[str]:
    if len(name) > MAX_ZIP_NAME_CHARS:
        raise PortablePathError("archive entry name is too long")
    if not name or "\\" in name or name.startswith("/") or re.match(r"^[A-Za-z]:", name):
        raise PortablePathError(f"unsafe archive entry: {name!r}")
    parts = []
    for part in name.split("/"):
        if part in ("", "."):
            continue
        if part == ".." or ":" in part or any(ord(ch) < 32 for ch in part):
            raise PortablePathError(f"unsafe archive entry: {name!r}")
        if part.endswith((".", " ")) or part.split(".", 1)[0].upper() in WINDOWS_RESERVED:
            raise PortablePathError(f"Windows-unsafe archive entry: {name!r}")
        parts.append(part)
    if not parts:
        raise PortablePathError(f"archive entry resolves to nothing: {name!r}")
    return parts


def extract_split_apks(bundle: Path, destination: Path) -> list[Path]:
    apks: list[Path] = []
    with zipfile.ZipFile(bundle) as archive:
        infos = archive.infolist()
        if len(infos) > MAX_OUTER_ENTRIES:
            raise PortablePathError("bundle has too many entries")
        total = 0
        seen_targets: set[str] = set()
        for info in infos:
            if stat.S_ISLNK(info.external_attr >> 16):
                raise PortablePathError(f"symlink entry is not allowed: {info.filename!r}")
            parts = validate_extract_name(info.filename)
            if info.file_size > MAX_OUTER_ENTRY_BYTES:
                raise PortablePathError(f"bundle entry is too large: {info.filename!r}")
            if info.file_size > 16 * 1024 * 1024 and info.compress_size > 0 and info.file_size > info.compress_size * MAX_COMPRESSION_RATIO:
                raise PortablePathError(f"bundle entry compression ratio is unsafe: {info.filename!r}")
            total += info.file_size
            if total > MAX_OUTER_TOTAL_BYTES:
                raise PortablePathError("bundle expanded size exceeds 4 GiB")
            if info.is_dir() or not info.filename.lower().endswith(".apk"):
                continue
            # Flattening is intentional, so reject colliding APK basenames.
            target_name = parts[-1]
            key = unicodedata.normalize("NFC", target_name).casefold()
            if key in seen_targets:
                raise PortablePathError(f"colliding split APK name: {target_name}")
            seen_targets.add(key)
            target = destination / target_name
            with archive.open(info) as src, target.open("xb") as dst:
                copied = 0
                while True:
                    chunk = src.read(1024 * 1024)
                    if not chunk: break
                    copied += len(chunk)
                    if copied > MAX_OUTER_ENTRY_BYTES or copied > info.file_size + 1024 * 1024:
                        raise PortablePathError(f"split APK expanded beyond declared safe size: {info.filename!r}")
                    dst.write(chunk)
            apks.append(target)
    if not apks:
        raise PortablePathError("bundle contains no APK files")
    return apks


def dex_descriptors(archive: zipfile.ZipFile, infos: list[zipfile.ZipInfo]) -> tuple[set[str], int]:
    result: set[str] = set()
    total = 0
    for info in infos:
        if not re.fullmatch(r"classes\d*\.dex", info.filename):
            continue
        if info.file_size > MAX_DEX_ENTRY_BYTES:
            continue
        total += info.file_size
        if total > MAX_DEX_TOTAL_BYTES:
            break
        tail = b""
        with archive.open(info) as fh:
            remaining = info.file_size + 1024 * 1024
            while remaining > 0:
                chunk = fh.read(min(1024 * 1024, remaining))
                if not chunk: break
                remaining -= len(chunk)
                data = tail + chunk
                for match in DEX_DESCRIPTOR.finditer(data):
                    result.add(match.group()[1:-1].decode("ascii", errors="ignore"))
                    if len(result) >= MAX_DESCRIPTORS:
                        return result, total
                tail = data[-4096:]
    return result, total


def inspect_apks(apks: list[Path]):
    names: set[str] = set()
    descriptors: set[str] = set()
    for apk in apks:
        try:
            with zipfile.ZipFile(apk) as archive:
                infos = archive.infolist()
                if len(infos) > MAX_APK_ENTRIES:
                    raise PortablePathError(f"APK has too many ZIP entries: {apk.name}")
                name_chars = 0
                for info in infos:
                    if len(info.filename) > MAX_ZIP_NAME_CHARS:
                        raise PortablePathError(f"APK entry name is too long: {apk.name}")
                    name_chars += len(info.filename)
                    if name_chars > MAX_ZIP_NAME_TOTAL_CHARS:
                        raise PortablePathError(f"APK ZIP metadata names are too large: {apk.name}")
                    names.add(info.filename)
                dex, _ = dex_descriptors(archive, infos)
                descriptors.update(dex)
                if len(descriptors) > MAX_DESCRIPTORS:
                    descriptors = set(list(descriptors)[:MAX_DESCRIPTORS])
        except zipfile.BadZipFile as exc:
            raise PortablePathError(f"invalid APK ZIP: {apk}") from exc
    universe = [*names, *descriptors]
    return names, descriptors, universe


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("input")
    args = parser.parse_args(argv)
    try:
        root = find_portable_root(__file__)
        input_path = resolve_inside(root, args.input, kind="file")
        suffix = input_path.suffix.lower()
        if suffix not in {".apk", ".xapk", ".apks", ".apkm"}:
            raise PortablePathError(f"unsupported input: {input_path}")
        tmp_base = resolve_inside(root, root / "tmp" / "android", must_exist=False)
        tmp_base.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="apkfp-", dir=tmp_base) as tmp:
            temp_dir = Path(tmp)
            apks = [input_path] if suffix == ".apk" else extract_split_apks(input_path, temp_dir)
            names, descriptors, universe = inspect_apks(apks)

        def has(pattern: str) -> bool:
            rx = re.compile(pattern)
            return any(rx.search(value) for value in universe)

        framework = "unknown"; rationale = ""
        if has(r"^lib/[^/]+/libflutter\.so$"):
            framework = "Flutter"; rationale = "lib/<abi>/libflutter.so present"
            if has(r"^lib/[^/]+/libapp\.so$"): rationale += "; libapp.so contains AOT-compiled Dart"
        elif has(r"^lib/[^/]+/libhermes\.so$") or has(r"^assets/index\.android\.bundle$") or has(r"^lib/[^/]+/libreactnativejni\.so$"):
            framework = "React Native"
            reasons = []
            if has(r"^lib/[^/]+/libhermes\.so$"): reasons.append("libhermes.so")
            if has(r"^lib/[^/]+/libreactnativejni\.so$"): reasons.append("libreactnativejni.so")
            if has(r"^assets/index\.android\.bundle$"): reasons.append("assets/index.android.bundle")
            rationale = "; ".join(reasons)
        elif has(r"^assets/www/(index\.html|cordova\.js)$") or has(r"^assets/public/index\.html$"):
            framework = "Cordova / Capacitor (WebView hybrid)"; rationale = "assets/www/ or assets/public/ shell present"
        elif has(r"^lib/[^/]+/libmonodroid\.so$") or has(r"^assemblies/"):
            framework = "Xamarin / .NET MAUI"; rationale = "libmonodroid.so or assemblies/ present"
        elif has(r"^lib/[^/]+/libmaui\.so$"):
            framework = ".NET MAUI"; rationale = "libmaui.so present"
        elif has(r"^assets/flutter_assets/"):
            framework = "Flutter (code-only split?)"; rationale = "flutter_assets/ present without libflutter.so"
        elif has(r"androidx[./]compose"):
            framework = "Native Android (Kotlin + Jetpack Compose)"; rationale = "androidx.compose libraries detected"
        elif has(r"^META-INF/.*\.kotlin_module$"):
            framework = "Native Android (Kotlin)"; rationale = "kotlin_module metadata present, no Compose markers"
        else:
            framework = "Native Android (Java/Kotlin)"; rationale = "no cross-platform framework markers found"

        http = []
        for pat, label in [(r"retrofit2", "Retrofit"),(r"okhttp3", "OkHttp"),(r"io/ktor/", "Ktor"),(r"com/apollographql/", "Apollo (GraphQL)"),(r"com/android/volley", "Volley")]:
            if has(pat): http.append(label)
        di = []
        for pat,label in [(r"dagger/hilt/","Hilt"),(r"^META-INF/.*dagger.*","Dagger"),(r"org/koin/","Koin")]:
            if has(pat): di.append(label)
        if not di and has(r"javax/inject/"): di.append("javax.inject")
        serialization = []
        for pat,label in [(r"kotlinx/serialization/","kotlinx.serialization"),(r"com/google/gson/","Gson"),(r"com/squareup/moshi/","Moshi"),(r"com/fasterxml/jackson/","Jackson")]:
            if has(pat): serialization.append(label)

        short_roots = {value.split("/",1)[0] for value in descriptors if "/" in value and 1 <= len(value.split("/",1)[0]) <= 2 and value.split("/",1)[0].islower()}
        if len(short_roots) > 30: obfuscation = f"HIGH ({len(short_roots)} single/double-letter root packages)"
        elif len(short_roots) > 10: obfuscation = f"MODERATE ({len(short_roots)} short root packages)"
        else: obfuscation = "LOW (no significant short-name namespace pollution)"

        native = sorted(name for name in names if re.fullmatch(r"lib/[^/]+/[^/]+\.so", name))
        sdks = []
        for pat,label in [
            (r"^assets/com/appsflyer/","AppsFlyer"),(r"datadog\.buildId|com/datadog/","Datadog"),(r"io/sentry/","Sentry"),
            (r"com/google/firebase/","Firebase"),(r"com/google/android/gms/","Google Play Services"),(r"com/facebook/","Facebook SDK"),
            (r"com/payu/","PayU"),(r"com/stripe/","Stripe"),(r"com/braintreepayments/","Braintree"),(r"com/storyteller/","Storyteller"),
            (r"zendesk/","Zendesk"),(r"com/intercom/","Intercom"),(r"com/segment/analytics","Segment"),(r"com/amplitude/","Amplitude"),
            (r"com/mixpanel/","Mixpanel"),(r"com/onesignal/","OneSignal"),(r"com/microsoft/clarity","Microsoft Clarity"),
            (r"com/hotjar/","Hotjar"),(r"com/instabug/","Instabug")]:
            if has(pat): sdks.append(label)
        build_config = "present (inspect BuildConfig.java after decompile)" if any(name.endswith("BuildConfig.class") for name in universe) else "not detected"

        print(f"=== APK Fingerprint: {input_path.name} ===\n")
        print(f"Framework:        {framework}\n  Rationale:      {rationale}")
        print(f"Obfuscation:      {obfuscation}\n")
        print(f"HTTP stack:       {' '.join(http) if http else 'none detected'}")
        print(f"DI:               {' '.join(di) if di else 'none detected'}")
        print(f"Serialization:    {' '.join(serialization) if serialization else 'none detected'}")
        print(f"BuildConfig:      {build_config}\n")
        print(f"Third-party SDKs: {' '.join(sdks) if sdks else 'none detected'}")
        print("\nNative libraries (consolidated across splits):")
        if native:
            for name in native: print(f"  {name}")
        else:
            print("  (none)")
        return 0
    except (PortablePathError, OSError, ValueError, zipfile.BadZipFile) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
