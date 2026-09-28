"""Journal and notifications with fake 'psql' and notify commands: the DSN never on a command
line, bounded batches in one transaction each, a queue rewritten batch by batch; an event is
new once whatever the channel, and a failing toast says so."""

import io
import json
import os
from contextlib import redirect_stderr
from pathlib import Path

from support import RepoCase, write

from deliveryctl import journal, notify

FAKE_PSQL = r'''#!/usr/bin/env python3
import json, os, sys
calls = os.environ["FAKE_PSQL_LOG"]
n = sum(1 for _ in open(calls)) if os.path.exists(calls) else 0
with open(calls, "a") as log:
    log.write(json.dumps({"argv": sys.argv[1:], "password": os.environ.get("PGPASSWORD"),
                          "host": os.environ.get("PGHOST"), "stdin": sys.stdin.read()}) + "\n")
if str(n + 1) in os.environ.get("FAKE_PSQL_FAIL", "").split(","):
    sys.stderr.write("could not connect to server\n")
    sys.exit(2)
'''


class JournalTest(RepoCase):
    def setUp(self):
        super().setUp()
        bin_dir = self.tmp / "bin"
        write(bin_dir / "psql", FAKE_PSQL).chmod(0o755)
        self.calls_file = self.tmp / "psql.log"
        os.environ.update(PATH=f"{bin_dir}{os.pathsep}{os.environ['PATH']}", FAKE_PSQL_LOG=str(self.calls_file))
        self.machine("postgresql://delivery:s%40cret@db.example:5433/journal?sslmode=disable")

    def machine(self, dsn: str, notify_cmd: str = ""):
        write(self.home / ".config/delivery-method/machine.toml",
              f'journal_dsn = "{dsn}"\nnotify_cmd = "{notify_cmd}"\n')

    def calls(self) -> list[dict]:
        return [json.loads(l) for l in self.calls_file.read_text().splitlines()] if self.calls_file.exists() else []

    def queued(self) -> list[dict]:
        path = journal.queue_path()
        return [json.loads(l) for l in path.read_text().splitlines()] if path.exists() else []

    def test_dsn_goes_to_the_environment(self):
        env = journal.psql_env("postgresql://delivery:s%40cret@[::1]:5433/journal?sslmode=require")
        self.assertEqual((env["PGUSER"], env["PGPASSWORD"], env["PGHOST"], env["PGPORT"], env["PGDATABASE"],
                          env["PGSSLMODE"]), ("delivery", "s@cret", "::1", "5433", "journal", "require"))
        env = journal.psql_env("host=127.0.0.1 port=55432 dbname=delivery user=delivery password='a b'")
        self.assertEqual((env["PGHOST"], env["PGPORT"], env["PGPASSWORD"]), ("127.0.0.1", "55432", "a b"))

    def test_record_sends_literals_on_stdin(self):
        journal.record(journal.event("todo", "note", "it's done\x00, \\o/"))
        call = self.calls()[0]
        self.assertNotIn("s@cret", " ".join(call["argv"]))
        self.assertNotIn("s%40cret", " ".join(call["argv"]))
        self.assertEqual((call["password"], call["host"]), ("s@cret", "db.example"))
        self.assertIn("--single-transaction", call["argv"])
        self.assertIn("it''s done, \\\\o/", call["stdin"])
        self.assertEqual(self.queued(), [])

    def test_unreachable_database_queues_the_event(self):
        os.environ["FAKE_PSQL_FAIL"] = "1"
        journal.record(journal.event("todo", "note", "kept"))
        self.assertEqual([e["text"] for e in self.queued()], ["kept"])

    def test_flush_by_batches_keeps_what_is_left(self):
        path = journal.queue_path()
        path.write_text("".join(json.dumps(journal.event("todo", "note", f"e{i}")) + "\n" for i in range(450)))
        os.environ["FAKE_PSQL_FAIL"] = "2"
        err = io.StringIO()
        with redirect_stderr(err):
            self.assertEqual(journal.flush(), (200, 250))
        self.assertIn("could not connect", err.getvalue())
        self.assertEqual(self.queued()[0]["text"], "e200")
        self.assertEqual(self.calls()[0]["stdin"].count("INSERT INTO"), 200)
        os.environ["FAKE_PSQL_FAIL"] = ""
        self.assertEqual(journal.flush(), (250, 0))
        self.assertFalse(path.exists())
        self.assertEqual([c["stdin"].count("INSERT INTO") for c in self.calls()], [200, 200, 200, 50])


class NotifyTest(RepoCase):
    def notify(self, key: str):
        err = io.StringIO()
        with redirect_stderr(err):
            new = notify.notify(self.repo, key, "decision", "s001 : blocked", "read report.md")
        return new, err.getvalue()

    def test_new_event_without_notify_cmd(self):
        self.assertEqual(self.notify("s001:blocked"), (True, "[notification] ⚠ todo — s001 : blocked — read report.md\n"))
        self.assertEqual(self.notify("s001:blocked"), (False, ""))

    def test_failing_notify_cmd_says_so(self):
        cmd = write(self.tmp / "toast", "#!/bin/sh\necho 'cannot open display' >&2\nexit 1\n")
        cmd.chmod(0o755)
        write(self.home / ".config/delivery-method/machine.toml", f'notify_cmd = "{cmd}"\n')
        new, err = self.notify("s001:stall")
        self.assertTrue(new)
        self.assertEqual(err, "[notification failed: cannot open display] ⚠ todo — s001 : blocked — read report.md\n")
        cmd.write_text("#!/bin/sh\nexit 0\n")
        self.assertEqual(self.notify("s001:other"), (True, ""))


if __name__ == "__main__":
    import unittest
    unittest.main()
