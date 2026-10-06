"""Command line of the engine (CONTRACTS.md §12.2)."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import VERSION
from .core import EXIT_ERROR, EXIT_OK, EXIT_RED, DeliveryError, eprint, main_root, require_human, require_local


def _cfg():
    from . import config
    return config.load(main_root())


def cmd_cards(args) -> int:
    from . import cards
    from .gitops import Git
    cfg = _cfg()
    git = Git(cfg.root)
    if args.action == "lint":
        here = Path.cwd() if (Path.cwd() / "backlog").is_dir() else cfg.root    # before a commit
        local = cards.load_all(here, cfg.risks)
        problems = cards.lint(local)
        for where, problem in problems:
            print(f"{cards.where_label(where, local)} — {problem}")
        for where, note in cards.notes(local):
            print(f"note: {cards.where_label(where, local)} — {note}")
        print("backlog: " + ("red" if problems else "green"))
        return EXIT_RED if problems else EXIT_OK
    all_cards = cards.load_from_rev(git, git.target_ref(), cfg.risks)    # what the run reads
    done = cards.merged_ids(git)
    known = {c.id: c.title for c in all_cards}
    if args.action == "order":
        for card, deps in cards.order(all_cards, done):
            waiting = f" (waits for {cards.labels(deps, known)})" if deps else ""
            print(f"{cards.label(card.id, card.title)} — {card.kind}, {card.status}{waiting}")
        return EXIT_OK
    for card in all_cards:
        state = "done" if card.id in done else card.status
        deps = f", depends on {cards.labels(card.depends_on, known)}" if card.depends_on else ""
        print(f"{cards.label(card.id, card.title)} — {card.kind}, {state}{deps}")
    return EXIT_OK


def cmd_story(args) -> int:
    from . import story
    action = args.action
    if action in ("open", "next", "wait"):
        require_local(f"story {action}")
    cfg = _cfg()
    if action == "prepare":
        print(story.prepare(cfg, args.id))
    elif action == "open":
        draft = Path(args.order) if args.order else None
        print(story.render(story.open_story(cfg, args.id, order_draft=draft, start=not args.no_start)))
    elif action == "status":
        ids = [args.id] if args.id else story.open_ids(cfg)
        if not ids:
            print("no story in flight")
        if args.watch:
            import time
            while True:
                try:
                    out = "\n\n".join(_describe(story, cfg, i) for i in (ids or story.open_ids(cfg)))
                    sys.stdout.write("\033[H\033[2J" + out + "\n")
                    sys.stdout.flush()
                    story.scan(cfg)
                except DeliveryError as exc:
                    eprint(f"deliveryctl: {exc.message}")
                time.sleep(5)
        for i in ids:
            print(story.describe(cfg, i))
    elif action == "next":
        if args.relaunch:
            print(story.render(story.relaunch(cfg, args.id)))
        else:
            print(story.render(story.next_step(cfg, args.id, go=args.go)))
    elif action == "wait":
        st = story.wait(cfg, args.id, timeout=args.timeout, until=args.until)
        print(story.render(st))
        if st.extra.get("timeout"):
            return 3
    elif action == "close":
        print(story.close(cfg, args.id))
    return EXIT_OK


def _describe(story, cfg, card_id: str) -> str:
    try:
        return story.describe(cfg, card_id)
    except DeliveryError as exc:
        from .cards import label_of
        from .gitops import Git
        return f"{label_of(Git(cfg.root), card_id)} — unknown for now ({exc.message.splitlines()[0]})"


def cmd_verify(args) -> int:
    from . import cards, story
    from .gitops import Git, story_branch
    from .verify import verify
    cfg = _cfg()
    wt = Git(cfg.root).worktree_for(story_branch(args.id))
    if not wt:
        raise DeliveryError(3, f"no worktree for {cards.label_of(Git(cfg.root), args.id)}")
    card = story._card(Git(cfg.root), args.id, cfg)
    result = verify(cfg, wt, args.id, card)
    print(f"{cards.label(args.id, card.title)} — verification {result.verdict} ({result.result})")
    return EXIT_OK if result.verdict == "pass" else EXIT_RED


def cmd_gate(args) -> int:
    from . import cards, gate
    from .gitops import Git, story_branch
    here = Git(Path.cwd())
    branch = here.branch()
    cwd = Path.cwd()
    if branch != story_branch(args.id):
        main = Git(main_root())
        wt = main.worktree_for(story_branch(args.id))
        cwd = wt or cwd
    git = Git(cwd)
    head = args.head or "HEAD"
    problems = gate.check(git, args.id, base=args.base, head=head)
    for problem in problems:
        print(f"- {problem}")
    print(f"{cards.label_of(git, args.id)} — integration check " + ("red" if problems else "green"))
    return EXIT_RED if problems else EXIT_OK


def cmd_submit(args) -> int:
    from . import story
    require_local("submit")
    print(story.submit(_cfg(), args.id))
    return EXIT_OK


def cmd_merge(args) -> int:
    from . import story
    require_human("deliveryctl merge")
    require_local("merge")
    cfg = _cfg()
    print(story.merge(cfg, args.id))
    if not args.keep:
        print(story.close(cfg, args.id))
    return EXIT_OK


def cmd_run(args) -> int:
    from . import run as run_mod
    require_human("deliveryctl run")
    require_local("run")
    return run_mod.start(_cfg(), campaign=args.campaign)


def cmd_campaign(args) -> int:
    from . import campaign
    print(campaign.open_campaign(_cfg(), args.name, args.phase))
    return EXIT_OK


def cmd_note(args) -> int:
    from . import journal
    require_human("deliveryctl note")
    require_local("note")
    root = main_root()
    journal.record(journal.event(root.name, "note", " ".join(args.text), story=args.story or "",
                                 role="human", source="human"))
    print("noted")
    return EXIT_OK


def cmd_journal(args) -> int:
    from . import journal
    if args.action == "add":
        root = main_root()
        import os
        ev = journal.event(root.name, args.category, " ".join(args.text),
                           story=os.environ.get("DELIVERY_STORY", ""),
                           role=os.environ.get("DELIVERY_ROLE", "agent"), source="agent")
        journal.record(ev)
        print("recorded")
    elif args.action == "flush":
        sent, left = journal.flush()
        print(f"sent {sent}, still queued {left}")
    elif args.action == "report":
        require_human("deliveryctl journal report")
        require_local("journal report")
        print(journal.report(args.limit))
    elif args.action == "setup":
        print(journal.SETUP)
    return EXIT_OK


def cmd_hook(args) -> int:
    from . import hooks
    return {"stop": hooks.stop, "session-start": hooks.session_start, "pre-tool": hooks.pre_tool}[args.event]()


def cmd_spec(args) -> int:
    from . import spec
    return spec.main(args)


def cmd_qualify(args) -> int:
    from . import qualify
    return qualify.main(args)


def cmd_nightly(args) -> int:
    from . import nightly
    require_human("deliveryctl nightly")
    require_local("nightly")
    return nightly.run(_cfg())


def cmd_init(args) -> int:
    from . import init
    require_human("deliveryctl init")
    require_local("init")
    return init.main(args)


def cmd_doctor(args) -> int:
    from . import doctor
    return doctor.main(args)


def cmd_kit(args) -> int:
    from . import kit
    return kit.main(args)


def build() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="deliveryctl", description="Engine of the delivery-method plugin.")
    p.add_argument("--version", action="version", version=f"deliveryctl {VERSION}")
    sub = p.add_subparsers(dest="verb", required=True)

    s = sub.add_parser("cards", help="list, lint or order backlog cards")
    s.add_argument("action", choices=["list", "lint", "order"])
    s.set_defaults(func=cmd_cards)

    s = sub.add_parser("story", help="story life cycle")
    s.add_argument("action", choices=["prepare", "open", "status", "next", "wait", "close"])
    s.add_argument("id", nargs="?")
    s.add_argument("--watch", action="store_true", help="story status: refresh until interrupted")
    s.add_argument("--no-start", action="store_true", help="open without starting the implementer")
    s.add_argument("--order", help="order draft to commit as docs/stories/<id>/order.md")
    s.add_argument("--go", action="store_true", help="continue after plan-ready (human gesture)")
    s.add_argument("--relaunch", action="store_true",
                   help="abandon the cloud implementer and start a new one (human gesture)")
    s.add_argument("--timeout", type=int, default=540, help="story wait: seconds before giving up")
    s.add_argument("--until", choices=["checkpoint", "merged"], default="checkpoint",
                   help="story wait: stop at the next checkpoint (default) or only at the merge")
    s.set_defaults(func=cmd_story)

    for verb, func, helptext in (("verify", cmd_verify, "run the checks of a story and commit the verdict"),
                                 ("submit", cmd_submit, "check, push and open the merge request")):
        s = sub.add_parser(verb, help=helptext)
        s.add_argument("id")
        s.set_defaults(func=func)

    s = sub.add_parser("gate", help="integration check of a story branch")
    s.add_argument("id")
    s.add_argument("--base")
    s.add_argument("--head")
    s.set_defaults(func=cmd_gate)

    s = sub.add_parser("merge", help="merge a story (human gesture)")
    s.add_argument("id")
    s.add_argument("--keep", action="store_true", help="keep the worktree")
    s.set_defaults(func=cmd_merge)

    s = sub.add_parser("run", help="start the technical-lead on the ready cards (human gesture)")
    s.add_argument("--campaign")
    s.set_defaults(func=cmd_run)

    s = sub.add_parser("campaign", help="open the campaign file of a lead")
    s.add_argument("action", choices=["open"])
    s.add_argument("name")
    s.add_argument("--phase", choices=["spec", "impl", "qualification"], default="impl")
    s.set_defaults(func=cmd_campaign)

    s = sub.add_parser("note", help="add a note to the experience journal (human)")
    s.add_argument("text", nargs="+")
    s.add_argument("--story")
    s.set_defaults(func=cmd_note)

    s = sub.add_parser("journal", help="experience journal")
    s.add_argument("action", choices=["add", "flush", "report", "setup"])
    s.add_argument("text", nargs="*")
    s.add_argument("--category", default="other")
    s.add_argument("--limit", type=int, default=50)
    s.set_defaults(func=cmd_journal)

    s = sub.add_parser("hook", help="called by the plugin hooks")
    s.add_argument("event", choices=["stop", "session-start", "pre-tool"])
    s.set_defaults(func=cmd_hook)

    s = sub.add_parser("spec", help="specification: lint, release, sync, verify")
    s.add_argument("action", choices=["lint", "release", "sync", "verify"])
    s.add_argument("version", nargs="?")
    s.add_argument("--source")
    s.set_defaults(func=cmd_spec)

    s = sub.add_parser("qualify", help="qualification: open, run, lint, submit, close")
    s.add_argument("action", choices=["open", "run", "lint", "submit", "close"])
    s.add_argument("increment")
    s.set_defaults(func=cmd_qualify)

    s = sub.add_parser("nightly", help="full UI suite on the target branch, anomalies by merge request")
    s.set_defaults(func=cmd_nightly)

    s = sub.add_parser("init", help="install or upgrade the method in this repository (human)")
    s.add_argument("layout", nargs="?", choices=["single", "spec", "impl"],
                   help="what the repository holds (default single); impl takes the spec repository next")
    s.add_argument("spec_repo", nargs="?", metavar="SPEC",
                   help="impl: the spec repository (short name, owner/name, URL or local path)")
    s.add_argument("--language")
    s.add_argument("--forge", choices=["github", "gitlab"])
    s.add_argument("--check")
    s.add_argument("--acceptance")
    s.add_argument("--serve")
    s.add_argument("--upgrade", action="store_true")
    s.add_argument("--dry-run", action="store_true")
    s.set_defaults(func=cmd_init)

    s = sub.add_parser("doctor", help="read-only diagnosis")
    s.set_defaults(func=cmd_doctor)

    s = sub.add_parser("kit", help="checks of the plugin itself")
    s.add_argument("action", choices=["lint"])
    s.add_argument("path", nargs="?", default=".")
    s.set_defaults(func=cmd_kit)
    return p


def main(argv=None) -> int:
    parser = build()
    try:
        args = parser.parse_args(argv)
        if getattr(args, "func", None) is cmd_story and args.action not in ("status",) and not args.id:
            parser.error(f"story {args.action} needs a card id")
    except SystemExit as exc:          # argparse exits 2, the code of a red check: usage is 1 (§17)
        return EXIT_ERROR if exc.code == 2 else (exc.code or EXIT_OK)
    try:
        return args.func(args)
    except DeliveryError as exc:
        eprint(f"deliveryctl: {exc.message}")
        return exc.code
    except KeyboardInterrupt:
        return EXIT_ERROR
