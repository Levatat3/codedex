"""Tests for codedex. Standard library only: python -m unittest -v

Every test builds its own throwaway tree in a temp dir, so nothing here reads
or writes the real index or the user's code.
"""
import json
import os
import shutil
import tempfile
import unittest

import codedex


def write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)


RADIO = '''"""
Drake Interplanetary HCN Radio
Star Citizen themed internet radio player.
Requires: PyQt6, python-vlc
"""
import sys


def main():
    pass
'''

QR = '''"""Generate QR codes from whatever is on the clipboard."""
import sys


def run():
    pass
'''

UNDOCUMENTED = '''import math


def servo_angle(pulse):
    return pulse * math.pi


def servo_reset():
    pass
'''


class TreeCase(unittest.TestCase):
    """Base: a temp tree plus an index path that never touches the real one."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="codedex-test-")
        self.root = os.path.join(self.tmp, "tree")
        os.makedirs(self.root)
        self._env = {}
        for k in ("CODEDEX_INDEX", "CODEDEX_CATEGORIES", "CODEDEX_ROOT"):
            self._env[k] = os.environ.pop(k, None)
        os.environ["CODEDEX_INDEX"] = os.path.join(self.tmp, "index.json")

    def tearDown(self):
        for k, v in self._env.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        shutil.rmtree(self.tmp, ignore_errors=True)

    def build(self, **kw):
        return codedex.build(self.root, verbose=False, **kw)

    def names(self, results):
        return [p["name"] for _score, p, _hits in results]


class HeaderExtraction(TreeCase):

    def test_pulls_module_docstring(self):
        p = os.path.join(self.root, "a.py")
        write(p, RADIO)
        header, total, _body = codedex.extract_header(p, "python")
        self.assertIn("Star Citizen", header)
        self.assertGreater(total, 5)

    def test_undocumented_file_has_no_header(self):
        p = os.path.join(self.root, "b.py")
        write(p, UNDOCUMENTED)
        header, _total, body = codedex.extract_header(p, "python")
        self.assertEqual(header.strip(), "")
        self.assertIn("servo", body.lower())

    def test_missing_file_is_not_fatal(self):
        header, total, _body = codedex.extract_header(
            os.path.join(self.root, "nope.py"), "python")
        self.assertEqual(header, "")
        self.assertEqual(total, 0)


class HeaderQuality(unittest.TestCase):

    def test_empty_scores_zero(self):
        self.assertEqual(codedex.header_quality(""), 0)

    def test_too_few_words_scores_zero(self):
        self.assertEqual(codedex.header_quality("ok go"), 0)

    def test_separator_line_scores_zero(self):
        self.assertEqual(codedex.header_quality("# ----------------------"), 0)

    def test_licence_text_scores_zero(self):
        mit = ("Permission is hereby granted, free of charge, to any person "
               "obtaining a copy of this software, THE SOFTWARE IS PROVIDED AS IS "
               "WITHOUT WARRANTIES OF MERCHANTABILITY and fitness")
        self.assertEqual(codedex.header_quality(mit), 0)

    def test_real_description_scores(self):
        self.assertGreater(
            codedex.header_quality("Star Citizen themed internet radio player."), 0)


class ProjectRoot(unittest.TestCase):

    def test_first_segment_without_categories(self):
        self.assertEqual(codedex.project_root_of("tools/radio/x.py", set()), "tools")

    def test_child_of_a_category(self):
        self.assertEqual(
            codedex.project_root_of("tools/radio/x.py", {"tools"}), "tools/radio")

    def test_backslashes_normalise(self):
        self.assertEqual(
            codedex.project_root_of(r"tools\radio\x.py", {"tools"}), "tools/radio")

    def test_file_at_root_is_dot(self):
        self.assertEqual(codedex.project_root_of("x.py", set()), ".")


class IndexPath(TreeCase):

    def test_env_override_wins(self):
        self.assertEqual(codedex.index_path_for(self.root),
                         os.environ["CODEDEX_INDEX"])

    def test_different_roots_get_different_files(self):
        os.environ.pop("CODEDEX_INDEX")
        a = codedex.index_path_for(os.path.join(self.tmp, "one"))
        b = codedex.index_path_for(os.path.join(self.tmp, "two"))
        self.assertNotEqual(a, b)

    def test_same_root_is_stable(self):
        os.environ.pop("CODEDEX_INDEX")
        a = codedex.index_path_for(self.root)
        b = codedex.index_path_for(self.root)
        self.assertEqual(a, b)

    def test_not_written_beside_the_module(self):
        os.environ.pop("CODEDEX_INDEX")
        here = os.path.dirname(os.path.abspath(codedex.__file__))
        self.assertNotEqual(
            os.path.dirname(codedex.index_path_for(self.root)), here)


class Building(TreeCase):

    def test_indexes_projects_and_writes_the_file(self):
        write(os.path.join(self.root, "radio-thing", "player.py"), RADIO)
        write(os.path.join(self.root, "qr-tool", "qr.py"), QR)
        index = self.build()
        self.assertEqual(index["n_files"], 2)
        self.assertEqual(sorted(index["projects"]), ["qr-tool", "radio-thing"])
        self.assertTrue(os.path.exists(os.environ["CODEDEX_INDEX"]))

    def test_records_absolute_root(self):
        write(os.path.join(self.root, "a", "x.py"), RADIO)
        self.assertTrue(os.path.isabs(self.build()["root"]))

    def test_skips_dependency_and_build_dirs(self):
        write(os.path.join(self.root, "real", "x.py"), RADIO)
        write(os.path.join(self.root, "real", "node_modules", "dep.js"), QR)
        write(os.path.join(self.root, "real", "__pycache__", "junk.py"), QR)
        self.assertEqual(self.build()["n_files"], 1)

    def test_skips_a_pyinstaller_build_wherever_it_lives(self):
        """Found on a real tree: a onedir build moved out of dist/ to
        FunkDrop/FunkDrop/ carried 578 bundled PIL files, and PIL's docstring
        became the project's description. Both the v6 layout (_internal/) and
        the older flat one must be skipped, but a real _internal package kept.
        """
        write(os.path.join(self.root, "app", "main.py"), RADIO)
        v6 = os.path.join(self.root, "app", "App", "_internal")
        write(os.path.join(v6, "base_library.zip"), "")
        write(os.path.join(v6, "PIL", "Image.py"), QR)
        old = os.path.join(self.root, "app", "OldApp")
        write(os.path.join(old, "base_library.zip"), "")
        write(os.path.join(old, "PIL", "Image.py"), QR)
        write(os.path.join(self.root, "lib", "_internal", "core.py"), QR)
        index = self.build()
        self.assertEqual(index["projects"]["app"]["n_files"], 1)
        self.assertEqual(index["projects"]["lib"]["n_files"], 1)

    def test_does_not_index_itself(self):
        """The README says to drop the single file wherever is handy, which may
        be inside the tree being scanned. Running it from there must not index
        it: its docstring name-drops other projects and would pollute results.
        SELF is patched to stand in for 'the copy you are running'.
        """
        tool = os.path.join(self.root, "codedex.py")
        shutil.copy(codedex.__file__, tool)
        write(os.path.join(self.root, "proj", "x.py"), RADIO)
        previous, codedex.SELF = codedex.SELF, os.path.abspath(tool)
        try:
            index = self.build()
        finally:
            codedex.SELF = previous
        self.assertEqual(index["n_files"], 1)
        self.assertEqual(sorted(index["projects"]), ["proj"])

    def test_ignores_unknown_extensions(self):
        write(os.path.join(self.root, "proj", "notes.rtf"), "some prose here")
        write(os.path.join(self.root, "proj", "x.py"), RADIO)
        self.assertEqual(self.build()["n_files"], 1)

    def test_readme_becomes_project_blurb(self):
        write(os.path.join(self.root, "proj", "x.py"), UNDOCUMENTED)
        write(os.path.join(self.root, "proj", "README.md"),
              "# proj\n\nA hovercraft full of eels.\n")
        index = self.build()
        self.assertIn("eels", index["projects"]["proj"]["readme"].lower())

    def test_categories_split_children_into_projects(self):
        write(os.path.join(self.root, "holder", "alpha", "a.py"), RADIO)
        write(os.path.join(self.root, "holder", "beta", "b.py"), QR)
        flat = self.build()
        self.assertEqual(sorted(flat["projects"]), ["holder"])
        split = self.build(categories={"holder"})
        self.assertEqual(sorted(split["projects"]), ["holder/alpha", "holder/beta"])


class Suggestions(TreeCase):

    def test_suggests_a_folder_of_projects(self):
        write(os.path.join(self.root, "holder", "alpha", "a.py"), RADIO)
        write(os.path.join(self.root, "holder", "beta", "b.py"), QR)
        self.assertIn("holder", codedex.suggest_categories(self.root))

    def test_does_not_suggest_a_plain_project(self):
        write(os.path.join(self.root, "proj", "x.py"), RADIO)
        self.assertNotIn("proj", codedex.suggest_categories(self.root))

    def test_does_not_suggest_a_project_with_its_own_readme_or_spec(self):
        """Code only in subfolders, but the top says 'one project'."""
        for name, marker in (("docd", "README.md"), ("frozen", "app.spec"),
                             ("pkg", "pyproject.toml")):
            write(os.path.join(self.root, name, marker), "x")
            write(os.path.join(self.root, name, "src", "a.py"), RADIO)
            write(os.path.join(self.root, name, "ui", "b.py"), QR)
        self.assertEqual(codedex.suggest_categories(self.root), set())

    def test_frozen_build_does_not_make_a_category(self):
        write(os.path.join(self.root, "shipped", "App", "base_library.zip"), "")
        write(os.path.join(self.root, "shipped", "App", "PIL", "Image.py"), QR)
        self.assertNotIn("shipped", codedex.suggest_categories(self.root))

    def test_suggestion_is_never_applied_on_its_own(self):
        """The whole point: a build with no --category stays flat."""
        write(os.path.join(self.root, "holder", "alpha", "a.py"), RADIO)
        write(os.path.join(self.root, "holder", "beta", "b.py"), QR)
        self.assertEqual(sorted(self.build()["projects"]), ["holder"])


class Searching(TreeCase):

    def setUp(self):
        super().setUp()
        write(os.path.join(self.root, "radio-thing", "player.py"), RADIO)
        write(os.path.join(self.root, "qr-tool", "qr.py"), QR)
        write(os.path.join(self.root, "servo-rig", "turret.py"), UNDOCUMENTED)
        self.index = self.build()

    def test_finds_by_docstring_not_folder_name(self):
        self.assertEqual(
            self.names(codedex.search(self.index, ["citizen"])), ["radio-thing"])

    def test_every_term_must_land(self):
        """AND semantics: 'radio' hits, 'aardvark' does not, so nothing matches."""
        self.assertEqual(codedex.search(self.index, ["radio", "aardvark"]), [])

    def test_multi_word_match(self):
        self.assertEqual(
            self.names(codedex.search(self.index, ["qr", "clipboard"])), ["qr-tool"])

    def test_case_insensitive(self):
        self.assertEqual(
            self.names(codedex.search(self.index, ["STAR", "CiTiZeN"])), ["radio-thing"])

    def test_undocumented_code_found_via_body_slice(self):
        self.assertIn("servo-rig", self.names(codedex.search(self.index, ["servo"])))

    def test_header_outranks_folder_name(self):
        """A project whose docstring says 'radio' beats one merely named it."""
        write(os.path.join(self.root, "radio", "unrelated.py"),
              '"""Spreadsheet column width calculator for invoices."""\nimport os\n\n\ndef go():\n    pass\n')
        index = self.build()
        ranked = self.names(codedex.search(index, ["radio"]))
        self.assertEqual(ranked[0], "radio-thing")
        self.assertIn("radio", ranked)

    def test_no_match_returns_empty(self):
        self.assertEqual(codedex.search(self.index, ["zzzznothing"]), [])


class Roundtrip(TreeCase):

    def test_index_reloads_from_disk(self):
        write(os.path.join(self.root, "radio-thing", "player.py"), RADIO)
        self.build()
        with open(os.environ["CODEDEX_INDEX"], encoding="utf-8") as f:
            reloaded = json.load(f)
        self.assertEqual(
            self.names(codedex.search(reloaded, ["citizen"])), ["radio-thing"])

    def test_load_index_builds_when_missing(self):
        write(os.path.join(self.root, "radio-thing", "player.py"), RADIO)
        self.assertFalse(os.path.exists(os.environ["CODEDEX_INDEX"]))
        index = codedex.load_index(self.root)
        self.assertEqual(index["n_files"], 1)


class OtherLanguages(TreeCase):
    """Each language's leading comment block must survive extraction."""

    # filename -> (source lines, phrase that must come back out of the header)
    CASES = {
        'main.go':     ('// Package fleet tracks cargo ships across systems.\n// Talks to the harbour API.\npackage fleet\n',
                        'cargo ships'),
        'lib.rs':      ('//! Crate for parsing telemetry frames off a serial port.\nuse std::io;\n',
                        'telemetry frames'),
        'conf.lua':    ('-- Neovim colourscheme that mimics an amber CRT terminal.\nlocal M = {}\n',
                        'amber CRT'),
        'block.lua':   ('--[[\nSprite atlas packer for the roguelike.\nBin-packs frames into one texture.\n]]\nlocal atlas = {}\n',
                        'Sprite atlas'),
        'report.sql':  ('-- Monthly revenue rollup by warehouse region.\nSELECT 1;\n',
                        'revenue rollup'),
        'app.rb':      ("# Sinatra app that serves the allotment watering schedule.\nrequire 'sinatra'\n",
                        'watering schedule'),
        'View.swift':  ('// SwiftUI view for the tide table widget.\nimport SwiftUI\n',
                        'tide table'),
        'Main.kt':     ('/* Android service that syncs beehive sensor readings. */\npackage hive\n',
                        'beehive sensor'),
        'core.clj':    (';; Clojure namespace for the chord progression generator.\n(ns core)\n',
                        'chord progression'),
        'Parse.hs':    ('{- Haskell parser for the tabletop dice notation. -}\nmodule Parse where\n',
                        'dice notation'),
        'index.php':   ('<?php\n// Invoice PDF generator for the plumbing business.\n',
                        'Invoice PDF'),
        'site.scss':   ('/* Stylesheet for the brutalist photography portfolio. */\nbody { margin: 0; }\n',
                        'brutalist photography'),
    }

    def test_header_extracted_for_each_language(self):
        for fn, (text, want) in self.CASES.items():
            with self.subTest(file=fn):
                path = os.path.join(self.root, "proj", fn)
                write(path, text)
                kind = codedex.SOURCE_EXT[os.path.splitext(fn)[1].lower()]
                header, _total, _body = codedex.extract_header(path, kind)
                self.assertIn(want.lower(), header.lower(),
                              "%s (%s) header was: %r" % (fn, kind, header))

    def test_each_language_is_searchable_after_a_build(self):
        for i, (fn, (text, _want)) in enumerate(self.CASES.items()):
            write(os.path.join(self.root, "proj%d" % i, fn), text)
        index = self.build()
        self.assertEqual(index["n_files"], len(self.CASES))
        for fn, (_text, want) in self.CASES.items():
            with self.subTest(file=fn):
                terms = want.lower().split()
                self.assertTrue(codedex.search(index, terms),
                                "%s: no project matched %s" % (fn, terms))

    def test_language_labels_recorded(self):
        write(os.path.join(self.root, "p", "main.go"), self.CASES["main.go"][0])
        write(os.path.join(self.root, "p", "conf.lua"), self.CASES["conf.lua"][0])
        langs = self.build()["projects"]["p"]["langs"]
        self.assertEqual(langs.get("go"), 1)
        self.assertEqual(langs.get("lua"), 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
