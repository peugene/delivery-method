"""The campaign branch (CONTRACTS.md §12.3): open puts the main checkout on campaign/<name>, push
opens or updates its pull request, run starts the lead on it."""

import io
import json
import os
import unittest
from contextlib import redirect_stdout
from unittest import mock

from support import RepoCase, git, write

from test_impl_templates import card_text, fill

from deliveryctl import campaign, config, core
from deliveryctl import frontmatter as fm
from deliveryctl import run as run_mod

CARD = "---\nid: s001\nkind: story\ntitle: Sign in\nstatus: {status}\n---\n## Objective\nSign in.\n"


class CampaignBranchTest(RepoCase):
    def setUp(self):
        super().setUp()
        write(self.repo / "delivery.toml", 'repo_role = "impl"\nforge = "github"\n[commands]\ncheck = "true"\n')
        write(self.repo / "backlog/s001-sign-in.md", CARD.format(status="draft"))
        write(self.repo / ".gitignore", "docs/campaigns/work/\n")
        self.commit_all("setup")
        git(self.repo, "push", "--quiet", "origin", "main")
        self.cfg = config.load(self.repo)

    def open(self, name="c1"):
        out = io.StringIO()
        with redirect_stdout(out):
            campaign.open_campaign(self.cfg, name, "impl")
        return out.getvalue()

    def requests(self):
        return json.loads((self.forge_dir / "requests.json").read_text())

    def calls(self):
        path = self.forge_dir / "calls"
        return path.read_text().splitlines() if path.exists() else []

    def push(self, name=None):
        out = io.StringIO()
        with redirect_stdout(out):
            self.assertEqual(campaign.push(self.cfg, name), 0)
        return out.getvalue().strip().splitlines()[-1]

    def work(self, message="Frame", *trailer):
        write(self.repo / "backlog/s001-sign-in.md", CARD.format(status="ready"))
        git(self.repo, "add", "-A")
        git(self.repo, "commit", "--quiet", "-m", message, *[a for t in trailer for a in ("--trailer", t)])

    def test_open_creates_the_branch_from_the_target_head(self):
        out = self.open()
        self.assertIn("on campaign/c1 (created from origin/main)", out)
        self.assertEqual(git(self.repo, "rev-parse", "--abbrev-ref", "HEAD"), "campaign/c1")
        self.assertEqual(git(self.repo, "rev-parse", "HEAD"), git(self.repo, "rev-parse", "origin/main"))
        self.assertTrue((self.repo / "docs/campaigns/c1.md").exists())

    def test_open_again_stays_and_switching_back_from_the_default_branch_reuses_the_branch(self):
        self.open()
        self.assertIn("on campaign/c1", self.open())
        self.work()
        git(self.repo, "switch", "--quiet", "main")
        out = self.open()
        self.assertIn("(existing)", out)
        self.assertEqual(git(self.repo, "rev-parse", "--abbrev-ref", "HEAD"), "campaign/c1")
        self.assertIn("ready", (self.repo / "backlog/s001-sign-in.md").read_text())

    def test_open_starts_again_from_the_target_head_after_a_merged_pull_request(self):
        self.open()
        self.work("Frame", "Go: cards")
        self.push()
        sh_merge = self.forge_dir / "bin" / "gh"
        os.system(f"cd {self.repo} && {sh_merge} pr merge campaign/c1 --subject Merge --body x >/dev/null")
        self.assertEqual(self.requests()["campaign/c1"]["state"], "MERGED")
        git(self.repo, "switch", "--quiet", "main")
        git(self.repo, "pull", "--quiet", "--ff-only")
        out = self.open()
        self.assertIn("started again", out)
        self.assertEqual(git(self.repo, "rev-parse", "HEAD"), git(self.repo, "rev-parse", "origin/main"))
        git(self.repo, "commit", "--quiet", "--allow-empty", "-m", "Second frame")
        self.assertEqual(self.push(), "https://forge.test/pr/2")
        self.assertEqual(self.requests()["campaign/c1"]["state"], "OPEN")

    def test_open_refuses_another_branch_and_names_the_line_to_type(self):
        git(self.repo, "switch", "--quiet", "-c", "work")
        with self.assertRaises(core.DeliveryError) as ctx:
            self.open()
        self.assertIn("git switch main", ctx.exception.message)
        self.assertEqual(git(self.repo, "rev-parse", "--abbrev-ref", "HEAD"), "work")
        self.assertFalse((self.repo / "docs/campaigns/c1.md").exists())

    def test_open_refuses_a_dirty_tree_it_would_lose_work_from(self):
        self.open()
        self.work()
        git(self.repo, "switch", "--quiet", "main")
        write(self.repo / "README.md", "# changed\n")
        with self.assertRaises(core.DeliveryError) as ctx:
            self.open()
        self.assertIn("uncommitted", ctx.exception.message)
        self.assertEqual(git(self.repo, "rev-parse", "--abbrev-ref", "HEAD"), "main")

    def test_push_opens_one_pull_request_then_updates_it(self):
        self.open()
        write(self.repo / "docs/campaigns/c1.md", "---\ncampaign: c1\n---\n## Objective\nShip sign-in.\n## Next\nx\n")
        self.work("Frame c1", "Go: cards")
        self.assertEqual(self.push(), "https://forge.test/pr/1")
        request = self.requests()["campaign/c1"]
        self.assertEqual((request["title"], request["base"]), ("Campagne c1", "main"))
        for text in ("Ship sign-in.", "s001 : Sign in — `ready`", "- cards"):
            self.assertIn(text, request["body"])
        self.assertEqual(git(self.origin, "rev-parse", "campaign/c1"), git(self.repo, "rev-parse", "HEAD"))

        git(self.repo, "commit", "--quiet", "--allow-empty", "-m", "Run c1", "--trailer", "Go: run")
        self.assertEqual(self.push("c1"), "https://forge.test/pr/1")
        self.assertEqual(len(self.requests()), 1)
        self.assertIn("- cards\n- run", self.requests()["campaign/c1"]["body"])
        self.assertEqual(len([c for c in self.calls() if c.startswith("pr create")]), 1)

    def test_push_refuses_the_default_branch_and_another_branch(self):
        with self.assertRaises(core.DeliveryError) as ctx:
            campaign.push(self.cfg)
        self.assertIn("default branch", ctx.exception.message)
        git(self.repo, "switch", "--quiet", "-c", "work")
        with self.assertRaises(core.DeliveryError) as ctx:
            campaign.push(self.cfg)
        self.assertIn("not a campaign branch", ctx.exception.message)
        git(self.repo, "switch", "--quiet", "main")
        self.open()
        with self.assertRaises(core.DeliveryError) as ctx:
            campaign.push(self.cfg, "other")
        self.assertIn("campaign/other", ctx.exception.message)
        with self.assertRaises(core.DeliveryError) as ctx:
            campaign.push(self.cfg)                       # no commit beyond main yet
        self.assertIn("nothing to propose", ctx.exception.message)
        self.assertFalse([c for c in self.calls() if c.startswith("pr create")])

    def test_run_puts_the_checkout_on_the_campaign_branch(self):
        write(self.repo / "backlog/s001-sign-in.md",
              fm.set_key(fill(card_text("story").replace("s004", "s001")), "status", "ready"))
        self.commit_all("ready")
        git(self.repo, "push", "--quiet", "origin", "main")
        started = []
        with mock.patch.object(run_mod.shutil, "which", return_value="/bin/claude"), \
                mock.patch.object(run_mod.os, "execvpe", lambda *a: started.append(a)), \
                mock.patch.object(run_mod.os, "chdir"), redirect_stdout(io.StringIO()):
            run_mod.start(self.cfg, campaign="c2")
        self.assertEqual(len(started), 1)
        self.assertEqual(git(self.repo, "rev-parse", "--abbrev-ref", "HEAD"), "campaign/c2")


if __name__ == "__main__":
    unittest.main()
