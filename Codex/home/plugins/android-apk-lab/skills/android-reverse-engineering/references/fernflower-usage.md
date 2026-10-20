# Fernflower / Vineflower CLI Reference

Fernflower is the JetBrains analytical Java decompiler. [Vineflower](https://github.com/Vineflower/vineflower) is the actively maintained community fork with better output quality and published releases. They share the same CLI interface.

## When to Use Fernflower vs jadx

| Scenario | Recommended |
|---|---|
| APK with resources needed | jadx |
| Standard Java JAR/library | Fernflower |
| jadx output has warnings/errors on specific classes | Fernflower on those classes |
| Complex lambdas, generics, streams | Fernflower |
| Large APK (>50MB), quick overview | jadx |
| Obfuscated Android app | jadx first, Fernflower on problem areas |
| Both decompilers available | Use `--engine both` and compare |

## Basic Usage

```bash
java -jar fernflower.jar [options] <source>... <destination>
```

- `<source>` — JAR file, class file, or directory containing class files
- `<destination>` — output directory

For a JAR input, Fernflower produces a JAR in the destination containing `.java` source files. Extract it with `unzip` to browse the sources.

## Key Options

Options use the format `-<key>=<value>`. Boolean options: `1` = enabled, `0` = disabled.

| Option | Default | Description |
|---|---|---|
| `-dgs=1` | 0 | Decompile generic signatures (recommended) |
| `-ren=1` | 0 | Rename obfuscated identifiers |
| `-mpm=60` | 0 | Max seconds per method — prevents hangs (recommended) |
| `-hes=0` | 1 | Show empty super() calls |
| `-hdc=0` | 1 | Show empty default constructors |
| `-udv=1` | 1 | Use debug variable names if available |
| `-ump=1` | 1 | Use debug parameter names if available |
| `-lit=1` | 0 | Output numeric literals as-is |
| `-asc=1` | 0 | Encode non-ASCII as unicode escapes |
| `-lac=1` | 0 | Decompile lambdas as anonymous classes |
| `-log=WARN` | INFO | Reduce output verbosity |
| `-e=<lib>` | — | Add library for context (not decompiled, improves type resolution) |

## Recommended Presets

### General use

```bash
java -jar fernflower.jar -dgs=1 -mpm=60 input.jar output/
```

### Obfuscated code

```bash
java -jar fernflower.jar -dgs=1 -ren=1 -mpm=60 input.jar output/
```

### Maximum detail

```bash
java -jar fernflower.jar -dgs=1 -hes=0 -hdc=0 -mpm=60 input.jar output/
```

### With Android SDK context (better type resolution)

```bash
java -jar fernflower.jar -dgs=1 -mpm=60 -e=$ANDROID_HOME/platforms/android-34/android.jar input.jar output/
```

## Working with APK Files

Fernflower cannot read APK/DEX files directly. In this portable package, do not reproduce the dex2jar/JAR extraction pipeline with raw host commands. Use the guarded Windows entrypoint, which keeps staging inside the package and safely validates archive extraction before materializing source files:

```powershell
& "$env:CODEX_INSTALL_DIR\home\skills\android-reverse-engineering\scripts\decompile.ps1" -InputFile app.apk -Engine fernflower -Output "$env:CODEX_INSTALL_DIR\work\apk-jobs\manual\app-fernflower"
```

The legacy Bash wrapper is documentation/compatibility only; on this Windows portable bundle, prefer the PowerShell entrypoint. Never replace its guarded extraction with `unzip`, `Expand-Archive`, `7z x`, or `zipfile.extractall` for untrusted APK/JAR/AAR input.

## Supported Input Formats

| Format | Direct support | Via dex2jar |
|---|---|---|
| `.jar` | Yes | — |
| `.class` | Yes | — |
| `.zip` (with classes) | Yes | — |
| `.apk` | No | Yes |
| `.dex` | No | Yes |
| `.aar` | No | Yes |

## Output Format

- **JAR input** → Produces `<destination>/<input-name>.jar` containing `.java` files
- **Class file input** → Produces `.java` files directly in the destination
- **No resource decoding** — Fernflower only produces Java source, never XML/resources

## Fernflower vs Vineflower

Vineflower is the recommended fork. Improvements over upstream Fernflower:

- Published releases on GitHub and Maven Central
- Better handling of modern Java (records, sealed classes, pattern matching)
- More accurate lambda and switch expression decompilation
- Active bug fixes and community maintenance
- Same CLI interface — drop-in replacement
