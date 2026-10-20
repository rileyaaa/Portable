---
name: appium-prepare-development-environment
description: Use only for an explicit request to edit or validate the bundled Appium workflow files. This is repository maintenance, not driver setup or a reason to probe devices or start Appium.
---

# Maintain the bundled Appium workflows

Read the current package root's `DEVELOPMENT.md` and the target repository's own instructions. Inspect only files and existing changes relevant to the requested edit; preserve unrelated user work.

This package bundles workflow instructions, not the upstream Appium skills repository's complete `contexts/`, `tools/` or readiness-summary system. Do not invent those paths or require their outputs. Validate frontmatter, actual relative links, referenced package-local paths and the affected code when present. Use package-local runtimes for a relevant check; a Markdown-only change does not require Node, npm, network or device probes.

Keep downloaded dependencies, caches, test fixtures and outputs inside the current package. Never fall back to host/global tools or alter permanent PATH. Preserve functional skill entrypoints and licences. There is one maintained Android workflow copy under `home/plugins/android-apk-lab/skills`; the outer APK router is an entrypoint, not a duplicate collection.

Driver or device provisioning is a different task and must be requested before following `../appium-setup/SKILL.md`. Report only performed validation and concrete limitations; do not claim Appium/device readiness from a documentation review.
