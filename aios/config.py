"""Machine and project configuration (contract: architecture/contracts/project.schema.md, ADR-0030)."""
from __future__ import annotations

import os
import stat
import tomllib
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

SCHEMA = 1
FORGES = ("github", "local")
TIERS = ("T1", "T2", "T3")


class ConfigError(ValueError):
    """A configuration file is missing or invalid. The message names the file and the problem."""


@dataclass(frozen=True)
class Paths:
    config: Path
    cache: Path
    state: Path
    data: Path

    @property
    def credentials(self) -> Path:
        return self.config / "credentials"


def paths(env: Mapping[str, str] = os.environ) -> Paths:
    home = Path(env.get("HOME") or Path.home())

    def xdg(var: str, default: str) -> Path:
        return Path(env.get(var) or home / default) / "aios"

    return Paths(xdg("XDG_CONFIG_HOME", ".config"), xdg("XDG_CACHE_HOME", ".cache"),
                 xdg("XDG_STATE_HOME", ".local/state"), xdg("XDG_DATA_HOME", ".local/share"))


def load_key(p: Paths) -> str:
    """Read the OpenRouter key. Refuse a file other users can read (lesson #9: keys never leak)."""
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


@dataclass(frozen=True)
class Component:
    name: str
    path: str  # "" = repo root, otherwise a relative directory ending in "/"
    profile: str
    setup: tuple[str, ...] | None = None
    checks: tuple[str, ...] | None = None
    checks_waiver: str = ""


@dataclass(frozen=True)
class Project:
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
    max_tier: str = "T3"
    frontier_auto: bool = False
    router_model: str = "clef-flash"
    router_escalation_model: str = "clef"
    escalate_below_confidence: float = 0.6
    sensitive_paths: tuple[str, ...] = ()

    def component_for(self, path: str) -> Component | None:
        """The component owning `path`: longest matching directory prefix (ADR-0030 §8)."""
        hits = [c for c in self.components if path.startswith(c.path)]
        return max(hits, key=lambda c: len(c.path), default=None)


_STR, _BOOL, _NUM, _LIST = "a string", "true/false", "a number", "a list of strings"


def _get(table: dict, key: str, kind: str, where: str, default=None, required=False):
    if key not in table:
        if required:
            raise ConfigError(f"{where}: missing required key '{key}'")
        return default
    v = table[key]
    ok = {_STR: isinstance(v, str), _BOOL: isinstance(v, bool),
          _NUM: isinstance(v, (int, float)) and not isinstance(v, bool),
          _LIST: isinstance(v, list) and all(isinstance(x, str) for x in v)}[kind]
    if not ok:
        raise ConfigError(f"{where}: '{key}' must be {kind}")
    return tuple(v) if kind == _LIST else v


def _section(doc: dict, name: str, keys: set[str], where: str) -> dict:
    t = doc.get(name, {})
    if not isinstance(t, dict):
        raise ConfigError(f"{where}: [{name}] must be a table")
    _no_unknown(t, keys, f"{where} [{name}]")
    return t


def _no_unknown(t: dict, keys: set[str], where: str) -> None:
    if unknown := sorted(set(t) - keys):
        raise ConfigError(f"{where}: unknown key(s): {', '.join(unknown)}")


def _one_of(value, allowed: tuple, key: str, where: str):
    if value not in allowed:
        raise ConfigError(f"{where}: '{key}' must be one of {', '.join(allowed)}")
    return value


def _component(t: dict, where: str) -> Component:
    _no_unknown(t, {"name", "path", "profile", "setup", "checks", "checks_waiver"}, where)
    path = _get(t, "path", _STR, where, required=True)
    if path == "./":
        path = ""
    elif not path.endswith("/") or path.startswith("/") or ".." in path.split("/") or "\\" in path:
        raise ConfigError(f"{where}: 'path' must be './' or a relative directory ending in '/'")
    c = Component(_get(t, "name", _STR, where, required=True), path, _get(t, "profile", _STR, where, required=True),
                  _get(t, "setup", _LIST, where), _get(t, "checks", _LIST, where),
                  _get(t, "checks_waiver", _STR, where, ""))
    if c.checks == () and not c.checks_waiver.strip():
        raise ConfigError(f"{where}: 'checks = []' needs a non-empty 'checks_waiver' (components fail closed)")
    return c


def find_root(start: Path) -> Path | None:
    for d in (start.resolve(), *start.resolve().parents):
        if (d / ".aios" / "project.toml").is_file():
            return d
    return None


def load_project(root: Path) -> Project:
    f = root / ".aios" / "project.toml"
    w = str(f)
    try:
        doc = tomllib.loads(f.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise ConfigError(f"{w}: missing; run 'aios init' in the repo root") from None
    except tomllib.TOMLDecodeError as e:
        raise ConfigError(f"{w}: invalid TOML: {e}") from e
    _no_unknown(doc, {"schema", "name", "forge", "remote", "default_branch", "components",
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
    budget = _section(doc, "budget", {"per_task_usd", "per_day_usd"}, w)
    privacy = _section(doc, "privacy", {"data_collection", "zdr", "deny_vendors", "max_tier"}, w)
    routing = _section(doc, "routing", {"frontier_auto", "router_model", "router_escalation_model",
                                        "escalate_below_confidence"}, w)
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
        max_tier=_one_of(_get(privacy, "max_tier", _STR, w, "T3"), TIERS, "max_tier", w),
        frontier_auto=_get(routing, "frontier_auto", _BOOL, w, False),
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
