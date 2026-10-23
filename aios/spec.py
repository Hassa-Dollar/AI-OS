"""Parse and validate AI-OS v2 task specs (Markdown + TOML frontmatter)."""

from __future__ import annotations

import os
import re
import tomllib
from dataclasses import dataclass, field

KINDS = frozenset(
    {"feature", "bugfix", "refactor", "tests", "docs", "research", "infra",
     "security", "migration"}
)
BLAST = ("low", "medium", "high")

_ALLOWED_KEYS = frozenset(
    {"id", "title", "files_allowed", "deps_preapproved", "contracts",
     "blast_radius", "depends_on", "human_required", "irreversible",
     "budget_usd", "kind", "pin"}
)
_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
NAME_RE = re.compile(r"^[a-z][a-z0-9]*(-[a-z0-9]+){1,5}$")
_HEADING_RE = re.compile(r"#{1,3} (.*)$")


class SpecError(ValueError):
    """Raised when a spec is malformed; message names the source and problem."""


@dataclass(frozen=True)
class Spec:
    id: str
    title: str
    files_allowed: tuple[str, ...]
    deps_preapproved: tuple[str, ...] = ()
    contracts: tuple[str, ...] = ()
    blast_radius: str = "low"
    depends_on: tuple[str, ...] = ()
    human_required: bool = False
    irreversible: bool = False
    budget_usd: float | None = None
    kind: str | None = None
    pin_model: str | None = None
    pin_reason: str | None = None
    body: str = ""
    sections: dict[str, str] = field(default_factory=dict)

    @property
    def branch(self) -> str:
        return "aios/" + self.id


def _valid_path(p: object) -> bool:
    if not isinstance(p, str) or not p:
        return False
    if p.startswith("/") or "\\" in p:
        return False
    return all(seg not in ("", ".", "..") for seg in p.split("/"))


def _valid_grant(p: object) -> bool:
    return isinstance(p, str) and bool(p) and (not p.endswith("/") or p != "/") \
        and _valid_path(p.removesuffix("/"))


def _str_list(data: dict, key: str, source: str) -> list[str]:
    v = data.get(key, [])
    if not isinstance(v, list) or not all(isinstance(x, str) for x in v):
        raise SpecError(f"{source}: {key!r} must be a list of strings")
    return v


def _bool(data: dict, key: str, source: str) -> bool:
    v = data.get(key, False)
    if not isinstance(v, bool):
        raise SpecError(f"{source}: {key!r} must be a TOML boolean")
    return v


def _parse_sections(body: str) -> dict[str, str]:
    sections: dict[str, str] = {}
    key: str | None = None
    buf: list[str] = []
    for line in body.splitlines():
        m = _HEADING_RE.match(line)
        if m:
            if key is not None:
                sections[key] = "\n".join(buf).strip()
            key = m.group(1).strip().lower()
            buf = []
        elif key is not None:
            buf.append(line)
    if key is not None:
        sections[key] = "\n".join(buf).strip()
    return sections


def parse_spec(text: str, source: str = "<spec>") -> Spec:
    text = text.lstrip("\ufeff")
    lines = text.splitlines()
    if not lines or lines[0] != "+++":
        raise SpecError(f"{source}: first line must be '+++'")
    close = None
    for i in range(1, len(lines)):
        if lines[i] == "+++":
            close = i
            break
    if close is None:
        raise SpecError(f"{source}: missing closing '+++' fence")
    front = "\n".join(lines[1:close])
    try:
        data = tomllib.loads(front)
    except tomllib.TOMLDecodeError as e:
        raise SpecError(f"{source}: invalid TOML frontmatter: {e}") from e
    for key in data:
        if key not in _ALLOWED_KEYS:
            raise SpecError(f"{source}: unknown key {key!r}")
    for key in ("id", "title", "files_allowed"):
        if key not in data:
            raise SpecError(f"{source}: missing required key {key!r}")
    id_ = data["id"]
    if not isinstance(id_, str) or not _ID_RE.match(id_):
        raise SpecError(f"{source}: invalid 'id' value {id_!r}")
    title = data["title"]
    if not isinstance(title, str) or not title.strip():
        raise SpecError(f"{source}: 'title' must be a non-empty string")
    files = data["files_allowed"]
    if not isinstance(files, list) or not files:
        raise SpecError(f"{source}: 'files_allowed' must be a non-empty list")
    seen: set[str] = set()
    for entry in files:
        if not isinstance(entry, str):
            raise SpecError(f"{source}: 'files_allowed' entries must be strings")
        if not _valid_grant(entry):
            raise SpecError(
                f"{source}: invalid 'files_allowed' entry {entry!r}"
                " (want a relative POSIX path)"
            )
        if entry in seen:
            raise SpecError(f"{source}: duplicate 'files_allowed' entry {entry!r}")
        seen.add(entry)
    blast = data.get("blast_radius", "low")
    if blast not in BLAST:
        raise SpecError(f"{source}: 'blast_radius' must be one of {BLAST}")
    kind = data.get("kind")
    if kind is not None and kind not in KINDS:
        raise SpecError(f"{source}: 'kind' must be one of {sorted(KINDS)}")
    budget = data.get("budget_usd")
    if budget is not None:
        if isinstance(budget, bool) or not isinstance(budget, (int, float)) \
                or budget <= 0:
            raise SpecError(f"{source}: 'budget_usd' must be a number > 0")
        budget = float(budget)
    pin_model = pin_reason = None
    pin = data.get("pin")
    if pin is not None:
        if not isinstance(pin, dict) or set(pin) != {"model", "reason"}:
            raise SpecError(
                f"{source}: 'pin' must be a table with keys 'model' and 'reason'"
            )
        pin_model, pin_reason = pin["model"], pin["reason"]
        if not isinstance(pin_model, str) or not pin_model.strip() \
                or not isinstance(pin_reason, str) or not pin_reason.strip():
            raise SpecError(
                f"{source}: 'pin.model' and 'pin.reason' must be non-empty strings"
            )
    body = "\n".join(lines[close + 1:]).lstrip("\n")
    sections = _parse_sections(body)
    for name in ("goal", "acceptance criteria"):
        if name not in sections:
            raise SpecError(f"{source}: missing required section {name!r}")
    return Spec(
        id=id_,
        title=title,
        files_allowed=tuple(files),
        deps_preapproved=tuple(_str_list(data, "deps_preapproved", source)),
        contracts=tuple(_str_list(data, "contracts", source)),
        blast_radius=blast,
        depends_on=tuple(_str_list(data, "depends_on", source)),
        human_required=_bool(data, "human_required", source),
        irreversible=_bool(data, "irreversible", source),
        budget_usd=budget,
        kind=kind,
        pin_model=pin_model,
        pin_reason=pin_reason,
        body=body,
        sections=sections,
    )


def load_spec(path: str | os.PathLike) -> Spec:
    with open(path, encoding="utf-8") as f:
        return parse_spec(f.read(), source=str(path))


def path_allowed(spec: Spec, path: str) -> bool:
    if not _valid_path(path):
        return False
    for grant in spec.files_allowed:
        if path == grant or (grant.endswith("/") and path.startswith(grant)):
            return True
    return False


def _covers(a: str, b: str) -> bool:
    return a == b or (a.endswith("/") and b.startswith(a))


def overlaps(a: Spec, b: Spec) -> list[str]:
    pairs = {
        f"{ga} <-> {gb}"
        for ga in a.files_allowed
        for gb in b.files_allowed
        if _covers(ga, gb) or _covers(gb, ga)
    }
    return sorted(pairs)


def name_problem(s: Spec, path: str | None = None) -> str | None:
    """Return the problem with the task's name, or None when it is descriptive."""
    if len(s.id) > 50 or not NAME_RE.match(s.id):
        return f"'{s.id}' is not a descriptive name: 2 to 6 lowercase words joined by hyphens"
    file = os.path.basename(str(path)) if path is not None else s.id + ".md"
    if file != s.id + ".md":
        return f"the file is named {file} but the id is {s.id}; name the file {s.id}.md"
    return None
