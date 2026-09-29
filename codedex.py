#!/usr/bin/env python3
"""
codedex - find your own code by what it DOES, not what the folder is called.

The problem this solves: "Cleanup\\Radio_Drake.py" is a Star Citizen themed
radio player. Nothing in the folder name says radio, or Star Citizen. But the
file's own docstring says both, in the first three lines.

So: read the header of every source file once, remember it, and search that.

    python codedex.py build          scan the tree, write index.json
    python codedex.py find radio     search
    python codedex.py list           every project, one line each
    python codedex.py stale          projects not touched in 90+ days

Stdlib only. No installs.
"""

import os
import re
import sys
import hashlib
import json
import time
import argparse
from datetime import datetime, timedelta

# --------------------------------------------------------------------------
# config
# --------------------------------------------------------------------------

ROOT = os.environ.get("CODEDEX_ROOT") or os.getcwd()


def data_dir():
    """Per-user directory for generated indexes.

    Never beside the script: once pip-installed that is site-packages, which is
    read-only on most systems.
    """
    if os.name == "nt":
        base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~/AppData/Local")
    else:
        base = os.environ.get("XDG_DATA_HOME") or os.path.expanduser("~/.local/share")
    d = os.path.join(base, "codedex")
    os.makedirs(d, exist_ok=True)
    return d


def index_path_for(root):
    """One index per tree, so several checkouts can each keep their own."""
    override = os.environ.get("CODEDEX_INDEX")
    if override:
        return override
    key = os.path.normcase(os.path.abspath(root))
    digest = hashlib.sha1(key.encode("utf-8", "replace")).hexdigest()[:10]
    stem = os.path.basename(key.rstrip("\\/")) or "root"
    slug = re.sub(r"[^A-Za-z0-9]+", "-", stem).strip("-").lower() or "root"
    return os.path.join(data_dir(), slug + "-" + digest + ".json")

# directories never worth reading - build output, dependencies, caches
SKIP_DIRS = {
    "__pycache__", "node_modules", ".git", ".gradle", ".idea", ".vs",
    "venv", ".venv", "env", "build", "dist", "out", "obj", "bin",
    "site-packages", "target", ".pytest_cache", ".mypy_cache",
    "localpycs", "geojson_cache", "pygame_textures_cache",
    "pyvista_textures_cache",
    "codedex",            # this tool - its docstring name-drops other projects
}

# Extension -> language label. The label is only used for the "python:12, go:3"
# summary and to pick a comment style in extract_header(), so near-neighbours
# can share one.
SOURCE_EXT = {
    ".py": "python", ".pyw": "python",
    ".js": "js", ".mjs": "js", ".cjs": "js",
    ".ts": "js", ".jsx": "js", ".tsx": "js",
    ".java": "java", ".kt": "kotlin", ".kts": "kotlin", ".scala": "scala",
    ".cs": "csharp", ".fs": "fsharp",
    ".c": "c", ".h": "c", ".cpp": "c", ".cc": "c", ".cxx": "c",
    ".hpp": "c", ".hh": "c",
    ".go": "go", ".rs": "rust", ".zig": "zig", ".swift": "swift",
    ".dart": "dart", ".nim": "nim",
    ".rb": "ruby", ".rake": "ruby",
    ".php": "php", ".pl": "perl", ".pm": "perl",
    ".ex": "elixir", ".exs": "elixir", ".jl": "julia", ".r": "r",
    ".lua": "lua", ".hs": "haskell", ".sql": "sql",
    ".clj": "clojure", ".cljs": "clojure", ".el": "lisp", ".lisp": "lisp",
    ".ps1": "shell", ".psm1": "shell", ".bat": "shell", ".cmd": "shell",
    ".sh": "shell", ".bash": "shell", ".zsh": "shell", ".fish": "shell",
    ".gd": "gdscript",
    ".html": "web", ".css": "web", ".scss": "web", ".sass": "web",
    ".less": "web", ".vue": "web", ".svelte": "web",
    ".glsl": "shader", ".hlsl": "shader", ".wgsl": "shader",
}

# how much of each file to read looking for a header
HEADER_BYTES = 4096
# body slice kept for undocumented files, searched at low weight
SAMPLE_BYTES, SAMPLE_CHARS = 3000, 700
# a file smaller than this is probably not the point of its folder
MIN_INTERESTING_LINES = 5

# category folders - a project is the child directly under one of these
# How deep to look when deciding whether a folder is a category (below).
CATEGORY_PROBE_DEPTH = 3

# This file, so a scan never indexes the tool itself.
SELF = os.path.abspath(__file__)


def _has_source_directly(path):
    """Any indexable source file sitting directly in this folder?"""
    try:
        with os.scandir(path) as it:
            return any(e.is_file() and os.path.splitext(e.name)[1].lower() in SOURCE_EXT
                       for e in it)
    except OSError:
        return False


def _has_source_below(path, depth=CATEGORY_PROBE_DEPTH):
    """Any source file at or under this folder? Stops at the first hit."""
    if depth < 0:
        return False
    if _has_source_directly(path):
        return True
    try:
        with os.scandir(path) as it:
            subs = [e for e in it if e.is_dir() and e.name not in SKIP_DIRS]
    except OSError:
        return False
    return any(_has_source_below(e.path, depth - 1) for e in subs)


def categories_from_env():
    """Explicit category folders from CODEDEX_CATEGORIES, if set."""
    return {d.strip() for d in os.environ.get("CODEDEX_CATEGORIES", "").split(",")
            if d.strip()}


def suggest_categories(root):
    """Folders that *might* hold projects rather than being one.

    A folder directly under root is a category when it has no source files of
    its own but its children do -- so "tools/Star Citizen/logger/x.py" becomes
    the project "tools/Star Citizen" instead of lumping all of "tools" together.

    This is only ever a *suggestion* printed after a build. It is deliberately
    not applied automatically: whether "AutoCraft" is one project with a bot/
    and a brain/, or a folder holding two projects, is the author's intent and
    cannot be read off the directory shape. Guessing wrong silently merges
    unrelated projects, which is worse than asking.
    """
    cats = set()
    try:
        with os.scandir(root) as it:
            tops = [e for e in it if e.is_dir() and e.name not in SKIP_DIRS]
    except OSError:
        return cats
    for e in tops:
        if _has_source_directly(e.path):
            continue                       # a project in its own right
        try:
            with os.scandir(e.path) as it:
                kids = [c for c in it if c.is_dir() and c.name not in SKIP_DIRS]
        except OSError:
            continue
        if any(_has_source_below(c.path) for c in kids):
            cats.add(e.name)
    return cats


# --------------------------------------------------------------------------
# header extraction
# --------------------------------------------------------------------------

def _clean(lines):
    """Strip comment punctuation and blank padding off a header block."""
    out = []
    for l in lines:
        l = l.strip()
        l = re.sub(r'^(--\[\[|#+|//+|/\*+|\*+/?|--+|;+|%+|REM\b|<!--|-->)',
                   '', l, flags=re.I).strip()
        l = re.sub(r'(\*/|-->|\]\]|--\}|-\})$', '', l).strip()
        if l in ('"""', "'''"):
            continue
        out.append(l)
    # trim leading/trailing blanks
    while out and not out[0]:
        out.pop(0)
    while out and not out[-1]:
        out.pop()
    return out


def extract_header(path, kind):
    """Pull the leading docstring or comment block out of a source file.

    Returns (header_text, total_lines). Header may be empty.
    """
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            head = f.read(HEADER_BYTES)
    except (OSError, ValueError):
        return "", 0, ""

    # cheap total-line count without holding the file in memory
    try:
        with open(path, "rb") as f:
            total = sum(1 for _ in f)
    except OSError:
        total = 0

    lines = head.splitlines()
    if not lines:
        return "", total, ""

    collected = []

    if kind == "python":
        # module docstring, possibly after a shebang / encoding line
        i = 0
        while i < len(lines) and (lines[i].startswith("#!") or "coding" in lines[i][:30]):
            i += 1
        rest = lines[i:]
        m = re.match(r'\s*(?:[rubf]*)("""|\'\'\')', rest[0]) if rest else None
        if m:
            quote = m.group(1)
            first = rest[0].split(quote, 1)[1]
            if quote in first:                      # one-line docstring
                collected = [first.split(quote)[0]]
            else:
                collected = [first]
                for l in rest[1:]:
                    if quote in l:
                        collected.append(l.split(quote)[0])
                        break
                    collected.append(l)
        else:
            # fall back to a leading run of # comments
            for l in rest:
                if l.strip().startswith("#"):
                    collected.append(l)
                elif not l.strip():
                    if collected:
                        break
                else:
                    break
    else:
        # C-style block, or a leading run of line comments
        started = False
        close_on = "*/"
        # Skip preamble that is not a comment and not a description: PHP's
        # "<?php", a shebang, "@echo off", a doctype. Without this the scan
        # stops on line 1 and a perfectly good comment below it is missed.
        scan = list(lines)
        while scan:
            probe = scan[0].strip().lower()
            if (not probe
                    or probe.startswith(("<?php", "<?=", "<?", "#!", "@echo",
                                         "<!doctype", "﻿"))):
                scan.pop(0)
                continue
            break
        for l in scan:
            s = l.strip()
            # block comment openers, with the closer each one expects
            opener = None
            for start, end in (("/*", "*/"), ("--[[", "]]"), ("{-", "-}")):
                if s.startswith(start):
                    opener = (start, end)
                    break
            if not started and opener:
                start, closer = opener
                started, close_on = True, closer
                collected.append(l)
                if closer in s[len(start):]:
                    break
                continue
            if started:
                collected.append(l)
                if close_on in s:
                    break
                continue
            # line comments: // (C family), # (shell/ruby/perl), -- (lua, sql,
            # haskell), ; (lisp), % (erlang/tex), REM (batch)
            if (s.startswith(("//", "#", "--", ";", "%"))
                    or s.upper().startswith("REM")):
                collected.append(l)
            elif not s:
                if collected:
                    break
            else:
                break

    text = _strip_boilerplate(_clean(collected))
    # a header that is just a path repeated back is not informative
    if len(text) < 3:
        text = ""

    # Old code here is undocumented - laser-turret-test.py opens straight into
    # "import math". Keep a slice of the actual body so those files are still
    # findable by their identifiers and inline comments. Costs no extra I/O.
    body = re.sub(r"\s+", " ", head[:SAMPLE_BYTES]).strip()[:SAMPLE_CHARS]
    return text, total, body


# lines that tell you nothing about what the code does
_RE_FILENAME = re.compile(
    r'^[\w \-.()/\\]+\.(py|pyw|js|ts|java|cs|ps1|bat|cmd|sh|html|css|glsl)$', re.I)
_RE_SEPARATOR = re.compile(r'^[=\-*_~#+.\s]+$')
_RE_VERSION = re.compile(r'^#?\s*version\s+\d+', re.I)
_RE_LICENSE = re.compile(r'^(copyright|licen[cs]e|all rights reserved|'
                         r'permission is hereby|the mit licen)', re.I)


def _strip_boilerplate(lines):
    """Drop leading noise so the first line is actually descriptive.

    Real headers here often open with the file's own path ("data/commands/music.py"),
    a banner of ='s, or a vendored copyright block. The useful sentence is below it.
    """
    out = list(lines)
    while out:
        first = out[0].strip()
        if (not first or _RE_SEPARATOR.match(first) or _RE_FILENAME.match(first)
                or _RE_VERSION.match(first) or _RE_LICENSE.match(first)):
            out.pop(0)
            continue
        break
    # trim trailing noise too
    while out and (not out[-1].strip() or _RE_SEPARATOR.match(out[-1].strip())):
        out.pop()
    return "\n".join(out)


def header_quality(text):
    """How much does this header actually explain? 0 means useless."""
    if not text:
        return 0
    first = text.splitlines()[0].strip()
    if _RE_SEPARATOR.match(first) or _RE_FILENAME.match(first):
        return 0
    words = len(re.findall(r"[A-Za-z]{2,}", text))
    if words < 3:
        return 0
    # vendored third-party licence text describes the licence, not your project
    if _RE_LICENSE.search(text[:300]) or "warranties of merchantability" in text.lower():
        return 0
    return min(words, 40)


def read_readme(path):
    """First meaningful prose out of a README."""
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            body = f.read(HEADER_BYTES)
    except OSError:
        return ""
    out = []
    for l in body.splitlines():
        s = l.strip()
        if not s or s.startswith(("#", "=", "-", "|", "```", ">")):
            if out:
                break
            continue
        out.append(s)
        if len(out) >= 4:
            break
    return " ".join(out)


# --------------------------------------------------------------------------
# scanning
# --------------------------------------------------------------------------

def project_root_of(rel_path, categories):
    """Map a file path to the project it belongs to.

    Under a known category folder, the project is that folder's direct child
    (so tools/Star Citizen/logger/x.py -> tools/Star Citizen). Otherwise the
    first path segment.
    """
    parts = rel_path.replace("\\", "/").split("/")
    if len(parts) >= 2 and parts[0] in categories:
        return "/".join(parts[:2])
    return parts[0] if len(parts) > 1 else "."


def build(root=ROOT, verbose=True, categories=None):
    t0 = time.time()
    categories = categories_from_env() if categories is None else set(categories)
    if verbose and categories:
        print("  category folders: " + ", ".join(sorted(categories)))
    projects = {}
    n_files = 0

    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        rel_dir = os.path.relpath(dirpath, root)
        if rel_dir == ".":
            rel_dir = ""

        for fn in filenames:
            ext = os.path.splitext(fn)[1].lower()
            full = os.path.join(dirpath, fn)
            rel = os.path.join(rel_dir, fn) if rel_dir else fn

            if fn.lower().startswith("readme") and ext in (".md", ".txt", ""):
                proj = project_root_of(rel, categories)
                p = projects.setdefault(proj, _blank_project(proj))
                blurb = read_readme(full)
                if blurb and len(blurb) > len(p["readme"]):
                    p["readme"] = blurb
                continue

            if ext not in SOURCE_EXT:
                continue

            # Don't index ourselves. The README suggests dropping this single
            # file wherever it is handy, which can be inside the tree being
            # scanned -- and its docstring name-drops other projects.
            if os.path.abspath(full) == SELF:
                continue

            kind = SOURCE_EXT[ext]
            header, total, body = extract_header(full, kind)
            if total < MIN_INTERESTING_LINES and not header:
                continue

            n_files += 1
            proj = project_root_of(rel, categories)
            p = projects.setdefault(proj, _blank_project(proj))
            p["langs"][kind] = p["langs"].get(kind, 0) + 1
            p["files"].append({
                "path": rel.replace("\\", "/"),
                "name": fn,
                "lines": total,
                "header": header,
                "body": body,
            })
            try:
                mt = os.path.getmtime(full)
                if mt > p["mtime"]:
                    p["mtime"] = mt
            except OSError:
                pass

            if verbose and n_files % 250 == 0:
                print(f"  ...{n_files} files", end="\r", flush=True)

    # keep only the most substantial files per project, biggest first
    for p in projects.values():
        p["files"].sort(key=lambda f: (bool(f["header"]), f["lines"]), reverse=True)
        p["total_lines"] = sum(f["lines"] for f in p["files"])
        p["n_files"] = len(p["files"])
        p["files"] = p["files"][:12]

    index = {
        "root": os.path.abspath(root),
        "built": datetime.now().isoformat(timespec="seconds"),
        "n_projects": len(projects),
        "n_files": n_files,
        "projects": projects,
    }
    out = index_path_for(root)
    with open(out, "w", encoding="utf-8") as f:
        json.dump(index, f, indent=1)

    if verbose:
        print(f"  indexed {n_files} files in {len(projects)} projects "
              f"({time.time() - t0:.1f}s) -> {out}")
        hint = sorted(suggest_categories(root) - categories)
        if hint:
            print()
            print("  These folders may hold several projects each rather than being")
            print("  one project:  " + ", ".join(hint))
            print("  If so, index their children separately with:")
            print("      codedex build --category " + ",".join(hint))
    return index


def _blank_project(name):
    return {"name": name, "files": [], "langs": {}, "readme": "", "mtime": 0.0}


# --------------------------------------------------------------------------
# search
# --------------------------------------------------------------------------

W_HEADER, W_README, W_FOLDER, W_FILENAME = 10, 8, 6, 4
W_BREADTH, MAX_BREADTH = 3, 15   # bonus per extra file mentioning a term
W_BODY = 2                       # last resort: term appears in the code itself


def load_index(root=None, auto_build=True):
    root = root or ROOT
    path = index_path_for(root)
    if not os.path.exists(path):
        if not auto_build:
            return None
        print("no index for " + os.path.abspath(root) + " yet - building...")
        return build(root)
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def search(index, terms):
    """Score every project against all query terms. AND semantics."""
    terms = [t.lower() for t in terms if t.strip()]
    results = []

    for name, p in index["projects"].items():
        folder = name.lower()
        readme = p["readme"].lower()
        score = 0
        hits = []           # (file, line) evidence to show the user
        matched_terms = set()

        for t in terms:
            got = False
            if t in folder:
                score += W_FOLDER
                matched_terms.add(t)
                got = True
            if t in readme:
                score += W_README
                matched_terms.add(t)
                got = True

            # How many files mention this term? A project that merely name-drops
            # "discord bot" in a README should not outrank the actual discord bot,
            # which says it in file after file. Breadth is the signal.
            in_files = [f for f in p["files"] if t in f["header"].lower()]
            # match the whole relative path, not just the basename: sub-project
            # folders (games/roguelike-tcod/...) collapse into the project key,
            # so "roguelike" would otherwise be unfindable.
            by_name = [f for f in p["files"] if t in f["path"].lower()]

            if in_files:
                score += W_HEADER + min((len(in_files) - 1) * W_BREADTH, MAX_BREADTH)
                matched_terms.add(t)
                if not got:
                    hits.append(in_files[0])
                got = True
            elif by_name:
                score += W_FILENAME
                matched_terms.add(t)
                if not got:
                    hits.append(by_name[0])
                got = True
            else:
                in_body = [f for f in p["files"] if t in f.get("body", "").lower()]
                if in_body:
                    score += W_BODY + min((len(in_body) - 1), 4)
                    matched_terms.add(t)
                    if not got:
                        hits.append(in_body[0])

        # every term must land somewhere
        if len(matched_terms) == len(terms) and score:
            # nudge bigger, more documented projects up
            score += min(p["total_lines"] / 1000.0, 5)
            results.append((score, p, hits))

    results.sort(key=lambda r: r[0], reverse=True)
    return results


# --------------------------------------------------------------------------
# output
# --------------------------------------------------------------------------

def _age(mtime):
    if not mtime:
        return "?"
    d = (datetime.now() - datetime.fromtimestamp(mtime)).days
    if d == 0:
        return "today"
    if d == 1:
        return "1d ago"
    if d < 60:
        return f"{d}d ago"
    return f"{d // 30}mo ago"


def _best_blurb(p, hits):
    """The most explanatory sentence we have about this project.

    When the user searched, prefer the file that actually matched - that is the
    evidence for why this result is here. Otherwise pick the best-explained file
    in the project, not merely the first or biggest.
    """
    if hits and header_quality(hits[0]["header"]):
        return hits[0]["header"], hits[0]["path"]

    # Among files that explain themselves properly, the project's identity is the
    # BIGGEST one - not the wordiest. Drake Radio's 2767-line player defines the
    # folder; its 413-line stream monitor merely has a chattier docstring.
    explained = [f for f in p["files"] if header_quality(f["header"]) >= 8]
    if explained:
        best = max(explained, key=lambda f: f["lines"])
        return best["header"], best["path"]

    best, best_q = None, 0
    for f in p["files"]:
        q = header_quality(f["header"])
        if q > best_q:
            best, best_q = f, q
    if best:
        return best["header"], best["path"]

    if p["readme"]:
        return p["readme"], "README"
    # nothing documented - at least name the biggest file
    if p["files"]:
        return "", p["files"][0]["path"]
    return "", ""


def print_result(score, p, hits, show_score=False):
    langs = ", ".join(f"{k}:{v}" for k, v in
                      sorted(p["langs"].items(), key=lambda kv: -kv[1])[:3])
    tag = f"  [{score:.0f}]" if show_score else ""
    print(f"\n  {p['name']}{tag}")
    print(f"     {p['n_files']} files, {p['total_lines']:,} lines, {langs}, {_age(p['mtime'])}")

    blurb, src = _best_blurb(p, hits)
    if blurb:
        for line in blurb.splitlines()[:3]:
            if line.strip():
                print(f"     | {line[:96]}")
    elif src:
        print("     | (undocumented)")
    if src:
        print(f"     -> {src}")

    # If the term was found in an undocumented file, the blurb above came from a
    # different file entirely - say which one actually matched, or the result
    # reads as a non sequitur ("servo" -> an IMU demo docstring).
    if hits and hits[0]["path"] != src:
        print(f"     matched in {hits[0]['path']}")


def cmd_find(args):
    index = load_index(args.root)
    results = search(index, args.terms)
    q = " ".join(args.terms)
    if not results:
        print(f"\nno match for '{q}'")
        print("try fewer/different words, or 'build' if the tree changed")
        return
    print(f"\n{len(results)} match(es) for '{q}':")
    for score, p, hits in results[:args.limit]:
        print_result(score, p, hits, show_score=args.scores)
    print()


def cmd_list(args):
    index = load_index(args.root)
    ps = sorted(index["projects"].values(), key=lambda p: -p["mtime"])
    print(f"\n{len(ps)} projects in {index['root']}  (indexed {index['built']})\n")
    for p in ps:
        blurb, src = _best_blurb(p, [])
        first = blurb.splitlines()[0] if blurb else (f"({src})" if src else "")
        print(f"  {_age(p['mtime']):>9}  {p['name']:<34} {first[:60]}")
    print()


def cmd_stale(args):
    index = load_index(args.root)
    cutoff = (datetime.now() - timedelta(days=args.days)).timestamp()
    ps = [p for p in index["projects"].values() if p["mtime"] and p["mtime"] < cutoff]
    ps.sort(key=lambda p: p["mtime"])
    print(f"\n{len(ps)} projects untouched in {args.days}+ days:\n")
    for p in ps:
        blurb, _ = _best_blurb(p, [])
        first = blurb.splitlines()[0] if blurb else ""
        print(f"  {_age(p['mtime']):>9}  {p['name']:<34} {first[:60]}")
    print()


def cmd_build(args):
    print(f"scanning {args.root} ...")
    cats = None
    if args.category is not None:
        cats = {d.strip() for d in args.category.split(",") if d.strip()}
    build(args.root, categories=cats)


def main():
    # console is usually cp1252 on Windows; headers are utf-8 and full of dashes
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, OSError):
            pass

    ap = argparse.ArgumentParser(
        prog="codedex",
        description="Find your code by what it does, not what the folder is called.")
    sub = ap.add_subparsers(dest="cmd")

    b = sub.add_parser("build", help="rescan the tree")
    b.add_argument("--root", default=ROOT)
    b.add_argument("--category", default=None,
                   help="comma-separated folders that hold projects rather than being one")
    b.set_defaults(func=cmd_build)

    f = sub.add_parser("find", help="search")
    f.add_argument("terms", nargs="+")
    f.add_argument("-n", "--limit", type=int, default=8)
    f.add_argument("--scores", action="store_true", help="show match scores")
    f.add_argument("--root", default=ROOT)
    f.set_defaults(func=cmd_find)

    l = sub.add_parser("list", help="all projects, newest first")
    l.add_argument("--root", default=ROOT)
    l.set_defaults(func=cmd_list)

    s = sub.add_parser("stale", help="projects gathering dust")
    s.add_argument("--days", type=int, default=90)
    s.add_argument("--root", default=ROOT)
    s.set_defaults(func=cmd_stale)

    # bare `codedex radio` means find
    argv = sys.argv[1:]
    if argv and argv[0] not in {"build", "find", "list", "stale", "-h", "--help"}:
        argv = ["find"] + argv

    args = ap.parse_args(argv)
    if not getattr(args, "func", None):
        ap.print_help()
        return
    args.func(args)


if __name__ == "__main__":
    main()
