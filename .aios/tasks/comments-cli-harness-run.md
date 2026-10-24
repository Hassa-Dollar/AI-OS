+++
id = "comments-cli-harness-run"
title = "Section comments for cli.py and harness.py, and the last docstring in run.py"
files_allowed = ["aios/cli.py", "aios/harness.py", "aios/run.py"]
depends_on = ["rollback-command"]
blast_radius = "low"
kind = "docs"
budget_usd = 0.4
+++

## Goal
The operator reads aios's code to understand it. `AGENTS.md` defines the comment style they chose: a section map
in the module docstring, a header before each section, and a one-line docstring on every function. Two modules have
none of it yet: `aios/cli.py` (the `aios` command line) and `aios/harness.py` (the worker sandbox). `aios/run.py`
has its map and headers, but one function lacks a docstring.

**Change comments and docstrings only. The code must stay exactly as it is.**

## Context
- Read `AGENTS.md`, especially its comment rule and the example there. Good examples already in the repository:
  `aios/review.py`, `aios/land.py`, `aios/status.py`.
- `.mypy_cache/` is a build-cache folder that aios never commits. Your copies and the checkers go there, so they
  survive between your commands, while `/tmp` is fresh for every command.
- Comments must be true. Read the code before describing it, and describe what it does now.
- ASCII only. Never reformat, reorder or compress code (`AGENTS.md`; lesson 20 in `docs/lessons.md`).
- **Docstrings count against the CI line budget, and `#` comments do not.** Keep each new docstring to one line,
  and write the section headers as `#` comments.
- Missing docstrings today:
  - `aios/cli.py`: `cmd_init`, `cmd_models`, `main`;
  - `aios/harness.py`: the `Attempt` class and its `record` method, `home`, `installed_version`, `_mini_yaml`,
    `_instance_template`, `run`;
  - `aios/run.py`: `project_id`.

## Required changes
1. **Before editing anything,** copy the files you will change:
   `mkdir -p .mypy_cache/orig && cp aios/cli.py aios/harness.py aios/run.py .mypy_cache/orig/`.
2. **`aios/cli.py` and `aios/harness.py`:**
   - keep what each module docstring says now, and add a numbered **section map** to it, one line per section (what
     it does, input -> output);
   - a header before each section: `# --- N. <name> ---`, then `# From: ...` and `# To: ...` lines;
   - a one-line docstring on every function, method and class listed above, saying what it takes and returns (for a
     class: what one instance holds).
3. **`aios/run.py`:** add the one-line docstring to `project_id`.
4. **Plain references.** In these three files, write a lesson reference as `lesson N in docs/lessons.md`, never
   `lesson #N`: the operator reads `#N` as a code. Today that means `aios/harness.py` (lesson #1) and `aios/run.py`
   (lesson #3).

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
  `python3 .mypy_cache/doccheck.py aios/cli.py aios/harness.py aios/run.py` prints nothing.
- `grep -n "lesson #" aios/cli.py aios/harness.py aios/run.py` finds nothing.
- `aios/cli.py` and `aios/harness.py` each have a section map, and a `# --- N.` header for every section in it.
- `python3 -m unittest discover -s tests -t .` passes.

## Out of scope
Any code change, and any other file.

## Stop conditions
If something above is contradictory or impossible, stop and reply `ESCALATE: <reason>`.
