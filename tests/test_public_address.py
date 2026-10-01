"""`doctor` and the address a public GitHub repository publishes. The forge is the fake `gh`."""

import io
from contextlib import redirect_stdout

from support import RepoCase, fake_forge, git, write

from deliveryctl import doctor


class PublicAddressTest(RepoCase):
    def setUp(self):
        super().setUp()
        self.forge = fake_forge(self.tmp)
        write(self.repo / "delivery.toml", 'repo_role = "impl"\nforge = "github"\nintegration = "ai"\n')
        git(self.repo, "remote", "set-url", "origin", "git@github.com:acme/todo.git")

    def doctor(self, visibility="PUBLIC", email="owner@example.test", checks="green"):
        write(self.forge / "visibility", visibility)
        write(self.forge / "checks", checks)
        git(self.repo, "config", "user.email", email)
        out = io.StringIO()
        with redirect_stdout(out):
            doctor.main([])
        return out.getvalue()

    def test_public_repository_with_a_personal_address_warns(self):
        out = self.doctor()
        self.assertIn("warn: public repository: the git address (owner@example.test) is published", out)
        self.assertIn("Approved-By", out)
        self.assertIn("git config user.email <id>+<login>@users.noreply.github.com", out)
        self.assertIn("Keep my email addresses private", out)

    def test_public_repository_with_a_noreply_address_is_ok(self):
        out = self.doctor(email="42+owner@users.noreply.github.com")
        self.assertIn("ok: public repository, git address 42+owner@users.noreply.github.com", out)
        self.assertNotIn("warn: public repository", out)

    def test_private_repository_says_nothing(self):
        out = self.doctor(visibility="PRIVATE")
        self.assertNotIn("public repository", out)

    def test_forge_failure_says_nothing_and_doctor_goes_on(self):
        out = self.doctor(checks="down")
        self.assertNotIn("public repository", out)
        self.assertIn("CLAUDE.md", out)

    def test_other_host_does_not_ask_the_forge(self):
        git(self.repo, "remote", "set-url", "origin", "https://gitlab.com/acme/todo.git")
        self.doctor()
        self.assertNotIn("repo view", (self.forge / "calls").read_text())
