import json
import os
import pwd
import shutil
import subprocess
import tempfile
import textwrap
import unittest
from pathlib import Path

from aios import config, harness

FAKE_PYTHON = """#!/usr/bin/env python3
import json
print(json.dumps("Please solve this issue: {{task}}\\n\\nUse bash."))
"""
# A stand-in for mini-swe-agent: checks how it was invoked, edits the workspace, writes a trajectory.
FAKE_MINI = """#!/usr/bin/env python3
import json, os, sys
argv = sys.argv[1:]
cfg = json.load(open(argv[argv.index("-c", argv.index("-c") + 1) + 1]))
out = argv[argv.index("-o") + 1]
ws = cfg["environment"]["cwd"]
json.dump({"argv": argv, "key": os.environ.get("OPENROUTER_API_KEY"), "configured": os.environ.get("MSWEA_CONFIGURED"),
           "template": cfg["agent"]["instance_template"], "wrapper": cfg["environment"]["wrapper_args"],
           "model": cfg["model"]}, open(os.path.join(os.path.dirname(out), "seen.json"), "w"))
open(os.path.join(ws, "fixed.txt"), "w").write("done\\n")
for junk in ("__pycache__/m.cpython-314.pyc", "pkg/__pycache__/n.pyc", "node_modules/x/index.js", "loose.pyc"):
    os.makedirs(os.path.dirname(os.path.join(ws, junk)) or ws, exist_ok=True)
    open(os.path.join(ws, junk), "w").write("cache")  # a worker that ran tests leaves build caches behind
here = os.path.dirname(os.path.abspath(__file__))  # the harness passes no extra env, so overrides live in files
override = lambda name, default: open(os.path.join(here, name)).read() if os.path.exists(os.path.join(here, name)) else default
status, final = override("fake_exit", "Submitted"), override("fake_final", "I fixed it.")
json.dump({"info": {"exit_status": status, "submission": "", "model_stats": {"instance_cost": 0.0123, "api_calls": 7}},
           "messages": [{"role": "user", "content": "task"}, {"role": "assistant", "content": final}]}, open(out, "w"))
"""


def fake_harness(p: config.Paths) -> None:
    site = harness.home(p) / "lib" / "python3.99" / "site-packages"
    (site / "minisweagent" / "config").mkdir(parents=True, exist_ok=True)
    (site / "minisweagent" / "config" / "mini.yaml").write_text("agent: {}\n")
    (site / "mini_swe_agent-2.4.6.dist-info").mkdir(exist_ok=True)
    (harness.home(p) / "bin").mkdir(parents=True, exist_ok=True)
    for name, body in (("python", FAKE_PYTHON), ("mini", FAKE_MINI)):
        f = harness.home(p) / "bin" / name
        f.write_text(body)
        f.chmod(0o755)


class Sandbox(unittest.TestCase):
    def test_worker_has_no_network_and_own_pids(self):
        p = config.paths({"HOME": tempfile.mkdtemp()})
        args, env = harness.sandbox(p, network=False)
        self.assertIn("--unshare-net", args)
        self.assertIn("--unshare-pid", args)
        self.assertNotIn("/mnt/wsl/resolv.conf", args)
        self.assertEqual(env["HOME"], "/tmp")
        self.assertIn("--clearenv", args)  # bwrap would otherwise pass the harness's API key through
        self.assertLess(args.index("--clearenv"), args.index("--setenv"))

    def test_setup_gets_dns_and_toolchains(self):
        p = config.paths({"HOME": tempfile.mkdtemp()})
        (p.data / "toolchains" / "node22" / "bin").mkdir(parents=True)
        args, env = harness.sandbox(p, network=True)
        self.assertNotIn("--unshare-net", args)
        self.assertIn("/mnt/wsl/resolv.conf", args)
        self.assertIn(str(p.data / "toolchains"), args)
        self.assertTrue(env["PATH"].startswith(str((p.data / "toolchains" / "node22" / "bin").resolve())))

    @unittest.skipUnless(os.environ.get("AIOS_TEST_SANDBOX") and shutil.which("bwrap"), "set AIOS_TEST_SANDBOX=1")
    def test_seeded_escapes_fail_for_real(self):
        p = config.paths({"HOME": tempfile.mkdtemp()})
        ws = Path(tempfile.mkdtemp())
        real_home = pwd.getpwuid(os.getuid()).pw_dir
        args, env = harness.sandbox(p, network=False)
        probe = textwrap.dedent(f"""
            test ! -e {real_home} || echo ESCAPE:home
            (exec 3<>/dev/tcp/1.1.1.1/443) 2>/dev/null && echo ESCAPE:network
            test ! -e /proc/{os.getpid()} || echo ESCAPE:host-pids
            touch /usr/aios-probe 2>/dev/null && echo ESCAPE:system-write
            env | grep -qi openrouter && echo ESCAPE:key-in-env
            touch ./inside && echo OK:workspace-writable
        """)
        planted = dict(os.environ, OPENROUTER_API_KEY="sk-or-v1-planted")  # gitleaks:allow (fake key; must not leak)
        r = subprocess.run(["bwrap", *args, "--bind", str(ws), str(ws), "--chdir", str(ws), "bash", "-c", probe],
                           env=planted, capture_output=True, text=True, timeout=30)
        self.assertNotIn("ESCAPE", r.stdout, r.stdout + r.stderr)
        self.assertIn("OK:workspace-writable", r.stdout, r.stderr)


class Parse(unittest.TestCase):
    def traj(self, status, final="done", submission=""):
        f = Path(tempfile.mkdtemp()) / "traj.json"
        f.write_text(json.dumps({"info": {"exit_status": status, "submission": submission,
                                          "model_stats": {"instance_cost": 0.5, "api_calls": 12}},
                                 "messages": [{"role": "assistant", "content": final}]}))
        return harness.parse(f, "m/x", 30, "mini-swe-agent 2.4.6")

    def test_exit_kinds(self):
        a = self.traj("Submitted")
        self.assertEqual((a.exit, a.usd, a.steps, a.secs), ("submitted", 0.5, 12, 30))
        self.assertEqual(self.traj("LimitsExceeded").exit, "limits")
        self.assertEqual(self.traj("OpenRouterAPIError").exit, "infra")  # 402/5xx never count against a model
        self.assertEqual(self.traj("RuntimeError").exit, "error")
        esc = self.traj("Submitted", final="Cannot proceed.\nESCALATE: the contract must change first")
        self.assertEqual((esc.exit, esc.summary), ("escalated", "ESCALATE: the contract must change first"))
        missing = harness.parse(Path(tempfile.mkdtemp()) / "none.json", "m/x", 1, "v")
        self.assertEqual(missing.exit, "infra")


class Run(unittest.TestCase):
    def test_task_travels_in_config_not_argv_and_key_stays_outside(self):
        p = config.paths({"HOME": tempfile.mkdtemp()})
        fake_harness(p)
        ws, run_dir = Path(tempfile.mkdtemp()), Path(tempfile.mkdtemp()) / "run"
        task = "Fix the parser. ESC-MARKER {{ not jinja }} $dollar"
        a = harness.run(p, ws, "z-ai/glm-5.3", task, key="sk-or-v1-secret", run_dir=run_dir,
                        privacy={"data_collection": "deny"}, cost_limit=0.5)
        self.assertEqual((a.exit, a.steps, a.usd, a.harness), ("submitted", 7, 0.0123, "mini-swe-agent 2.4.6"))
        seen = json.loads((run_dir / "seen.json").read_text())
        self.assertNotIn("ESC-MARKER", " ".join(seen["argv"]))  # lesson #1
        self.assertIn("{% raw %}" + task + "{% endraw %}", seen["template"])
        self.assertEqual((seen["key"], seen["configured"]), ("sk-or-v1-secret", "true"))
        self.assertIn("--unshare-net", seen["wrapper"])
        self.assertEqual(seen["model"]["model_kwargs"], {"provider": {"data_collection": "deny"}})
        self.assertTrue((ws / "fixed.txt").exists())

    def test_missing_harness_is_reported(self):
        p = config.paths({"HOME": tempfile.mkdtemp()})
        self.assertIsNone(harness.installed_version(p))
        with self.assertRaises(harness.HarnessError):
            harness.run(p, Path(tempfile.mkdtemp()), "m/x", "t", key="k", run_dir=Path(tempfile.mkdtemp()),
                        privacy={}, cost_limit=1.0)


if __name__ == "__main__":
    unittest.main()
