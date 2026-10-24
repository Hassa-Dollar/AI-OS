"""The toolchains a component may declare (ADR-0035): their version commands, defaults, fixes and detection.

Sections:
  1. Known toolchains   the five names aios knows -> KNOWN, each with its version command and fix
  2. Versions           a version command's output -> a tuple of ints; a declared minimum -> a yes or no
  3. Detection          a repo's marker files -> the toolchain table, setup and checks, per component
"""
from __future__ import annotations

import json
import re
import tomllib
from dataclasses import dataclass
from pathlib import Path

from . import config


# --- 1. Known toolchains ----------------------------------------------------------------
# From: nothing (constants)
# To:   config (which names and minimums are legal), cli (init's defaults), doctor (version commands and fixes)

@dataclass(frozen=True)
class Toolchain:
    """One known toolchain: its name, the command that prints its version, its default minimum and its fix."""
    name: str
    version_cmd: tuple[str, ...]  # prints the version; run inside the worker sandbox
    default: str                  # the minimum `aios init` proposes when the repo names none
    fix: str                      # how the operator installs it when aios cannot


KNOWN: dict[str, Toolchain] = {t.name: t for t in (
    Toolchain("node", ("node", "--version"), "22", "aios doctor --fix"),
    Toolchain("python", ("python3", "--version"), "3.11", "sudo apt install python3"),
    Toolchain("rust", ("cargo", "--version"), "1.75",
              "sudo apt install rustc cargo (rustup's ~/.cargo is invisible to workers)"),
    Toolchain("go", ("go", "version"), "1.22", "sudo apt install golang-go"),
    Toolchain("platformio", ("pio", "--version"), "6",
              "install PlatformIO Core where workers can see it, e.g. /usr/local/bin/pio"),
)}

VERSION_RE = re.compile(r"^\d+(\.\d+)*$")   # the shape of a declared minimum


# --- 2. Versions ------------------------------------------------------------------------
# From: a version command's output (text), or a found version and a declared minimum
# To:   the version as ints (None when the text has none), or whether the found version meets the minimum

def version_of(text: str) -> tuple[int, ...] | None:
    """Return the first run of digits and dots in `text` as a tuple of ints, or None when there is none."""
    m = re.search(r"\d+(?:\.\d+)*", text)
    return tuple(int(x) for x in m.group().split(".")) if m else None


def meets(found: tuple[int, ...], minimum: str) -> bool:
    """True when the `found` version is at least the dotted `minimum` (for example "3.11")."""
    return found >= tuple(int(x) for x in minimum.split("."))


# --- 3. Detection -----------------------------------------------------------------------
# From: a repo root's (or a component directory's) marker files and their fields
# To:   a Detected (toolchain table, setup, checks) per directory, or a ConfigError naming an unreadable file

PYTHON_FILES = ("pyproject.toml", "setup.py", "requirements.txt")
MARKER_FILES = ("platformio.ini", "Cargo.toml", "go.mod", "package.json") + PYTHON_FILES
SKIPPED_DIRS = {"node_modules", "vendor", "target", "dist", "build"}   # never a component, nor searched


@dataclass(frozen=True)
class Detected:
    """What a directory's markers propose: its toolchain table, its setup commands and its checks."""
    toolchain: dict[str, str]
    setup: list[str]
    checks: list[str]


def detect(root: Path) -> Detected:
    """Read the first marker that exists at `root` and propose its toolchain, setup and checks; empty when none."""
    if (root / "platformio.ini").is_file():
        return _platformio(root)
    if (root / "Cargo.toml").is_file():
        return _rust(root)
    if (root / "go.mod").is_file():
        return _go(root)
    if (root / "package.json").is_file():
        return _node(root)
    if _python_marked(root):
        return _python(root)
    return Detected({}, [], [])


def detect_components(root: Path) -> list[tuple[str, str, Detected]]:
    """Return (name, path, detected) per component, sorted by path; one "app" at "./" when root is marked."""
    if _marked(root):
        return [("app", "./", detect(root))]
    dirs = []
    for top in _subdirs(root):
        if _marked(top):
            dirs.append(top)
        else:
            dirs.extend(sub for sub in _subdirs(top) if _marked(sub))
    found = []
    for d in dirs:
        rel = d.relative_to(root)
        name = d.name if [x.name for x in dirs].count(d.name) == 1 else "-".join(rel.parts)
        found.append((name, rel.as_posix() + "/", detect(d)))
    return sorted(found, key=lambda c: c[1])


def _marked(d: Path) -> bool:
    """True when directory `d` holds a marker file or a tests/ directory."""
    return any((d / m).is_file() for m in MARKER_FILES) or (d / "tests").is_dir()


def _python_marked(d: Path) -> bool:
    """True when `d` holds a Python marker: pyproject.toml, setup.py, requirements.txt or tests/."""
    return any((d / m).is_file() for m in PYTHON_FILES) or (d / "tests").is_dir()


def _subdirs(d: Path) -> list[Path]:
    """The visible subdirectories of `d` that are not skipped build or vendor folders, sorted by name."""
    return sorted(p for p in d.iterdir() if p.is_dir() and not p.name.startswith(".") and p.name not in SKIPPED_DIRS)


def _load(path: Path, parse):
    """Parse the file at `path` with `parse`; raise ConfigError naming the file when it cannot be parsed."""
    try:
        return parse(path.read_text(encoding="utf-8"))
    except ValueError as e:
        raise config.ConfigError(f"{path}: cannot parse: {e}") from e


def _field(data, *keys):
    """The value at the nested `keys` of `data`, or None when a key or table is missing."""
    for k in keys:
        if not isinstance(data, dict):
            return None
        data = data.get(k)
    return data


def _version(value, default: str) -> str:
    """The first run of digits and dots in `value` (for example ">=20.6" -> "20.6"), or `default` when none."""
    m = re.search(r"\d+(?:\.\d+)*", str(value or ""))
    return m.group() if m else default


def _platformio(root: Path) -> Detected:
    """PlatformIO: its default version, `pio run`, and `pio test -e native` when [env:native] exists."""
    text = (root / "platformio.ini").read_text(encoding="utf-8")
    checks = ["pio run"] + (["pio test -e native"] if re.search(r"^\[env:native\]\s*$", text, re.M) else [])
    return Detected({"platformio": KNOWN["platformio"].default}, [], checks)


def _rust(root: Path) -> Detected:
    """Rust: the [package] rust-version as the minimum, and `cargo test`; no setup (ADR-0035)."""
    data = _load(root / "Cargo.toml", tomllib.loads)
    return Detected({"rust": _version(_field(data, "package", "rust-version"), KNOWN["rust"].default)}, [],
                    ["cargo test"])


def _go(root: Path) -> Detected:
    """Go: the `go` directive as the minimum, and `go vet` and `go test`; no setup (ADR-0035)."""
    m = re.search(r"^go\s+(\S+)", (root / "go.mod").read_text(encoding="utf-8"), re.M)
    return Detected({"go": _version(m.group(1) if m else "", KNOWN["go"].default)}, [],
                    ["go vet ./...", "go test ./..."])


def _node(root: Path) -> Detected:
    """Node: engines.node as the minimum; `npm ci` only with a lockfile; the lint, typecheck and test scripts."""
    pkg = _load(root / "package.json", json.loads)
    if not isinstance(pkg, dict):
        raise config.ConfigError(f"{root / 'package.json'}: must be a JSON object")
    scripts = pkg.get("scripts") or {}
    setup = ["npm ci --no-audit --no-fund"] if (root / "package-lock.json").is_file() else []
    checks = [f"npm run -s {s}" for s in ("lint", "typecheck", "test") if s in scripts]
    return Detected({"node": _version(_field(pkg, "engines", "node"), KNOWN["node"].default)}, setup, checks)


def _python(root: Path) -> Detected:
    """Python: [project] requires-python as the minimum, and the stdlib unittest discovery; no setup."""
    pyproject = root / "pyproject.toml"
    data = _load(pyproject, tomllib.loads) if pyproject.is_file() else {}
    return Detected({"python": _version(_field(data, "project", "requires-python"), KNOWN["python"].default)}, [],
                    ["python3 -m unittest discover -s tests -t ."])
