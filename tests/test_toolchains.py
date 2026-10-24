"""Tests for the toolchain table (ADR-0035): version parsing, minimum checks and the known set."""
import unittest

from aios import toolchains


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


if __name__ == "__main__":
    unittest.main()
