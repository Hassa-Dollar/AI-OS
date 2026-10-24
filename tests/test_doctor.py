import contextlib
import hashlib
import io
import os
import shutil
import subprocess
import tarfile
import tempfile
import unittest
from pathlib import Path
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
    """doctor.run() against the fake server, outside any project; returns (checks, the machine Paths)."""
    p, routes = monthly_env(machine, **key)
    env = {"HOME": home(p), "OLLAMA_HOST": "http://127.0.0.1:9"}
    with fake_http(routes, log) as base:
        checks = doctor.run(env | {"AIOS_OPENROUTER_URL": base}, cwd=Path(tempfile.mkdtemp()))
    return checks, p


def project_dir(toolchain=None, name="app"):
    """A throwaway project whose one component `name` declares `toolchain` (default node = 22)."""
    root = Path(tempfile.mkdtemp())
    (root / ".aios").mkdir()
    table = ", ".join(f'{k} = "{v}"' for k, v in (toolchain or {"node": "22"}).items())
    (root / ".aios" / "project.toml").write_text(
        f'schema = 1\nname = "t"\n\n[[components]]\nname = "{name}"\npath = "./"\n'
        f'toolchain = {{ {table} }}\nchecks = ["true"]\n')
    return root


def completed(stdout="", returncode=0):
    """A fake subprocess.CompletedProcess for a runner."""
    return subprocess.CompletedProcess([], returncode, stdout, "")


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
            return doctor.main(fix=True, ask=ask, cwd=Path(tempfile.mkdtemp())), out.getvalue(), p

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
        self.assertIn("Then set your OpenRouter key's credit limit to that same amount, "
                      "with a monthly reset (https://openrouter.ai/settings/keys).", out)
        self.assertEqual(rc, 0)

    def test_does_not_ask_when_the_budget_is_set(self):
        def ask(prompt):
            raise AssertionError("setup must not ask twice")

        with fixed_home() as p:
            config.save_machine(p, config.Machine(9.0))
            with mock.patch("aios.doctor.harness.installed_version", return_value="1.2.3"), \
                    mock.patch("aios.doctor.run", return_value=[]), contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(doctor.main(fix=True, ask=ask, cwd=Path(tempfile.mkdtemp())), 0)

    def test_no_fix_never_asks(self):
        def ask(prompt):
            raise AssertionError("only --fix asks for the budget")

        with fixed_home() as p, mock.patch("aios.doctor.harness.installed_version", return_value="1.2.3"), \
                mock.patch("aios.doctor.run", return_value=[]), contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(doctor.main(fix=False, ask=ask, cwd=Path(tempfile.mkdtemp())), 0)
        self.assertFalse(config.machine_file(p).exists())

    def test_fix_then_the_budget_check_passes(self):
        prompts = []
        routes = {"/key": (200, {"data": KEY}), "/api/version": (200, {"version": "0.40.7"}),
                  "/api/tags": (200, {"models": [{"name": "clef-flash:latest"}, {"name": "clef:latest"}]})}
        with fake_http(routes) as base:
            with fixed_home({"AIOS_OPENROUTER_URL": base, "OLLAMA_HOST": base}) as p, \
                    mock.patch("aios.doctor.harness.installed_version", return_value="1.2.3"), \
                    contextlib.redirect_stdout(io.StringIO()) as out:
                # the exit code counts every FAIL, and the other checks depend on this machine
                # (bwrap, ollama), so here we assert only the budget: what the fix round is about
                doctor.main(fix=True, ask=fake_ask(["20"], prompts), cwd=Path(tempfile.mkdtemp()))
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


class CheckToolchains(unittest.TestCase):
    def setUp(self):
        self.p = config.paths({"HOME": tempfile.mkdtemp()})

    def check(self, stdout="", returncode=0, root=None, toolchain=None):
        """check_toolchains over a fake runner that answers `stdout`; returns (checks, the commands it ran)."""
        ran = []

        def runner(cmd, **kw):
            ran.append((cmd, kw))
            return completed(stdout, returncode)

        root = root or project_dir(toolchain)
        return doctor.check_toolchains(self.p, root, runner=runner), ran

    def test_pass_for_a_new_enough_version(self):
        checks, ran = self.check("v22.23.4\n")
        self.assertEqual([(c.status, c.name, c.detail) for c in checks],
                         [("PASS", "node (app)", "22.23.4, needs 22 or newer")])
        cmd, kw = ran[0]
        self.assertEqual(cmd[0], "bwrap")
        self.assertEqual(cmd[-2:], ["node", "--version"])
        self.assertEqual((kw["capture_output"], kw["text"], kw["timeout"]), (True, True, 30))
        self.assertIn("--unshare-net", cmd)

    def test_fail_for_an_older_version(self):
        checks, _ = self.check("v20.11.0\n")
        self.assertEqual((checks[0].status, checks[0].detail), ("FAIL", "20.11.0 is older than 22"))
        self.assertEqual(checks[0].fix, "aios doctor --fix")

    def test_fail_when_the_command_cannot_run(self):
        checks, _ = self.check("", returncode=127)
        self.assertEqual((checks[0].status, checks[0].detail), ("FAIL", "not found inside the worker sandbox"))
        self.assertEqual(checks[0].fix, "aios doctor --fix")

    def test_fail_on_a_timeout(self):
        def runner(cmd, **kw):
            raise subprocess.TimeoutExpired(cmd, 30)
        checks = doctor.check_toolchains(self.p, project_dir(), runner=runner)
        self.assertEqual((checks[0].status, checks[0].detail), ("FAIL", "not found inside the worker sandbox"))

    def test_fail_when_bwrap_is_missing(self):
        def runner(cmd, **kw):
            raise FileNotFoundError("bwrap")
        checks = doctor.check_toolchains(self.p, project_dir(), runner=runner)
        self.assertEqual(checks[0].status, "FAIL")

    def test_fail_on_output_with_no_version(self):
        checks, _ = self.check("command not understood\n")
        self.assertEqual((checks[0].status, checks[0].detail), ("FAIL", "not found inside the worker sandbox"))

    def test_names_each_toolchain_by_component(self):
        root = project_dir({"python": "3.11"}, name="tool")
        checks, ran = self.check("Python 3.12.1\n", root=root)
        self.assertEqual([c.name for c in checks], ["python (tool)"])
        self.assertEqual(checks[0].status, "PASS")
        self.assertEqual(ran[0][0][-2:], ["python3", "--version"])

    def test_no_project_means_no_checks(self):
        self.assertEqual(doctor.check_toolchains(self.p, None, runner=None), [])

    def test_run_outside_a_project_adds_nothing(self):
        with mock.patch("aios.doctor.check_toolchains", wraps=doctor.check_toolchains) as spy:
            doctor.run({"HOME": tempfile.mkdtemp(), "AIOS_OPENROUTER_URL": "http://127.0.0.1:9",
                        "OLLAMA_HOST": "http://127.0.0.1:9"}, cwd=Path(tempfile.mkdtemp()))
        self.assertIsNone(spy.call_args.args[1])


class InstallNode(unittest.TestCase):
    def setUp(self):
        self.p = config.paths({"HOME": tempfile.mkdtemp()})
        self.tars = {}
        for arch in ("x64", "arm64"):
            self.tars[arch] = self.tarball(f"node-v22.23.4-linux-{arch}", f"node {arch}".encode())
        self.shasums = "".join(f"{hashlib.sha256(t).hexdigest()}  node-v22.23.4-linux-{a}.tar.xz\n"
                               for a, t in self.tars.items()) + "deadbeef  node-v22.23.4.tar.gz\n"
        self.urls = []

    def tarball(self, folder, body):
        """A .tar.xz holding <folder>/bin/node, with `body` as the file."""
        buf = io.BytesIO()
        with tarfile.open(fileobj=buf, mode="w:xz") as tar:
            info = tarfile.TarInfo(f"{folder}/bin/node")
            info.size = len(body)
            tar.addfile(info, io.BytesIO(body))
        return buf.getvalue()

    def fetch(self, shasums=None, tar=None):
        """A fake fetch serving SHASUMS256.txt and the x64 or arm64 tarball, recording each URL."""
        def fetch(url):
            self.urls.append(url)
            if url.endswith("SHASUMS256.txt"):
                return (shasums or self.shasums).encode()
            return tar if tar is not None else self.tars["x64"]
        return fetch

    def test_picks_the_file_for_each_machine(self):
        bin_ = doctor.install_node(self.p, 22, fetch=self.fetch(), machine=lambda: "x86_64")
        self.assertEqual(self.urls[-1], "https://nodejs.org/dist/latest-v22.x/node-v22.23.4-linux-x64.tar.xz")
        self.assertEqual(bin_, self.p.data / "toolchains" / "node-v22.23.4-linux-x64" / "bin")
        self.urls.clear()
        doctor.install_node(fresh_paths(self.p), 22, fetch=self.fetch(tar=self.tars["arm64"]),
                            machine=lambda: "aarch64")
        self.assertEqual(self.urls[-1], "https://nodejs.org/dist/latest-v22.x/node-v22.23.4-linux-arm64.tar.xz")

    def test_unpacks_under_toolchains_and_returns_bin(self):
        bin_ = doctor.install_node(self.p, 22, fetch=self.fetch(), machine=lambda: "x86_64")
        self.assertEqual((bin_ / "node").read_bytes(), b"node x64")
        self.assertEqual([x.name for x in (self.p.data / "toolchains").iterdir()], ["node-v22.23.4-linux-x64"])

    def test_checksum_mismatch_raises_and_leaves_nothing(self):
        bad = self.shasums.replace(hashlib.sha256(self.tars["x64"]).hexdigest(), "0" * 64)
        with self.assertRaises(config.ConfigError):
            doctor.install_node(self.p, 22, fetch=self.fetch(shasums=bad), machine=lambda: "x86_64")
        tc = self.p.data / "toolchains"
        self.assertFalse(tc.exists() and any(tc.iterdir()), "a failed install left files behind")

    def test_existing_folder_skips_the_download(self):
        dest = self.p.data / "toolchains" / "node-v22.23.4-linux-x64" / "bin"
        dest.mkdir(parents=True)
        bin_ = doctor.install_node(self.p, 22, fetch=self.fetch(), machine=lambda: "x86_64")
        self.assertEqual(bin_, dest)
        self.assertTrue(all(u.endswith("SHASUMS256.txt") for u in self.urls))

    def test_unknown_machine_raises(self):
        with self.assertRaises(config.ConfigError):
            doctor.install_node(self.p, 22, fetch=self.fetch(), machine=lambda: "riscv64")
        self.assertEqual(self.urls, [])

    def test_no_build_for_the_major_raises(self):
        with self.assertRaises(config.ConfigError):
            doctor.install_node(self.p, 99, fetch=self.fetch(shasums="x  node-v1.0.0.tar.gz\n"),
                                machine=lambda: "x86_64")


def fresh_paths(p):
    """The same Paths, with a new HOME, so a second install starts from nothing."""
    return config.paths({"HOME": tempfile.mkdtemp()})


class FixInstallsNode(unittest.TestCase):
    def test_fix_installs_node_and_checks_again(self):
        failing = [doctor.Check("FAIL", "node (app)", "not found inside the worker sandbox", "aios doctor --fix")]
        passing = [doctor.Check("PASS", "node (app)", "22.23.4, needs 22 or newer")]
        root = project_dir()
        with fixed_home(), mock.patch("aios.doctor.harness.installed_version", return_value="1.2.3"), \
                mock.patch("aios.doctor.run", side_effect=[failing, passing]) as run, \
                mock.patch("aios.doctor.install_node") as install, contextlib.redirect_stdout(io.StringIO()) as out:
            want = config.paths()
            rc = doctor.main(fix=True, ask=fake_ask(["20"], []), cwd=root)
        install.assert_called_once_with(want, 22)
        self.assertEqual(run.call_count, 2)
        self.assertIn(f"installing Node 22 into {want.data / 'toolchains'}...", out.getvalue())
        self.assertIn("PASS  node (app)", out.getvalue())
        self.assertEqual(rc, 0)

    def test_no_fix_installs_nothing(self):
        failing = [doctor.Check("FAIL", "node (app)", "not found inside the worker sandbox", "aios doctor --fix")]
        with fixed_home(), mock.patch("aios.doctor.harness.installed_version", return_value="1.2.3"), \
                mock.patch("aios.doctor.run", return_value=failing), mock.patch("aios.doctor.install_node") as install, \
                contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(doctor.main(fix=False, ask=fake_ask([], []), cwd=project_dir()), 1)
        install.assert_not_called()


if __name__ == "__main__":
    unittest.main()
