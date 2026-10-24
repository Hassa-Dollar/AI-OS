"""Tests for the toolchain table (ADR-0035): version parsing, minimum checks and the known set."""
import json
import tempfile
import unittest
from pathlib import Path

from aios import config, toolchains


class VersionOf(unittest.TestCase):
    def test_real_tool_output(self):
        cases = {"v22.23.4": (22, 23, 4),
                 "Python 3.12.3": (3, 12, 3),
                 "cargo 1.82.0 (8f40fc59f 2024-08-21)": (1, 82, 0),
                 "go version go1.23.4 linux/amd64": (1, 23, 4),
                 "PlatformIO Core, version 6.1.16": (6, 1, 16)}
        for text, found in cases.items():
            with self.subTest(text=text):
                self.assertEqual(toolchains.version_of(text), found)

    def test_no_version(self):
        self.assertIsNone(toolchains.version_of("command not found"))
        self.assertIsNone(toolchains.version_of(""))


class Meets(unittest.TestCase):
    def test_one_part_minimum(self):
        self.assertTrue(toolchains.meets((22, 0, 0), "22"))
        self.assertTrue(toolchains.meets((23, 1, 0), "22"))
        self.assertFalse(toolchains.meets((21, 9, 9), "22"))

    def test_two_part_minimum(self):
        self.assertTrue(toolchains.meets((3, 11, 0), "3.11"))
        self.assertTrue(toolchains.meets((3, 12, 3), "3.11"))
        self.assertFalse(toolchains.meets((3, 10, 12), "3.11"))
        self.assertFalse(toolchains.meets((2, 99), "3.11"))

    def test_version_regex(self):
        self.assertTrue(toolchains.VERSION_RE.match("22"))
        self.assertTrue(toolchains.VERSION_RE.match("3.12"))
        for bad in ("v22", "22.", "", "3..11", "1.x"):
            self.assertIsNone(toolchains.VERSION_RE.match(bad), bad)


class Known(unittest.TestCase):
    def test_the_five_known_toolchains(self):
        self.assertEqual(sorted(toolchains.KNOWN), ["go", "node", "platformio", "python", "rust"])
        self.assertEqual(toolchains.KNOWN["node"].version_cmd, ("node", "--version"))
        self.assertEqual(toolchains.KNOWN["node"].default, "22")
        self.assertEqual(toolchains.KNOWN["python"].default, "3.11")
        self.assertEqual(toolchains.KNOWN["platformio"].version_cmd, ("pio", "--version"))


def tree(files: dict[str, str]) -> Path:
    """A throwaway directory holding `files` (relative path -> text); the empty text makes a directory-only file."""
    root = Path(tempfile.mkdtemp(prefix="aios-detect-"))
    for rel, text in files.items():
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).write_text(text)
    return root


PKG = json.dumps({"scripts": {"lint": "eslint .", "typecheck": "tsc", "test": "vitest", "dev": "x"}})


class Detect(unittest.TestCase):
    def test_platformio(self):
        d = toolchains.detect(tree({"platformio.ini": "[env:uno]\nboard = uno\n"}))
        self.assertEqual(d, toolchains.Detected({"platformio": "6"}, [], ["pio run"]))

    def test_platformio_native_env_adds_host_tests(self):
        d = toolchains.detect(tree({"platformio.ini": "[env:uno]\n\n[env:native]\nplatform = native\n"}))
        self.assertEqual(d.checks, ["pio run", "pio test -e native"])

    def test_rust(self):
        d = toolchains.detect(tree({"Cargo.toml": '[package]\nname = "x"\nrust-version = "1.80"\n'}))
        self.assertEqual(d, toolchains.Detected({"rust": "1.80"}, [], ["cargo test"]))

    def test_rust_without_rust_version_uses_default(self):
        d = toolchains.detect(tree({"Cargo.toml": '[package]\nname = "x"\n'}))
        self.assertEqual(d.toolchain, {"rust": "1.75"})

    def test_go(self):
        d = toolchains.detect(tree({"go.mod": "module example.com/x\n\ngo 1.23.0\n"}))
        self.assertEqual(d, toolchains.Detected({"go": "1.23.0"}, [], ["go vet ./...", "go test ./..."]))

    def test_go_without_directive_uses_default(self):
        d = toolchains.detect(tree({"go.mod": "module example.com/x\n"}))
        self.assertEqual(d.toolchain, {"go": "1.22"})

    def test_node_with_lockfile(self):
        d = toolchains.detect(tree({"package.json": PKG.replace("{", '{"engines": {"node": ">=20.6"},', 1),
                                    "package-lock.json": "{}"}))
        self.assertEqual(d, toolchains.Detected({"node": "20.6"}, ["npm ci --no-audit --no-fund"],
                                                ["npm run -s lint", "npm run -s typecheck", "npm run -s test"]))

    def test_node_without_lockfile_has_no_setup(self):
        d = toolchains.detect(tree({"package.json": PKG}))
        self.assertEqual(d.setup, [])
        self.assertEqual(d.toolchain, {"node": "22"})

    def test_node_without_engines_or_scripts(self):
        d = toolchains.detect(tree({"package.json": "{}"}))
        self.assertEqual(d, toolchains.Detected({"node": "22"}, [], []))

    def test_python_from_pyproject(self):
        d = toolchains.detect(tree({"pyproject.toml": '[project]\nrequires-python = ">=3.10,<4"\n'}))
        self.assertEqual(d, toolchains.Detected({"python": "3.10"}, [],
                                                ["python3 -m unittest discover -s tests -t ."]))

    def test_python_without_requires_python_uses_default(self):
        d = toolchains.detect(tree({"pyproject.toml": "[project]\nname = 'x'\n"}))
        self.assertEqual(d.toolchain, {"python": "3.11"})

    def test_python_from_other_markers_and_tests_dir(self):
        for files in ({"setup.py": "x"}, {"requirements.txt": "x"}, {"tests/test_a.py": ""}):
            with self.subTest(files=files):
                d = toolchains.detect(tree(files))
                self.assertEqual(d, toolchains.Detected({"python": "3.11"}, [],
                                                        ["python3 -m unittest discover -s tests -t ."]))

    def test_no_marker(self):
        self.assertEqual(toolchains.detect(tree({"README.md": "x"})), toolchains.Detected({}, [], []))

    def test_broken_cargo_toml_names_the_file(self):
        with self.assertRaises(config.ConfigError) as ctx:
            toolchains.detect(tree({"Cargo.toml": "[package\nname ="}))
        self.assertIn("Cargo.toml", str(ctx.exception))

    def test_broken_package_json_names_the_file(self):
        with self.assertRaises(config.ConfigError) as ctx:
            toolchains.detect(tree({"package.json": "{not json"}))
        self.assertIn("package.json", str(ctx.exception))

    def test_platformio_wins_over_package_json(self):
        d = toolchains.detect(tree({"platformio.ini": "[env:uno]\n", "package.json": PKG}))
        self.assertEqual(d.toolchain, {"platformio": "6"})


class DetectComponents(unittest.TestCase):
    def test_root_marker_is_one_app_component(self):
        comps = toolchains.detect_components(tree({"Cargo.toml": "[package]\n"}))
        self.assertEqual([(n, p) for n, p, _ in comps], [("app", "./")])

    def test_shrink_shaped_monorepo(self):
        root = tree({"components/api/package.json": PKG, "components/api/package-lock.json": "{}",
                     "components/web/package.json": PKG, "components/web/package-lock.json": "{}"})
        comps = toolchains.detect_components(root)
        self.assertEqual([(n, p) for n, p, _ in comps], [("api", "components/api/"), ("web", "components/web/")])
        for _, _, found in comps:
            self.assertEqual(found.setup, ["npm ci --no-audit --no-fund"])
            self.assertEqual(found.checks, ["npm run -s lint", "npm run -s typecheck", "npm run -s test"])

    def test_marker_nested_in_a_component_is_not_a_component(self):
        root = tree({"api/package.json": PKG, "api/web/package.json": PKG})
        self.assertEqual([(n, p) for n, p, _ in toolchains.detect_components(root)], [("api", "api/")])

    def test_same_last_part_gets_joined_relative_paths(self):
        root = tree({"services/api/package.json": PKG, "apps/api/package.json": PKG})
        comps = toolchains.detect_components(root)
        self.assertEqual([(n, p) for n, p, _ in comps],
                         [("apps-api", "apps/api/"), ("services-api", "services/api/")])

    def test_hidden_and_build_directories_are_skipped(self):
        root = tree({".hidden/package.json": PKG, "node_modules/x/package.json": PKG,
                     "dist/app/package.json": PKG, "vendor/lib/go.mod": "module x\n", "app/go.mod": "module y\n"})
        self.assertEqual([(n, p) for n, p, _ in toolchains.detect_components(root)], [("app", "app/")])

    def test_no_component_when_nothing_is_marked(self):
        self.assertEqual(toolchains.detect_components(tree({"docs/readme.md": "x"})), [])


if __name__ == "__main__":
    unittest.main()
