"""What CONTRACTS.md and README.md promise about ports, the CI templates and the committed
qualification order, checked against the engine and the templates."""

import io
import json
import os
import re
import subprocess
import tempfile
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

from support import ROOT, RepoCase, git, write
from test_qualify import QualifyCase

from deliveryctl import config, core, hooks, nightly, qualify, roles
from deliveryctl.forge import Forge
from deliveryctl.gitops import Git


class NightlyPortTest(QualifyCase):
    acceptance = "echo port={port} env=$DELIVERY_PORT; echo '3 passed'"

    def test_night_suite_gets_its_port_then_releases_it(self):
        code, out = self.quiet(nightly.run, self.cfg)
        self.assertEqual(code, core.EXIT_OK, out)
        log = (self.repo / f".delivery/run/logs/nightly-{core.today()}.log").read_text()
        found = re.search(r"port=(\d+) env=(\d+)", log)
        self.assertIsNotNone(found, log)
        self.assertEqual(found.group(1), found.group(2))
        self.assertTrue(found.group(1).startswith("31"), found.group(1))
        ports = json.loads((self.repo / ".delivery/run/ports.json").read_text())
        self.assertNotIn(f"nightly-{core.today()}", ports)


class CiTemplateTest(RepoCase):
    """The CI reads the card's spec as the engine does, and substitutes {port}."""

    def script_lines(self, name):
        text = (ROOT / "templates" / "project" / name).read_text(encoding="utf-8")
        lines = [line.strip() for line in text.splitlines()]
        sed = next(line for line in lines if "sed -n" in line)
        sed = sed.split("spec=$(", 1)[1].split(' "$card"', 1)[0]
        port = next(line for line in lines if line.startswith("export DELIVERY_PORT="))
        cmd = next(line for line in lines if line.startswith("cmd()"))
        return sed, port, cmd

    def test_quoted_spec_and_port(self):
        work = Path(tempfile.mkdtemp(dir=self.tmp))
        write(work / "a.md", 'spec: "s004"\n')
        write(work / "b.md", "spec: 's005'\n")
        write(work / "c.md", "spec: s006\n")
        write(work / "delivery.toml", '[commands]\nacceptance = "BASE={port} run {grep}"\n')
        for name in ("github-ci.yml", "gitlab-ci.yml"):
            sed, port, cmd = self.script_lines(name)
            with self.subTest(template=name):
                specs = [subprocess.run(["sh", "-c", f'{sed} "{f}"'], cwd=work, text=True,
                                        capture_output=True).stdout.strip() for f in ("a.md", "b.md", "c.md")]
                self.assertEqual(specs, ["s004", "s005", "s006"])
                env = {k: v for k, v in os.environ.items() if k != "DELIVERY_PORT"}
                out = subprocess.run(["sh", "-c", f"{port}\n{cmd}\ncmd acceptance @s004"], cwd=work,
                                     text=True, capture_output=True, env=env).stdout.strip()
                self.assertEqual(out, "BASE=3999 run @s004")


class DocsTest(RepoCase):
    def test_shell_function_stays_out_of_claude_sessions(self):
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        self.assertIn('[ -n "$CLAUDECODE" ] || deliveryctl() {', readme)
        self.assertNotIn("Les volets de suivi des fenêtres s'en servent", readme)

    def test_qualification_order_is_the_committed_one(self):
        for rel in ("README.md", "CONTRACTS.md"):
            text = (ROOT / rel).read_text(encoding="utf-8")
            with self.subTest(rel=rel):
                self.assertIn(qualify.ORDER, text)
                self.assertNotIn("qualification/work/order.md", text)
        self.assertIn(qualify.ORDER, roles.PROMPTS["qualification-runner"])
        os.environ.update(DELIVERY_ROLE="qualification-runner", DELIVERY_STORY="0.1.0")
        out = io.StringIO()
        with mock.patch("sys.stdin", io.StringIO("{}")), redirect_stdout(out):
            self.assertEqual(hooks.session_start(), 0)
        self.assertIn(qualify.ORDER, out.getvalue())

    def test_contracts_name_cards_like_the_engine(self):
        from deliveryctl import cards, notify, story
        text = (ROOT / "CONTRACTS.md").read_text(encoding="utf-8")
        example = text.split("## 5. Cartes")[1].split("```markdown\n")[1].split("```")[0]
        card = cards.parse(Path("backlog/s004-partager-une-liste.md"), example)
        self.assertEqual(card.problems, [])
        self.assertEqual(cards.label(card.id, card.title), "s004 : Partager une liste")
        heading = next(line for line in text.splitlines() if line.startswith("### Q17"))
        self.assertTrue(qualify.CONTROL_RX.match(heading), heading)
        for promised, built in (
                ("Merge story/<id> : <titre>", story.merge_subject("s004", "Partager une liste")),
                ("<id> : <titre> (story/<id>)", story.request_title("s004", "Partager une liste")),
                ("🚨 <dépôt> — <id> : <titre> — bloqué", notify.subject("s004", "Partager une liste", "bloqué"))):
            with self.subTest(promised=promised):
                self.assertIn(promised, text)
                self.assertEqual(built, promised.replace("<id>", "s004").replace("<titre>", "Partager une liste")
                                 .replace("🚨 <dépôt> — ", ""))
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        self.assertIn("`<dépôt>-<id> : <titre>`", readme)
        self.assertIn(cards.TITLE_REQUIRED, text)

    def test_no_human_question_silence_claimed(self):
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        self.assertNotIn("reste silencieuse", readme)
        self.assertIn("Outcome: question", readme)


if __name__ == "__main__":
    import unittest
    unittest.main()
