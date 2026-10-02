"""Spec verbs: lint findings and exemptions, version levels, release, sync and verify."""

import io
import os
import shutil
import tempfile
import unittest
from argparse import Namespace
from contextlib import redirect_stdout
from pathlib import Path

from support import ROOT, RepoCase, git, sh, write

from deliveryctl import core, spec

TOML = 'name = "lists"\nversion = "0.0.0"\nlocales = ["fr"]\n'
COPY = '{"lists.create": "Nouvelle liste"}\n'
STORY = """---
id: s001
title: Créer une liste
status: ready
---
## Business rules
- BR1 Une liste a un nom.
## Main flow
1. La personne choisit `lists.create`.
2. Le système montre la liste.
## Extensions
- 2a. Le nom est vide : le système affiche `lists.name-required`.
## Acceptance criteria
- AC1 @main — Given une personne connectée, When elle crée « Courses », Then « Courses » apparaît dans ses listes
- AC2 @ext-2a — Given une personne connectée, When elle enregistre un nom vide, Then un message le refuse
## UI contract
| Key | Role | Where |
|---|---|---|
| `lists.create` | button | accueil |
## Outcomes
none
## Out of scope
- Partager une liste.
## Open questions
"""
TESTS = """import { test, expect } from '@playwright/test';
test.describe('@s001 listes', () => {
  test('@s001-ac1 la liste créée apparaît', async ({ page }) => {});
  test.skip('@s001-ac2 un nom vide est refusé', async ({ page }) => {});
});
"""


def make_spec(root: Path, story: str = STORY, tests: str = TESTS, toml: str = TOML) -> None:
    write(root / "spec/spec.toml", toml)
    write(root / "spec/ui/copy.fr.json", COPY)
    write(root / "spec/stories/s001-create-list.md", story)
    write(root / "spec/acceptance/tests/s001.spec.ts", tests)


def rules(findings) -> list[str]:
    return [f.rule for f in findings]


class LintTest(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp(prefix="dm-spec-"))

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def lint(self, **kwargs):
        make_spec(self.root, **kwargs)
        return spec.lint(self.root)

    def test_clean_spec_is_green(self):
        self.assertEqual(self.lint(), [])

    def test_templates_are_green(self):
        shutil.copytree(ROOT / "templates/spec", self.root / "spec")
        story = (self.root / "spec/story.md").read_text()
        write(self.root / "spec/stories/s001-create-list.md", story)
        self.assertEqual([str(f) for f in spec.lint(self.root)], [])
        write(self.root / "spec/stories/s001-create-list.md", story.replace("status: draft", "status: ready"))
        self.assertEqual([str(f) for f in spec.lint(self.root)], [])

    def test_draft_is_tolerant_ready_is_strict(self):
        short = "---\nid: s001\ntitle: Lists\nstatus: {s}\n---\n## Main flow\n1. Open.\n"
        self.assertEqual(self.lint(story=short.format(s="draft"), tests=""), [])
        found = self.lint(story=short.format(s="ready"), tests="")
        self.assertIn("missing section '## Acceptance criteria'", [f.message for f in found])
        self.assertTrue(all(f.rule == "schema" for f in found), found)
        found = self.lint(story=STORY.replace("## Open questions", "## Open questions\n- Qui voit la liste ?"))
        self.assertEqual([f.line for f in found], [24])
        found = self.lint(story=STORY.replace("- AC1 @main — Given", "- AC1 @main Given"))
        self.assertTrue(any("14: schema: a criterion reads" in str(f) for f in found), found)

    def test_neutrality_lexicon_and_settings(self):
        body = STORY.replace("- BR1 Une liste a un nom.",
                             "- BR1 Le nom va dans une table SQL via un endpoint (code 404), le reste suit.\n"
                             "- BR2 La clé `lists.table` et le Kanban.")
        found = self.lint(story=body)
        words = sorted(f.message.split("'")[1] for f in found if f.rule == "neutrality")
        self.assertEqual(words, ["SQL", "code 404", "endpoint", "table"])
        self.assertEqual({f.line for f in found}, {7})
        found = self.lint(story=STORY.replace("| `lists.create` | button | accueil |",
                                              "| `lists.items` | table | accueil, pas en JSON |"))
        self.assertEqual([f.message.split("'")[1] for f in found], ["JSON"])
        toml = TOML + '[neutrality]\nallow = ["table", "HTTP status code"]\nextra = ["Kanban"]\n'
        words = sorted(f.message.split("'")[1] for f in self.lint(story=body, toml=toml))
        self.assertEqual(words, ["Kanban", "SQL", "endpoint"])

    def test_brief_neutrality(self):
        brief = self.root / "spec/product/brief.md"
        self.assertEqual(self.lint(), [])                       # no brief: no finding
        write(brief, "# Brief\n<!-- une base SQL\nsur deux lignes -->\n## SQL\n"
                     "Des listes dans une base SQL via un endpoint.\n")
        found = spec.lint(self.root)
        self.assertEqual([str(f).split(" (")[0] for f in found],
                         ["spec/product/brief.md:5: neutrality: technology word 'SQL': say what the user observes",
                          "spec/product/brief.md:5: neutrality: technology word 'endpoint': say what the user observes"])
        write(self.root / "spec/spec.toml", TOML + '[neutrality]\nallow = ["SQL"]\n')
        self.assertEqual([f.message.split("'")[1] for f in spec.lint(self.root)], ["endpoint"])
        write(brief, "# Brief\nlint-exempt: neutrality — nom du produit\nUn endpoint SQL.\n")
        self.assertEqual(spec.lint(self.root), [])

    def test_extension_rules(self):
        body = STORY.replace("## Acceptance criteria", "- 3b. La liste existe déjà : rien ne change.\n"
                             "## Acceptance criteria\n- AC3 @ext-9z — Given a, When b, Then c")
        found = [f for f in self.lint(story=body) if f.rule == "extension"]
        self.assertEqual(sorted(f.message for f in found),
                         ["AC3 names extension 9z, absent from '## Extensions'", "extension 3b has no criterion (@ext-3b)"])
        draft = [f for f in self.lint(story=body.replace("status: ready", "status: draft")) if f.rule == "extension"]
        self.assertEqual(len(draft), 1, draft)

    def test_coverage_and_test_tags(self):
        tests = TESTS.replace("@s001-ac2", "@s001-ac7") + (
            "test.describe('@s099 ailleurs', () => {});\ntest('@s001-ac2 sans étiquette', async () => {});\n")
        write(self.root / "spec/acceptance/tests/other.spec.ts",
              "import { test } from '@playwright/test';\ntest('@s001-ac1 orphelin', async () => {});\n")
        found = self.lint(tests=tests)
        self.assertEqual(sorted(str(f) for f in found), [
            "spec/acceptance/tests/other.spec.ts:2: test-tag: covers @s001-ac1 but does not carry @s001",
            "spec/acceptance/tests/s001.spec.ts:4: orphan-tag: @s001-ac7 names no criterion",
            "spec/acceptance/tests/s001.spec.ts:6: orphan-tag: @s099 names no story",
        ])
        (self.root / "spec/acceptance/tests/other.spec.ts").unlink()
        found = self.lint(tests=TESTS.replace("@s001-ac2", "@s001 pas de critère"))
        self.assertEqual([str(f) for f in found],
                         ["spec/stories/s001-create-list.md:15: coverage: AC2 has no test tagged @s001-ac2"])
        draft = self.lint(story=STORY.replace("status: ready", "status: draft"), tests="")
        self.assertEqual(draft, [])

    def test_exemptions(self):
        exempt = STORY.replace("## Business rules", "lint-exempt: neutrality — nom du produit\n"
                               "lint-exempt: schema — pas encore\n## Business rules")
        body = exempt.replace("Une liste a un nom.", "Une liste a un nom SQL.").replace("## Outcomes\nnone\n", "")
        self.assertEqual([str(f) for f in self.lint(story=body)],
                         ["spec/stories/s001-create-list.md:1: schema: missing section '## Outcomes'"])
        self.assertEqual(self.lint(story=body.replace("status: ready", "status: draft")), [])
        found = self.lint(story=STORY.replace("## Business rules", "lint-exempt: speed — x\nlint-exempt: coverage\n## Business rules"))
        self.assertEqual(rules(found), ["schema", "schema"])
        self.assertIn("unknown rule 'speed'", found[0].message)
        self.assertIn("needs a reason", found[1].message)


class VersionTest(unittest.TestCase):
    def test_levels(self):
        before = {"s001-ac1": "@main — a", "s001-ac2": "@main — b"}
        self.assertEqual(spec.level_of(spec.diff_criteria(before, dict(before))), "patch")
        self.assertEqual(spec.level_of(spec.diff_criteria(before, {**before, "s002-ac1": "@main — c"})), "minor")
        self.assertEqual(spec.level_of(spec.diff_criteria(before, {"s001-ac1": "@main — a"})), "major")
        self.assertEqual(spec.level_of(spec.diff_criteria(before, {**before, "s001-ac2": "@main — B"})), "major")

    def test_next_version(self):
        cases = [(None, "major", "pre-release", "0.1.0"), (None, "patch", "released", "0.1.0"),
                 ("0.2.3", "major", "pre-release", "0.3.0"), ("0.2.3", "minor", "pre-release", "0.2.4"),
                 ("0.2.3", "patch", "pre-release", "0.2.4"), ("0.4.0", "major", "released", "1.0.0"),
                 ("1.2.3", "major", "released", "2.0.0"), ("1.2.3", "minor", "released", "1.3.0"),
                 ("1.2.3", "patch", "released", "1.2.4")]
        for previous, level, stage, expected in cases:
            self.assertEqual(spec.next_version(previous, level, stage), expected, (previous, level, stage))

    def test_bump_level_and_clean_version(self):
        self.assertEqual(spec.bump_level("1.2.3", "2.0.0"), "major")
        self.assertEqual(spec.bump_level("1.2.3", "1.3.0"), "minor")
        self.assertEqual(spec.bump_level("1.2.3", "1.2.9"), "patch")
        self.assertIsNone(spec.bump_level("1.2.3", "1.2.3"))
        self.assertEqual(spec.clean_version("spec-v1.0.0"), "1.0.0")
        with self.assertRaises(core.DeliveryError):
            spec.clean_version("1.0")


def run_main(action, version=None, source=None):
    out = io.StringIO()
    with redirect_stdout(out):
        code = spec.main(Namespace(action=action, version=version, source=source))
    return code, out.getvalue()


class ReleaseTest(RepoCase):
    def setUp(self):
        super().setUp()
        write(self.repo / "delivery.toml", 'repo_role = "spec"\nforge = "github"\n')
        make_spec(self.repo)
        self.commit_all("spec")

    def test_lint_output_and_exit_code(self):
        self.assertEqual(run_main("lint"), (0, "spec: green\n"))
        write(self.repo / "spec/acceptance/tests/s001.spec.ts", TESTS.replace("@s001-ac2", "@s001-ac9"))
        code, out = run_main("lint")
        self.assertEqual(code, core.EXIT_RED)
        self.assertEqual(out.splitlines()[-1], "spec: red")
        self.assertIn("spec/stories/s001-create-list.md:15: coverage: AC2 has no test tagged @s001-ac2", out)

    def test_first_release_then_pre_release_minor_is_patch(self):
        code, out = run_main("release")
        self.assertEqual(code, 0, out)
        self.assertIn('git tag -a spec-v0.1.0 -m "spec 0.1.0"', out)
        self.assertIn("## 0.1.0", (self.repo / "spec/CHANGELOG.md").read_text())
        self.assertIn('version = "0.1.0"', (self.repo / "spec/spec.toml").read_text())
        self.commit_all("release")
        git(self.repo, "tag", "-a", "spec-v0.1.0", "-m", "spec 0.1.0")
        with self.assertRaises(core.DeliveryError) as ctx:
            run_main("release")
        self.assertIn("has not changed since spec-v0.1.0", ctx.exception.message)
        write(self.repo / "spec/stories/s001-create-list.md",
              STORY.replace("## UI contract", "- AC3 @main — Given a, When b, Then c\n## UI contract"))
        write(self.repo / "spec/acceptance/tests/more.spec.ts",
              "test.describe('@s001 plus', () => {\n  test('@s001-ac3 c', async () => {});\n});\n")
        self.commit_all("new criterion")
        code, out = run_main("release")
        self.assertEqual(code, 0, out)
        self.assertIn("criteria: 1 added, 0 changed, 0 removed -> minor", out)
        changelog = (self.repo / "spec/CHANGELOG.md").read_text()
        self.assertLess(changelog.index("## 0.1.1"), changelog.index("## 0.1.0"))
        self.assertIn("- s001-ac3 @main — Given a, When b, Then c", changelog)

    def test_released_refuses_a_lower_level_without_override(self):
        write(self.repo / "delivery.toml", 'repo_role = "spec"\nforge = "github"\nrelease_stage = "released"\n')
        self.commit_all("released")
        git(self.repo, "tag", "-a", "spec-v1.0.0", "-m", "spec 1.0.0")
        write(self.repo / "spec/stories/s001-create-list.md", STORY.replace("dans ses listes", "en tête de ses listes"))
        self.commit_all("changed criterion")
        with self.assertRaises(core.DeliveryError) as ctx:
            run_main("release", "1.1.0")
        self.assertEqual(ctx.exception.code, core.EXIT_RED)
        git(self.repo, "commit", "--quiet", "--allow-empty", "-m", "keep minor",
            "--trailer", "Version-Override: wording only")
        code, out = run_main("release", "1.1.0")
        self.assertEqual(code, 0, out)
        self.assertIn("override: wording only", out)
        self.assertIn("## 1.1.0", (self.repo / "spec/CHANGELOG.md").read_text())

    def test_pre_release_refuses_1x_and_versions_go_up(self):
        with self.assertRaises(core.DeliveryError) as ctx:
            run_main("release", "1.0.0")
        self.assertIn("versions stay 0.x", ctx.exception.message)
        code, out = run_main("release", "0.2.0")
        self.assertEqual(code, 0, out)
        self.commit_all("release")
        git(self.repo, "tag", "-a", "spec-v0.2.0", "-m", "spec 0.2.0")
        write(self.repo / "spec/stories/s001-create-list.md",
              STORY.replace("## UI contract", "- AC3 @main — Given a, When b, Then c\n## UI contract"))
        write(self.repo / "spec/acceptance/tests/more.spec.ts",
              "test.describe('@s001 plus', () => {\n  test('@s001-ac3 c', async () => {});\n});\n")
        self.commit_all("new criterion")
        with self.assertRaises(core.DeliveryError) as ctx:
            run_main("release", "0.1.5")
        self.assertIn("is not above the previous version 0.2.0", ctx.exception.message)

    def test_release_is_human_and_needs_green_lint(self):
        os.environ["DELIVERY_ROLE"] = "product-analyst"
        with self.assertRaises(core.DeliveryError) as ctx:
            run_main("release")
        self.assertEqual(ctx.exception.code, core.EXIT_REFUSED)
        os.environ.pop("DELIVERY_ROLE")
        write(self.repo / "spec/stories/s001-create-list.md", STORY.replace("un nom.", "un nom SQL."))
        self.commit_all("leak")
        code, out = run_main("release")
        self.assertEqual(code, core.EXIT_RED)
        self.assertFalse((self.repo / "spec/CHANGELOG.md").exists())


class SyncTest(RepoCase):
    def setUp(self):
        super().setUp()
        self.spec_repo = self.tmp / "spec-repo"
        self.spec_repo.mkdir()
        git(self.spec_repo, "init", "--quiet")
        make_spec(self.spec_repo)
        write(self.spec_repo / "spec/stories/s002-share.md", STORY.replace("s001", "s002").replace("status: ready", "status: draft"))
        write(self.spec_repo / "refinement/01/framing.md", "---\nid: 01\nstatus: closed\n---\n")
        self.commit_all("spec", cwd=self.spec_repo)
        git(self.spec_repo, "tag", "-a", "spec-v0.1.0", "-m", "spec 0.1.0")
        write(self.repo / "delivery.toml", 'repo_role = "impl"\nforge = "github"\n')
        self.commit_all("impl")

    def blob(self, rev="spec-v0.1.0"):
        return git(self.spec_repo, "rev-parse", f"{rev}:spec/stories/s001-create-list.md")

    def test_sync_then_verify(self):
        git(self.repo, "commit", "--quiet", "--allow-empty", "-m", "Merge story/s001 : Créer une liste",
            "-m", f"Story: s001\nSpec: s001@0.1.0#{self.blob()[:7]}")
        before = git(self.repo, "rev-parse", "HEAD")
        code, out = run_main("sync", "0.1.0", str(self.spec_repo))
        self.assertEqual(code, 0, out)
        self.assertIn("2 stories, 1 conforming, 0 outdated", out)
        self.assertEqual(git(self.repo, "rev-parse", "HEAD~1"), before)
        self.assertIn("Spec-Version: 0.1.0", git(self.repo, "log", "-1", "--format=%B"))
        self.assertFalse((self.repo / "spec/refinement").exists())
        lock = (self.repo / "spec.lock").read_text()
        self.assertIn(f'commit = "{git(self.spec_repo, "rev-parse", "spec-v0.1.0^{commit}")}"', lock)
        self.assertIn(f'tree = "{git(self.spec_repo, "rev-parse", "spec-v0.1.0:spec")}"', lock)
        report = (self.repo / "docs/conformance.md").read_text()
        self.assertIn(f"| s001 | Créer une liste | s001@0.1.0#{self.blob()[:7]} | conforming |", report)
        self.assertIn("| s002 |", report)
        self.assertIn("| not merged | — |", report)
        self.assertEqual(run_main("verify")[0], 0)
        self.assertEqual(run_main("sync", "0.1.0")[1].split(";")[0], "spec: already at 0.1.0 (" +
                         git(self.spec_repo, "rev-parse", "spec-v0.1.0^{commit}")[:12] + ")")

        write(self.spec_repo / "spec/stories/s001-create-list.md", STORY.replace("dans ses listes", "en tête"))
        self.commit_all("change", cwd=self.spec_repo)
        git(self.spec_repo, "tag", "-a", "spec-v0.2.0", "-m", "spec 0.2.0")
        code, out = run_main("sync", "spec-v0.2.0")
        self.assertEqual(code, 0, out)
        self.assertIn("1 outdated", out)
        self.assertIn(f"s001@0.2.0#{self.blob('spec-v0.2.0')[:7]} | outdated | s001@0.1.0#",
                      (self.repo / "docs/conformance.md").read_text())

        write(self.repo / "spec/stories/s001-create-list.md", "edited by hand\n")
        self.commit_all("hand edit")
        code, out = run_main("verify")
        self.assertEqual(code, core.EXIT_RED)
        self.assertTrue(out.endswith("spec: red\n"), out)

    def test_verify_needs_a_lock_and_sync_needs_an_impl_repo(self):
        with self.assertRaises(core.DeliveryError) as ctx:
            run_main("verify")
        self.assertEqual(ctx.exception.code, core.EXIT_PRECONDITION)
        with self.assertRaises(core.DeliveryError) as ctx:
            run_main("sync", "0.1.0")
        self.assertIn("no source", ctx.exception.message)
        write(self.repo / "delivery.toml", 'repo_role = "spec"\nforge = "github"\n')
        self.commit_all("spec role")
        with self.assertRaises(core.DeliveryError) as ctx:
            run_main("sync", "0.1.0", str(self.spec_repo))
        self.assertEqual(ctx.exception.code, core.EXIT_PRECONDITION)


if __name__ == "__main__":
    unittest.main()
