"""The toolchains a component may declare (ADR-0035): their version commands, defaults and fixes.

Sections:
  1. Known toolchains   the five names aios knows -> KNOWN, each with its version command and fix
  2. Versions           a version command's output -> a tuple of ints; a declared minimum -> a yes or no
"""
from __future__ import annotations

import re
from dataclasses import dataclass


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
