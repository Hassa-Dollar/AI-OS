import os
import tempfile
import unittest
from pathlib import Path

from aios import config

HEAD = 'schema = 1\nname = "p"\n'
COMP = '[[components]]\nname = "app"\npath = "./"\nprofile = "node"\nchecks = ["npm test"]\n'
MIN = HEAD + COMP


def project(text: str) -> Path:
    root = Path(tempfile.mkdtemp())
    (root / ".aios").mkdir()
    (root / ".aios" / "project.toml").write_text(text)
    return root


class ProjectConfig(unittest.TestCase):
    def bad(self, text: str, *needles: str):
        with self.assertRaises(config.ConfigError) as cm:
            config.load_project(project(text))
        for n in ("project.toml", *needles):
            self.assertIn(n, str(cm.exception))

    def test_minimal_defaults(self):
        p = config.load_project(project(MIN))
        self.assertEqual((p.name, p.forge, p.remote, p.default_branch), ("p", "github", "origin", None))
        self.assertEqual(p.components[0].path, "")
        self.assertEqual(p.components[0].checks, ("npm test",))
        self.assertEqual((p.data_collection, p.max_tier, p.frontier_auto), ("deny", "T3", False))
        self.assertEqual((p.router_model, p.escalate_below_confidence), ("clef-flash", 0.6))

    def test_full(self):
        p = config.load_project(project(MIN + '[budget]\nper_task_usd = 2\nper_day_usd = 9.5\n'
                                        '[privacy]\nzdr = true\ndeny_vendors = ["x-ai"]\nmax_tier = "T2"\n'
                                        '[routing]\nfrontier_auto = true\nescalate_below_confidence = 0.5\n'
                                        '[sensitive]\npaths = [".github/"]\n'))
        self.assertEqual((p.per_task_usd, p.per_day_usd, p.zdr, p.deny_vendors), (2.0, 9.5, True, ("x-ai",)))
        self.assertEqual((p.max_tier, p.frontier_auto, p.sensitive_paths), ("T2", True, (".github/",)))

    def test_schema_versions(self):
        self.bad(MIN.replace("schema = 1", "schema = 2"), "upgrade aios")
        self.bad(MIN.replace("schema = 1", "schema = 0"), "aios migrate")
        self.bad(MIN.replace("schema = 1\n", ""), "schema")

    def test_unknown_keys_fail(self):
        self.bad(HEAD + 'owner_role = "x"\n' + COMP, "owner_role")
        self.bad(MIN + '[budget]\nmonthly = 3\n', "monthly")
        self.bad(MIN.replace('profile = "node"', 'profile = "node"\nmodel = "x"'), "model")

    def test_components_required_and_unique(self):
        self.bad('schema = 1\nname = "p"\n', "components")
        self.bad(MIN + '[[components]]\nname = "app"\npath = "api/"\nprofile = "node"\nchecks = ["t"]\n', "unique")

    def test_component_paths(self):
        for bad_path in ("api", "/abs/", "../x/", "a\\\\b/"):
            self.bad(MIN.replace('path = "./"', f'path = "{bad_path}"'), "path")
        self.assertEqual(config.load_project(project(MIN.replace('"./"', '"api/"'))).components[0].path, "api/")

    def test_checks_fail_closed(self):
        self.bad(MIN.replace('["npm test"]', "[]"), "checks_waiver")
        p = config.load_project(project(MIN.replace('["npm test"]', '[]\nchecks_waiver = "docs-only repo"')))
        self.assertEqual(p.components[0].checks, ())

    def test_values_and_types(self):
        self.bad(MIN + '[privacy]\ndata_collection = "maybe"\n', "data_collection")
        self.bad(MIN + '[privacy]\nmax_tier = "T4"\n', "max_tier")
        self.bad(MIN + '[privacy]\nzdr = "yes"\n', "zdr")
        self.bad(MIN + '[privacy]\ndeny_vendors = "x-ai"\n', "deny_vendors")
        self.bad(MIN + '[budget]\nper_task_usd = 0\n', "budget")
        self.bad(MIN + '[routing]\nescalate_below_confidence = 1.5\n', "escalate_below_confidence")
        self.bad(HEAD + 'forge = "gitlab"\n' + COMP, "forge")
        self.bad("schema = 1\nname = \n", "invalid TOML")

    def test_component_for_longest_prefix(self):
        p = config.load_project(project(MIN + '[[components]]\nname = "api"\npath = "api/"\nprofile = "node"\n'
                                        'checks = ["t"]\n'))
        self.assertEqual(p.component_for("api/src/a.ts").name, "api")
        self.assertEqual(p.component_for("README.md").name, "app")

    def test_find_root_walks_up(self):
        root = project(MIN)
        (root / "a" / "b").mkdir(parents=True)
        self.assertEqual(config.find_root(root / "a" / "b"), root.resolve())
        self.assertIsNone(config.find_root(Path(tempfile.mkdtemp())))


class Machine(unittest.TestCase):
    def test_paths_follow_xdg(self):
        p = config.paths({"HOME": "/h", "XDG_CONFIG_HOME": "/c"})
        self.assertEqual((p.config, p.cache, p.credentials), (Path("/c/aios"), Path("/h/.cache/aios"),
                                                              Path("/c/aios/credentials")))

    def test_load_key(self):
        p = config.paths({"HOME": tempfile.mkdtemp()})
        with self.assertRaisesRegex(config.ConfigError, "missing"):
            config.load_key(p)
        p.config.mkdir(parents=True)
        p.credentials.write_text("sk-or-v1-abc\n")
        os.chmod(p.credentials, 0o644)
        with self.assertRaisesRegex(config.ConfigError, "chmod 600"):
            config.load_key(p)
        os.chmod(p.credentials, 0o600)
        self.assertEqual(config.load_key(p), "sk-or-v1-abc")
        p.credentials.write_text("not-a-key")
        with self.assertRaisesRegex(config.ConfigError, "sk-or-"):
            config.load_key(p)

    def test_tests_never_see_real_home(self):
        self.assertIn("aios-tests-", os.environ["HOME"])  # tests/__init__.py redirected it


if __name__ == "__main__":
    unittest.main()
