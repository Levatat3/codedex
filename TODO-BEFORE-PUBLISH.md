# Release status

Honest record of what's done, what changed from the original, and what's left.

## What this folder is

A publishable port of `F:\Codes\tools\codeindex` (built 2026-08-24/25). **The original is
untouched.** Funk cleared it on 2026-09-28: *"Keyword ranking over file headers is a different
tool from recall, and nothing is shared, so Levy doesn't need our sign-off. Go ahead."*

## Blockers — all cleared

### 1. Index location — DONE

Was `os.path.dirname(__file__)`, which becomes `site-packages` once installed and is read-only
on most systems. Now a per-user data dir, one index per tree keyed by a hash of the absolute
root path:

```
C:\Users\Tyler\AppData\Local\codedex\codes-dae811ac2d.json
C:\Users\Tyler\AppData\Local\codedex\testtree-0681e3d982.json
```

`CODEDEX_INDEX` overrides it. Verified: two trees indexed from one install, no collision.

### 2. Categories — DONE, but not the way it was planned

The plan was auto-detection. **I built it, measured it, and it was wrong**, so it was cut.

The heuristic (a folder with no source files of its own whose children have them) produced
`Archive-2024, AutoCraft, Lev, ai, games, novelty` on `F:\Codes`. Two errors:

- **Missed `tools`** — one loose `bigxfer.py` at its top level made it look like a project.
- **Wrongly added `AutoCraft`** — one project whose parts live in `bot/`, `brain/`, `referee/`.

The result was a regression: `find radio` returned the whole `tools` category instead of
`tools/Drake Radio`. A second heuristic based on project markers (`.git`, `README`,
`pyproject.toml`) fails on `AutoCraft` for the same reason — its subfolders each look like
projects.

**This is intent, not structure, and cannot be inferred.** So: the default is no categories
(correct for the common flat layout), `--category` / `CODEDEX_CATEGORIES` sets them, and a
build *suggests* candidates with the exact command to apply them. Never silently wrong.

Known nit: once you apply categories, it will keep suggesting any it still considers a
candidate (`AutoCraft` on this tree). Accurate, mildly naggy, would need a persisted
"declined" list to fix. Left alone deliberately.

### 3. `pip install` — DONE, verified

```
codedex-0.1.0-py3-none-any.whl   14,073 bytes
```

Built with `pip wheel . --no-deps`, installed into a clean throwaway venv, and exercised
through the `codedex.exe` console script — not by running the source file.

| Test | Result |
|---|---|
| `codedex --help` | correct usage, all four subcommands |
| `build` from a fresh cwd, zero config | 4 files / 3 projects, index to the per-user dir |
| category suggestion on the fresh tree | correctly flagged `holder`, did not apply it |
| `build --category holder` | 4 projects, `holder/alpha` and `holder/beta` split out |
| `find radio` | correct project, docstring shown as evidence |
| `find qr clipboard` | multi-word AND works |
| `list` | correct, newest first |
| bare `codedex radio` shorthand | works |
| two trees indexed from one install | both index files coexist |

### 4. Homepage URL — DONE

`pyproject.toml` → `https://github.com/Levatat3/codedex`.

## Left to do

- **Push.** Tyler's, not mine. Repo is committed locally and ready; see below.
- **Licence attribution.** `LICENSE` says "Tyler (Levatat3)" and `pyproject.toml` carries the
  gmail. Change if you'd rather publish as Boolin Inc. or a different contact.
- **No tests.** The table above is a manual run, not a suite. A dozen cases over a small
  fixture tree would make this credible to anyone considering depending on it. This is the
  main thing still standing between "works" and "production".
- **`SOURCE_EXT` is fixed** — no Go, Rust, Ruby, PHP, Lua, Kotlin, Swift. Cheap to add and it
  widens the audience considerably.
- **README prose uses Windows paths** in places. The tool is fine cross-platform; it has only
  been *run* on Windows.

## Safety notes

- `index.json` is gitignored. It describes the user's entire tree and must never be committed.
  The one generated during testing was deleted.
- `codedex.py.bak-preblockers` is the pre-fix copy, gitignored.

## To push (yours to run)

```bash
cd "F:\Codes\codedex"
gh repo create codedex --public --source=. --remote=origin --push
```

Or make the repo by hand at github.com/new and then:

```bash
git remote add origin https://github.com/Levatat3/codedex.git
git push -u origin main
```
