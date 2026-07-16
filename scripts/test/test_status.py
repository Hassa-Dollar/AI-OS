#!/usr/bin/env python3
"""Unit tests for scripts/os state derivation (OS-V1 / ADR-0026 §4).

The operator CLI lives at scripts/os (an extensionless stdlib-only executable, the
ADR-0023 entrypoint). We load it as a module via SourceFileLoader (no .py suffix)
and drive derive_state() with fixture logs + ledger rows — no git, no FS, no model
calls. Run: `python3 -m unittest scripts.test.test_status` from the repo root, or
`python3 scripts/test/test_status.py` directly.
"""
import importlib.machinery
import importlib.util
import os
import sys
import tempfile
import unittest
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]


def _load_os():
    loader = importlib.machinery.SourceFileLoader("aios_os", str(_REPO / "scripts" / "os"))
    spec = importlib.util.spec_from_loader("aios_os", loader)
    mod = importlib.util.module_from_spec(spec)
    loader.exec_module(mod)
    return mod


OS = _load_os()


def ev(kind, task_id="T", note=""):
    return {"ts": "2026-07-15T00:00:00Z", "event": kind, "task_id": task_id,
            "branch": "task/T-x", "actor": "robot", "note": note}


class DeriveStateTests(unittest.TestCase):
    def test_queued_no_dispatch_event(self):
        self.assertEqual(OS.derive_state("T", "", [], now=0.0), "queued")

    def test_running_dispatch_no_footer(self):
        self.assertEqual(
            OS.derive_state("T", "", [ev("dispatch")], now=0.0), "running")

    def test_running_dispatch_with_partial_log_no_footer(self):
        log = "=== 2026-07-15T00:00:00Z dispatch.sh model=opencode-go/glm-5.2 ===\nworking\n"
        self.assertEqual(
            OS.derive_state("T", log, [ev("dispatch")], now=0.0), "running")

    def test_done_land_after_exit_zero_footer(self):
        log = "=== ... dispatch.sh ... ===\n=== exit 0 2026-07-15T00:10:00Z ===\n"
        self.assertEqual(
            OS.derive_state("T", log, [ev("dispatch"), ev("land")], now=0.0), "done")

    def test_done_auto_approve_event(self):
        # auto-approve merges the task immediately -> done
        self.assertEqual(
            OS.derive_state("T", "", [ev("dispatch"), ev("auto-approve")], now=0.0), "done")

    def test_failed_nonzero_footer(self):
        log = "=== exit 137 2026-07-15T00:05:00Z ===\n"
        self.assertEqual(
            OS.derive_state("T", log, [ev("dispatch")], now=0.0), "failed")

    def test_failed_guardrail_event_aborts_gate(self):
        self.assertEqual(
            OS.derive_state("T", "", [ev("dispatch"), ev("guardrail", note="escaped_files=x")],
                           now=0.0), "failed")

    def test_gated_held_opus_gate_event(self):
        self.assertEqual(
            OS.derive_state("T", "", [ev("dispatch"), ev("opus-gate")], now=0.0), "gated-held")

    def test_waiting_gate_exit_zero_no_qa(self):
        log = "=== exit 0 2026-07-15T00:10:00Z ===\n"
        self.assertEqual(
            OS.derive_state("T", log, [ev("dispatch")], now=0.0), "waiting-gate")

    def test_qa_pass_no_opus_gate_is_held_at_gate(self):
        # qa passed, no land yet, no opus-gate -> still sitting at the gate (pending merge)
        log = "=== exit 0 2026-07-15T00:10:00Z ===\n"
        self.assertEqual(
            OS.derive_state("T", log, [ev("dispatch"), ev("qa", note="verdict=pass")], now=0.0),
            "gated-held")

    def test_land_reshapes_a_failed_worker_into_done(self):
        # a worker crash is not terminal if the operator later lands the task
        log = "=== exit 1 2026-07-15T00:05:00Z ===\n"
        self.assertEqual(
            OS.derive_state("T", log, [ev("dispatch"), ev("land")], now=0.0), "done")


class FooterParserTests(unittest.TestCase):
    def test_parses_last_footer_in_appended_log(self):
        log = ("=== exit 1 2026-07-15T00:05:00Z ===\n"
               "=== 2026-07-15T01:00:00Z dispatch.sh model=opencode-go/glm-5.2 ===\n"
               "ok\n"
               "=== exit 0 2026-07-15T01:10:00Z ===\n")
        self.assertEqual(OS.parse_footer(log), (0, "2026-07-15T01:10:00Z"))

    def test_returns_none_when_no_footer(self):
        self.assertIsNone(OS.parse_footer("noise\n=== 2026-07-15T00:00:00Z dispatch.sh model=x ===\n"))

    def test_negative_exit_codes_parse(self):
        log = "=== exit -1 2026-07-15T00:05:00Z ===\n"
        self.assertEqual(OS.parse_footer(log), (-1, "2026-07-15T00:05:00Z"))


class LastLineTests(unittest.TestCase):
    def test_skips_trailing_footer_returns_last_real_line(self):
        log = ("=== 2026-07-15T00:00:00Z dispatch.sh model=x ===\n"
               "doing work\n"
               "=== exit 0 2026-07-15T00:10:00Z ===\n")
        self.assertEqual(OS.last_log_line(log), "doing work")

    def test_empty_log(self):
        self.assertEqual(OS.last_log_line(""), "")


class FrontMatterTests(unittest.TestCase):
    def test_parses_scalar_list_and_inline_comment(self):
        text = (
            "---\n"
            "id: \"T05\"   # the task\n"
            "slug: redirect-click\n"
            "owner_role: implementer_secondary\n"
            "files_allowed:\n"
            "  - components/api/src/redirect.ts\n"
            "  - \"@scope/pkg\"   # list item\n"
            "---\n# Goal\nbody\n"
        )
        fm = OS._front_matter(text)
        self.assertEqual(fm["id"], "T05")
        self.assertEqual(fm["slug"], "redirect-click")
        self.assertEqual(fm["owner_role"], "implementer_secondary")
        self.assertEqual(fm["files_allowed"], ["components/api/src/redirect.ts", "@scope/pkg"])

    def test_missing_fences_returns_empty(self):
        self.assertEqual(OS._front_matter("no front matter here"), {})


class ShortSlugTests(unittest.TestCase):
    def test_strips_gateway_prefix(self):
        self.assertEqual(OS.short_slug("opencode-go/glm-5.2"), "glm-5.2")

    def test_empty(self):
        self.assertEqual(OS.short_slug(""), "")


class LastRunTests(unittest.TestCase):
    def test_no_header_returns_none(self):
        self.assertEqual(OS.last_run(""), (None, None))
        self.assertEqual(OS.last_run("noise\n=== exit 0 2026-07-15T00:10:00Z ===\n"),
                         (None, None))

    def test_header_in_flight_returns_none_terminator(self):
        log = "=== 2026-07-15T00:00:00Z dispatch.sh model=opencode-go/glm-5.2 ===\nworking\n"
        h, term = OS.last_run(log)
        self.assertIsNotNone(h)
        self.assertEqual(h.group("script"), "dispatch.sh")
        self.assertEqual(h.group("slug"), "opencode-go/glm-5.2")
        self.assertIsNone(term)

    def test_exit_terminator_after_last_header(self):
        log = ("=== 2026-07-15T00:00:00Z dispatch.sh model=a ===\n"
               "=== exit 0 2026-07-15T00:10:00Z ===\n")
        _, term = OS.last_run(log)
        self.assertEqual(term, ("exit", 0, "2026-07-15T00:10:00Z"))

    def test_stopped_preferred_over_exit_after_last_header(self):
        # os stop appends `=== stopped ... ===`; dispatch.sh's tee close may also land an
        # exit footer — stopped must win so status shows `stopped`.
        log = ("=== 2026-07-15T00:00:00Z dispatch.sh model=a ===\n"
               "=== stopped 2026-07-15T00:05:00Z ===\n"
               "=== exit 143 2026-07-15T00:05:01Z ===\n")
        hdr, term = OS.last_run(log)
        self.assertEqual(term, ("stopped", "2026-07-15T00:05:00Z"))

    def test_multi_run_picks_the_last_header(self):
        # two run blocks: the second is a fix round, in flight.
        log = ("=== 2026-07-15T00:00:00Z dispatch.sh model=a ===\n"
               "=== exit 0 2026-07-15T00:10:00Z ===\n"
               "=== 2026-07-15T01:00:00Z dispatch.sh model=b ===\n"
               "fix in progress\n")
        h, term = OS.last_run(log)
        self.assertEqual(h.group("slug"), "b")
        self.assertIsNone(term)

    def test_last_run_header_helper(self):
        log = ("=== 2026-07-15T00:00:00Z dispatch.sh model=opencode-go/glm-5.2 ===\n"
               "=== exit 0 2026-07-15T00:10:00Z ===\n"
               "=== 2026-07-15T01:00:00Z gate.sh model=opencode-go/deepseek-v4-pro ===\n")
        hdr = OS.last_run_header(log)
        self.assertEqual(hdr["script"], "gate.sh")
        self.assertEqual(hdr["slug"], "opencode-go/deepseek-v4-pro")


class MultiRunStateTests(unittest.TestCase):
    """The T09 live bug: a re-dispatched fix round was invisible as `running` because
    state derivation keyed on the FIRST/any footer; it must key on the LAST run block."""

    def _fixture_two_runs_second_live(self):
        return (
            "=== 2026-07-15T00:00:00Z dispatch.sh model=opencode-go/glm-5.2 ===\n"
            "first attempt\n"
            "=== exit 0 2026-07-15T00:10:00Z ===\n"
            "=== 2026-07-15T01:00:00Z dispatch.sh model=opencode-go/glm-5.2 ===\n"
            "fix round in flight\n"
        )

    def test_second_run_live_shows_running(self):
        log = self._fixture_two_runs_second_live()
        self.assertEqual(
            OS.derive_state("T09", log, [ev("dispatch"), ev("dispatch")], now=0.0),
            "running")

    def test_second_run_finished_shows_waiting_gate(self):
        log = self._fixture_two_runs_second_live() + "=== exit 0 2026-07-15T01:10:00Z ===\n"
        # the second (last) run exited 0 with no qa event yet
        self.assertEqual(
            OS.derive_state("T09", log, [ev("dispatch"), ev("dispatch")], now=0.0),
            "waiting-gate")

    def test_first_run_exit_zero_alone_is_waiting_gate(self):
        log = ("=== 2026-07-15T00:00:00Z dispatch.sh model=a ===\n"
               "ok\n"
               "=== exit 0 2026-07-15T00:10:00Z ===\n")
        self.assertEqual(
            OS.derive_state("T", log, [ev("dispatch")], now=0.0), "waiting-gate")


class VerifyingStateTests(unittest.TestCase):
    def test_gate_run_in_flight_is_verifying(self):
        # the last run header is gate.sh with no exit footer -> QA is running
        log = ("=== 2026-07-15T00:00:00Z dispatch.sh model=a ===\n"
               "worker ok\n"
               "=== exit 0 2026-07-15T00:10:00Z ===\n"
               "=== 2026-07-15T00:11:00Z gate.sh model=opencode-go/deepseek-v4-pro ===\n"
               "verifier running\n")
        self.assertEqual(
            OS.derive_state("T", log, [ev("dispatch")], now=0.0), "verifying")

    def test_gate_run_finished_is_waiting_gate_or_gated_held(self):
        # gate.sh exited 0 with no qa ledger event yet -> waiting-gate
        log = ("=== 2026-07-15T00:11:00Z gate.sh model=v ===\n"
               "review done\n"
               "=== exit 0 2026-07-15T00:15:00Z ===\n")
        self.assertEqual(
            OS.derive_state("T", log, [ev("dispatch")], now=0.0), "waiting-gate")


class StoppedStateTests(unittest.TestCase):
    def test_os_stop_then_status_shows_stopped(self):
        log = ("=== 2026-07-15T00:00:00Z dispatch.sh model=a ===\n"
               "working...\n"
               "=== stopped 2026-07-15T00:05:00Z ===\n")
        self.assertEqual(
            OS.derive_state("T", log, [ev("dispatch")], now=0.0), "stopped")

    def test_resume_dispatch_overrides_stopped(self):
        # after resume re-dispatch, a new header (no footer) flips back to running
        log = ("=== 2026-07-15T00:00:00Z dispatch.sh model=a ===\n"
               "=== stopped 2026-07-15T00:05:00Z ===\n"
               "=== 2026-07-15T01:00:00Z dispatch.sh model=b ===\n"
               "resumed\n")
        self.assertEqual(
            OS.derive_state("T", log, [ev("dispatch"), ev("dispatch")], now=0.0),
            "running")


class AgentsFromHeaderTests(unittest.TestCase):
    def _fm(self, role="implementer"):
        return {"owner_role": role, "model": ""}

    def test_fallback_to_spec_role_when_no_header(self):
        self.assertEqual(OS.agent_from_log(Path(""), self._fm(), ""), "—/implementer")

    def test_dispatch_header_uses_owner_role(self):
        log = "=== 2026-07-15T00:00:00Z dispatch.sh model=opencode-go/glm-5.2 ===\n"
        self.assertEqual(OS.agent_from_log(Path(""), self._fm(), log), "glm-5.2/implementer")

    def test_gate_header_uses_verifier_role(self):
        log = "=== 2026-07-15T00:00:00Z gate.sh model=opencode-go/deepseek-v4-pro ===\n"
        self.assertEqual(OS.agent_from_log(Path(""), self._fm(), log), "deepseek-v4-pro/verifier")


class StripAnsiTests(unittest.TestCase):
    def test_strips_real_ansi_reset(self):
        self.assertEqual(OS.strip_ansi("\x1b[32mhi\x1b[0m"), "hi")

    def test_strips_bare_zero_m_leakage(self):
        # the artifact the operator reported: a bare [0m leaking into LAST_LINE
        self.assertEqual(OS.strip_ansi("done\x1b[0m"), "done")
        self.assertEqual(OS.strip_ansi("compiling[0m "), "compiling ")


class WidthTableTests(unittest.TestCase):
    def _row(self, last_line="x", state="running", id="T01", agent="glm-5.2/implementer",
             branch="task/T01-x", report="yes", log="logs/T01.log"):
        return {"id": id, "agent": agent, "branch": branch, "state": state,
                "report": report, "log": log, "last_line": last_line}

    def test_wide_uses_full_last_line(self):
        row = self._row(last_line="A" * 90)
        rendered = OS.render_table([row], width=80, wide=True)
        self.assertIn("A" * 90, rendered)

    def test_fits_columns_80_no_line_overflow(self):
        row = self._row(last_line="A" * 90)
        rendered = OS.render_table([row], width=80, wide=False)
        longest = max(len(ln) for ln in rendered.splitlines())
        self.assertLessEqual(longest, 80)

    def test_json_shape_unchanged(self):
        import json
        rows = [self._row()]
        parsed = json.loads(OS.render_json(rows))
        self.assertEqual(parsed[0]["state"], "running")
        self.assertEqual(parsed[0]["agent"], "glm-5.2/implementer")


class VerdictFallbackTests(unittest.TestCase):
    def test_qa_section_extracts_last_gate_block(self):
        log = ("=== 2026-07-15T00:00:00Z dispatch.sh model=a ===\n"
               "worker out\n"
               "=== exit 0 2026-07-15T00:10:00Z ===\n"
               "=== 2026-07-15T00:11:00Z gate.sh model=v ===\n"
               "VERDICT: pass\n"
               "RISK: low\n"
               "=== exit 0 2026-07-15T00:15:00Z ===\n")
        body = OS._qa_section_from_log(log)
        self.assertIn("VERDICT: pass", body)
        self.assertIn("RISK: low", body)
        self.assertNotIn("worker out", body)

    def test_qa_section_none_when_no_gate_run(self):
        log = ("=== 2026-07-15T00:00:00Z dispatch.sh model=a ===\n"
               "worker out\n"
               "=== exit 0 2026-07-15T00:10:00Z ===\n")
        self.assertEqual(OS._qa_section_from_log(log), "")

    def test_note_kv_parse(self):
        self.assertEqual(OS._parse_note_kv("verifier=v risk=low verdict=pass"),
                         {"verifier": "v", "risk": "low", "verdict": "pass"})


class StopIdentityTests(unittest.TestCase):
    """`os stop` must verify a pidfile PID is STILL an opencode worker before
    SIGTERM (Lead gate OS-V1.1 REQUEST-CHANGES, blocking): a recycled PID or a
    pidfile left by a crashed dispatch.sh could point at an unrelated process.
    Both decision paths are tested via an injected cmdline_reader so no real
    /proc is needed."""

    # a pid that is guaranteed not to be a live process on this host; used so the
    # proceed path flows through without a real kill (the bats suite covers the
    # real-SIGTERM black-box path against an opencode-named fake worker).
    _DEAD_PID = 4184303

    def _mkroot(self, pid):
        root = Path(tempfile.mkdtemp(prefix="osstop-"))
        (root / "logs").mkdir()
        (root / "logs" / "T.pid").write_text(str(pid))
        (root / "logs" / "T.log").write_text(
            "=== 2026-07-15T00:00:00Z dispatch.sh model=a ===\nworking\n")
        self.addCleanup(self._cleanup(root))
        return root

    def _cleanup(self, root):
        import shutil
        return lambda: shutil.rmtree(str(root), ignore_errors=True)

    def test_refuses_when_cmdline_not_opencode(self):
        root = self._mkroot(self._DEAD_PID)
        rc = OS.cmd_stop(root, "T", cmdline_reader=lambda pid: "sleep 30")
        self.assertEqual(rc, 1)
        # pidfile is PRESERVED (not removed) and NO stopped footer was appended
        self.assertTrue((root / "logs" / "T.pid").exists())
        self.assertNotIn("=== stopped", (root / "logs" / "T.log").read_text())

    def test_refuses_when_cmdline_unreadable(self):
        root = self._mkroot(self._DEAD_PID)
        rc = OS.cmd_stop(root, "T", cmdline_reader=lambda pid: None)
        self.assertEqual(rc, 1)
        self.assertTrue((root / "logs" / "T.pid").exists())
        self.assertNotIn("=== stopped", (root / "logs" / "T.log").read_text())

    def test_proceeds_when_cmdline_is_opencode(self):
        root = self._mkroot(self._DEAD_PID)
        # identity check passes -> the proceed-path runs: stopped footer is
        # appended + the pidfile is removed + exit 0 (the real SIGTERM is
        # exercised by the bats black-box test against a live opencode process).
        rc = OS.cmd_stop(root, "T",
                         cmdline_reader=lambda pid: "opencode run --model opencode-go/glm-5.2")
        self.assertEqual(rc, 0)
        self.assertFalse((root / "logs" / "T.pid").exists())
        self.assertIn("=== stopped", (root / "logs" / "T.log").read_text())


if __name__ == "__main__":
    # allow `python3 scripts/test/test_status.py` directly (and `python3 -m unittest`)
    sys.path.insert(0, os.path.dirname(__file__))
    unittest.main()