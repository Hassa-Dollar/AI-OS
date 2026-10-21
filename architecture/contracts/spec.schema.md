# Contract: task spec (v2)

**Owner:** Lead. **Implemented by:** `aios/spec.py`. **Decided in:** ADR-0030.

A spec is a Markdown file at `.aios/tasks/<id>.md`. It has TOML frontmatter between two `+++` lines; the first line must
be exactly `+++`, with an optional UTF-8 BOM before it. The frontmatter is parsed with `tomllib`.

## Frontmatter
| Key | Type | Req. | Rule |
|---|---|---|---|
| `id` | string | ✓ | Matches `^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$`. The branch is `aios/<id>` |
| `title` | string | ✓ | Must not be empty or whitespace only |
| `files_allowed` | list[string] | ✓ | Non-empty relative POSIX paths, with no duplicates. Rejected: a leading `/`, `\`, `..` or `.` segments, `//`. An entry ending in `/` is a directory grant |
| `deps_preapproved` | list[string] | | Dependencies the task may add |
| `contracts` | list[string] | | Contracts the task depends on (changing one raises a LEAD flag) |
| `blast_radius` | `low`·`medium`·`high` | | Default `low` |
| `depends_on` | list[string] | | Task ids that must land first |
| `human_required` | bool | | Forces the HUMAN gate |
| `irreversible` | bool | | Forces the HUMAN gate |
| `budget_usd` | number > 0 | | Per-task dollar cap |
| `kind` | `feature`·`bugfix`·`refactor`·`tests`·`docs`·`research`·`infra`·`security`·`migration` | | Router hint |
| `pin` | `{ model = "...", reason = "..." }` | | Bypasses routing for the author model and raises a LEAD flag. Both fields must be non-empty, with no other keys |

The table is complete. Any key not listed, a wrong type or an invalid value is an error. A validation error message
names the file and the offending key.

## Body
A section starts at a heading line made of `#`, `##` or `###` followed by a space. The section's key is the heading
text, lower-cased; its text runs to the next such heading. A `####` heading is ordinary text.

Required sections:
- `Goal`
- `Acceptance criteria`. These must be executable.

Expected sections:
- `Context`, kept compressed.
- `Out of scope`. Binding on the worker.
- `Stop conditions`. The worker replies `ESCALATE: <reason>`.

## Path grants
- **`path_allowed(spec, path)`.** True when `path` equals a file grant, or begins with a directory grant (`src/` covers
  `src/a/b` but not `src` or `srcx/`). Invalid paths are never allowed.
- **Overlap.** Two active tasks overlap if any of their grants are equal, or if one is a directory grant covering the
  other. Tasks that overlap cannot be in flight at the same time.
