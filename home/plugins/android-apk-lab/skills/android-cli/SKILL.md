---
name: android-cli
description: "Use only for an explicitly requested Android/APK task. Provides instructions for installing and using the `android` CLI. The `android` command-line tool is a critical tool for Android development and helps you create new Android projects, run Android apps on devices, manage and interact with Android virtual devices (including screenshots and UI inspection), manage Android SDK components, look up official Android documentation, and discover and install official Android skills."
---

## Task activation

Loading this skill, detecting an APK, or entering maintenance mode does not authorize execution. Do not run prerequisite probes, ADB, device discovery, servers, downloads, or installations until the user has requested the relevant Android/APK task. Use the existing authorization for the selected target/session; do not ask again for the same authorized operation. Device/helper installation and actions outside that scope need separate authorization. Resolve the current package root from this skill/script location and validate its markers and lexical ancestors first; environment roots such as `CODEX_INSTALL_DIR` are usable only after they match that current root. Never follow a stale root after moving the package.

## APK Lab portable override
For this portable Codex package, treat any upstream examples that mention user-home installs, global package managers, system PATH edits, Homebrew, winget, choco, scoop, or OS-level install locations as layout examples only. Place tools, caches, generated files, credentials, test outputs, and temporary files under the package root (`CODEX_INSTALL_DIR`, or parent of `CODEX_HOME`). Prefer `tool/android`, `cache/android`, `tmp/android`, and `work/apk-jobs`.

Portable execution boundary:
- Resolve executable commands to package-local tools under `CODEX_INSTALL_DIR` (or Windows system components explicitly required by the launcher). Never silently use host/global npm, Appium, Git, curl, Python, Java, Android SDK, or package-manager installs. `npx` may be used only with `--no-install`, from an explicitly selected project that is itself inside the Codex package.
- A connected phone, emulator, remote Android instance, or its filesystem/state is outside the Codex package. Before reading from or changing such a target, obtain explicit user approval for that target/session. Commands that mutate device state (`adb push/install/uninstall`, `adb shell am/pm/settings/input/chmod/rm/mv/cp`, Frida/Objection injection, Maestro/Appium sessions, reboot/root/trust changes) always require that approval before execution.

# Android CLI Specialist

This skill provides instructions for using the `android` CLI tool. The tool includes various commands for creating projects, running applications, interacting with devices, and managing the CLI environment.

## Installation — Codex Portable policy

On Windows in this portable package, **never auto-install the Android CLI into the host**. First resolve `android` and verify its physical path is under `CODEX_INSTALL_DIR\tool\android\cli` (or another explicitly package-local directory). A host/global `android` binary must not be used silently.

If the package-local CLI is missing, stop and ask the user to approve a download/install for this operation. Do **not** run the upstream `install.cmd`, `winget`, Homebrew, `curl | bash`, registry installers, or user/global PATH modifications automatically. After approval, use an official direct-download artifact only when it can be safely extracted/copied into `CODEX_INSTALL_DIR\tool\android\cli`; reject absolute paths, `..`, symlinks/junctions and Windows-unsafe archive names. If a safe package-local install cannot be verified, report the blocker instead of falling back to a host install.

Prefer `android --sdk="$env:ANDROID_HOME" ...` so SDK writes remain in the package. Commands that install/update/remove SDK components, initialize CLI state, manage skills, self-update the CLI, create projects, install/run apps, or control devices can have side effects: keep filesystem targets under the package and obtain explicit user approval when the action reaches outside the package or changes an external device. Read-only commands such as `android info`, `android sdk list`, and documentation search may still require network permission.

## SDK management
To manage the installation of Android SDKs and tools, use the `sdk` command. For example:

- `android sdk install <package>[@<version>]...`: Install specific packages. Multiple packages can be specified, separated by spaces. `<version>` defaults to latest. For example: `android sdk install platforms/android-30@2 platforms/android-34`
- `android sdk update [<pkg-name>]`: Update a specific package or all packages to the latest version.
- `android sdk remove <pkg-name>`: Remove a package from the local SDK.
- `android sdk list --all`: List installed and available SDK packages.

## Project creation
Create projects from templates using the `create` command.

For example: `android create empty-activity --name="My App" --output=./my-app`

## Interacting with devices
For more information on interacting with running devices, see [here](references/interact.md)

## Running journey tests
For more information on running journeys, see [here](references/journeys.md)

## Doc searching
The `docs` command searches authoritative, high-quality Android developer documentation in the Android Knowledge Base.
By providing a few keywords, this tool will return high quality articles that contain examples or guidance on how to use Android APIs or libraries.
Use this tool to obtain additional information on how to achieve Android-specific tasks or to know more about Android APIs, surfaces, libraries, or devices.

Always use this tool to get the most up-to-date information about Android concepts. Typical good use cases are:
  - Finding migration guides for APIs.
  - Finding examples for APIs.
  - Finding up-to-date information about Android APIs.
  - Finding best practices for Android concepts.

## Running APKs
Use the `run` command to run Android apps.

## Managing emulators

On Windows, do not assume `android emulator` works: the official Android CLI documentation currently marks that command as unavailable on Windows. Use the package-local Android SDK `emulator.exe` and `adb.exe` instead until the CLI documents Windows support.

## Capturing screenshots

Capture an image of the current screen of a connected Android device and output it to a file using the `android screenshot` command.

## Managing skills

Manage agent skills for Android using the `android skills` command.

## Inspecting UI Layouts

Use the `android layout` command to inspect the UI layout of an Android application. It returns the layout tree of an Android application in JSON format. When debugging UI errors, this is often a much faster approach than taking a screenshot.

## Updating the CLI

Do not self-update silently. Before `android update`, verify the CLI binary is package-local and obtain explicit approval; abort if the updater would write to a user/global installation. Prefer replacing the package-local artifact explicitly.

# `android help` output

Usage: android [-hvV] [--sdk=PARAM] [COMMAND]
  -h, --help        Show this help message and exit.
      --sdk=PARAM   Path to the Android SDK
  -v, --verbose     Enable verbose output for troubleshooting
  -V, --version     Print version information and exit.
Commands:
  create    Create a new Android project from available templates. Allows
              specifying project name, output directory, minSdk, and dry-run
              execution.
  describe  Analyzes an Android project to generate descriptive metadata.
  docs      Android documentation commands for searching and fetching developer
              documentation from the official knowledge base.
  emulator  Manage Android Virtual Devices (AVDs). Includes commands to start,
              stop, list, and view details about emulators.
  help      Shows the help of all commands
  info      Print environment information including SDK location, connected
              devices, and configuration variables. Use specific fields to
              narrow the output.
  init      Initializes the environment for the Android CLI. Sets up required
              configurations, directories, and default skills.
  install   Install an Android Application (one or more APKs) to a connected
              device or emulator without activating any components using
              incremental optimizations for faster deployment than adb.
  layout    Returns the layout tree of an application
  run       Build, deploy, and launch an Android application on a connected
              device or emulator.
  screen    Commands to view the device
  sdk       Manage the Android SDK installation. Includes commands to install,
              update, remove, and list available and installed SDK packages.
  skills    Manage Android CLI skills. Includes commands to install, remove,
              list, and search for skills by keyword.
  studio    Android Studio commands
  update    Update the Android CLI to the latest version.

create
          Usage: android create [-h] [--verbose] [--list] [--minSdk=api]
                                --name=applicationName [-o=dest-path] [template-name]
          Create a new Android project from available templates. Allows specifying
          project name, output directory, minSdk, and dry-run execution.
                [template-name]      The template name
            -h, --help               Show this help message and exit.
                --minSdk=api         The 'minSdk' supported by the application (default
                                       is defined in the template)
                --name=applicationName
                                     The name of the application (e.g. 'My Application')
            -o, --output=dest-path   The destination project directory path (default is
                                       '.')
                --verbose            Enables verbose output
                --list               List all available templates

describe
          Usage: android describe [-hV] [--project_dir=PARAM]
          Analyzes an Android project to generate descriptive metadata.
          This command identifies and outputs the paths to JSON files that detail the
          project's structure, including build targets and their corresponding output
          artifact locations (e.g., APKs). This information enables other tools and
          commands to locate build artifacts efficiently.
            -h, --help                Show this help message and exit.
                --project_dir=PARAM   The project directory to describe
            -V, --version             Print version information and exit.

docs
          Usage: android docs [-h] [COMMAND]
          Android documentation commands for searching and fetching developer
          documentation from the official knowledge base.
            -h, --help   Show this help message and exit.
          Commands:
            search  Search Android documentation. Enclose keywords in quotes.
            fetch   Fetch an Android documentation article from a URL (kb://...)

emulator
          Usage: android emulator [-h] [COMMAND]
          Manage Android Virtual Devices (AVDs). Includes commands to start, stop, list,
          and view details about emulators.
            -h, --help   Show this help message and exit.
          Commands:
            create  Creates a virtual device
            start   Launches the specified virtual device. This command will return when
                      the emulator is fully started and ready to use.
            stop    Stops the specified virtual device
            list    Lists available virtual devices
            remove  Delete a virtual device

help
          Usage: android help [COMMAND]
          Shows the help of all commands
                [COMMAND]   The command to show help for

info
          Usage: android info <field>
          Print environment information including SDK location, connected devices, and
          configuration variables. Use specific fields to narrow the output.
                <field>   The specific field to print the value of. If omitted print all.

init
          Usage: android init
          Initializes the environment for the Android CLI. Sets up required
          configurations, directories, and default skills.

install
          Usage: android install [-hv] [--use-delta-install] [--device=PARAM]
                                 [--apks=PARAM[,PARAM...]]... [--install-options=PARAM[,
                                 PARAM...]]...
          Install an Android Application (one or more APKs) to a connected device or
          emulator without activating any components using incremental optimizations for
          faster deployment than adb.
                --apks=PARAM[,PARAM...]
                                      The paths to the APKs
                --device=PARAM        The device serial number
            -h, --help                Show this help message and exit.
                --install-options=PARAM[,PARAM...]
                                      Additional options/flags to pass to package manager
                                        install (e.g. -g,-d)
                --use-delta-install   Use fast delta install (speeds up incremental
                                        updates by transferring only modified code and
                                        resources; default: true)
            -v, --verbose             Enable verbose logging

layout
          Usage: android layout [-dhp] [--device=PARAM] [-o=PARAM]
          Returns the layout tree of an application
            -d, --diff           Returns a flat list of the layout elements that have
                                   changed since the last invocation of ui-dump
                --device=PARAM   The device serial number
            -h, --help           Show this help message and exit.
            -o, --output=PARAM   Writes the layout tree to the specified file or
                                   directory. If omitted, prints the tree to standard
                                   output
            -p, --pretty         Pretty-prints the returned JSON

run
          Usage: android run [-hv] [--debug] [--use-delta-install] [--activity=PARAM]
                             [--device=PARAM] [--type=PARAM] [--apks=PARAM[,PARAM...]]...
                             [--install-options=PARAM[,PARAM...]]...
          Build, deploy, and launch an Android application on a connected device or
          emulator.
                --activity=PARAM      The activity name
                --apks=PARAM[,PARAM...]
                                      The paths to the APKs
                --debug               Run in debug mode
                --device=PARAM        The device serial number
            -h, --help                Show this help message and exit.
                --install-options=PARAM[,PARAM...]
                                      Additional options/flags to pass to package manager
                                        install (e.g. -g,-d)
                --type=PARAM          The component type (ACTIVITY, WATCH_FACE, TILE,
                                        COMPLICATION, DECLARATIVE_WATCH_FACE, WEAR_WIDGET)
                --use-delta-install   Use fast delta install (speeds up incremental
                                        updates by transferring only modified code and
                                        resources; default: false)
            -v, --verbose             Enable verbose logging

screen
          Usage: android screen [-h] [COMMAND]
          Commands to view the device
            -h, --help   Show this help message and exit.
          Commands:
            capture  Outputs the device screen to a PNG
            resolve  Target UI elements visually

sdk
          Usage: android sdk [COMMAND]
          Manage the Android SDK installation. Includes commands to install, update,
          remove, and list available and installed SDK packages.
          Commands:
            install  Install SDK packages
            update   Update one or all packages to the latest version
            remove   Remove packages from the SDK
            list     List installed and available SDK packages

skills
          Usage: android skills [-h] [COMMAND]
          Manage Android CLI skills. Includes commands to install, remove, list, and
          search for skills by keyword.
            -h, --help   Show this help message and exit.
          Commands:
            add     [id]      Install a specific skill by its ID to your environment
            remove  [id]      Remove an installed skill by its ID
            list              List installed and available skills
            find    [keyword] Search for available skills in the repository matching a
                      keyword

studio
          Usage: android studio [-h] [COMMAND]
          Android Studio commands
            -h, --help   Show this help message and exit.
          Commands:
            find-declaration        Find declaration of a symbol
            find-usages             Find usages of a symbol
            open-file               Open a file in Android Studio
            check                   Check the status of running Studio instances
            analyze-file            Analyze a file in Android Studio
            render-compose-preview  Render a Compose preview in Android Studio
            version-lookup          Looks up the latest available versions on the
                                      internet of maven artifacts, Android versions, and
                                      more.

update
          Usage: android update [--url=PARAM]
          Update the Android CLI to the latest version.
                --url=PARAM   The URL to download the update from

## Codex Portable APK Lab constraints
- Keep all downloaded tools, generated files, test artifacts, credentials, SDK state, package-manager caches, and temporary files under the Codex package root (`CODEX_INSTALL_DIR` or the parent of `CODEX_HOME`).
- Prefer package-local paths from `ANDROID_HOME`, `ANDROID_USER_HOME`, `APKTOOL_FRAMEWORK_DIR`, `FRIDA_CACHE_DIR`, `MITMPROXY_HOME`, `APPIUM_HOME`, `APK_LAB_CACHE_DIR`, `APK_LAB_TMP_DIR`, and `APK_LAB_JOBS_DIR`.
- Before writing/deleting, resolve the final absolute path and keep it inside the package root; skip reparse points/symlinks.
- For authorized local `sqlite3.exe` / `etc1tool.exe` tasks, use the package-local absolute executable and validated task cwd with ASCII relative filenames. Native Unicode arguments are a known Windows limitation; never copy only the SQLite main file when WAL may be active, and never accept an etc1tool exit code alone. See the package's [tool update guide](../../../../../tool/工具更新说明.md#android-platform-tools-本地文件用法不涉及设备) for snapshot and output verification.
- Start Appium, device sessions, proxies, emulators, Frida, or GUI tools only for the current task and stop them when done.
