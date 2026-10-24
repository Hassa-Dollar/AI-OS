"""Machine and project configuration (contracts: project.schema.md, machine.schema.md, ADR-0030).

Sections:
  1. Paths and the key   XDG environment -> Paths; the credentials file -> the OpenRouter key
  2. Project settings    the Component and Project dataclasses, field helpers, .aios/project.toml -> Project
  3. The machine config  <config>/config.toml -> Machine, the operator's monthly budget
"""
from __future__ import annotations

import os
import stat
import sys
import tomllib
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path

from . import toolchains

SCHEMA = 1
FORGES = ("github", "local")


class ConfigError(ValueError):
    """A configuration file is missing or invalid. The message names the file and the problem."""


# --- 1. Paths and the key ---------------------------------------------------------------
# From: the environment (HOME and the XDG variables) and ~/.config/aios/credentials
# To:   Paths, which every other module takes; the key, for the gateway, the doctor, the budget


@dataclass(frozen=True)
class Paths:
    """One instance holds the four aios directories: config, cache, state and data."""
    config: Path
    cache: Path
    state: Path
    data: Path

    @property
    def credentials(self) -> Path:
        """The credentials file: <config>/credentials."""
        return self.config / "credentials"


def paths(env: Mapping[str, str] = os.environ) -> Paths:
    """Resolve the four aios directories from `env` (HOME and the XDG variables); return Paths."""
    home = Path(env.get("HOME") or Path.home())

    def xdg(var: str, default: str) -> Path:
        """One XDG variable and its HOME-relative default; return the aios directory under it."""
        return Path(env.get(var) or home / default) / "aios"

    return Paths(xdg("XDG_CONFIG_HOME", ".config"), xdg("XDG_CACHE_HOME", ".cache"),
                 xdg("XDG_STATE_HOME", ".local/state"), xdg("XDG_DATA_HOME", ".local/share"))


def load_key(p: Paths) -> str:
    """Read the OpenRouter key. Refuse a file other users can read (lesson 9 in docs/lessons.md: keys never leak)."""
    f = p.credentials
    try:
        mode = f.stat().st_mode
    except FileNotFoundError:
        raise ConfigError(f"{f}: missing; store your OpenRouter key there (docs/INSTALL.md, step 2)") from None
    if mode & (stat.S_IRWXG | stat.S_IRWXO):
        raise ConfigError(f"{f}: readable by other users; fix: chmod 600 {f}")
    key = f.read_text(encoding="utf-8").strip()
    if not key.startswith("sk-or-"):
        raise ConfigError(f"{f}: does not look like an OpenRouter key (expected 'sk-or-...')")
    return key


# --- 2. Project settings ----------------------------------------------------------------
# From: <root>/.aios/project.toml, which the operator writes by hand (project.schema.md)
# To:   Component and Project, the shape the rest of aios reads; the helpers do the type checking
#       ([models] is only validated later, by catalog.load_policy; the keys ADR-0034 retired, and `profile` (ADR-0035),
#       warn and are ignored)


@dataclass(frozen=True)
class Component:
    """One [[components]] entry: name, relative path, toolchains (name -> minimum version), setup and checks."""
    name: str
    path: str  # "" = repo root, otherwise a relative directory ending in "/"
    # e.g. {"node": "22"}, the minimums (ADR-0035); left out of the hash, since a dict cannot be hashed
    toolchain: dict[str, str] = field(default_factory=dict, hash=False)
    setup: tuple[str, ...] | None = None
    checks: tuple[str, ...] | None = None
    checks_waiver: str = ""


@dataclass(frozen=True)
class Project:
    """One .aios/project.toml: its root, name, components, budget, privacy and routing settings."""
    root: Path
    name: str
    components: tuple[Component, ...]
    forge: str = "github"
    remote: str = "origin"
    default_branch: str | None = None
    per_task_usd: float = 1.0
    per_day_usd: float = 5.0
    data_collection: str = "deny"
    zdr: bool = False
    deny_vendors: tuple[str, ...] = ()
    models: dict | None = None   # the project's [models] table; catalog.load_policy validates it
    router_model: str = "clef-flash"
    router_escalation_model: str = "clef"
    escalate_below_confidence: float = 0.6
    sensitive_paths: tuple[str, ...] = ()

    def component_for(self, path: str) -> Component | None:
        """The component owning `path`: longest matching directory prefix (ADR-0030 section 8)."""
        hits = [c for c in self.components if path.startswith(c.path)]
        return max(hits, key=lambda c: len(c.path), default=None)


_STR, _BOOL, _NUM, _LIST, _TABLE = "a string", "true/false", "a number", "a list of strings", "a table"


def _get(table: dict, key: str, kind: str, where: str, default=None, required=False):
    """Fetch `key` from `table` as `kind`; return the value (a list as a tuple), the default, or ConfigError."""
    if key not in table:
        if required:
            raise ConfigError(f"{where}: missing required key '{key}'")
        return default
    v = table[key]
    ok = {_STR: isinstance(v, str), _BOOL: isinstance(v, bool), _TABLE: isinstance(v, dict),
          _NUM: isinstance(v, (int, float)) and not isinstance(v, bool),
          _LIST: isinstance(v, list) and all(isinstance(x, str) for x in v)}[kind]
    if not ok:
        raise ConfigError(f"{where}: '{key}' must be {kind}")
    return tuple(v) if kind == _LIST else v


def _section(doc: dict, name: str, keys: set[str], where: str) -> dict:
    """The [name] table of `doc`, checked against `keys`; return it as a dict, or raise ConfigError."""
    t = doc.get(name, {})
    if not isinstance(t, dict):
        raise ConfigError(f"{where}: [{name}] must be a table")
    _no_unknown(t, keys, f"{where} [{name}]")
    return t


def _no_unknown(t: dict, keys: set[str], where: str) -> None:
    """Raise ConfigError naming any key of `t` outside `keys`; return None."""
    if unknown := sorted(set(t) - keys):
        raise ConfigError(f"{where}: unknown key(s): {', '.join(unknown)}")


def _one_of(value, allowed: tuple, key: str, where: str):
    """Return `value` when it is one of `allowed`; otherwise raise ConfigError naming `key`."""
    if value not in allowed:
        raise ConfigError(f"{where}: '{key}' must be one of {', '.join(allowed)}")
    return value


def _toolchain(t: dict, where: str) -> dict[str, str]:
    """The checked `toolchain` table of `t`: known names, versions matching VERSION_RE; {} when absent."""
    table = _get(t, "toolchain", _TABLE, where, {})
    for name, version in table.items():
        if name not in toolchains.KNOWN:
            known = ", ".join(sorted(toolchains.KNOWN))
            raise ConfigError(f"{where}: toolchain '{name}' is unknown; known: {known}")
        if not isinstance(version, str) or not toolchains.VERSION_RE.match(version):
            raise ConfigError(f"{where}: toolchain '{name}' version {version!r} must be digits and dots, e.g. \"22\"")
    return dict(table)


def _component(t: dict, where: str) -> Component:
    """Build a Component from the table `t`, checked; raise ConfigError naming `where` on a bad value."""
    _no_unknown(t, {"name", "path", "profile", "toolchain", "setup", "checks", "checks_waiver"}, where)
    if "profile" in t:
        print(f"warning: {where} 'profile' was retired by ADR-0035 and is ignored; "
              "declare toolchain = { ... } instead", file=sys.stderr)
    path = _get(t, "path", _STR, where, required=True)
    if path == "./":
        path = ""
    elif not path.endswith("/") or path.startswith("/") or ".." in path.split("/") or "\\" in path:
        raise ConfigError(f"{where}: 'path' must be './' or a relative directory ending in '/'")
    c = Component(_get(t, "name", _STR, where, required=True), path, _toolchain(t, where),
                  _get(t, "setup", _LIST, where), _get(t, "checks", _LIST, where),
                  _get(t, "checks_waiver", _STR, where, ""))
    if c.checks == () and not c.checks_waiver.strip():
        raise ConfigError(f"{where}: 'checks = []' needs a non-empty 'checks_waiver' (components fail closed)")
    return c


def find_root(start: Path) -> Path | None:
    """The nearest directory at or above `start` holding .aios/project.toml; None when there is none."""
    for d in (start.resolve(), *start.resolve().parents):
        if (d / ".aios" / "project.toml").is_file():
            return d
    return None


def load_project(root: Path) -> Project:
    """Read <root>/.aios/project.toml; return the checked Project, or raise ConfigError."""
    f = root / ".aios" / "project.toml"
    w = str(f)
    try:
        doc = tomllib.loads(f.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise ConfigError(f"{w}: missing; run 'aios init' in the repo root") from None
    except tomllib.TOMLDecodeError as e:
        raise ConfigError(f"{w}: invalid TOML: {e}") from e
    _no_unknown(doc, {"schema", "name", "forge", "remote", "default_branch", "components", "models",
                      "budget", "privacy", "routing", "sensitive"}, w)
    schema = _get(doc, "schema", _NUM, w, required=True)
    if schema != SCHEMA:
        raise ConfigError(f"{w}: schema {schema} is not supported by this aios (expects {SCHEMA}); "
                          + ("upgrade aios" if schema > SCHEMA else "run 'aios migrate'"))
    comps = doc.get("components")
    if not isinstance(comps, list) or not comps or not all(isinstance(c, dict) for c in comps):
        raise ConfigError(f"{w}: needs at least one [[components]] table")
    components = tuple(_component(c, f"{w} components[{i}]") for i, c in enumerate(comps))
    if len({c.name for c in components}) != len(components):
        raise ConfigError(f"{w}: component names must be unique")
    # ADR-0034 removed the model tiers, so these two keys mean nothing any more: drop each one before the
    # unknown-key check, so a project file written before ADR-0034 only costs a warning, not a load failure.
    for section, key in {"privacy": "max_tier", "routing": "frontier_auto"}.items():
        if isinstance(doc.get(section), dict) and doc[section].pop(key, None) is not None:
            print(f"warning: {w} [{section}] '{key}' was retired by ADR-0034 and is ignored", file=sys.stderr)
    budget = _section(doc, "budget", {"per_task_usd", "per_day_usd"}, w)
    privacy = _section(doc, "privacy", {"data_collection", "zdr", "deny_vendors"}, w)
    routing = _section(doc, "routing", {"router_model", "router_escalation_model", "escalate_below_confidence"}, w)
    sensitive = _section(doc, "sensitive", {"paths"}, w)
    p = Project(
        root=root, name=_get(doc, "name", _STR, w, required=True), components=components,
        forge=_one_of(_get(doc, "forge", _STR, w, "github"), FORGES, "forge", w),
        remote=_get(doc, "remote", _STR, w, "origin"), default_branch=_get(doc, "default_branch", _STR, w),
        per_task_usd=float(_get(budget, "per_task_usd", _NUM, w, 1.0)),
        per_day_usd=float(_get(budget, "per_day_usd", _NUM, w, 5.0)),
        data_collection=_one_of(_get(privacy, "data_collection", _STR, w, "deny"), ("deny", "allow"),
                                "data_collection", w),
        zdr=_get(privacy, "zdr", _BOOL, w, False), deny_vendors=_get(privacy, "deny_vendors", _LIST, w, ()),
        models=_get(doc, "models", _TABLE, w),
        router_model=_get(routing, "router_model", _STR, w, "clef-flash"),
        router_escalation_model=_get(routing, "router_escalation_model", _STR, w, "clef"),
        escalate_below_confidence=float(_get(routing, "escalate_below_confidence", _NUM, w, 0.6)),
        sensitive_paths=_get(sensitive, "paths", _LIST, w, ()))
    if not p.name.strip():
        raise ConfigError(f"{w}: 'name' must not be empty")
    if min(p.per_task_usd, p.per_day_usd) <= 0:
        raise ConfigError(f"{w} [budget]: amounts must be > 0")
    if not 0 <= p.escalate_below_confidence <= 1:
        raise ConfigError(f"{w} [routing]: 'escalate_below_confidence' must be between 0 and 1")
    return p


# --- 3. The machine config --------------------------------------------------------------
# From: <config>/config.toml, written by hand or by `aios doctor --fix` (machine.schema.md)
# To:   Machine, the operator's monthly budget, for the doctor and the budget governor


@dataclass(frozen=True)
class Machine:
    """One <config>/config.toml: the operator's monthly budget amount, when one is set."""
    per_month_usd: float | None = None


def machine_file(p: Paths) -> Path:
    """The machine config file: <config>/config.toml."""
    return p.config / "config.toml"


def save_machine(p: Paths, m: Machine) -> Path:
    """Write the machine config and return the file written."""
    f = machine_file(p)
    f.parent.mkdir(parents=True, exist_ok=True)
    budget = "" if m.per_month_usd is None else f"\n[budget]\nper_month_usd = {m.per_month_usd}\n"
    f.write_text(f"schema = 1\n{budget}", encoding="utf-8")
    return f


def load_machine(p: Paths) -> Machine:
    """The machine config: Machine() when the file is missing, ConfigError when it is invalid."""
    f = machine_file(p)
    try:
        doc = tomllib.loads(f.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return Machine()
    except tomllib.TOMLDecodeError as e:
        raise ConfigError(f"{f}: invalid TOML: {e}") from e
    _no_unknown(doc, {"schema", "budget"}, f)
    schema = _get(doc, "schema", _NUM, f, required=True)
    if schema != SCHEMA:
        raise ConfigError(f"{f}: schema {schema} is not supported by this aios (expects {SCHEMA}); "
                          + ("upgrade aios" if schema > SCHEMA else "run 'aios migrate'"))
    amount = _get(_section(doc, "budget", {"per_month_usd"}, f), "per_month_usd", _NUM, f"{f} [budget]")
    if amount is not None and amount <= 0:
        raise ConfigError(f"{f} [budget]: 'per_month_usd' must be > 0")
    return Machine(None if amount is None else float(amount))
