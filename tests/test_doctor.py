import os
import shutil
import tempfile
import unittest
from unittest import mock

from aios import config, doctor
from tests.helpers import fake_http


def key_env(limit):
    home = tempfile.mkdtemp()
    p = config.paths({"HOME": home})
    p.config.mkdir(parents=True)
    p.credentials.write_text("sk-or-v1-test")
    os.chmod(p.credentials, 0o600)
    return p, {"/key": (200, {"data": {"limit": limit, "limit_remaining": 39.5}})}


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
