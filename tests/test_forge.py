"""Merge requests with a fake 'gh' on PATH (no network): merge only on a green CI, never push
again a branch whose request is merged, tell 'no request' from 'forge unreachable'."""

import json
import os
from pathlib import Path
from unittest import mock

from support import RepoCase, git, write

from deliveryctl import config, core, forge
from deliveryctl.forge import Forge
from deliveryctl.gitops import Git

FAKE_GH = r'''#!/usr/bin/env python3
import json, os, sys
state = json.loads(open(os.environ["FAKE_GH_STATE"]).read())
with open(os.environ["FAKE_GH_LOG"], "a") as log:
    log.write(" ".join(sys.argv[1:]) + "\n")
args = sys.argv[1:]
if args[:2] == ["pr", "view"]:
    view = state.get("view", "none")
    if view == "none":
        sys.stderr.write('no pull requests found for branch "%s"\n' % args[2]); sys.exit(1)
    if view == "error":
        sys.stderr.write("HTTP 403: API rate limit exceeded\n"); sys.exit(1)
    print(json.dumps({"url": "https://forge.test/pr/7", "state": view,
                      "statusCheckRollup": state.get("rollup", [])}))
elif args[:2] == ["pr", "create"]:
    print("https://forge.test/pr/8")
elif args[:2] == ["pr", "merge"]:
    pass
else:
    sys.exit(2)
'''


class ForgeCase(RepoCase):
    def setUp(self):
        super().setUp()
        bin_dir = self.tmp / "bin"
        write(bin_dir / "gh", FAKE_GH).chmod(0o755)
        self.state_file = self.tmp / "gh-state.json"
        self.log = self.tmp / "gh.log"
        os.environ.update(PATH=f"{bin_dir}{os.pathsep}{os.environ['PATH']}",
                          FAKE_GH_STATE=str(self.state_file), FAKE_GH_LOG=str(self.log))
        self.gh(view="none")
        write(self.repo / "delivery.toml", 'repo_role = "impl"\nforge = "github"\nintegration = "ai"\n'
                                           '[commands]\ncheck = "true"\n')
        write(self.repo / ".gitignore", ".delivery/run/\n")
        self.commit_all("setup")
        git(self.repo, "push", "--quiet", "origin", "main")
        git(self.repo, "switch", "--quiet", "-c", "story/s001")
        write(self.repo / "src" / "app.txt", "v2\n")
        self.commit_all("implement s001")
        self.forge = Forge(config.load(self.repo), Git(self.repo))

    def gh(self, **state):
        self.state_file.write_text(json.dumps(state))

    def calls(self) -> list[str]:
        return self.log.read_text().splitlines() if self.log.exists() else []

    def remote_branch(self) -> str:
        return git(self.repo, "ls-remote", "origin", "refs/heads/story/s001")


class FindTest(ForgeCase):
    def test_no_request_and_unreachable_forge_differ(self):
        self.assertIsNone(self.forge.find("s001"))
        self.gh(view="error")
        with self.assertRaises(core.DeliveryError) as ctx:
            self.forge.find("s001")
        self.assertEqual(ctx.exception.code, core.EXIT_TOOL)
        self.assertIn("rate limit", ctx.exception.message)


class OpenTest(ForgeCase):
    def test_merged_request_is_neither_pushed_nor_opened_again(self):
        self.gh(view="MERGED")
        with self.assertRaises(core.DeliveryError) as ctx:
            self.forge.open("s001", "s001 : Sign in (story/s001)", "body")
        self.assertEqual(ctx.exception.code, core.EXIT_PRECONDITION)
        self.assertIn("already merged", ctx.exception.message)
        self.assertEqual(self.remote_branch(), "")
        self.assertFalse(any(c.startswith("pr create") for c in self.calls()))

    def test_open_request_is_pushed_and_reused(self):
        self.gh(view="OPEN")
        self.assertEqual(self.forge.open("s001", "s001 : Sign in (story/s001)", "body"), "https://forge.test/pr/7")
        self.assertTrue(self.remote_branch())
        self.assertFalse(any(c.startswith("pr create") for c in self.calls()))

    def test_new_request_is_pushed_then_created(self):
        self.assertEqual(self.forge.open("s001", "s001 : Sign in (story/s001)", "body"), "https://forge.test/pr/8")
        self.assertTrue(self.remote_branch())
        self.assertTrue(any(c.startswith("pr create") for c in self.calls()))


class MergeTest(ForgeCase):
    def merge(self):
        return self.forge.merge("s001", "Merge story/s001 : Sign in", [("Story", "s001")], head="abc")

    def test_request_body_names_the_story(self):
        body = forge.request_body("s001", "Sign in", "Outcome: done — x", None, None, [])
        self.assertTrue(body.startswith("# s001 : Sign in\n"), body)
        self.assertTrue(forge.request_body("s001", "", None, None, None, []).startswith("# s001\n"))

    def test_merges_only_on_a_green_ci(self):
        for rollup, code in (([], core.EXIT_PRECONDITION),
                             ([{"status": "IN_PROGRESS"}], core.EXIT_PRECONDITION),
                             ([{"status": "COMPLETED", "conclusion": "FAILURE"}], core.EXIT_RED)):
            self.gh(view="OPEN", rollup=rollup)
            with self.assertRaises(core.DeliveryError) as ctx:
                self.merge()
            self.assertEqual(ctx.exception.code, code, rollup)
        self.assertFalse(any(c.startswith("pr merge") for c in self.calls()))
        self.gh(view="OPEN", rollup=[{"status": "COMPLETED", "conclusion": "SUCCESS"}])
        self.assertEqual(self.merge(), "merged https://forge.test/pr/7")
        self.assertIn("--match-head-commit abc", [c for c in self.calls() if c.startswith("pr merge")][0])
