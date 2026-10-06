"""Installation (init, init --upgrade) and read-only diagnosis (doctor) on a throwaway repo."""

import io
import json
import os
import shutil
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

from support import ROOT, RepoCase, git, sh, write

from deliveryctl import VERSION, cli, config, core, init, spec
from deliveryctl.window import mentions


def snapshot(root: Path) -> dict:
    return {p.relative_to(root).as_posix(): (p.read_bytes(), p.stat().st_mode)
            for p in sorted(root.rglob("*")) if p.is_file() and ".git" not in p.relative_to(root).parts}


class InitTest(RepoCase):
    with_agents = False

    def cli(self, *argv, ask=False):
        """Run the engine; `init` is told --yes (nobody answers here) unless the test is about the question."""
        argv = list(argv)
        if argv[:1] == ["init"] and not ask and "--dry-run" not in argv:
            argv.append("--yes")
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = cli.main(argv)
        return code, out.getvalue() + err.getvalue()

    def init(self, *extra):
        code, out = self.cli("init", "impl", "todo-spec", "--forge", "github", *extra)
        self.assertEqual(code, 0, out)
        return out

    def settings(self) -> dict:
        return json.loads((self.repo / ".claude" / "settings.json").read_text())

    def test_next_steps_are_few_and_carry_no_cloud_note(self):
        out = self.init()
        lines = out.split("Prochaines étapes :\n")[1].splitlines()
        self.assertLessEqual(len(lines), 4, out)
        self.assertRegex(lines[0], r"^  \d+ fichiers posés, commités et poussés sur main$")
        self.assertIn("spec sync <version>", lines[1])
        self.assertNotIn("/remote-env", "\n".join(lines))
        self.assertNotIn("cloud-setup.sh", out)
        self.assertNotIn("Relisez", out)

    def test_init_lays_everything_in_one_commit_and_pushes_it(self):
        head = git(self.repo, "rev-parse", "HEAD")
        out = self.init()
        cfg = config.load(self.repo)
        self.assertEqual((cfg.repo_role, cfg.forge, cfg.content_language), ("impl", "github", "fr"))
        self.assertEqual(cfg.commands["acceptance"], "just acceptance {grep}")
        self.assertIn("max_in_flight = 3", (self.repo / "delivery.toml").read_text())
        self.assertEqual(cfg.max_in_flight, 3)
        dot = self.repo / ".delivery"
        self.assertTrue((dot / "engine" / "deliveryctl" / "cli.py").exists())
        self.assertEqual(list(dot.rglob("__pycache__")), [])
        self.assertTrue((dot / "templates" / "project" / "delivery.toml").exists())
        self.assertTrue((dot / "templates" / "project" / "cloud-setup.sh").exists())
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
        pre = data["hooks"]["PreToolUse"][0]
        self.assertEqual(pre["matcher"], "Bash")
        self.assertEqual([(h["if"], h["command"], h["timeout"]) for h in pre["hooks"]],
                         [(rule, '"$CLAUDE_PROJECT_DIR"/.delivery/deliveryctl hook pre-tool', 10)
                          for rule in ("Bash(deliveryctl *)", "Bash(.delivery/deliveryctl *)")])
        self.assertIn("SendMessage", data["permissions"]["deny"])
        for rule in ("Bash(deliveryctl merge *)", "Bash(.delivery/deliveryctl merge *)",
                     "Bash(deliveryctl nightly)", "Bash(.delivery/deliveryctl story next *--go*)"):
            self.assertIn(rule, data["permissions"]["ask"])
        ignored = (self.repo / ".gitignore").read_text().splitlines()
        for line in init.GITIGNORE:
            self.assertIn(line, ignored)
        self.assertIn("check:", (self.repo / "justfile").read_text())
        self.assertIn("deliveryctl gate", (self.repo / ".github/workflows/delivery.yml").read_text())
        self.assertEqual(git(self.repo, "rev-list", "--count", f"{head}..HEAD"), "1")
        message = git(self.repo, "log", "-1", "--format=%B")
        self.assertEqual(message.splitlines()[0], f"Équipe le dépôt avec delivery-method {VERSION} (impl)")
        self.assertEqual(message.strip().splitlines()[-1], f"Delivery-Method: {VERSION}")
        self.assertEqual(git(self.repo, "status", "--porcelain"), "")
        self.assertEqual(git(self.origin, "rev-parse", "main"), git(self.repo, "rev-parse", "HEAD"))
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

    def test_brainstorm_drafts_are_ignored_by_a_new_gitignore(self):
        self.init()
        self.assertIn("docs/maybe/*.draft.md", (self.repo / ".gitignore").read_text().splitlines())

    def test_brainstorm_drafts_are_added_to_an_existing_gitignore_and_on_upgrade(self):
        write(self.repo / ".gitignore", "node_modules/\n")
        self.init()
        path = self.repo / ".gitignore"
        self.assertIn("docs/maybe/*.draft.md", path.read_text().splitlines())
        path.write_text("node_modules/\n.delivery/run/\n")           # a project equipped before drafts
        code, out = self.cli("init", "--upgrade")
        self.assertEqual(code, 0, out)
        ignored = path.read_text().splitlines()
        self.assertEqual(ignored.count("docs/maybe/*.draft.md"), 1)
        self.assertEqual(ignored[:2], ["node_modules/", ".delivery/run/"])

    def test_conflict_is_listed_and_nothing_is_written(self):
        write(self.repo / ".claude" / "settings.json", json.dumps({"permissions": {"deny": "SendMessage"}}))
        code, out = self.cli("init", "impl", "todo-spec", "--forge", "github")
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
        code, out = self.cli("init", "impl", "todo-spec", "--forge", "github")
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
        self.assertEqual(data["hooks"]["PreToolUse"], init.method_hooks()["PreToolUse"])
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

    def test_upgrade_adds_the_pre_tool_hook_and_doctor_warns_without_it(self):
        self.init()
        data = self.settings()
        del data["hooks"]["PreToolUse"]
        write(self.repo / ".claude" / "settings.json", json.dumps(data))
        code, out = self.cli("doctor")
        self.assertIn("the PreToolUse hook is missing", out)
        code, out = self.cli("init", "--upgrade")
        self.assertEqual(code, 0, out)
        self.assertEqual(self.settings()["hooks"]["PreToolUse"], init.method_hooks()["PreToolUse"])
        self.assertNotIn("PreToolUse", self.cli("doctor")[1])

    def test_layout_defaults_to_single_and_dry_run_writes_nothing(self):
        before = snapshot(self.repo)
        code, out = self.cli("init", "--forge", "github", "--dry-run")
        self.assertEqual(code, 0, out)
        self.assertIn("created  delivery.toml", out)
        self.assertEqual(snapshot(self.repo), before)
        code, out = self.cli("init", "--forge", "github")
        self.assertEqual(code, 0, out)
        self.assertEqual(config.load(self.repo).repo_role, "single")
        self.assertTrue((self.repo / "spec" / "spec.toml").exists())
        self.assertNotIn("spec_source", (self.repo / "delivery.toml").read_text())

    def test_impl_needs_a_spec_repository_and_only_impl_takes_one(self):
        before = snapshot(self.repo)
        code, out = self.cli("init", "impl", "--forge", "github")
        self.assertEqual(code, core.EXIT_ERROR)
        self.assertIn("usage: deliveryctl init impl <spec repository>", out)
        code, out = self.cli("init", "spec", "one", "two", "--forge", "github")
        self.assertEqual(code, core.EXIT_ERROR)
        self.assertIn("usage: deliveryctl init spec [name]: unexpected 'two'", out)
        code, out = self.cli("init", "impl", "todo-spec", "todo-kotlin", "extra", "--forge", "github")
        self.assertEqual(code, core.EXIT_ERROR)
        self.assertIn("unexpected 'extra'", out)
        self.assertEqual(snapshot(self.repo), before)

    def test_spec_source_is_written_for_impl_and_read_by_spec_sync(self):
        sources = {"todo-spec": "https://github.com/acme/todo-spec.git", "other/todo-spec": "https://github.com/other/todo-spec.git",
                   "https://example.org/x/y.git": "https://example.org/x/y.git"}
        git(self.repo, "remote", "set-url", "origin", "https://github.com/acme/todo-kotlin.git")
        for value, expected in sources.items():
            (self.repo / "delivery.toml").unlink(missing_ok=True)
            code, out = self.cli("init", "impl", value, "--dry-run")
            self.assertEqual(code, 0, out)
            self.assertEqual(init.spec_address(self.repo, value, "github"), expected)
        local = self.tmp / "todo-spec"
        local.mkdir()
        self.assertEqual(init.spec_address(self.repo, str(local), "github"), str(local))
        git(self.repo, "remote", "set-url", "origin", "git@forge.example.org:acme/todo-kotlin.git")
        self.assertEqual(init.spec_address(self.repo, "todo-spec", "github"), "git@forge.example.org:acme/todo-spec.git")
        git(self.repo, "config", f"url.{self.origin}.pushInsteadOf", "git@forge.example.org:acme/todo-kotlin.git")
        code, out = self.cli("init", "impl", "todo-spec", "--forge", "github")
        self.assertEqual(code, 0, out)
        cfg = config.load(self.repo)
        self.assertEqual((cfg.repo_role, cfg.spec_source), ("impl", "git@forge.example.org:acme/todo-spec.git"))
        self.assertIn("Une fois la spec publiée", out)
        self.assertNotIn("spec/product/brief.md", out)
        with self.assertRaises(core.DeliveryError) as ctx:
            config.parse({"repo_role": "spec", "spec_source": "x"}, self.repo)
        self.assertIn("spec_source belongs to", ctx.exception.message)
        self.assertEqual(config.parse({"repo_role": "impl"}, self.repo).spec_source, "")

    def test_spec_sync_falls_back_on_the_configured_source(self):
        write(self.repo / "delivery.toml", 'repo_role = "impl"\nforge = "github"\nspec_source = "/nowhere/todo-spec"\n')
        with self.assertRaises(core.DeliveryError) as ctx:
            spec.sync(self.repo, "0.1.0", None)
        self.assertNotIn("no source", ctx.exception.message)

    def test_spec_layout_lays_a_working_justfile_and_names_the_product(self):
        code, out = self.cli("init", "spec", "--forge", "github")
        self.assertEqual(code, 0, out)
        recipes = (self.repo / "justfile").read_text()
        self.assertEqual(recipes, (ROOT / "templates" / "project" / "justfile-spec").read_text())
        self.assertIn(".delivery/deliveryctl spec lint", recipes)
        self.assertIn("npm install --no-audit --no-fund", recipes)
        self.assertIn("npx playwright install chromium", recipes)
        self.assertIn('APP_CMD="just serve ${DELIVERY_PORT:-3999}"', recipes)
        self.assertIn("PORT={{port}} node spec/acceptance/fixtures/empty-app/server.mjs", recipes)
        self.assertNotIn("définir la recette", recipes)
        self.assertIn(f'name = "{self.repo.name}"', (self.repo / "spec" / "spec.toml").read_text())
        self.assertNotIn("<nom du produit>", (self.repo / "spec" / "spec.toml").read_text())
        self.assertIn("claude --agent product-analyst", out)
        self.assertIn("/brainstorm --vision", out)
        self.assertNotIn("/remote-env", out.split("Prochaines étapes")[1])
        if shutil.which("just"):
            summary = sh(["just", "--summary"], self.repo).stdout
            self.assertEqual(sorted(summary.split()), ["acceptance", "check", "serve", "test"])

    def test_single_layout_keeps_the_stack_justfile(self):
        code, out = self.cli("init", "single", "--forge", "github")
        self.assertEqual(code, 0, out)
        self.assertEqual((self.repo / "justfile").read_text(), (ROOT / "templates" / "project" / "justfile").read_text())

    def test_machine_language_feeds_content_language(self):
        self.assertEqual((config.machine()["language"], config.machine()["visibility"]), ("fr", "private"))
        write(config.machine_path(), 'language = "en"\nvisibility = "public"\n')
        self.assertEqual((config.machine()["language"], config.machine()["visibility"]), ("en", "public"))
        code, out = self.cli("init", "single", "--forge", "github")
        self.assertEqual(code, 0, out)
        self.assertEqual(config.load(self.repo).content_language, "en")

    def test_machine_refuses_a_bad_visibility(self):
        write(config.machine_path(), 'visibility = "secret"\n')
        with self.assertRaises(core.DeliveryError) as ctx:
            config.machine()
        self.assertIn("visibility must be one of private, public, internal", ctx.exception.message)

    def test_machine_forge_settings(self):
        defaults = config.machine()
        self.assertEqual((defaults["forge"], defaults["gitlab_host"], defaults["gitlab_group"]), ("github", "", ""))
        write(config.machine_path(), 'forge = "gitlab"\ngitlab_host = "gitlab.example.org"\ngitlab_group = "acme"\n'
                                     'visibility = "internal"\n')
        found = config.machine()
        self.assertEqual((found["forge"], found["gitlab_host"], found["gitlab_group"], found["visibility"]),
                         ("gitlab", "gitlab.example.org", "acme", "internal"))
        write(config.machine_path(), 'forge = "bitbucket"\n')
        with self.assertRaises(core.DeliveryError) as ctx:
            config.machine()
        self.assertIn("forge must be one of github, gitlab", ctx.exception.message)

    def test_init_writes_the_brief_from_the_template(self):
        code, out = self.cli("init", "spec", "--forge", "github")
        self.assertEqual(code, 0, out)
        brief = (self.repo / "spec" / "product" / "brief.md").read_text()
        self.assertEqual(brief, (ROOT / "templates" / "spec" / "brief.md").read_text())
        self.assertTrue(brief.startswith("# Brief\n"))
        for section in ("Purpose", "Users", "Principles", "Blocks", "Not the product"):
            self.assertIn(f"\n## {section}\n", brief)
        self.assertEqual(spec.lint(self.repo), [])

    def test_init_writes_the_implementer_key(self):
        self.init()
        text = (self.repo / "delivery.toml").read_text()
        self.assertIn('implementer = "cloud"', text)
        self.assertEqual(config.load(self.repo).implementer, "cloud")
        (self.repo / "delivery.toml").unlink()
        code, out = self.cli("init", "single", "--forge", "gitlab")
        self.assertEqual(code, 0, out)
        self.assertIn('implementer = "local"', (self.repo / "delivery.toml").read_text())
        self.assertEqual(config.load(self.repo).implementer, "local")

    def test_gitlab_ci_is_laid_and_included(self):
        code, out = self.cli("init", "single", "--forge", "gitlab", "--language", "en")
        self.assertEqual(code, 0, out)
        self.assertTrue((self.repo / ".gitlab" / "delivery-ci.yml").exists())
        self.assertFalse((self.repo / ".github").exists())
        self.assertEqual((self.repo / ".gitlab-ci.yml").read_text(), "include:\n  - local: .gitlab/delivery-ci.yml\n")
        self.assertNotIn("Ajoutez à .gitlab-ci.yml", out)
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
        code, _ = self.cli("init", "impl", "todo-spec", "--forge", "github")
        self.assertEqual(code, 0)
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
        self.assertIn("ok: CI of merge requests", out)
        git(self.repo, "rm", "--cached", "--quiet", ".github/workflows/delivery.yml")
        code, out = self.cli("doctor")
        self.assertIn("warn: .github/workflows/delivery.yml not committed", out)
        (self.repo / ".github" / "workflows" / "delivery.yml").unlink()
        code, out = self.cli("doctor")
        self.assertIn("warn: .github/workflows/delivery.yml is missing", out)
        write(self.repo / "delivery.toml", (self.repo / "delivery.toml").read_text().replace(
            'forge = "github"', 'forge = "gitlab"').replace('implementer = "cloud"', 'implementer = "local"'))
        code, out = self.cli("doctor")
        self.assertIn("warn: .gitlab-ci.yml does not include .gitlab/delivery-ci.yml", out)

    def test_doctor_notes_a_repository_claude_code_does_not_trust(self):
        code, _ = self.cli("init", "impl", "todo-spec", "--forge", "github")
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
