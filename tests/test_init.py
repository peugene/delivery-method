"""Installation (init, init --upgrade) and read-only diagnosis (doctor) on a throwaway repo."""

import io
import json
import os
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

from support import ROOT, RepoCase, git, sh, write

from deliveryctl import VERSION, cli, config, init
from deliveryctl.window import mentions


def snapshot(root: Path) -> dict:
    return {p.relative_to(root).as_posix(): (p.read_bytes(), p.stat().st_mode)
            for p in sorted(root.rglob("*")) if p.is_file() and ".git" not in p.relative_to(root).parts}


class InitTest(RepoCase):
    def cli(self, *argv):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = cli.main(list(argv))
        return code, out.getvalue() + err.getvalue()

    def init(self, *extra):
        code, out = self.cli("init", "--role", "impl", "--forge", "github", *extra)
        self.assertEqual(code, 0, out)
        return out

    def settings(self) -> dict:
        return json.loads((self.repo / ".claude" / "settings.json").read_text())

    def test_init_lays_everything_and_commits_nothing(self):
        head = git(self.repo, "rev-parse", "HEAD")
        out = self.init()
        cfg = config.load(self.repo)
        self.assertEqual((cfg.repo_role, cfg.forge, cfg.content_language), ("impl", "github", "fr"))
        self.assertEqual(cfg.commands["acceptance"], "just acceptance {grep}")
        dot = self.repo / ".delivery"
        self.assertTrue((dot / "engine" / "deliveryctl" / "cli.py").exists())
        self.assertEqual(list(dot.rglob("__pycache__")), [])
        self.assertTrue((dot / "templates" / "project" / "delivery.toml").exists())
        self.assertEqual((dot / "rules.md").read_text(), (ROOT / "rules" / "rules.md").read_text())
        self.assertEqual((dot / "VERSION").read_text().strip(), VERSION)
        self.assertTrue(os.access(dot / "deliveryctl", os.X_OK))
        claude_md = (self.repo / "CLAUDE.md").read_text()
        self.assertIn("@.delivery/rules.md", claude_md)
        self.assertIn("## Project conventions", claude_md)
        data = self.settings()
        self.assertIs(data["enabledPlugins"][init.PLUGIN_KEY], True)
        self.assertEqual(data["extraKnownMarketplaces"]["delivery-method"]["source"]["ref"],
                         f"delivery-method--v{VERSION}")
        self.assertIn("SendMessage", data["permissions"]["deny"])
        for rule in ("Bash(deliveryctl merge *)", "Bash(.delivery/deliveryctl merge *)",
                     "Bash(deliveryctl nightly)", "Bash(.delivery/deliveryctl story next *--go*)"):
            self.assertIn(rule, data["permissions"]["ask"])
        ignored = (self.repo / ".gitignore").read_text().splitlines()
        for line in init.GITIGNORE:
            self.assertIn(line, ignored)
        self.assertIn("check:", (self.repo / "justfile").read_text())
        self.assertIn("deliveryctl gate", (self.repo / ".github/workflows/delivery.yml").read_text())
        self.assertEqual(git(self.repo, "rev-parse", "HEAD"), head)
        self.assertIn("Prochaines étapes", out)

    def test_second_run_changes_nothing(self):
        self.init()
        before = snapshot(self.repo)
        out = self.init()
        self.assertEqual(snapshot(self.repo), before)
        self.assertNotIn("created", out)
        self.assertIn("kept     .claude/settings.json", out)

    def test_existing_files_are_merged_by_addition(self):
        write(self.repo / ".claude" / "settings.json", json.dumps(
            {"model": "opus", "permissions": {"allow": ["Bash(npm test)"], "deny": ["Read(./.env)"]}}))
        write(self.repo / "CLAUDE.md", "# Todo\n\nKeep answers short.")
        write(self.repo / ".gitignore", "node_modules/\n/.delivery/run\n")
        write(self.repo / "Justfile", "check:\n    npm test\n")
        self.init()
        data = self.settings()
        self.assertEqual(data["model"], "opus")
        self.assertEqual(data["permissions"]["allow"], ["Bash(npm test)"])
        self.assertEqual(data["permissions"]["deny"], ["Read(./.env)", "SendMessage"])
        self.assertIs(data["enabledPlugins"][init.PLUGIN_KEY], True)
        claude_md = (self.repo / "CLAUDE.md").read_text()
        self.assertTrue(claude_md.startswith("# Todo\n\nKeep answers short.\n"))
        self.assertIn("\n@.delivery/rules.md\n", claude_md)
        ignored = (self.repo / ".gitignore").read_text().splitlines()
        self.assertEqual(ignored[:2], ["node_modules/", "/.delivery/run"])
        self.assertNotIn(".delivery/run/", ignored)
        self.assertFalse((self.repo / "justfile").exists())
        self.assertEqual((self.repo / "Justfile").read_text(), "check:\n    npm test\n")

    def test_conflict_is_listed_and_nothing_is_written(self):
        write(self.repo / ".claude" / "settings.json", json.dumps({"enabledPlugins": {init.PLUGIN_KEY: False}}))
        code, out = self.cli("init", "--role", "impl", "--forge", "none")
        self.assertEqual(code, 3)
        self.assertIn("enabledPlugins.delivery-method@delivery-method: false", out)
        self.assertFalse((self.repo / "delivery.toml").exists())
        self.assertFalse((self.repo / ".delivery").exists())

    def test_role_is_required_and_dry_run_writes_nothing(self):
        code, out = self.cli("init", "--forge", "none")
        self.assertEqual(code, 3)
        self.assertIn("--role", out)
        before = snapshot(self.repo)
        code, out = self.cli("init", "--role", "spec", "--forge", "none", "--dry-run")
        self.assertEqual(code, 0, out)
        self.assertIn("created  delivery.toml", out)
        self.assertEqual(snapshot(self.repo), before)

    def test_gitlab_ci_and_include_hint(self):
        code, out = self.cli("init", "--role", "single", "--forge", "gitlab", "--language", "en")
        self.assertEqual(code, 0, out)
        self.assertTrue((self.repo / ".gitlab" / "delivery-ci.yml").exists())
        self.assertFalse((self.repo / ".github").exists())
        self.assertIn("- local: .gitlab/delivery-ci.yml", out)
        self.assertEqual(config.load(self.repo).content_language, "en")

    def test_upgrade_refreshes_the_engine_copy_only(self):
        self.init()
        engine = self.repo / ".delivery" / "engine" / "deliveryctl"
        (engine / "cli.py").write_text("# edited\n")
        (engine / "stale.py").write_text("# from an older version\n")
        (self.repo / ".delivery" / "VERSION").write_text("0.0.1\n")
        data = self.settings()
        data["extraKnownMarketplaces"]["delivery-method"]["source"]["ref"] = "delivery-method--v0.0.1"
        write(self.repo / ".claude" / "settings.json", json.dumps(data))
        write(self.repo / "justfile", "check:\n    make test\n")
        self.init()
        self.assertEqual((engine / "cli.py").read_text(), "# edited\n")
        code, out = self.cli("init", "--upgrade")
        self.assertEqual(code, 0, out)
        self.assertEqual((engine / "cli.py").read_text(),
                         (ROOT / "engine" / "deliveryctl" / "cli.py").read_text())
        self.assertFalse((engine / "stale.py").exists())
        self.assertEqual((self.repo / ".delivery" / "VERSION").read_text().strip(), VERSION)
        self.assertEqual(self.settings()["extraKnownMarketplaces"]["delivery-method"]["source"]["ref"],
                         f"delivery-method--v{VERSION}")
        self.assertEqual((self.repo / "justfile").read_text(), "check:\n    make test\n")
        (self.repo / ".delivery" / "VERSION").write_text("9.0.0\n")
        code, out = self.cli("init", "--upgrade")
        self.assertEqual(code, 3)
        self.assertIn("newer than the plugin", out)

    def test_copied_launcher_runs_and_doctor_says_ok(self):
        self.init()
        proc = sh([str(self.repo / ".delivery" / "deliveryctl"), "--version"], self.repo)
        self.assertEqual(proc.stdout.strip(), f"deliveryctl {VERSION}")
        proc = sh([str(self.repo / ".delivery" / "deliveryctl"), "doctor"], self.repo)
        self.assertIn("ok: engine copy", proc.stdout)
        self.assertEqual(list((self.repo / ".delivery").rglob("__pycache__")), [])

    def test_doctor_returns_zero_and_notes_mentions(self):
        code, out = self.cli("doctor")
        self.assertEqual(code, 0, out)
        self.assertIn("warn: no engine copy", out)
        self.init()
        write(self.repo / "CLAUDE.md", f"@.delivery/rules.md\n\nOpen stories in {mentions.NAME}.\n")
        self.assertEqual(mentions.files_naming_it(self.repo, self.home), [self.repo / "CLAUDE.md"])
        code, out = self.cli("doctor")
        self.assertEqual(code, 0, out)
        lines = [line for line in out.splitlines() if line.strip()]
        self.assertTrue(all(line.split(":", 1)[0] in ("ok", "note", "warn") for line in lines), out)
        self.assertIn("note: CLAUDE.md names the terminal multiplexer", out)
        self.assertIn("ok: engine copy", out)

    def test_doctor_notes_a_version_tag_without_accepted_report(self):
        from deliveryctl.gitops import Git
        code, _ = self.cli("init", "--role", "impl", "--forge", "none")
        self.assertEqual(code, 0)
        self.commit_all("equip")
        git(self.repo, "tag", "v0.1.0")
        code, out = self.cli("doctor")
        self.assertIn("note: tag v0.1.0 has no accepted qualification report", out)
        tree = Git(self.repo).code_tree("v0.1.0")
        write(self.repo / "qualification" / "reports" / "0.1.0.md",
              f"# Qualification 0.1.0\n\nVerdict: accepted\nTree: {tree}\nCommand: just acceptance\n"
              "Result: 12 passed\nBy: qualification-lead\n")
        self.commit_all("qualification report")
        git(self.repo, "tag", "v0.1.1")
        code, out = self.cli("doctor")
        self.assertEqual(code, 0, out)
        self.assertNotIn("qualification report", out)

    def test_doctor_warns_when_no_ci_runs_on_merge_requests(self):
        self.init()
        code, out = self.cli("doctor")
        self.assertIn("warn: .github/workflows/delivery.yml not committed", out)
        self.commit_all("equip")
        code, out = self.cli("doctor")
        self.assertIn("ok: CI of merge requests", out)
        (self.repo / ".github" / "workflows" / "delivery.yml").unlink()
        code, out = self.cli("doctor")
        self.assertIn("warn: .github/workflows/delivery.yml is missing", out)
        write(self.repo / "delivery.toml", (self.repo / "delivery.toml").read_text().replace(
            'forge = "github"', 'forge = "gitlab"'))
        code, out = self.cli("doctor")
        self.assertIn("warn: .gitlab-ci.yml does not include .gitlab/delivery-ci.yml", out)

    def test_doctor_notes_a_repository_claude_code_does_not_trust(self):
        code, _ = self.cli("init", "--role", "impl", "--forge", "none")
        self.assertEqual(code, 0)
        write(self.tmp / "bin" / "claude", "#!/bin/sh\nexit 0\n").chmod(0o755)
        os.environ.update(PATH=f"{self.tmp / 'bin'}{os.pathsep}{os.environ['PATH']}", DELIVERY_WINDOW="auto")
        claude_json = self.home / ".claude.json"
        claude_json.write_text(json.dumps({"projects": {str(self.repo): {"hasTrustDialogAccepted": False}}}))
        code, out = self.cli("doctor")
        self.assertIn("note: Claude Code has no accepted trust", out)
        claude_json.write_text(json.dumps({"projects": {str(self.repo): {"hasTrustDialogAccepted": True}}}))
        code, out = self.cli("doctor")
        self.assertNotIn("accepted trust", out)
        os.environ["DELIVERY_WINDOW"] = "terminal"
        claude_json.write_text("{}")
        code, out = self.cli("doctor")
        self.assertNotIn("accepted trust", out)
