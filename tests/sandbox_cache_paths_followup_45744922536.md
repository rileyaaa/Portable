# Narrow followup to Windows 45744922536 (a96e0c70)

Preserve the two earlier course/candidate JSONs, original official ZIP audit and 45744922536 report byte-for-byte. No re-run of course dual windows, 50/50, disconnect, Office round trips or OCR language preflight on the same images. 45744922536 source 96a24513: both modes Office merge/comment/add_slide and malformed archive scratch cleanup PASS_ACTUAL; both genuine restricted tokens; outside write denied. Its new-file create/delete succeeded at allowed roots. Preexisting fixture open r+b failed in 2 normal and 5 maintenance allowed roots. It did not distinguish owner/group DACL, file attributes, combined access versus write-only, or reopening a sandbox-created file. Do not conclude a launcher defect yet.

## ACL and SSH

Fixed official runtime rust-v0.172.0 -> 3d86e43b075adeba2193ec5c22ac92f55afd82e6:
- windows-sandbox-rs/src/acl.rs WRITE_ALLOW_MASK = FILE_GENERIC_READ | FILE_GENERIC_WRITE | FILE_GENERIC_EXECUTE | DELETE; inheritance avoids parent DELETE_CHILD bypass. The capability ACE is not the ordinary Windows user's access grant.
- spawn_prep.rs prepares a capability per actual write root; token.rs builds WRITE_RESTRICTED with capability, logon and Everyone SIDs, not an extra user SID for the legacy backend. Keep launcher and ACLs unmodified. Read ordinary token user, enabled versus deny-only group and restricting-SID mask categories from synthetic objects without recording raw identities or ACLs. Test pre-created non-readonly files, write-only and r+b, native open requested rights, close/reopen a sandbox-created file. Check original bytes and denied-root behavior. Do not automatically change ACLs, elevate or retry outside sandbox.
- SSH work/ssh creation succeeded but access to it denied (WinError 5), work/ssh/keys does not yet exist. Previous mkdir(0700) diagnostic reproduced failure under both real tokens; 0777 control succeeded. Python 3.14 Windows mkdir(0700) protected DACL and current private-directory policy explain the root cause hypothesis; direct runner keygen succeeded but that process was elevated and unrestricted, not proof of ordinary-user or sandbox success. Read host-side DACL of the synthetic failed work/ssh only, correlate with native evidence. Preserve 0700 and private-key policy. No safe tested fix granting access without changing that boundary; keep unresolved/known restriction unless native evidence changes. No remote SSH.

## System cache

Previous exact pristine ZIP integrity: 9147 members. Native refresh removed 12 old paths, added 5, changed 8 non-marker files, same marker 408224ce9771867c in two launches, non-system shipped members unchanged. Official fixed source tree contains 52 asset blobs; the observed 12 removed and 5 added names exactly correspond to the official source-set difference excluding marker. Many existing Git blobs differ only in Windows CRLF (e.g. imagegen/SKILL.md normalized equals official). Verify all actual runtime bytes against the pinned source inventory, allowing only exact blob or fully CRLF UTF-8 checkout conversion proven by re-hashing LF bytes, binary exact. Require identical per-file actual SHA256 across independent normal and maintenance launches, exact marker, unchanged non-system members and custom skill file set. Only then replace stale seeded .system with these already-embedded, verified bytes (not new skills/feature upgrades). No blanket ignore. A new exact ZIP from a successful seed correction must be checked and its normal startup must preserve the corrected member bytes. Old candidate and official ZIP are different evidence.

## Existing CLI boundaries

- f2py fixed NumPy 2.4.6: f2py2e.py get_newer_options calls (' '.join(iline)).split(). Previously actual relative path signature generation passed in all modes. Distinguish direct bundled module and wrapper, Chinese relative without spaces versus space-relative and absolute Chinese-space inputs. No wheel edits or compiler claim.
- Android Platform Tools 37.0.1 sqlite3/etc1tool: previous actual relative ASCII DB and image round trips passed, original absolute Unicode failures. Direct bundled executable, verify real DB contents / image pixels, separate Chinese relative, space-relative and absolute Chinese-space. No ADB device, host fallback, renaming user files or global PATH changes.
- HTTPX 0.28.1 METADATA cli extra requires click==8.*, pygments==2.*, rich>=10,<14. Fixed input pins rich==15.0.0 and Pygments 2.20.0; Click absent from fixed input. Its __init__.py fallback explicitly exits 1 if optional CLI imports fail. Prior actual CLI known-limit and HTTP library consumer evidence are separate. No install or downgrade. Verify actual metadata/import availability and CLI refusal once, not repeat network consumer.
- Existing independent rg PATH priority was already proven in normal/maintenance/YOLO 45741929384, and tool/工具更新说明.md explicitly keeps Codex runtime rg first; keep both binaries and no PATH change.

## Chinese OCR source exploration, no runtime installation

Actual previous hosted win25-vs2026 and win22 each returned only en-US; do not repeat them. Microsoft WinRT AvailableRecognizerLanguages requires the OS language pack. GitHub larger Windows x64 custom images require configured runner group/authorized organizational infrastructure; connector cannot list available self-hosted runners, no evidence of a preconfigured authorized Chinese machine. Do not schedule an unknown self-hosted label or install Windows language components.

A more concrete offline candidate is official MSYS2 UCRT64 native Tesseract package (not an installer), public package index 5.5.4-1 SHA256 a38f3f00d23ff9e05f2e6df87a65ec7f10b6735b131548e87aa15016a79538b2, with chi_sim model 4.1.0-3 SHA256 a618b5e820ae86c600d68ee93295873a3b73ea2a471c8d15d2a59dc8313c45f1. Both listed Apache-2.0; actual code/model notices must travel with distribution. Tesseract needs cc-libs, curl, ICU, leptonica, libarchive, omp plus recursive DLL closure. MSYS2 explicitly says package metadata license labels may be incomplete. These are publisher metadata, not downloaded or independently verified package bytes. Remaining minimum: pinned signed archive + recursive native import/delay-import closure and each applicable license/NOTICE/source obligations, safe in-package extraction and runtime DLL search, actual moved Windows offline Chinese+digits recognition/provenance and no host writes. No verified complete redistributable closure yet; no unverified Tesseract binary, language or package added, no runtime pip. Chinese OCR remains blocked, not English substitute.

Public sources:
- https://github.com/openai/codex/blob/3d86e43b075adeba2193ec5c22ac92f55afd82e6/codex-rs/skills/src/lib.rs
- https://github.com/openai/codex/blob/3d86e43b075adeba2193ec5c22ac92f55afd82e6/codex-rs/windows-sandbox-rs/src/acl.rs
- https://github.com/openai/codex/blob/3d86e43b075adeba2193ec5c22ac92f55afd82e6/codex-rs/windows-sandbox-rs/src/token.rs
- https://docs.python.org/3.14/library/os.html#os.mkdir
- https://learn.microsoft.com/en-us/uwp/api/windows.media.ocr.ocrengine.availablerecognizerlanguages?view=winrt-26100
- https://docs.github.com/en/actions/how-tos/manage-runners/larger-runners/use-custom-images
- https://packages.msys2.org/packages/mingw-w64-ucrt-x86_64-tesseract-ocr?repo=ucrt64
- https://packages.msys2.org/packages/mingw-w64-ucrt-x86_64-tesseract-data-chi_sim
- https://www.msys2.org/license/
- https://github.com/tesseract-ocr/tessdata_fast/blob/main/LICENSE
