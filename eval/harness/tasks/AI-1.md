+++
id = "AI-1"
title = "aios/spec.py: parse and validate v2 task specs (TOML frontmatter), path grants, overlap check"
files_allowed = ["aios/__init__.py", "aios/spec.py", "tests/__init__.py", "tests/test_spec.py"]
deps_preapproved = []
contracts = []
blast_radius = "medium"
kind = "feature"
budget_usd = 0.75
+++

## Goal
Create `aios/spec.py`, the module every other part of AI-OS uses to read task specs. Specs are Markdown files with
TOML frontmatter between `+++` fences (this file is an example).

The module must use the **Python standard library only** (`tomllib`, `dataclasses`, `pathlib`, `re`), on Python ≥3.11.

## Interface (exact)
```python
class SpecError(ValueError): ...            # message must contain the `source` name and the offending key or problem

KINDS = frozenset({"feature", "bugfix", "refactor", "tests", "docs", "research", "infra", "security", "migration"})
BLAST = ("low", "medium", "high")

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
    body: str = ""                          # everything after the closing fence, with leading newlines stripped
    sections: dict[str, str] = field(default_factory=dict)  # lower-cased heading text -> section text (stripped)

    @property
    def branch(self) -> str: ...            # "aios/" + id

def parse_spec(text: str, source: str = "<spec>") -> Spec: ...
def load_spec(path: str | os.PathLike) -> Spec: ...   # source = str(path); file read as UTF-8
def path_allowed(spec: Spec, path: str) -> bool: ...
def overlaps(a: Spec, b: Spec) -> list[str]: ...
```

## Rules
**Fences and TOML**
1. The text must start with a line that is exactly `+++` (an optional UTF-8 BOM is allowed) and contain a later line
   that is exactly `+++`. Anything else → `SpecError`.
2. The frontmatter between the fences is parsed with `tomllib`. A TOML error → `SpecError` (chain the original).

**Keys and types**

3. Only these keys are allowed: `id`, `title`, `files_allowed`, `deps_preapproved`, `contracts`, `blast_radius`,
   `depends_on`, `human_required`, `irreversible`, `budget_usd`, `kind`, `pin`. Any other key → `SpecError` naming it.
4. Required keys and their checks:
   - `id`: a string matching `^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$`.
   - `title`: a non-empty string (whitespace-only counts as empty).
   - `files_allowed`: a non-empty list of strings.
5. Optional keys and their checks:
   - `deps_preapproved`, `contracts`, `depends_on`: lists of strings.
   - `human_required`, `irreversible`: booleans. TOML booleans only; `0`/`"true"` are errors.
   - `budget_usd`: an int or float > 0 (but not a bool). Stored as a float.
   - `kind`: one of `KINDS`.
   - `blast_radius`: one of `BLAST`.
   - A wrong type or value → `SpecError` naming the key.
6. `pin`, if present, must be a table with exactly the keys `model` and `reason`, both non-empty strings. They are
   stored as `pin_model` and `pin_reason`.

**`files_allowed` entries**

7. Each entry must be a relative POSIX path. Rejected with `SpecError`: empty entries, a leading `/`, backslashes,
   `..` segments, `.` segments, and `//`.
8. An entry ending in `/` is a **directory grant**: it covers everything below it.
9. Duplicate entries → `SpecError`.

**Body sections**

10. A section starts at a Markdown heading line: one to three `#` characters followed by a space (`#`, `##` or `###`).
    Its key is the heading text, lower-cased and stripped. Its text (stripped) runs up to the next such heading line.
    Deeper headings such as `####` are ordinary text.
11. The sections `goal` and `acceptance criteria` are required; a missing one → `SpecError`.

**`path_allowed(spec, path)`**

12. Returns `False` for any `path` that would be rejected by rule 7.
13. Otherwise returns `True` if `path` equals a file grant, or starts with a directory grant. A directory grant
    `"src/"` covers `"src/a.py"` and `"src/x/y"`, but not `"src"` and not `"srcx/a"`.

**`overlaps(a, b)`**

14. Returns a sorted list of de-duplicated strings `"<grant in a> <-> <grant in b>"`, one for every pair that
    conflicts. A pair conflicts if the two grants are equal, or one is a directory grant that covers the other.
    Returns an empty list when the specs are disjoint.

## Acceptance criteria
- `aios/spec.py` implements the interface and rules above, using the standard library only.
- `tests/test_spec.py` (`unittest`) covers every rule, both valid and invalid cases.
- `python3 -m unittest discover -s tests -t . -v` passes from the repo root.
- `aios/spec.py` has at most 220 non-blank, non-comment lines.

## Out of scope
CLI wiring, reading files other than via `load_spec`, and any other module.

## Stop conditions
If the interface or rules are contradictory or ambiguous in a way that blocks a correct implementation, stop and reply
`ESCALATE: <reason>`.
