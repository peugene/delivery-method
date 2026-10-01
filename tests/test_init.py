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
    with_agents = False

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
        self.assertIs(data["enabledPlugins"][init.PLUGIN_KEY], False)
        self.assertEqual(data["extraKnownMarketplaces"]["delivery-method"]["source"]["ref"],
                         f"delivery-method--v{VERSION}")
        self.assertEqual(data["hooks"], init.method_hooks())
        stop = data["hooks"]["Stop"][0]["hooks"][0]
        self.assertEqual((stop["command"], stop["timeout"]),
                         ('"$CLAUDE_PROJECT_DIR"/.delivery/deliveryctl hook stop', 40))
        start = data["hooks"]["SessionStart"][0]
        self.assertNotIn("matcher", start)
        self.assertEqual((start["hooks"][0]["command"], start["hooks"][0]["timeout"]),
                         ('"$CLAUDE_PROJECT_DIR"/.delivery/deliveryctl hook session-start', 10))
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
        self.assertIs(data["enabledPlugins"][init.PLUGIN_KEY], False)
        claude_md = (self.repo / "CLAUDE.md").read_text()
        self.assertTrue(claude_md.startswith("# Todo\n\nKeep answers short.\n"))
        self.assertIn("\n@.delivery/rules.md\n", claude_md)
        ignored = (self.repo / ".gitignore").read_text().splitlines()
        self.assertEqual(ignored[:2], ["node_modules/", "/.delivery/run"])
        self.assertNotIn(".delivery/run/", ignored)
        self.assertFalse((self.repo / "justfile").exists())
        self.assertEqual((self.repo / "Justfile").read_text(), "check:\n    npm test\n")

    def test_conflict_is_listed_and_nothing_is_written(self):
        write(self.repo / ".claude" / "settings.json", json.dumps({"permissions": {"deny": "SendMessage"}}))
        code, out = self.cli("init", "--role", "impl", "--forge", "github")
        self.assertEqual(code, 3)
        self.assertIn("permissions.deny", out)
        self.assertFalse((self.repo / "delivery.toml").exists())
        self.assertFalse((self.repo / ".delivery").exists())

    def test_first_init_disables_a_plugin_installed_at_project_scope(self):
        write(self.repo / ".claude" / "settings.json",
              json.dumps({"enabledPlugins": {init.PLUGIN_KEY: True, "x@y": True}}))
        self.init()
        plugins = self.settings()["enabledPlugins"]
        self.assertEqual(plugins, {init.PLUGIN_KEY: False, "x@y": True})

    def test_copy_of_the_method_lands_in_claude_without_the_namespace(self):
        self.init()
        claude = self.repo / ".claude"
        for agent in (ROOT / "agents").glob("*.md"):
            self.assertTrue((claude / "agents" / agent.name).exists(), agent.name)
        for skill in (ROOT / "skills").iterdir():
            self.assertTrue((claude / "skills" / skill.name / "SKILL.md").exists(), skill.name)
        commands = sorted(p.name for p in (claude / "commands").iterdir())
        self.assertEqual(commands, sorted(p.name for p in (ROOT / "commands").glob("*.md") if p.name != "init.md"))
        self.assertIn("run-campaign.md", commands)
        lead = (claude / "agents" / "technical-lead.md").read_text()
        self.assertIn("`/run-campaign <campaign>`", lead)
        self.assertIn("skills `anchoring` and", lead)
        self.assertNotIn("delivery-method:", lead)
        plugin_lead = (ROOT / "agents" / "technical-lead.md").read_text()
        self.assertIn("/delivery-method:run-campaign", plugin_lead)    # the plugin's own files keep it
        spec_frame = (claude / "commands" / "spec-frame.md").read_text()
        self.assertIn("`claude --agent product-analyst`", spec_frame)
        self.assertIn("/spec-write <incr>", spec_frame)
        self.assertNotIn("delivery-method:", spec_frame)
        manifest = json.loads((self.repo / ".delivery" / "method.json").read_text())
        self.assertEqual(manifest["version"], VERSION)
        self.assertEqual(set(manifest["files"]), {p.relative_to(self.repo).as_posix()
                                                  for p in claude.rglob("*") if p.is_file()} - {".claude/settings.json"})
        for rel, sha in manifest["files"].items():
            self.assertEqual(init.sha((self.repo / rel).read_bytes()), sha)

    def test_namespace_is_removed_from_known_names_only(self):
        plugin = self.tmp / "plugin"
        for rel, text in {"agents/a.md": "see `delivery-method:s`, /delivery-method:c and /delivery-method:init, "
                                         "delivery-method:other, delivery-method:s-x\n",
                          "skills/s/SKILL.md": "x", "skills/s/notes.txt": "delivery-method:s\n",
                          "commands/c.md": "y", "commands/init.md": "z"}.items():
            write(plugin / rel, text)
        files = init.method_files(plugin)
        self.assertEqual(sorted(files), [".claude/agents/a.md", ".claude/commands/c.md",
                                         ".claude/skills/s/SKILL.md", ".claude/skills/s/notes.txt"])
        self.assertEqual(files[".claude/agents/a.md"].decode(),
                         "see `s`, /c and /delivery-method:init, delivery-method:other, delivery-method:s-x\n")
        self.assertEqual(files[".claude/skills/s/notes.txt"], b"delivery-method:s\n")

    def test_init_refuses_a_different_file_at_a_copy_path(self):
        write(self.repo / ".claude" / "agents" / "refuter.md", "mine\n")
        code, out = self.cli("init", "--role", "impl", "--forge", "github")
        self.assertEqual(code, 3)
        self.assertIn(".claude/agents/refuter.md", out)
        self.assertFalse((self.repo / ".delivery").exists())
        write(self.repo / ".claude" / "agents" / "mine.md", "the project's own\n")

    def test_upgrade_refreshes_the_copy_and_leaves_the_projects_own_files(self):
        self.init()
        write(self.repo / ".claude" / "agents" / "mine.md", "the project's own\n")
        write(self.repo / ".claude" / "skills" / "mine" / "SKILL.md", "own skill\n")
        manifest_path = self.repo / ".delivery" / "method.json"
        manifest = json.loads(manifest_path.read_text())
        old = self.repo / ".claude" / "commands" / "gone.md"
        write(old, "from an older version\n")
        write(self.repo / ".claude" / "skills" / "gone" / "SKILL.md", "from an older version\n")
        manifest["files"][".claude/commands/gone.md"] = init.sha(old.read_bytes())
        manifest["files"][".claude/skills/gone/SKILL.md"] = init.sha(b"from an older version\n")
        old_text = "# an older refuter\n"
        refuter = self.repo / ".claude" / "agents" / "refuter.md"
        refuter.write_text(old_text)
        manifest["files"][".claude/agents/refuter.md"] = init.sha(old_text.encode())
        manifest_path.write_text(json.dumps(manifest))
        data = self.settings()
        data["enabledPlugins"][init.PLUGIN_KEY] = True              # equipped by 0.1.0
        data["hooks"] = {"Stop": [{"hooks": [{"type": "command", "command": "mine"}]},
                                  {"hooks": [{"type": "command", "command": "x/.delivery/deliveryctl hook stop"}]}]}
        write(self.repo / ".claude" / "settings.json", json.dumps(data))
        code, out = self.cli("init", "--upgrade")
        self.assertEqual(code, 0, out)
        self.assertIn("updated  .claude/agents/refuter.md", out)
        self.assertIn("removed  .claude/commands/gone.md", out)
        self.assertEqual(refuter.read_text(), (ROOT / "agents" / "refuter.md").read_text().replace(
            "delivery-method:", ""))
        self.assertFalse(old.exists())
        self.assertFalse((self.repo / ".claude" / "skills" / "gone").exists())
        self.assertEqual((self.repo / ".claude" / "agents" / "mine.md").read_text(), "the project's own\n")
        self.assertTrue((self.repo / ".claude" / "skills" / "mine" / "SKILL.md").exists())
        data = self.settings()
        self.assertIs(data["enabledPlugins"][init.PLUGIN_KEY], False)
        self.assertEqual(data["hooks"]["Stop"][0]["hooks"][0]["command"], "mine")
        self.assertEqual([e["hooks"][0]["command"] for e in data["hooks"]["Stop"]],
                         ["mine", init.HOOK_STOP])
        self.assertEqual(data["hooks"]["SessionStart"], init.method_hooks()["SessionStart"])
        self.assertNotIn(".claude/commands/gone.md", json.loads(manifest_path.read_text())["files"])
        code, out = self.cli("doctor")
        self.assertNotIn("warn: method copy", out)

    def test_upgrade_refuses_a_hand_edited_copy_before_writing(self):
        self.init()
        edited = self.repo / ".claude" / "agents" / "refuter.md"
        edited.write_text("edited by hand\n")
        (self.repo / ".claude" / "commands" / "spec-frame.md").unlink()
        data = self.settings()
        data["enabledPlugins"][init.PLUGIN_KEY] = True
        write(self.repo / ".claude" / "settings.json", json.dumps(data))
        (self.repo / ".delivery" / "VERSION").write_text("0.0.1\n")
        before = snapshot(self.repo)
        code, out = self.cli("init", "--upgrade")
        self.assertEqual(code, 3)
        self.assertIn(".claude/agents/refuter.md", out)
        self.assertEqual(snapshot(self.repo), before)

    def test_doctor_warns_on_a_missing_or_edited_copy(self):
        code, out = self.cli("doctor")
        self.assertNotIn("method copy", out)            # no project copy at all: engine warning only
        self.init()
        code, out = self.cli("doctor")
        self.assertIn("ok: method copy", out)
        self.assertNotIn("warn: method copy", out)
        (self.repo / ".claude" / "agents" / "refuter.md").write_text("edited\n")
        (self.repo / ".claude" / "skills" / "anchoring" / "SKILL.md").unlink()
        data = self.settings()
        data["enabledPlugins"][init.PLUGIN_KEY] = True
        del data["hooks"]["Stop"]
        write(self.repo / ".claude" / "settings.json", json.dumps(data))
        code, out = self.cli("doctor")
        for text in ("warn: method copy: .claude/agents/refuter.md was edited",
                     "warn: method copy: .claude/skills/anchoring/SKILL.md is missing",
                     "does not disable delivery-method@delivery-method", "the Stop hook is missing"):
            self.assertIn(text, out)
        self.assertIn("deliveryctl init --upgrade", out)
        (self.repo / ".delivery" / "method.json").unlink()
        code, out = self.cli("doctor")
        self.assertIn("warn: no .delivery/method.json", out)

    def test_role_is_required_and_dry_run_writes_nothing(self):
        code, out = self.cli("init", "--forge", "github")
        self.assertEqual(code, 3)
        self.assertIn("--role", out)
        before = snapshot(self.repo)
        code, out = self.cli("init", "--role", "spec", "--forge", "github", "--dry-run")
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
        code, _ = self.cli("init", "--role", "impl", "--forge", "github")
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
        code, _ = self.cli("init", "--role", "impl", "--forge", "github")
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
