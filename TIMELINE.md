# codedex — timeline

What we built, changed and fixed, newest first. Written from the Claude chats by `F:\Tools\ClaudeKit-Windows\timeline`.
**draft** = written automatically and nobody has checked it yet. Edit anything; an edited entry is never overwritten.

<!-- tl:71b16b6d:codedex:2026-09-28 claude -->
### 2026-09-28 · codeindex ported to publishable codedex project
- New folder F:\Codes\codedex holds a publishable copy of tools\codeindex (original untouched). Named codedex - free on PyPI, keeps the lineage.
- Ported for portability: ROOT now CODEDEX_ROOT or cwd instead of hardcoded F:\Codes; CATEGORY_DIRS now from CODEDEX_CATEGORIES instead of Tyler's own folder names. Scoring and search logic unchanged.
- Smoke-tested after port: build 940 files / 43 projects / 21.0s; 'find radio' and 'find discord bot' both rank correctly.
- Added README, MIT LICENSE, pyproject.toml, .gitignore, TODO-BEFORE-PUBLISH.md. Blockers: index writes next to script (breaks pip install), categories should auto-detect, pip install untested.
- Funk cleared it 2026-09-28 - different tool from recall, nothing shared, no sign-off needed.

_Files: `README.md`, `TODO-BEFORE-PUBLISH.md` · Chat: “Internet service ideas” · claude_
