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


if __name__ == "__main__":
    # allow `python3 scripts/test/test_status.py` directly (and `python3 -m unittest`)
    sys.path.insert(0, os.path.dirname(__file__))
    unittest.main()