+++
id = "comments-spec-git-gateway"
title = "Section comments for spec.py, git.py and gateway.py"
files_allowed = ["aios/spec.py", "aios/git.py", "aios/gateway.py"]
blast_radius = "low"
kind = "docs"
budget_usd = 0.4
+++

## Goal
The operator reads aios's code to understand it, and asked for comments that say what each part does and where its
data comes from and goes. `AGENTS.md` defines the style: a section map in the module docstring, a header before each
section, and a one-line docstring on every function. Apply that style to `aios/spec.py`, `aios/git.py`, `aios/gateway.py`.

**Change comments and docstrings only. The code must stay exactly as it is.**

## Context
- Read `AGENTS.md`, especially its comment rule and the example there. Good examples already in the repository:
  `aios/review.py`, `aios/calibrate.py`, `aios/records.py`.
- `.mypy_cache/` is a build-cache folder that aios never commits. Your copies and the checker go there, so
  they survive between your commands, while `/tmp` is fresh for every command.
- Comments must be true. Read the code before describing it, and describe what it does now.
- ASCII only. Never reformat, reorder or compress code (`AGENTS.md`, lesson 20).

## Required changes
1. **Before editing anything,** copy the files you will change:
   `mkdir -p .mypy_cache/orig && cp aios/spec.py aios/git.py aios/gateway.py .mypy_cache/orig/`.
2. **For each file:**
   - a module docstring with a numbered **section map**, one line per section (what it does, input -> output);
   - a header before each section: `# --- N. <name> ---`, then `# From: ...` and `# To: ...` lines;
   - a one-line docstring on every function or method that lacks one, saying what it takes and returns. Improve an
     existing docstring only if it is wrong or unclear.

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
  For each file, `python3 .mypy_cache/astcheck.py .mypy_cache/orig/<file name> aios/<file name>` must print `same code`.
- `python3 -m unittest discover -s tests -t .` passes.
- Every file listed above has a section map and section headers.

## Out of scope
Any code change, and any other file.

## Stop conditions
If something above is contradictory or impossible, stop and reply `ESCALATE: <reason>`.
