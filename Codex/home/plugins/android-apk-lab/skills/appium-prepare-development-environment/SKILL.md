---
name: appium-prepare-development-environment
description: "Prepare and validate this Appium Skills repository for local development or contribution by checking the workspace, Git, Node, npm, helper scripts, Skill entrypoint structure, repository-local paths, and JavaScript syntax. Use before editing or validating repository Skills, Context Assets, examples, or tools. Do not use for Appium driver setup, existing runtime failures, or real-device signing."
---

## Codex Portable execution boundary
- Resolve executable commands to package-local tools under `CODEX_INSTALL_DIR` (plus Windows system components explicitly required by the launcher). Never silently use host/global npm, Appium, Git, curl, Python, Java, Android SDK, or package-manager installs. `npx` may be used only with `--no-install`, from an explicitly selected project that is itself inside the Codex package.
- A connected phone, emulator, remote Android instance, or its filesystem/state is outside the Codex package. Before reading from or changing such a target, obtain explicit user approval for that target/session. Commands that mutate device state (`adb push/install/uninstall`, `adb shell am/pm/settings/input/chmod/rm/mv/cp`, Frida/Objection injection, Maestro/Appium sessions, reboot/root/trust changes) always require that approval before execution.

## APK Lab portable override
For this portable Codex package, treat any upstream examples that mention user-home installs, global package managers, system PATH edits, Homebrew, winget, choco, scoop, or OS-level install locations as layout examples only. Place tools, caches, generated files, credentials, test outputs, and temporary files under the package root (`CODEX_INSTALL_DIR`, or parent of `CODEX_HOME`). Prefer `tool/android`, `cache/android`, `tmp/android`, and `work/apk-jobs`.

# Appium Repository Development Workflow

## Repository-readiness routing and handoffs

Use this Skill for repository development readiness and repository-wide
validation. Route Appium driver installation to `../appium-setup/SKILL.md` and existing runtime failures to `../appium-troubleshooting/SKILL.md`. This package does not bundle a dedicated XCUITest setup Skill; do not invent one. For explicitly requested XCUITest work, use current upstream Appium guidance and preserve the package boundary.

## Required inputs

Confirm the repository root, requested validation or edit scope, host OS and
shell, available permissions, and existing uncommitted changes that must be
preserved.

## Workflow outline

1. Load `AGENTS.md` and inspect the workspace without changing it:
   `git status --short`, repository file inventory, `node --version`,
   `npm --version`, and `npm config get registry`.
2. Verify the package-local runtime directly with `node --version` and `npm --version`. Require top-level
   `summary.requiredOk: true`; report `summary.npmConnectivityOk` separately
   and gate it only when the requested work needs network access.
3. Identify the changed or explicitly in-scope files. Read each affected Skill
   and Context Asset and verify every changed repository-relative target.
4. Make only the requested repository changes, preserving repository-first
   shared `contexts/` and `tools/` boundaries and unrelated user work.
5. For every changed Skill, verify required `name` and `description`
   frontmatter, explicit Context relationships, and provider UI metadata when
   present. Use an already installed platform validator only as optional
   evidence.
6. Run `node --check` for every changed JavaScript module. For repository-wide
   helper edits, check every module under `tools/`.
7. Run the edited helper or narrowest representative helper when practical.
8. Run `git diff --check`, then review `git status --short` and the final diff
   for unintended changes.

## Hard constraints

- Preserve uncommitted user work and avoid unrelated edits.
- If work requires Appium drivers, optional dependencies, privileged system
  packages, signing, or device authorization, stop repository readiness and
  hand off to the owning setup workflow.
- Use already installed repository analyzers or validators only as optional
  evidence. When unavailable, rely on the required repository-local checks.
- Retain reusable Context Assets and deterministic repository tools at the
  repository level unless the request explicitly changes architecture.
- Run commands step by step and rerun only the affected check after each fix.

## Completion criteria

- The Node readiness helper reports `summary.requiredOk: true`.
- `git status --short` has been reviewed so existing, in-scope, and unrelated
  changes are distinguished.
- Every changed Skill contains required frontmatter and valid explicit Context
  relationships.
- Every changed or introduced repository-local path resolves.
- Changed JavaScript modules pass syntax checks.
- The edited or representative helper passes when practical.
- `git diff --check` passes and the final diff contains no unintended changes.

## Evidence boundary

Report command status summaries, paths checked, validation results, preserved
unrelated work, and unresolved external blockers. Quote only sanitized lines
when additional evidence is requested.

## Self-Improvement Prompt

Before the final response, identify any missing, ambiguous, outdated, or
retry-causing instruction encountered in this Skill or any loaded asset.
Report the asset path and proposed wording. Leave unrelated files unchanged.

## Evidence

Example input: `Prepare this Appium skills repo for development and validate
the changed helpers.` Verify workspace state, Node/npm readiness, explicit
paths, Skill metadata, changed JavaScript syntax, the narrowest helper,
`git diff --check`, and the final diff.

## Codex Portable APK Lab constraints
- Keep all downloaded tools, generated files, test artifacts, credentials, SDK state, package-manager caches, and temporary files under the Codex package root (`CODEX_INSTALL_DIR` or the parent of `CODEX_HOME`).
- Prefer package-local paths from `ANDROID_HOME`, `ANDROID_USER_HOME`, `APKTOOL_FRAMEWORK_DIR`, `FRIDA_CACHE_DIR`, `MITMPROXY_HOME`, `APPIUM_HOME`, `APK_LAB_CACHE_DIR`, `APK_LAB_TMP_DIR`, and `APK_LAB_JOBS_DIR`.
- Before writing/deleting, resolve the final absolute path and keep it inside the package root; skip reparse points/symlinks.
- Start Appium, device sessions, proxies, emulators, Frida, or GUI tools only for the current task and stop them when done.
