import contextlib
import io
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
        self.assertEqual((p.data_collection, p.models), ("deny", None))
        self.assertEqual((p.router_model, p.escalate_below_confidence), ("clef-flash", 0.6))

    def test_full(self):
        p = config.load_project(project(MIN + '[budget]\nper_task_usd = 2\nper_day_usd = 9.5\n'
                                        '[privacy]\nzdr = true\ndeny_vendors = ["x-ai"]\n'
                                        '[routing]\nescalate_below_confidence = 0.5\n'
                                        '[models]\nlevels = { junior = 30, mid = 35, senior = 40 }\n'
                                        '[sensitive]\npaths = [".github/"]\n'))
        self.assertEqual((p.per_task_usd, p.per_day_usd, p.zdr, p.deny_vendors), (2.0, 9.5, True, ("x-ai",)))
        self.assertEqual((p.escalate_below_confidence, p.sensitive_paths), (0.5, (".github/",)))
        self.assertEqual(p.models, {"levels": {"junior": 30, "mid": 35, "senior": 40}})

    def test_models_table_is_read_raw(self):
        # config passes the table through untouched; catalog.load_policy validates it against the contract.
        text = ('[models]\nlevels = { junior = 40, mid = 45, senior = 52 }\n'
                '[[models.block]]\nmodel = "a/x"\nroles = ["reviewer"]\nreason = "measured"\n')
        self.assertEqual(config.load_project(project(MIN + text)).models["block"][0]["model"], "a/x")

    def test_models_must_be_a_table(self):
        self.bad(HEAD + "models = 3\n" + COMP, "'models' must be a table")

    def test_retired_keys_warn_and_are_ignored(self):
        # ADR-0034 removed the model tiers; old project files keep loading, with one warning per key.
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            p = config.load_project(project(MIN + '[privacy]\nmax_tier = "T2"\n'
                                            '[routing]\nfrontier_auto = true\n'))
        self.assertEqual((p.router_model, p.escalate_below_confidence), ("clef-flash", 0.6))
        lines = err.getvalue().splitlines()
        self.assertEqual(len(lines), 2, err.getvalue())
        self.assertIn("max_tier", lines[0])
        self.assertIn("ADR-0034", lines[0])
        self.assertIn("frontier_auto", lines[1])
        self.assertIn("ADR-0034", lines[1])

    def test_schema_versions(self):
        self.bad(MIN.replace("schema = 1", "schema = 2"), "upgrade aios")
        self.bad(MIN.replace("schema = 1", "schema = 0"), "aios migrate")
        self.bad(MIN.replace("schema = 1\n", ""), "schema")

    def test_unknown_keys_fail(self):
        self.bad(HEAD + 'owner_role = "x"\n' + COMP, "owner_role")
        self.bad(MIN + '[budget]\nmonthly = 3\n', "monthly")
        self.bad(MIN.replace('profile = "node"', 'profile = "node"\nmodel = "x"'), "model")
        self.bad(MIN + '[privacy]\nmax_tier = "T2"\nvendor = "x"\n', "vendor")
        self.bad(MIN + '[routing]\nfrontier_auto = true\nmodel = "x"\n', "model")

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
        self.bad(MIN + '[routing]\nrouter_model = 3\n', "router_model")
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


class MachineConfig(unittest.TestCase):
    """The machine config: <config>/config.toml (architecture/contracts/machine.schema.md)."""

    def setUp(self):
        self.p = config.paths({"HOME": tempfile.mkdtemp()})

    def write(self, text: str) -> None:
        self.p.config.mkdir(parents=True, exist_ok=True)
        config.machine_file(self.p).write_text(text)

    def bad(self, text: str, *needles: str):
        self.write(text)
        with self.assertRaises(config.ConfigError) as cm:
            config.load_machine(self.p)
        for n in ("config.toml", *needles):
            self.assertIn(n, str(cm.exception))

    def test_machine_file_is_config_toml(self):
        self.assertEqual(config.machine_file(self.p), self.p.config / "config.toml")

    def test_missing_file_is_the_default(self):
        self.assertEqual(config.load_machine(self.p), config.Machine())
        self.assertIsNone(config.load_machine(self.p).per_month_usd)

    def test_round_trip(self):
        f = config.save_machine(self.p, config.Machine(20.0))  # also creates the directory
        self.assertEqual(f, config.machine_file(self.p))
        self.assertEqual(f.read_text(), "schema = 1\n\n[budget]\nper_month_usd = 20.0\n")
        self.assertEqual(config.load_machine(self.p), config.Machine(20.0))
        self.assertEqual(config.load_machine(self.p).per_month_usd, 20.0)

    def test_save_without_a_budget(self):
        config.save_machine(self.p, config.Machine())
        self.assertEqual(config.machine_file(self.p).read_text(), "schema = 1\n")
        self.assertEqual(config.load_machine(self.p), config.Machine())

    def test_schema_is_required_and_must_be_one(self):
        self.bad("schema = 2\n", "schema", "upgrade aios")
        self.bad("schema = 0\n", "schema", "migrate")
        self.bad("schema = \"1\"\n", "schema")
        self.bad("[budget]\nper_month_usd = 5\n", "schema")

    def test_unknown_keys_fail(self):
        self.bad('schema = 1\nowner = "x"\n', "owner")
        self.bad("schema = 1\n[budget]\nper_month_usd = 5\nper_day_usd = 1\n", "per_day_usd")
        self.bad("schema = 1\n[budgets]\nper_month_usd = 5\n", "budgets")
        self.bad("schema = 1\nbudget = 5\n", "table")

    def test_per_month_usd_must_be_a_positive_number(self):
        for bad in ("0", "-1", "-0.5", '"20"', "true", "[]"):
            self.bad(f"schema = 1\n[budget]\nper_month_usd = {bad}\n", "per_month_usd")
        self.write("schema = 1\n[budget]\nper_month_usd = 0.01\n")
        self.assertEqual(config.load_machine(self.p).per_month_usd, 0.01)

    def test_invalid_toml(self):
        self.bad("schema = \n", "invalid TOML")


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
