"""Templates and prompts of the implementation phase: cards (CONTRACTS.md §5), work order
skeleton (§6.1), review (§6.4), campaign (§12.3), and the rules the role prompts must keep
(targeted test, Outcome lines, run steps, no shell expansion)."""

import os
import re
import tomllib
import unittest
from pathlib import Path

from support import ROOT, RepoCase, git, write

from deliveryctl import campaign, cards, config, gate, kit, roles, story
from deliveryctl import frontmatter as fm
from deliveryctl import verdict as vd

IMPL = ROOT / "templates" / "impl"
CARD_TEMPLATES = {"story": ("card-story.md", "s004"), "task": ("card-task.md", "t004"),
                  "anomaly": ("card-anomaly.md", "a004")}
PROMPT_DIRS = ("agents", "commands", "skills", "rules")
MINE = ("agents/technical-lead.md", "agents/story-implementer.md", "agents/story-reviewer.md",
        "commands/impl-frame.md", "commands/run.md", "skills/anchoring/SKILL.md",
        "skills/testing-doctrine/SKILL.md", "skills/work-orders/SKILL.md",
        "templates/impl/", "templates/campaign/", "templates/story/")


def card_text(kind: str) -> str:
    name, card_id = CARD_TEMPLATES[kind]
    return (IMPL / name).read_text(encoding="utf-8").replace("<nnn>", card_id[1:])


def fill(text: str, sections=("Objective", "Context and scope")) -> str:
    """Replace the placeholder title and the placeholder lines of the given sections, as a lead
    would."""
    out, current = [], ""
    for line in text.splitlines():
        heading = re.match(r"^## (.+)$", line)
        if not current and line.startswith("title: <"):
            line = "title: Share a list"
        elif heading:
            current = heading.group(1)
        elif current in sections and line.startswith("<") and not line.startswith("<!--"):
            line = f"Filled {current.lower()}: src/share/, route POST /lists/{{id}}/share."
        out.append(line)
    return "\n".join(out) + "\n"


class CardTemplatesTest(unittest.TestCase):
    def parse(self, kind: str, text: str) -> cards.Card:
        card_id = CARD_TEMPLATES[kind][1]
        return cards.parse(Path(f"backlog/{card_id}-sample.md"), text)

    def test_templates_parse_and_lint_clean(self):
        for kind in CARD_TEMPLATES:
            with self.subTest(kind=kind):
                card = self.parse(kind, card_text(kind))
                self.assertEqual(card.problems, [])
                self.assertEqual(card.kind, kind)
                self.assertEqual(cards.lint([card]), [])

    def test_statuses_follow_the_contract(self):
        self.assertEqual(self.parse("story", card_text("story")).status, "draft")
        self.assertEqual(self.parse("task", card_text("task")).status, "draft")
        anomaly = self.parse("anomaly", card_text("anomaly"))
        self.assertEqual(anomaly.status, "to-triage")
        self.assertTrue(anomaly.found)
        self.assertEqual(self.parse("story", card_text("story")).spec, "s004")

    def test_unfilled_card_is_not_ready(self):
        for kind in CARD_TEMPLATES:
            with self.subTest(kind=kind):
                text = fm.set_key(card_text(kind), "status", "ready")
                problems = cards.readiness(self.parse(kind, text))
                self.assertIn(cards.TITLE_REQUIRED, problems)
                self.assertIn("'## Objective' is empty", problems)
                self.assertIn("'## Context and scope' is empty", problems)

    def test_filled_card_is_ready(self):
        for kind in CARD_TEMPLATES:
            with self.subTest(kind=kind):
                text = fm.set_key(fill(card_text(kind)), "status", "ready")
                card = self.parse(kind, text)
                self.assertEqual(cards.readiness(card), [])
                self.assertEqual(cards.lint([card]), [])

    def test_review_template_follows_the_contract(self):
        text = (ROOT / "templates" / "story" / "review.md").read_text(encoding="utf-8")
        headings = [h for h, _ in fm.sections(text) if h]
        self.assertEqual(headings, ["Findings", "Reinforced checks"])
        filled = re.sub(r"^Verdict: .*$", "Verdict: yes", text, flags=re.M)
        filled = re.sub(r"^Tree: .*$", "Tree: " + "a" * 40, filled, flags=re.M)
        parsed = vd.parse(filled, "review")
        self.assertTrue(parsed.valid, parsed.problems)
        self.assertEqual(parsed.by, "story-reviewer")


class OrderAndCampaignTest(RepoCase):
    def setUp(self):
        super().setUp()
        os.environ["DELIVERY_FAKE_WINDOW"] = "1"
        write(self.repo / "delivery.toml",
              'repo_role = "impl"\nforge = "github"\n[commands]\ncheck = "true"\n')
        card = fm.set_key(fill(card_text("story").replace("s004", "s001")), "status", "ready")
        write(self.repo / "backlog/s001-share.md", card)
        write(self.repo / ".gitignore", ".delivery/run/\ndocs/stories/*/work/\ndocs/campaigns/work/\n")
        self.commit_all("setup")
        git(self.repo, "push", "--quiet", "origin", "main")
        self.cfg = config.load(self.repo)

    def test_campaign_template_is_filled_by_the_engine(self):
        campaign.open_campaign(self.cfg, "run-first", "impl")
        path = self.repo / "docs" / "campaigns" / "run-first.md"
        text = path.read_text(encoding="utf-8")
        for placeholder in ("<name>", "<phase>", "<date>"):
            self.assertNotIn(placeholder, text)
        data, body = fm.split(text)
        self.assertEqual((data["campaign"], data["phase"]), ("run-first", "impl"))
        self.assertRegex(str(data["opened"]), r"^\d{4}-\d\d-\d\d$")
        self.assertEqual([h for h, _ in fm.sections(body) if h], ["Objective", "Questions", "Run", "Next"])
        self.assertLessEqual(len(text.splitlines()), 40)
        self.assertIn("docs/campaigns/work/run-first/", text)
        self.assertTrue((self.repo / "docs" / "campaigns" / "work" / "run-first").is_dir())

    def test_order_skeleton_is_refused_until_written(self):
        order = story.prepare(self.cfg, "s001")
        text = order.read_text(encoding="utf-8")
        data, _ = fm.split(text)
        self.assertEqual(data["id"], "s001")
        self.assertEqual(data["base"], git(order.parents[3], "rev-parse", "HEAD"))
        self.assertEqual(data["base"], git(self.repo, "rev-parse", "origin/main"))
        self.assertEqual(data["path"], "plan")
        self.assertEqual(sorted(story.order_problems(text)), sorted([
            "frontmatter 'campaign' is not filled", "section '## Objective' is empty",
            "section '## Deliverables' is empty"]))

    def test_written_order_opens_the_story(self):
        order = story.prepare(self.cfg, "s001")
        text = order.read_text(encoding="utf-8").replace("<campaign>", "run-first")
        text = re.sub(r"^<One sentence.*>$", "Users share a list.", text, flags=re.M)
        text = re.sub(r"^<One deliverable per line.*>$", "- share route — proof: true → exit 0",
                      text, flags=re.M)
        order.write_text(text, encoding="utf-8")
        self.assertEqual(story.order_problems(text), [])
        st = story.open_story(self.cfg, "s001", start=False)
        self.assertEqual(st.name, "open")
        wt = order.parents[3]
        base = git(wt, "merge-base", "HEAD", "origin/main")
        self.assertEqual(story.Git(wt).first_commit_files(base), ["docs/stories/s001/order.md"])
        problems = gate.check(story.Git(wt), "s001")
        self.assertFalse(any("first commit" in p for p in problems), problems)


class PromptRulesTest(unittest.TestCase):
    def files(self):
        for rel in MINE:
            path = ROOT / rel
            yield from (sorted(p for p in path.rglob("*.md")) if path.is_dir() else [path])

    def test_kit_lint_is_green_for_these_files(self):
        errors, _ = kit.lint(ROOT)
        mine = [e for e in errors if e.startswith(MINE)]
        self.assertEqual(mine, [])

    def test_no_shell_variable_expansion_is_prescribed(self):
        # Unattended roles run under dontAsk: a command with $VAR is refused.
        for path in self.files():
            text = path.read_text(encoding="utf-8")
            found = [m for m in re.findall(r"\$\{?[A-Z][A-Z0-9_]*", text)
                     if m not in ("$ARGUMENTS", "$NAME")]
            self.assertEqual(found, [], path)

    def test_prompts_name_only_existing_skills_and_commands(self):
        for path in self.files():
            text = path.read_text(encoding="utf-8")
            for skill in re.findall(r"delivery-method:([a-z-]+)", text):
                exists = (ROOT / "skills" / skill / "SKILL.md").exists() or \
                         (ROOT / "commands" / f"{skill}.md").exists() or \
                         (ROOT / "agents" / f"{skill}.md").exists()
                self.assertTrue(exists, f"{path.name}: delivery-method:{skill}")

    def test_prompts_name_only_existing_templates(self):
        for path in self.files():
            text = path.read_text(encoding="utf-8")
            for rel in re.findall(r"\.delivery/templates/([a-z/-]+\.md)", text):
                self.assertTrue((ROOT / "templates" / rel).exists(), f"{path.name}: {rel}")
            for rel in re.findall(r"\.delivery/templates/([a-z-]+)/", text):
                self.assertTrue((ROOT / "templates" / rel).is_dir(), f"{path.name}: {rel}")


def text_of(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


def ends_with(agent: str) -> str:
    return fm.section_get(fm.load(ROOT / "agents" / f"{agent}.md")[1], "Ends with") or ""


class PromptContractTest(unittest.TestCase):
    def test_no_prompt_relies_on_shell_expansion(self):
        # Role sessions run under dontAsk: a command with $VAR is refused. $ARGUMENTS is the
        # slash-command argument; $NAME appears only in the rule that forbids it.
        for folder in PROMPT_DIRS:
            for path in sorted((ROOT / folder).rglob("*.md")):
                for line in path.read_text(encoding="utf-8").splitlines():
                    for found in re.findall(r"\$\{?[A-Za-z_(][A-Za-z0-9_]*", line):
                        with self.subTest(path=path.name, line=line):
                            self.assertIn(found, ("$ARGUMENTS", "$NAME"))
                            if found == "$NAME":
                                self.assertIn("refused", line)

    def test_targeted_test_is_the_test_command(self):
        for rel in ("skills/testing-doctrine/SKILL.md", "agents/story-implementer.md",
                    "agents/story-reviewer.md", "commands/impl-frame.md"):
            with self.subTest(rel=rel):
                self.assertIn("just test <selector>", text_of(rel))
        toml = text_of("templates/project/delivery.toml")
        self.assertIn('test = "just test {selector}"', toml)
        cfg = config.parse(tomllib.loads(toml), ROOT / "_kit")
        for role in ("story-implementer", "story-reviewer"):
            allow = roles.permissions(cfg, role, ROOT / "_kit-wt", "s001")["permissions"]["allow"]
            self.assertIn("Bash(just test *)", allow, role)
        self.assertRegex(text_of("templates/project/justfile"), r"(?m)^test selector:")

    def test_reviewer_bites_with_check_when_no_test_command(self):
        reviewer = text_of("agents/story-reviewer.md")
        self.assertIn("`check` on the broken tree", reviewer)
        self.assertIn("the aimed test is the one failing", reviewer)
        self.assertIn("replay `check` or the UI suites on the verified tree", reviewer)

    def test_each_role_ends_with_its_exact_outcome_lines(self):
        self.assertIn("Outcome: done|blocked|deferred|plan-ready — <reason>", ends_with("story-implementer"))
        reviewer = ends_with("story-reviewer")
        self.assertIn("`Outcome: done — verdict yes`", reviewer)
        self.assertIn("`Outcome: done — verdict no`", reviewer)
        runner = ends_with("qualification-runner")
        self.assertIn("`Outcome: done — ", runner)
        self.assertIn("`Outcome: blocked — <reason>`", runner)
        for other in ("deferred", "plan-ready", "question"):
            self.assertNotIn(other, runner)
        lead = ends_with("technical-lead")
        self.assertIn("`Outcome: blocked — <reason>`", lead)
        for agent in ("story-implementer", "story-reviewer", "qualification-runner", "technical-lead",
                      "qualification-lead", "product-analyst"):
            self.assertIn("Outcome: ", ends_with(agent), agent)

    def test_run_reads_what_the_engine_prints_on_exit_3(self):
        run, engine = text_of("commands/run.md"), text_of("engine/deliveryctl/story.py")
        for phrase in ("max_in_flight", "anchored before", "already open", "still running"):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, run)
                self.assertIn(phrase, engine)
        self.assertRegex(run, r"1: a malformed command or an\s+internal error")

    def test_run_anchors_ahead_without_preparing(self):
        run = text_of("commands/run.md")
        for needle in ("do not prepare it", "git show origin/<target>:<path>",
                       "git grep <pattern> origin/<target>", "implicit", "to reconfirm after merge",
                       "right before opening", "without `cd`", "git grep <pattern> story/<id>",
                       "git ls-tree -r --name-only story/<id>",
                       "not probed — to probe by the implementer: <mechanism>"):
            with self.subTest(needle=needle):
                self.assertIn(needle, run)
        self.assertIn("not probed — to probe by the implementer: <mechanism>",
                      text_of("skills/anchoring/SKILL.md"))

    def test_order_size_is_a_signal_not_a_stop(self):
        self.assertIn("signal, not a stop", text_of("skills/work-orders/SKILL.md"))
        for rel in ("skills/work-orders/SKILL.md", "templates/story/order.md"):
            self.assertNotIn("lines at most", text_of(rel), rel)

    def test_story_review_has_no_refuter(self):
        skill = text_of("skills/adversarial-review/SKILL.md")
        self.assertIn("Story review", skill)
        self.assertIn("no size, no refuter", skill)
        self.assertIn("in a spec review or a qualification,\n  each non-conforming one has a refuter verdict",
                      skill)

    def test_framing_template_follows_the_contract(self):
        body = fm.split(text_of("templates/spec/framing.md"))[1]
        self.assertIn('D1 : <short title> — <decision> — "<owner\'s words>" (<date>)',
                      fm.section_get(body, "Firm decisions"))
        self.assertIn("technical-lead", fm.section_get(body, "To investigate"))
        story_map = fm.section_get(body, "Story map")
        self.assertIn("- s001 : <short title", story_map)
        self.assertIn("covers: <D<n> : short title, or none>", story_map)

    def test_ids_are_named_with_their_short_title(self):
        # Wherever a person reads it, an identifier is written '<id> : <short title>'.
        self.assertIn("never by the identifier alone", text_of("rules/rules.md"))
        for rel, needle in (("templates/impl/card-story.md", "s<nnn> : <titre court>"),
                            ("templates/impl/card-task.md", "t<nnn> : <titre court>"),
                            ("templates/impl/card-anomaly.md", "a<nnn> : <titre court>"),
                            ("templates/story/order.md", "`<card id> : <short title>`"),
                            ("templates/story/report.md", "`<id> : <short title>`"),
                            ("templates/story/review.md", "1. <short title> — "),
                            ("templates/campaign/campaign.md", "« <id> : <titre court> »"),
                            ("templates/qualification/report.md", "<A-1 : "),
                            ("templates/spec/review-report.md", "<s001 : <short title>, AC2"),
                            ("commands/run.md", "`defer <id> : <title>`"),
                            ("agents/technical-lead.md", "`<id> : <title>`"),
                            ("agents/product-analyst.md", "`D3 : the sharing rule`")):
            with self.subTest(rel=rel):
                self.assertIn(needle, text_of(rel))
        for kind in CARD_TEMPLATES:
            with self.subTest(kind=kind):
                self.assertIn("3 à 8 mots", card_text(kind).split("\n---", 1)[0])


if __name__ == "__main__":
    unittest.main()
