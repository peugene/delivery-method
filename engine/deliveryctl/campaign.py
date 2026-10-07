"""Campaigns: the state file of a lead and its branch (CONTRACTS.md §12.3). The lead works on
`campaign/<name>` in the main checkout; `campaign push` pushes it and opens or updates its pull
request, which the decision owner merges: nothing the lead writes reaches the default branch
otherwise."""

from __future__ import annotations

from pathlib import Path

from . import cards, frontmatter as fm
from .config import Config
from .core import EXIT_OK, EXIT_PRECONDITION, check_slug, fail, today
from .forge import Forge
from .gitops import Git, trailer_values
from .spec import GO_TRAILER

TEMPLATE = Path(__file__).resolve().parents[2] / "templates" / "campaign" / "campaign.md"


def state_file(root: Path, name: str) -> Path:
    return Path(root) / "docs" / "campaigns" / f"{name}.md"


def branch_of(name: str) -> str:
    return f"campaign/{name}"


def _start_from_target(git: Git, branch: str, target: str) -> None:
    git.run("switch", "--quiet", "--no-track", "-C", branch, target)


def switch(cfg: Config, name: str) -> str:
    """Put the main checkout on `campaign/<name>`: created from the target head when it does not
    exist, switched to when its pull request is not merged, started again from the target head
    when it is merged. Only the default branch and the campaign branch are left."""
    git = Git(cfg.root)
    branch, default = branch_of(name), git.target_branch()
    here = git.branch()
    if here not in (default, branch):
        fail(EXIT_PRECONDITION, f"{here} is neither {default} nor {branch}: "
                                f"git switch {default}, then run it again")
    git.fetch()
    target = git.target_ref()
    exists = bool(git.rev(branch) or git.rev(f"origin/{branch}"))
    merged = False
    if exists and git.has_remote():
        request = Forge(cfg, git).find_branch(branch)
        merged = bool(request and request["state"] == "merged")
    if here == branch and not merged:
        return f"on {branch}"
    if git.out("status", "--porcelain", "--untracked-files=no"):
        fail(EXIT_PRECONDITION, f"uncommitted changes would be lost by the switch to {branch}: "
                                "commit or stash them, then run it again")
    if not exists or merged:
        _start_from_target(git, branch, target)
        return f"on {branch} ({'started again' if merged else 'created'} from {target})"
    git.run("switch", "--quiet", branch)
    return f"on {branch} (existing)"


def request_body(cfg: Config, git: Git, name: str) -> str:
    """Description of the campaign pull request: the objective, the cards with their status, the GOs."""
    objective = ""
    path = state_file(cfg.root, name)
    if path.exists():
        _, body = fm.split(path.read_text(encoding="utf-8"), str(path))
        objective = (fm.section_get(body, "Objective") or "").strip()
    lines = [f"- {cards.label(c.id, c.title)} — `{c.status}`" for c in cards.load_from_rev(git, "HEAD")]
    gos: list[str] = []
    log = git.out("log", "--reverse", "--format=%B%x00", f"{git.target_ref()}..HEAD", check=False)
    for message in log.split("\x00"):
        gos += [go for go in trailer_values(message, GO_TRAILER) if go not in gos]
    return "\n".join([f"# Campagne {name}", "", "## Objective", "", objective or "_not written yet_", "",
                      "## Cards", ""] + (lines or ["- none yet"]) + ["", "## GOs given", ""] +
                     ([f"- {go}" for go in gos] or ["- none yet"]) + [""])


def push(cfg: Config, name: str | None = None) -> int:
    """Push the campaign branch and open its pull request, or update the open one."""
    git = Git(cfg.root)
    branch, default = git.branch(), git.target_branch()
    if branch == default:
        fail(EXIT_PRECONDITION, f"{branch} is the default branch: the lead's work goes through a pull "
                                "request of the branch campaign/<name> (deliveryctl campaign open <name>)")
    if not branch.startswith("campaign/"):
        fail(EXIT_PRECONDITION, f"{branch} is not a campaign branch: switch to campaign/<name>")
    current = branch.split("/", 1)[1]
    if name and name != current:
        fail(EXIT_PRECONDITION, f"you are on {branch}, not on {branch_of(name)}: "
                                f"git switch {branch_of(name)}, or push without a name")
    if git.out("status", "--porcelain", "--", "docs/campaigns", "backlog"):
        print("note: uncommitted changes under backlog/ or docs/campaigns/ are not pushed")
    git.fetch()
    if git.out("rev-list", "--count", f"{git.target_ref()}..HEAD") == "0":
        fail(EXIT_PRECONDITION, f"{branch} has no commit beyond {default}: nothing to propose")
    print(Forge(cfg, git).open_branch(branch, f"Campagne {current}", request_body(cfg, git, current),
                                      refresh=True, again=True))
    return EXIT_OK


def open_campaign(cfg: Config, name: str, phase: str) -> str:
    check_slug(name, "campaign name")
    print(switch(cfg, name))
    path = state_file(cfg.root, name)
    (cfg.root / "docs" / "campaigns" / "work" / name).mkdir(parents=True, exist_ok=True)
    if path.exists():
        return f"campaign {name}: {path.relative_to(cfg.root)} (existing)"
    path.parent.mkdir(parents=True, exist_ok=True)
    text = TEMPLATE.read_text(encoding="utf-8") if TEMPLATE.exists() else \
        "## Objective\n\n## Questions\n\n## Run\n\n## Next\n"
    text = text.replace("<name>", name).replace("<phase>", phase).replace("<date>", today())
    path.write_text(text, encoding="utf-8")
    return f"campaign {name}: {path.relative_to(cfg.root)} (created, not committed)"
