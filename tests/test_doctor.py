import contextlib
import io
import os
import shutil
import tempfile
import unittest
from unittest import mock

from aios import config, doctor
from tests.helpers import fake_http

PROMPT = "How much do you want to spend per month on models, in USD? "
KEY = {"limit": 20.0, "limit_remaining": 16.5, "limit_reset": "monthly", "usage_monthly": 3.5}


def key_env(limit):
    home = tempfile.mkdtemp()
    p = config.paths({"HOME": home})
    p.config.mkdir(parents=True)
    p.credentials.write_text("sk-or-v1-test")
    os.chmod(p.credentials, 0o600)
    return p, {"/key": (200, {"data": {"limit": limit, "limit_remaining": 39.5}})}


def monthly_env(machine=20.0, **key):
    """A throwaway HOME with a machine budget of `machine` USD, and the /key route the checks read."""
    home = tempfile.mkdtemp()
    p = config.paths({"HOME": home})
    p.config.mkdir(parents=True)
    p.credentials.write_text("sk-or-v1-test")
    os.chmod(p.credentials, 0o600)
    if machine is not None:
        config.save_machine(p, config.Machine(machine))
    return p, {"/key": (200, {"data": KEY | key})}


def doctor_run(machine=20.0, log=None, **key):
    """doctor.run() against the fake server; returns (checks, the machine Paths)."""
    p, routes = monthly_env(machine, **key)
    env = {"HOME": home(p), "OLLAMA_HOST": "http://127.0.0.1:9"}
    with fake_http(routes, log) as base:
        checks = doctor.run(env | {"AIOS_OPENROUTER_URL": base})
    return checks, p


def home(p):
    return str(p.config.parent.parent)


def named(checks, name):
    return [c for c in checks if c.name == name][0]


def fake_ask(answers, prompts):
    """An `ask` that hands out `answers` in order and records every prompt."""
    it = iter(answers)
    return lambda prompt: (prompts.append(prompt), next(it))[1]


@contextlib.contextmanager
def fixed_home(env=None):
    """A throwaway HOME (and config dir) for the doctor's own `config.paths()`; yields its Paths."""
    h = tempfile.mkdtemp()
    with mock.patch.dict(os.environ, {"HOME": h, "XDG_CONFIG_HOME": f"{h}/.config", **(env or {})}):
        p = config.paths({"HOME": h})
        p.config.mkdir(parents=True)
        p.credentials.write_text("sk-or-v1-test")
        os.chmod(p.credentials, 0o600)
        yield p


class MonthlyBudget(unittest.TestCase):
    def test_pass(self):
        checks, p = doctor_run()
        c = named(checks, "monthly budget")
        self.assertEqual((c.status, c.detail), ("PASS", "$3.50 of $20.00 spent this month"))

    def test_fail_without_a_budget(self):
        checks, p = doctor_run(machine=None)
        c = named(checks, "monthly budget")
        self.assertEqual((c.status, c.detail, c.fix), ("FAIL", "no monthly budget is set", "run 'aios doctor --fix'"))

    def test_warn_on_a_different_limit(self):
        checks, p = doctor_run(limit=35.0)
        c = named(checks, "monthly budget")
        self.assertEqual(c.status, "WARN")
        self.assertIn("$20.00", c.detail)
        self.assertIn("35.0", c.detail)
        self.assertEqual(c.fix, "set the key's limit to $20.0 with a monthly reset")

    def test_warn_on_the_reset_period(self):
        for reset in ("weekly", "daily", None):
            checks, p = doctor_run(limit_reset=reset)
            c = named(checks, "monthly budget")
            self.assertEqual(c.status, "WARN", c)
            self.assertIn(reset or "never", c.detail)
            self.assertIn("monthly reset", c.fix)

    def test_warn_on_a_key_without_a_limit(self):
        checks, p = doctor_run(limit=None)
        self.assertEqual(named(checks, "monthly budget").status, "WARN")

    def test_run_makes_one_key_request(self):
        log = []
        checks, p = doctor_run(log=log)
        self.assertEqual([(m, path) for m, path, _ in log], [("GET", "/key")])
        self.assertEqual([c.name for c in checks][:5], ["python", "git", "gh", "openrouter key", "monthly budget"])

    def test_check_key_reuses_a_fetched_response(self):
        p, routes = monthly_env()
        log = []
        with fake_http(routes, log) as base:
            d, err = doctor.fetch_key(p, base)
            c = doctor.check_key(p, base, d)
        self.assertEqual([(m, path) for m, path, _ in log], [("GET", "/key")])
        self.assertIsNone(err)
        self.assertEqual(c.status, "PASS")


class FirstSetup(unittest.TestCase):
    def run_fix(self, ask, env=None):
        """`aios doctor --fix` with the harness already installed and no checks; returns (exit code, stdout)."""
        with fixed_home(env) as p, mock.patch("aios.doctor.harness.installed_version", return_value="1.2.3"), \
                mock.patch("aios.doctor.run", return_value=[]), contextlib.redirect_stdout(io.StringIO()) as out:
            return doctor.main(fix=True, ask=ask), out.getvalue(), p

    def test_asks_once_saves_and_tells(self):
        prompts = []
        rc, out, p = self.run_fix(fake_ask(["20"], prompts))
        self.assertEqual(prompts, [PROMPT])
        self.assertEqual(config.load_machine(p).per_month_usd, 20.0)
        self.assertIn("Now set your OpenRouter key's credit limit to $20.0 with a monthly reset "
                      "(https://openrouter.ai/settings/keys). aios reads that limit to know what is left this month.",
                      out)
        self.assertEqual(rc, 0)

    def test_reasks_until_the_answer_is_a_positive_number(self):
        prompts = []
        rc, out, p = self.run_fix(fake_ask(["0", "nope", "-2", "7.5"], prompts))
        self.assertEqual(prompts, [PROMPT] * 4)
        self.assertEqual(config.load_machine(p).per_month_usd, 7.5)
        self.assertIn("positive number", out)

    def test_without_a_terminal_it_tells_how_to_write_the_file(self):
        prompts = []

        def ask(prompt):
            prompts.append(prompt)
            raise EOFError

        rc, out, p = self.run_fix(ask)
        self.assertEqual(prompts, [PROMPT])
        self.assertFalse(config.machine_file(p).exists())
        self.assertIn(f"Write {config.machine_file(p)} by hand", out)
        self.assertIn("per_month_usd = 20.0", out)
        self.assertIn("monthly reset", out)
        self.assertEqual(rc, 0)

    def test_does_not_ask_when_the_budget_is_set(self):
        def ask(prompt):
            raise AssertionError("setup must not ask twice")

        with fixed_home() as p:
            config.save_machine(p, config.Machine(9.0))
            with mock.patch("aios.doctor.harness.installed_version", return_value="1.2.3"), \
                    mock.patch("aios.doctor.run", return_value=[]), contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(doctor.main(fix=True, ask=ask), 0)

    def test_no_fix_never_asks(self):
        def ask(prompt):
            raise AssertionError("only --fix asks for the budget")

        with fixed_home() as p, mock.patch("aios.doctor.harness.installed_version", return_value="1.2.3"), \
                mock.patch("aios.doctor.run", return_value=[]), contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(doctor.main(fix=False, ask=ask), 0)
        self.assertFalse(config.machine_file(p).exists())

    def test_fix_then_the_budget_check_passes(self):
        prompts = []
        routes = {"/key": (200, {"data": KEY}), "/api/version": (200, {"version": "0.40.7"}),
                  "/api/tags": (200, {"models": [{"name": "clef-flash:latest"}, {"name": "clef:latest"}]})}
        with fake_http(routes) as base:
            with fixed_home({"AIOS_OPENROUTER_URL": base, "OLLAMA_HOST": base}) as p, \
                    mock.patch("aios.doctor.harness.installed_version", return_value="1.2.3"), \
                    contextlib.redirect_stdout(io.StringIO()) as out:
                rc = doctor.main(fix=True, ask=fake_ask(["20"], prompts))
        self.assertEqual(rc, 0, out.getvalue())
        self.assertEqual(config.load_machine(p).per_month_usd, 20.0)
        self.assertIn("PASS  monthly budget", out.getvalue())
        self.assertIn("$3.50 of $20.00 spent this month", out.getvalue())


class Doctor(unittest.TestCase):
    def test_windows_shadowing(self):
        self.assertTrue(doctor.windows_shadowed("/mnt/c/Program Files/nodejs/npm"))
        self.assertFalse(doctor.windows_shadowed("/usr/bin/npm"))
        self.assertFalse(doctor.windows_shadowed(None))
        with mock.patch("aios.doctor.shutil.which", return_value="/mnt/c/x/npm"):
            self.assertEqual(doctor.check_tool("npm", True, "").status, "FAIL")
        with mock.patch("aios.doctor.shutil.which", return_value=None):
            self.assertEqual(doctor.check_tool("gh", False, "").status, "WARN")

    def test_version_tuple(self):
        self.assertEqual(doctor.version_tuple("0.40.7"), (0, 40, 7))
        self.assertEqual(doctor.version_tuple("v0.35.1-rc2"), (0, 35, 1))
        self.assertEqual(doctor.version_tuple("dev"), (0, 0, 0))

    def test_key_with_limit_passes(self):
        p, routes = key_env(40)
        with fake_http(routes) as base:
            c = doctor.check_key(p, base)
        self.assertEqual(c.status, "PASS", c)
        self.assertIn("39.5", c.detail)

    def test_key_without_limit_fails(self):
        p, routes = key_env(None)
        with fake_http(routes) as base:
            c = doctor.check_key(p, base)
        self.assertEqual(c.status, "FAIL")
        self.assertIn("credit limit", c.fix)

    def test_key_rejected_or_missing(self):
        p, _ = key_env(40)
        with fake_http({"/key": (401, {"error": "no"})}) as base:
            self.assertIn("HTTP 401", doctor.check_key(p, base).detail)
        empty = config.paths({"HOME": tempfile.mkdtemp()})
        self.assertEqual(doctor.check_key(empty, "http://127.0.0.1:9").status, "FAIL")

    def test_ollama(self):
        tags = {"models": [{"name": "clef-flash:latest"}, {"name": "clef:latest"}]}
        with fake_http({"/api/version": (200, {"version": "0.40.7"}), "/api/tags": (200, tags)}) as base:
            self.assertEqual([c.status for c in doctor.check_ollama(base)], ["PASS", "PASS", "PASS"])
        with fake_http({"/api/version": (200, {"version": "0.40.7"}),
                        "/api/tags": (200, {"models": [{"name": "clef-flash:latest"}]})}) as base:
            self.assertEqual([c.status for c in doctor.check_ollama(base)], ["PASS", "PASS", "WARN"])
        with fake_http({"/api/version": (200, {"version": "0.30.0"}), "/api/tags": (200, tags)}) as base:
            self.assertEqual(doctor.check_ollama(base)[0].status, "FAIL")
        self.assertEqual(doctor.check_ollama("http://127.0.0.1:9")[0].status, "FAIL")

    def test_sandbox_missing_bwrap(self):
        with mock.patch("aios.doctor.shutil.which", return_value=None):
            c = doctor.check_sandbox(config.paths({"HOME": "/h"}))
        self.assertEqual((c.status, c.fix), ("FAIL", "sudo apt install bubblewrap"))

    @unittest.skipUnless(os.environ.get("AIOS_TEST_SANDBOX") and shutil.which("bwrap"), "set AIOS_TEST_SANDBOX=1")
    def test_sandbox_probe_real(self):
        home = tempfile.mkdtemp()
        p = config.paths({"HOME": home})
        p.config.mkdir(parents=True)
        self.assertEqual(doctor.check_sandbox(p).status, "PASS")


if __name__ == "__main__":
    unittest.main()
