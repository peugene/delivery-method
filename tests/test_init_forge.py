"""What `init` does on the forge after one "ok": creates the repository, sets the git address of a
public one, commits and pushes what it laid down, protects the default branch. GitHub and GitLab
are played by the fake `gh` and `glab` of tests/support.py; nothing reaches the network."""

import io
import json
import os
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

from support import RepoCase, fake_glab, git, map_remotes, sh, write

from deliveryctl import VERSION, cli, config, core, init
from deliveryctl.forge import Forge
from deliveryctl.gitops import Git

GITLAB_RULE = {"main": {"name": "main", "allow_force_push": False,
                        "push_access_levels": [{"access_level": 40}], "merge_access_levels": [{"access_level": 40}]}}


class Tty:
    def isatty(self):
        return True


class ForgeInitCase(RepoCase):
    with_agents = False

    def setUp(self):
        super().setUp()
        self.work = self.tmp / "work"
        self.work.mkdir()
        fake_glab(self.forge_dir)
        map_remotes(self.forge_dir, "https://github.com/", "git@gitlab.test:")
        git(self.repo, "remote", "set-url", "origin", "https://github.com/test-owner/todo.git")   # the repository of the tests
        sh(["git", "config", "--global", "--add", f"url.{self.origin}.insteadOf", "https://github.com/test-owner/todo.git"],
           self.tmp)

    def machine(self, **values):
        write(config.machine_path(), "".join(f'{k} = "{v}"\n' for k, v in values.items()))

    def cli(self, *argv, ask=False):
        argv = list(argv)
        if argv[:1] == ["init"] and not ask and "--dry-run" not in argv:
            argv.append("--yes")
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = cli.main(argv)
        return code, out.getvalue() + err.getvalue()

    def calls(self, name="calls") -> list[str]:
        path = self.forge_dir / name
        return path.read_text().splitlines() if path.exists() else []

    def changing(self, name="calls") -> list[str]:
        """The calls that change something on a forge."""
        return [c for c in self.calls(name) if " -X " in f" {c} " and " -X GET" not in c or "repo create" in c]

    def origin_of(self, root) -> str:
        return git(root, "config", "--get", "remote.origin.url")

    def seen(self, name):
        return json.loads((self.forge_dir / name).read_text())

    def remote_head(self, path) -> str:
        return git(self.forge_dir / "remotes" / f"{path}.git", "rev-parse", "main")

    def tree(self, root: Path) -> dict:
        return {p.relative_to(root).as_posix(): p.read_bytes() for p in sorted(root.rglob("*"))
                if p.is_file() and ".git" not in p.relative_to(root).parts}


class CreateOnGithubTest(ForgeInitCase):
    def setUp(self):
        super().setUp()
        os.chdir(self.work)

    def test_a_name_creates_the_folder_the_repository_and_pushes(self):
        code, out = self.cli("init", "single", "labo")
        self.assertEqual(code, 0, out)
        root = self.work / "labo"
        self.assertEqual((self.forge_dir / "created").read_text(), "test-owner/labo")
        self.assertEqual((self.forge_dir / "visibility").read_text(), "PRIVATE")
        self.assertEqual(self.origin_of(root), "https://github.com/test-owner/labo.git")
        self.assertEqual(git(root, "rev-list", "--count", "HEAD"), "1")
        self.assertEqual(git(root, "rev-parse", "HEAD"), self.remote_head("test-owner/labo"))
        self.assertEqual(git(root, "status", "--porcelain"), "")
        cfg = config.load(root)
        self.assertEqual((cfg.repo_role, cfg.forge), ("single", "github"))
        self.assertIn("Dépôt : créer test-owner/labo sur GitHub, privé", out)
        self.assertLessEqual(len(out.split("Prochaines étapes")[0].split("  created")[0].splitlines()), 9)

    def test_the_launcher_is_committed_executable_where_the_file_system_drops_the_bit(self):
        root = self.work / "labo"
        root.mkdir()
        git(root, "init", "--quiet", "--initial-branch", "main")
        git(root, "config", "core.fileMode", "false")
        os.chdir(root)
        code, out = self.cli("init", "single")
        self.assertEqual(code, 0, out)
        self.assertTrue(git(root, "ls-files", "--stage", ".delivery/deliveryctl").startswith("100755 "))
        self.assertNotIn("update-index", out)

    def test_the_visibility_comes_from_the_machine_then_from_the_option(self):
        self.machine(visibility="public")
        code, out = self.cli("init", "spec", "un")
        self.assertEqual(code, 0, out)
        self.assertEqual((self.forge_dir / "visibility").read_text(), "PUBLIC")
        code, out = self.cli("init", "spec", "deux", "--private")
        self.assertEqual(code, 0, out)
        self.assertEqual((self.forge_dir / "visibility").read_text(), "PRIVATE")
        self.machine(visibility="private")
        code, out = self.cli("init", "spec", "trois", "--public")
        self.assertEqual((self.forge_dir / "visibility").read_text(), "PUBLIC")

    def test_a_public_repository_gets_the_noreply_address_and_a_private_one_does_not(self):
        code, out = self.cli("init", "single", "ouvert", "--public")
        self.assertEqual(code, 0, out)
        self.assertEqual(git(self.work / "ouvert", "config", "--local", "user.email"),
                         "4242+test-owner@users.noreply.github.com")
        self.assertIn("Adresse git : 4242+test-owner@users.noreply.github.com", out)
        self.assertNotIn("warn: public repository", out)
        code, out = self.cli("init", "single", "ferme", "--private")
        self.assertEqual(git(self.work / "ferme", "config", "--local", "user.email", check=False), "")
        self.assertIn("Adresse git : inchangée", out)

    def test_the_current_folder_is_the_project_when_it_is_no_repository(self):
        folder = self.work / "todo-spec"
        folder.mkdir()
        write(folder / "notes.txt", "mine\n")
        os.chdir(folder)
        code, out = self.cli("init", "spec")
        self.assertEqual(code, 0, out)
        self.assertEqual((self.forge_dir / "created").read_text(), "test-owner/todo-spec")
        self.assertEqual(git(folder, "ls-files", "notes.txt", check=False), "")      # not init's, not committed
        self.assertTrue((folder / "notes.txt").exists())
        self.assertEqual(git(folder, "rev-parse", "HEAD"), self.remote_head("test-owner/todo-spec"))

    def test_a_repository_without_origin_is_created_on_the_forge_and_keeps_its_history(self):
        folder = self.work / "vieux"
        folder.mkdir()
        git(folder, "init", "--quiet", "-b", "trunk")
        write(folder / "a.txt", "a\n")
        git(folder, "add", "-A")
        git(folder, "commit", "--quiet", "-m", "first")
        os.chdir(folder)
        code, out = self.cli("init", "single")
        self.assertEqual(code, 0, out)
        self.assertEqual((self.forge_dir / "created").read_text(), "test-owner/vieux")
        self.assertEqual(git(folder, "rev-list", "--count", "HEAD"), "2")
        self.assertEqual(git(folder, "branch", "--show-current"), "trunk")
        self.assertEqual(git(self.forge_dir / "remotes" / "test-owner" / "vieux.git", "rev-parse", "trunk"),
                         git(folder, "rev-parse", "HEAD"))

    def test_an_existing_origin_is_not_created_again(self):
        os.chdir(self.repo)
        code, out = self.cli("init", "single")
        self.assertEqual(code, 0, out)
        self.assertFalse((self.forge_dir / "created").exists())
        self.assertFalse([c for c in self.calls() if c.startswith("repo create")])
        self.assertIn("Dépôt : origin test-owner/todo", out)

    def test_a_name_whose_folder_is_not_empty_is_refused_with_the_line_to_type(self):
        write(self.work / "plein" / "a.txt", "a\n")
        before = self.tree(self.work)
        code, out = self.cli("init", "impl", "todo-spec", "plein")
        self.assertEqual(code, core.EXIT_PRECONDITION)
        self.assertIn("cd plein && deliveryctl init impl todo-spec", out)
        self.assertEqual(self.tree(self.work), before)
        self.assertFalse((self.forge_dir / "created").exists())

    def test_impl_takes_the_spec_repository_then_the_name_and_reads_the_owner_where_it_creates(self):
        code, out = self.cli("init", "impl", "todo-spec", "todo-kotlin")
        self.assertEqual(code, 0, out)
        cfg = config.load(self.work / "todo-kotlin")
        self.assertEqual(cfg.spec_source, "https://github.com/test-owner/todo-spec.git")
        self.assertEqual((self.forge_dir / "created").read_text(), "test-owner/todo-kotlin")

    def test_internal_is_refused_on_github_before_anything_is_written(self):
        code, out = self.cli("init", "single", "labo", "--internal")
        self.assertEqual(code, core.EXIT_ERROR)
        self.assertIn("internal exists on GitLab only", out)
        self.assertFalse((self.work / "labo").exists())
        self.assertFalse((self.forge_dir / "created").exists())
        self.machine(visibility="internal")
        code, out = self.cli("init", "single", "labo")
        self.assertEqual(code, core.EXIT_ERROR)
        self.assertFalse((self.work / "labo").exists())

    def test_a_name_that_is_no_repository_name_is_refused(self):
        code, out = self.cli("init", "single", "mon projet")
        self.assertEqual(code, core.EXIT_ERROR)
        self.assertIn("cannot name a repository 'mon projet'", out)


class ExistingGithubTest(ForgeInitCase):
    def test_the_noreply_address_is_set_for_a_public_repository_only(self):
        (self.forge_dir / "visibility").write_text("PUBLIC")
        code, out = self.cli("init", "single")
        self.assertEqual(code, 0, out)
        self.assertEqual(git(self.repo, "config", "--local", "user.email"), "4242+test-owner@users.noreply.github.com")
        self.assertIn("Dépôt : origin test-owner/todo (public)", out)
        self.assertNotIn("warn: public repository", out)

    def test_a_private_repository_keeps_the_configured_address(self):
        git(self.repo, "config", "user.email", "me@example.test")
        code, out = self.cli("init", "single")
        self.assertEqual(git(self.repo, "config", "--local", "user.email"), "me@example.test")
        self.assertIn("Adresse git : inchangée", out)

    def test_an_address_that_is_already_a_noreply_one_stays(self):
        (self.forge_dir / "visibility").write_text("PUBLIC")
        git(self.repo, "config", "user.email", "7+me@users.noreply.github.com")
        code, out = self.cli("init", "single")
        self.assertEqual(git(self.repo, "config", "--local", "user.email"), "7+me@users.noreply.github.com")

    def test_one_commit_with_the_paths_of_init_only(self):
        write(self.repo / "src" / "app.txt", "v2, not committed\n")
        write(self.repo / "staged.txt", "staged by the owner\n")
        git(self.repo, "add", "staged.txt")
        write(self.repo / "loose.txt", "untracked\n")
        head = git(self.repo, "rev-parse", "HEAD")
        code, out = self.cli("init", "single")
        self.assertEqual(code, 0, out)
        self.assertEqual(git(self.repo, "rev-list", "--count", f"{head}..HEAD"), "1")
        names = git(self.repo, "show", "--name-only", "--format=", "HEAD").splitlines()
        self.assertTrue({"delivery.toml", ".delivery/VERSION", ".github/workflows/delivery.yml"} <= set(names))
        self.assertFalse({"src/app.txt", "staged.txt", "loose.txt"} & set(names))
        status = sh(["git", "status", "--porcelain"], self.repo).stdout.splitlines()
        self.assertEqual(sorted(status), [" M src/app.txt", "?? loose.txt", "A  staged.txt"])
        self.assertEqual(git(self.origin, "rev-parse", "main"), git(self.repo, "rev-parse", "HEAD"))

    def test_init_commits_on_the_default_branch_only(self):
        git(self.repo, "switch", "--quiet", "-c", "feature")
        before = self.tree(self.repo)
        code, out = self.cli("init", "single")
        self.assertEqual(code, core.EXIT_PRECONDITION)
        self.assertIn("git switch main", out)
        self.assertEqual(self.tree(self.repo), before)


class ProtectionOnGithubTest(ForgeInitCase):
    def test_a_spec_repository_requires_the_pull_request_and_the_ci(self):
        code, out = self.cli("init", "spec")
        self.assertEqual(code, 0, out)
        rule = self.seen("protection.json")
        self.assertEqual(rule["required_status_checks"], {"strict": True, "contexts": ["checks"]})
        self.assertEqual(rule["required_pull_request_reviews"], {"required_approving_review_count": 0})
        self.assertIs(rule["enforce_admins"], True)
        self.assertIsNone(rule["restrictions"])
        self.assertEqual((rule["allow_force_pushes"], rule["allow_deletions"]), (False, False))
        self.assertEqual(self.seen("repo_settings.json"),
                         {"allow_merge_commit": True, "allow_squash_merge": False, "allow_rebase_merge": False})
        self.assertIn("api -X PUT repos/test-owner/todo/branches/main/protection --input -", self.calls())
        self.assertIn("Protection de main : demande de fusion obligatoire, commits de fusion seuls, CI exigée", out)

    def test_single_and_impl_do_not_require_the_ci_yet(self):
        for layout, extra in (("single", []), ("impl", ["todo-spec"])):
            with self.subTest(layout=layout):
                (self.forge_dir / "protection.json").unlink(missing_ok=True)
                (self.repo / "delivery.toml").unlink(missing_ok=True)
                code, out = self.cli("init", layout, *extra)
                self.assertEqual(code, 0, out)
                self.assertIsNone(self.seen("protection.json")["required_status_checks"])
                self.assertIn("CI exigée après la première fusion", out)

    def test_a_forge_that_refuses_gives_a_note_and_init_succeeds(self):
        (self.forge_dir / "protection_403").write_text("")
        code, out = self.cli("init", "spec")
        self.assertEqual(code, 0, out)
        self.assertIn("note: branch protection of main refused by the forge (HTTP 403", out)
        self.assertIn("set it in the repository settings", out)
        self.assertEqual(git(self.origin, "rev-parse", "main"), git(self.repo, "rev-parse", "HEAD"))
        self.assertTrue(self.seen("repo_settings.json")["allow_merge_commit"])

    def test_nothing_is_protected_when_there_is_nothing_to_change(self):
        self.cli("init", "single")
        (self.forge_dir / "protection.json").unlink()
        code, out = self.cli("init", "single")
        self.assertIn("Rien à changer", out)
        self.assertFalse((self.forge_dir / "protection.json").exists())

    def test_require_checks_adds_the_ci_once_and_keeps_the_owners_settings(self):
        self.cli("init", "single")
        cfg = config.load(self.repo)
        rule = self.seen("protection.json")
        rule["required_pull_request_reviews"]["required_approving_review_count"] = 1
        (self.forge_dir / "protection.json").write_text(json.dumps(rule))
        forge = Forge(cfg, Git(self.repo))
        self.assertIn("the CI is now required on main", forge.require_checks())
        after = self.seen("protection.json")
        self.assertEqual(after["required_status_checks"], {"strict": True, "contexts": ["checks"]})
        self.assertEqual(after["required_pull_request_reviews"], {"required_approving_review_count": 1})
        self.assertIs(after["enforce_admins"], True)
        puts = len([c for c in self.calls() if "-X PUT" in c])
        self.assertEqual(forge.require_checks(), "")
        self.assertEqual(len([c for c in self.calls() if "-X PUT" in c]), puts)

    def test_require_checks_is_silent_without_protection_or_when_the_forge_refuses(self):
        self.cli("init", "single")
        forge = Forge(config.load(self.repo), Git(self.repo))
        (self.forge_dir / "protection.json").unlink()
        self.assertEqual(forge.require_checks(), "")
        self.cli("init", "single", "--dry-run")
        self.assertFalse((self.forge_dir / "protection.json").exists())


class AskingTest(ForgeInitCase):
    def test_without_a_terminal_and_without_yes_nothing_is_written(self):
        os.chdir(self.work)
        before = self.tree(self.work)
        code, out = self.cli("init", "single", "labo", ask=True)
        self.assertEqual(code, core.EXIT_PRECONDITION)
        self.assertIn("relancez avec --yes", out)
        self.assertEqual(self.tree(self.work), before)
        self.assertFalse((self.work / "labo").exists())
        self.assertEqual(self.changing(), [])

    def test_only_o_oui_y_yes_go_on(self):
        os.chdir(self.work)
        with mock.patch.object(init.sys, "stdin", Tty()):
            for answer in ("", "n", "non", "peut-être"):
                with mock.patch("builtins.input", return_value=answer):
                    code, out = self.cli("init", "single", "labo", ask=True)
                self.assertEqual(code, 0, out)
                self.assertIn("Rien n'a été écrit.", out)
                self.assertFalse((self.work / "labo").exists(), answer)
            with mock.patch("builtins.input", return_value=" Oui ") as asked:
                code, out = self.cli("init", "single", "labo", ask=True)
            asked.assert_called_once_with("Continuer ? [o/N] ")
        self.assertEqual(code, 0, out)
        self.assertTrue((self.work / "labo" / "delivery.toml").exists())

    def test_the_summary_is_at_most_eight_lines_with_the_question(self):
        os.chdir(self.work)
        code, out = self.cli("init", "spec", "labo", "--dry-run")
        head = out.split("  created")[0].strip().splitlines()[1:]        # after the title line
        self.assertLessEqual(len(head) + 1, 8, out)
        self.assertEqual(head[0], f"Dossier : {self.work / 'labo'}")

    def test_dry_run_writes_nothing_and_changes_nothing_on_the_forge(self):
        os.chdir(self.work)
        before = self.tree(self.work)
        code, out = self.cli("init", "spec", "labo", "--public", "--dry-run")
        self.assertEqual(code, 0, out)
        self.assertIn("dry run, nothing written", out)
        self.assertIn("Dépôt : créer test-owner/labo sur GitHub, public", out)
        self.assertIn("Adresse git : 4242+test-owner@users.noreply.github.com", out)
        self.assertIn("created  delivery.toml", out)
        self.assertNotIn("Continuer", out)
        self.assertEqual(self.tree(self.work), before)
        self.assertFalse((self.work / "labo").exists())
        self.assertEqual(self.changing(), [])
        self.assertTrue(self.calls())                                       # it did read: who the owner is


class UpgradeTest(ForgeInitCase):
    def old_equipment(self):
        """A project equipped by an older version, committed and pushed."""
        self.cli("init", "single")
        write(self.repo / ".delivery" / "engine" / "deliveryctl" / "stale.py", "# from an older version\n")
        write(self.repo / ".delivery" / "VERSION", "0.0.1\n")
        self.commit_all("an older equipment")
        git(self.repo, "push", "--quiet", "origin", "main")

    def test_upgrade_commits_its_refresh_and_pushes_it(self):
        self.old_equipment()
        write(self.repo / "src" / "app.txt", "owner's change\n")
        head = git(self.repo, "rev-parse", "HEAD")
        code, out = self.cli("init", "--upgrade")
        self.assertEqual(code, 0, out)
        self.assertEqual(git(self.repo, "rev-list", "--count", f"{head}..HEAD"), "1")
        message = git(self.repo, "log", "-1", "--format=%B")
        self.assertEqual(message.splitlines()[0], f"Met à jour delivery-method vers {VERSION}")
        self.assertIn(f"Delivery-Method: {VERSION}", message)
        names = git(self.repo, "show", "--name-status", "--format=", "HEAD").splitlines()
        self.assertIn("D\t.delivery/engine/deliveryctl/stale.py", names)
        self.assertNotIn("M\tsrc/app.txt", names)
        self.assertEqual(sh(["git", "status", "--porcelain"], self.repo).stdout, " M src/app.txt\n")
        self.assertEqual(git(self.origin, "rev-parse", "main"), git(self.repo, "rev-parse", "HEAD"))
        self.assertIn(f"Mise à jour : delivery-method 0.0.1 → {VERSION}", out)

    def test_a_refused_push_leaves_the_commit_local_and_says_so(self):
        self.old_equipment()
        hook = self.origin / "hooks" / "pre-receive"
        write(hook, "#!/bin/sh\necho 'protected branch' >&2\nexit 1\n").chmod(0o755)
        before = len(self.calls())
        code, out = self.cli("init", "--upgrade")
        self.assertEqual(code, core.EXIT_TOOL, out)
        self.assertIn("note: push refused", out)
        self.assertIn("git push -u origin main", out)
        self.assertIn("commités sur main, push à refaire", out)
        self.assertEqual(git(self.repo, "log", "-1", "--format=%s"), f"Met à jour delivery-method vers {VERSION}")
        self.assertEqual([c for c in self.calls()[before:] if "protection" in c], [])


    def refuse_main(self):
        hook = self.origin / "hooks" / "pre-receive"
        write(hook, "#!/bin/sh\nwhile read old new ref; do\n  [ \"$ref\" = refs/heads/main ] && "
                    "{ echo 'protected branch' >&2; exit 1; }\ndone\nexit 0\n").chmod(0o755)

    def test_a_protected_default_branch_gets_the_refresh_through_a_merge_request(self):
        self.old_equipment()
        write(self.repo / "src" / "app.txt", "owner's change\n")
        remote = git(self.repo, "rev-parse", "origin/main")
        self.refuse_main()
        code, out = self.cli("init", "--upgrade")
        self.assertEqual(code, 0, out)
        branch = f"delivery-method/upgrade-{VERSION}"
        self.assertIn("merge request https://forge.test/pr/1", out)
        self.assertIn("main is protected", out)
        self.assertNotIn("push refused", out)
        self.assertEqual(git(self.repo, "branch", "--show-current"), "main")
        self.assertEqual(git(self.repo, "rev-parse", "main"), remote)
        self.assertEqual(git(self.origin, "rev-parse", "main"), remote)
        self.assertEqual(git(self.repo, "rev-parse", f"{branch}~1"), remote)
        self.assertEqual(git(self.repo, "log", "-1", "--format=%s", branch), f"Met à jour delivery-method vers {VERSION}")
        self.assertEqual(git(self.origin, "rev-parse", branch), git(self.repo, "rev-parse", branch))
        self.assertEqual(sh(["git", "status", "--porcelain"], self.repo).stdout, " M src/app.txt\n")
        request = json.loads((self.forge_dir / "requests.json").read_text())[branch]
        self.assertEqual((request["base"], request["title"]), ("main", f"Met à jour delivery-method vers {VERSION}"))
        self.assertIn("commités sur une branche", out)

    def test_the_branch_of_a_refused_refresh_is_kept_local_when_even_it_is_refused(self):
        self.old_equipment()
        write(self.origin / "hooks" / "pre-receive", "#!/bin/sh\nexit 1\n").chmod(0o755)
        code, out = self.cli("init", "--upgrade")
        self.assertEqual(code, core.EXIT_TOOL, out)
        self.assertEqual(git(self.repo, "branch", "--show-current"), "main")
        self.assertEqual(git(self.repo, "log", "-1", "--format=%s", "main"), f"Met à jour delivery-method vers {VERSION}")


class DiagnosisTest(ForgeInitCase):
    def test_doctor_prints_nothing_when_all_is_ok_and_its_notes_and_warns_otherwise(self):
        from deliveryctl import doctor
        with mock.patch.object(doctor, "collect", return_value=iter([("ok", "a"), ("ok", "b")])):
            self.assertEqual(init.diagnosis(self.repo), [])
        with mock.patch.object(doctor, "collect", return_value=iter([("ok", "a"), ("note", "n"), ("warn", "w")])):
            self.assertEqual(init.diagnosis(self.repo), ["note: n", "warn: w"])

    def test_the_diagnosis_comes_before_the_next_steps_and_reads_the_new_repository(self):
        os.chdir(self.work)
        code, out = self.cli("init", "single", "labo", "--public")
        before, after = out.split("\nProchaines étapes :\n")
        self.assertNotIn("not committed", before)
        self.assertNotIn("warn: public repository", before)
        self.assertEqual(after.splitlines()[0], "  " + after.splitlines()[0].strip())


class GitlabInitTest(ForgeInitCase):
    def setUp(self):
        super().setUp()
        os.chdir(self.work)

    def test_creation_in_the_configured_group_and_host(self):
        self.machine(forge="gitlab", gitlab_host="https://gitlab.example.org/", gitlab_group="acme/equipe",
                     visibility="internal")
        code, out = self.cli("init", "spec", "labo")
        self.assertEqual(code, 0, out)
        self.assertEqual(self.seen("created.json"),
                         {"path": "acme/equipe/labo", "visibility": "internal", "host": "gitlab.example.org"})
        creation = [c for c in self.calls("glab_calls") if "repo create" in c or c.endswith("git_protocol")]
        self.assertEqual(len(creation), 2)
        self.assertTrue(all(c.startswith("[gitlab.example.org] ") for c in creation), creation)
        root = self.work / "labo"
        self.assertEqual(self.origin_of(root), "git@gitlab.test:acme/equipe/labo.git")
        self.assertEqual(config.load(root).forge, "gitlab")
        self.assertEqual(config.load(root).implementer, "local")
        self.assertEqual(git(root, "rev-parse", "HEAD"), self.remote_head("acme/equipe/labo"))
        self.assertIn("Dépôt : créer acme/equipe/labo sur GitLab gitlab.example.org, interne", out)

    def test_the_default_group_is_the_users_namespace_and_the_https_address_when_glab_says_https(self):
        (self.forge_dir / "git_protocol").write_text("https")
        map_remotes(self.forge_dir, "https://gitlab.test/")
        code, out = self.cli("init", "single", "labo", "--forge", "gitlab", "--public")
        self.assertEqual(code, 0, out)
        self.assertEqual(self.seen("created.json")["path"], "glab-user/labo")
        self.assertEqual(self.seen("created.json")["visibility"], "public")
        self.assertEqual(self.origin_of(self.work / "labo"), "https://gitlab.test/glab-user/labo.git")
        self.assertEqual(git(self.work / "labo", "config", "--local", "user.email", check=False), "")  # GitHub only

    def test_impl_reads_the_owner_in_the_group_it_creates_in(self):
        self.machine(forge="gitlab", gitlab_group="acme", gitlab_host="gitlab.test")
        code, out = self.cli("init", "impl", "todo-spec", "todo-kotlin")
        self.assertEqual(code, 0, out)
        self.assertEqual(config.load(self.work / "todo-kotlin").spec_source, "git@gitlab.test:acme/todo-spec.git")

    def test_spec_repository_protects_main_and_requires_the_pipeline_at_once(self):
        code, out = self.cli("init", "spec", "labo", "--forge", "gitlab")
        self.assertEqual(code, 0, out)
        self.assertEqual(self.seen("protected.json"), GITLAB_RULE_NO_PUSH)
        self.assertEqual(self.seen("project.json"), {"only_allow_merge_if_pipeline_succeeds": True,
                                                    "merge_method": "merge"})
        self.assertIn("Protection de main : demande de fusion obligatoire, commits de fusion seuls, CI exigée", out)

    def test_single_requires_the_pipeline_after_the_first_merge_only(self):
        code, out = self.cli("init", "single", "labo", "--forge", "gitlab")
        self.assertEqual(code, 0, out)
        self.assertEqual(self.seen("protected.json"), GITLAB_RULE_NO_PUSH)
        self.assertIs(self.seen("project.json")["only_allow_merge_if_pipeline_succeeds"], False)
        self.assertEqual(self.seen("project.json")["merge_method"], "merge")
        root = self.work / "labo"
        forge = Forge(config.load(root), Git(root))
        self.assertIn("the CI is now required on main", forge.require_checks())
        self.assertIs(self.seen("project.json")["only_allow_merge_if_pipeline_succeeds"], True)
        puts = len([c for c in self.calls("glab_calls") if "-X PUT" in c])
        self.assertEqual(forge.require_checks(), "")
        self.assertEqual(len([c for c in self.calls("glab_calls") if "-X PUT" in c]), puts)

    def test_a_branch_gitlab_already_protects_with_other_levels_is_unprotected_then_protected(self):
        write(self.forge_dir / "protected.json", json.dumps(
            {"main": {"name": "main", "allow_force_push": False, "push_access_levels": [{"access_level": 40}],
                      "merge_access_levels": [{"access_level": 40}]}}))
        code, out = self.cli("init", "single", "labo", "--forge", "gitlab")
        self.assertEqual(code, 0, out)
        calls = self.calls("glab_calls")
        delete = next(i for i, c in enumerate(calls) if "-X DELETE" in c and "protected_branches/main" in c)
        post = next(i for i, c in enumerate(calls) if "-X POST" in c and c.endswith("allow_force_push=false"))
        self.assertLess(delete, post)
        self.assertEqual(self.seen("protected.json"), GITLAB_RULE_NO_PUSH)

    def test_a_forge_that_refuses_gives_notes_and_init_succeeds(self):
        (self.forge_dir / "protect_403").write_text("")
        code, out = self.cli("init", "spec", "labo", "--forge", "gitlab")
        self.assertEqual(code, 0, out)
        self.assertIn("note: protected branch main refused by the forge (403 Forbidden)", out)
        self.assertIn("note: project merge settings refused by the forge", out)
        self.assertEqual(git(self.work / "labo", "rev-parse", "HEAD"), self.remote_head("glab-user/labo"))

    def test_the_project_path_is_url_encoded(self):
        self.machine(forge="gitlab", gitlab_group="acme/equipe")
        self.cli("init", "spec", "labo")
        self.assertTrue([c for c in self.calls("glab_calls") if "projects/acme%2Fequipe%2Flabo/protected_branches" in c])


GITLAB_RULE_NO_PUSH = {"main": {"name": "main", "allow_force_push": False,
                                "push_access_levels": [{"access_level": 0}],
                                "merge_access_levels": [{"access_level": 40}]}}


class GitlabIncludeTest(ForgeInitCase):
    INCLUDE = ".gitlab/delivery-ci.yml"

    def step(self, text, name=".gitlab-ci.yml"):
        write(self.repo / name, text)
        notes = []
        step = init.gitlab_include_step(self.repo, notes)
        if step.write:
            step.write()
        return step, notes, (self.repo / name).read_text()

    def test_no_file_creates_it(self):
        step, notes, text = init.gitlab_include_step(self.repo, []), [], None
        self.assertEqual(step.status, "created")
        step.write()
        self.assertEqual((self.repo / ".gitlab-ci.yml").read_text(), f"include:\n  - local: {self.INCLUDE}\n")

    def test_a_block_list_gets_the_item_after_the_last_one(self):
        before = ("stages: [test]\n\ninclude:\n  - template: Security/SAST.gitlab-ci.yml\n"
                  "  - project: group/shared\n    file: ci.yml\n    ref: main\n\n# jobs\nbuild:\n  script: make\n")
        step, notes, text = self.step(before)
        self.assertEqual((step.status, notes), ("merged", []))
        self.assertEqual(text, before.replace("    ref: main\n", f"    ref: main\n  - local: {self.INCLUDE}\n"))

    def test_a_list_at_the_margin_keeps_its_indentation(self):
        step, notes, text = self.step(f"include:\n- local: other.yml\nbuild:\n  script: make\n")
        self.assertEqual(text, f"include:\n- local: other.yml\n- local: {self.INCLUDE}\nbuild:\n  script: make\n")

    def test_a_file_without_include_gets_the_block_appended(self):
        step, notes, text = self.step("build:\n  script: make")
        self.assertEqual((step.status, notes), ("merged", []))
        self.assertEqual(text, f"build:\n  script: make\n\ninclude:\n  - local: {self.INCLUDE}\n")

    def test_an_include_already_there_is_kept(self):
        step, notes, text = self.step(f"include:\n  - local: {self.INCLUDE}\n")
        self.assertEqual(step.status, "kept")

    def test_other_shapes_are_left_alone_and_noted(self):
        shapes = ['include: "other.yml"\nbuild:\n  script: make\n',
                  "include: [{ local: other.yml }]\n",
                  "include:\n  local: other.yml\n",
                  ".base: &base\n  script: make\ninclude:\n  - *base\n",
                  "include: &inc\n  - local: other.yml\n"]
        for shape in shapes:
            with self.subTest(shape=shape):
                step, notes, text = self.step(shape)
                self.assertEqual((step.status, text), ("kept", shape))
                self.assertEqual(len(notes), 1)
                self.assertIn("include:\n        - local: .gitlab/delivery-ci.yml", notes[0])

    def test_init_commits_the_edited_file_and_prints_the_note_for_the_fourth_shape(self):
        write(self.repo / ".gitlab-ci.yml", 'include: "other.yml"\n')
        self.commit_all("ci")
        code, out = self.cli("init", "single", "--forge", "gitlab")
        self.assertEqual(code, 0, out)
        self.assertIn("note: .gitlab-ci.yml is left as it is", out)
        self.assertEqual((self.repo / ".gitlab-ci.yml").read_text(), 'include: "other.yml"\n')
        names = git(self.repo, "show", "--name-only", "--format=", "HEAD").splitlines()
        self.assertIn(".gitlab/delivery-ci.yml", names)
        self.assertNotIn(".gitlab-ci.yml", names)
