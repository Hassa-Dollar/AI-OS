+++
id = "fill-missing-docstrings"
title = "One-line docstrings for the functions and classes that still lack one in five modules"
files_allowed = ["aios/config.py", "aios/doctor.py", "aios/router.py", "aios/catalog.py", "aios/calibrate.py"]
blast_radius = "low"
kind = "docs"
budget_usd = 0.4
+++

## Goal
`AGENTS.md` asks for a one-line docstring on every function, saying what it takes and what it returns. These five
modules already have their section maps and section headers, but 36 functions and classes in them have no
docstring. Add them, so the operator can read what each one does.

**Add docstrings and reword lesson references only. The code must stay exactly as it is.**

## Context
- Read `AGENTS.md`, especially its comment rule and the example there. Good examples already in the repository:
  `aios/review.py`, `aios/land.py`, `aios/status.py`.
- `.mypy_cache/` is a build-cache folder that aios never commits. Your copies and the checkers go there, so they
  survive between your commands, while `/tmp` is fresh for every command.
- Comments must be true. Read the code before describing it, and describe what it does now.
- ASCII only. Never reformat, reorder or compress code (`AGENTS.md`; lesson 20 in `docs/lessons.md`).
- **Docstrings count against the CI line budget.** Keep each new docstring to one line.
- Missing docstrings today:
  - `aios/config.py` (14): the `Paths` class and its `credentials` method, `paths` and the `xdg` function inside
    it, `Component`, `Project`, `Machine`, `_get`, `_section`, `_no_unknown`, `_one_of`, `_component`, `find_root`,
    `load_project`;
  - `aios/doctor.py` (9): `Check`, `_get_json`, `version_tuple`, `check_python`, `check_tool`, `check_ollama`,
    `check_harness`, `run`, `main`;
  - `aios/router.py` (7): the `Decision` class and its `record` method, `ask_clef`, `_score`, the `noul` function
    inside `heuristic`, `acceptance_lines`, `_at_least`;
  - `aios/catalog.py` (4): `cache_file`, `price_per_m`, `Policy`, `Candidate`;
  - `aios/calibrate.py` (2): `Case`, `Judgment`.

## Required changes
1. **Before editing anything,** copy the files you will change:
   `mkdir -p .mypy_cache/orig && cp aios/config.py aios/doctor.py aios/router.py aios/catalog.py aios/calibrate.py .mypy_cache/orig/`.
2. **Add a one-line docstring** to each function, method and class listed above, saying what it takes and returns
   (for a class: what one instance holds). Do not change existing docstrings, except as step 3 says.
3. **Plain references.** In these five files, write a lesson reference as `lesson N in docs/lessons.md`, never
   `lesson #N`: the operator reads `#N` as a code. Today that means `aios/config.py` (lesson #9) and
   `aios/router.py` (lesson #4).

## Acceptance criteria
- **The code is unchanged.** Save this checker as `.mypy_cache/astcheck.py`:
  ```python
  import ast, sys
  def strip(path):
      tree = ast.parse(open(path).read())
      for node in ast.walk(tree):
          body = getattr(node, "body", None)
          if isinstance(body, list) and body and isinstance(body[0], ast.Expr) and isinstance(getattr(body[0], "value", None), ast.Constant) and isinstance(body[0].value.value, str):
              node.body = body[1:] or [ast.Pass()]
      return ast.dump(tree)
  a, b = sys.argv[1], sys.argv[2]
  print("same code" if strip(a) == strip(b) else "CODE CHANGED")
  ```
  For each file, `python3 .mypy_cache/astcheck.py .mypy_cache/orig/<file name> aios/<file name>` must print
  `same code`.
- **Every function, method and class has a docstring.** Save this checker as `.mypy_cache/doccheck.py`:
  ```python
  import ast, sys
  for path in sys.argv[1:]:
      for node in ast.walk(ast.parse(open(path).read())):
          if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and not ast.get_docstring(node):
              print(f"{path}:{node.lineno}: {node.name} has no docstring")
  ```
  `python3 .mypy_cache/doccheck.py aios/config.py aios/doctor.py aios/router.py aios/catalog.py aios/calibrate.py`
  prints nothing.
- `grep -n "lesson #" aios/config.py aios/doctor.py aios/router.py aios/catalog.py aios/calibrate.py` finds nothing.
- `python3 -m unittest discover -s tests -t .` passes.

## Out of scope
Any code change; the section maps and headers, which already exist; any other file.

## Stop conditions
If something above is contradictory or impossible, stop and reply `ESCALATE: <reason>`.
