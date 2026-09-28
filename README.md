# codedex

**Find your own code by what it does, not what the folder is called.**

One Python file. Standard library only. No installs, no model, no server, no network.

---

## The problem

You wrote a Star Citizen themed internet radio player. Two years later you want it back.

It's in `Cleanup/Radio_Drake.py`.

Neither "Cleanup" nor "Radio_Drake" contains the word *radio* in a way you'd think to search
for, and nothing anywhere on that path says *Star Citizen*. `grep -r radio` gives you four
hundred hits across every project you've ever written. You give up and rewrite it.

But the file itself already told you exactly what it was, in its first three lines:

```
Drake Interplanetary — HCN Radio  MODEL R4-HCN
Star Citizen themed internet radio player.
Requires: PyQt6, python-vlc
```

That description exists in almost every source file you've ever written. It just isn't
searchable. So codedex reads the header of every source file once, remembers it, and
searches that instead.

```console
$ codedex find radio

3 match(es) for 'radio':

  tools/Drake Radio
     5 files, 5,813 lines, python:5, 34d ago
     | Drake Interplanetary — HCN Radio  MODEL R4-HCN
     | Star Citizen themed internet radio player.
     | Requires: PyQt6, python-vlc
     -> tools/Drake Radio/Radio_Drake.py
```

It returns **projects**, not files. The question you're asking is "which thing did I make,"
not "which lines contain this string."

---

## Install

```bash
pip install git+https://github.com/Levatat3/codedex.git
```

Or just take the single file and run it. It imports nothing outside the standard library:

```bash
python codedex.py build
```

## Tests

```bash
python -m unittest -v
```

34 tests, standard library only — no pytest, nothing to install.

---

## Use

```bash
codedex build                  # scan the tree, write the index
codedex find radio             # search
codedex find star citizen      # multiple words are ANDed
codedex list                   # every project, one line each, newest first
codedex stale --days 90        # projects nobody has touched in 90+ days
codedex find qr --scores       # show the scoring, for when ranking looks wrong
```

| Command | Does |
|---|---|
| `find <words>` | Search. Every word must land somewhere or the project is dropped. |
| `list` | Every project with a one-line description, newest first. |
| `stale [--days N]` | Projects untouched in N+ days (default 90). |
| `build` | Rescan. Run after moving things around. |

On a tree of ~950 files across 43 projects, a cold build takes about 20 seconds and a warm
rebuild about 1.5. Searches after that are instant — they read one JSON file.

---

## Nested projects

By default every top-level folder is one project. That's right for the common
`~/code/thing-one`, `~/code/thing-two` layout.

Some trees nest, though: `tools/Star Citizen/logger/main.py` should be the project
`tools/Star Citizen`, not all of `tools` lumped together. Tell it which folders merely
*hold* projects:

```bash
codedex build --category tools,games,ai
```

After a build, codedex points out folders that look like they might need this:

```
  These folders may hold several projects each rather than being
  one project:  games, tools
  If so, index their children separately with:
      codedex build --category games,tools
```

**It suggests and never applies this automatically**, on purpose. Whether `AutoCraft` is one
project with a `bot/` and a `brain/`, or a folder holding two projects, is the author's
intent — it cannot be read off the directory shape. I tried; the detector confidently got
real cases wrong in both directions. Guessing wrong silently merges unrelated projects,
which is worse than asking once.

## Configure

| Variable | Default | Does |
|---|---|---|
| `CODEDEX_ROOT` | current directory | Tree to index. |
| `CODEDEX_CATEGORIES` | unset | Same as `--category`. |
| `CODEDEX_INDEX` | unset | Exact index file path, overriding the default location. |

The index is **not** written next to the script — it goes to a per-user data directory
(`%LOCALAPPDATA%\codedex` on Windows, `$XDG_DATA_HOME/codedex` or `~/.local/share/codedex`
elsewhere), with one file per tree keyed by its absolute path. Several checkouts can each
keep their own index without colliding, and nothing is ever written into `site-packages`.

---

## How ranking works

Each search term scores against five places. **Every term must land somewhere**, or the
project is dropped entirely — that's what makes multi-word searches narrow instead of noisy.

| Signal | Weight | Why |
|---|---|---|
| file header / docstring | 10 | The author said what it is. Most trustworthy thing available. |
| README prose | 8 | Also deliberate, but often describes neighbours too. |
| folder name | 6 | Weak. Folder names are where this problem comes from. |
| file name | 4 | Weaker. `utils.py` tells you nothing. |
| body text | 2 | Last resort, for undocumented code. |

Plus a **breadth bonus**: +3 per additional file mentioning the term, capped at +15.

That cap matters more than it looks. A project that name-drops "discord bot" once in a
README should not outrank the actual Discord bot, which says it in file after file.
**Breadth of mention is the signal, not frequency.**

### Headers that don't count

A header only scores if it actually explains something. These are discarded:

- separator lines (`# ----------------`) and bare filenames (`# utils.py`)
- anything under three words
- **vendored licence text** — an MIT header describes the licence, not your project, and
  without this check every vendored dependency matches every search

### Undocumented code

Files that open straight into `import math` have no header to read. Rather than making them
invisible, codedex keeps a 700-character slice of the body at the lowest weight, so old
undocumented code stays findable by its identifiers. When a match lands there, the output
says which file it came from so you know the hit is weaker.

---

## What it is not

Being clear about this up front:

- **Not semantic.** It matches words, not meaning. Searching `music player` will not find a
  file whose docstring says "audio playback." If you want meaning, you want embeddings, and
  that means a model and a runtime — deliberately not what this is.
- **Not a code search tool.** It reads the first 4 KB of each file, not all of it. For
  searching *inside* code, use ripgrep. This answers a different question.
- **Not a documentation generator.** It reads what you already wrote. Projects with no
  docstrings and no README get thin results, and that is a fair reflection of reality.
- **Source files only.** It has a fixed extension list (Python, JS/TS, Java, C#, C/C++,
  shell, web, shaders) and skips build output, dependencies and caches.

The upside of all those noes: it runs anywhere Python runs, in one file, offline, with
nothing installed and nothing phoning home.

---

## Why it works *because* your folders are a mess

It doesn't ask you to organise anything. It works precisely because names are inconsistent:
`FQR2` is found by searching "qr code". `Bryan Test` by "spotify". `Version 5` by
"discord bot". The folder name is treated as the weakest signal, not the only one.

If your projects were already named well, you wouldn't need this.

---

## Licence

MIT. See `LICENSE`.
