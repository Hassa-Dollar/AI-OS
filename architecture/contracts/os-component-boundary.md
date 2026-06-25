# Contract: OS ↔ component boundary

> Governed by ADR-0002. This is the boundary every component implements against and every script
> respects. Changing it is HIGH leverage → Lead-owned, new ADR.

## Layout
```
components/<name>/
├─ .component.yml          # { profile: <family/variant> }   ← the only OS-facing metadata
├─ README.md               # how to build/run/extract THIS component
├─ <stack files>           # package.json, src/, tests/, build + CI-equivalent — self-contained
└─ (nothing references a path outside this directory)
```

## `.component.yml` schema
```yaml
profile: web-app/ts-hono-api   # which profile leaf governs this component (ADR-0003); locked for life
# optional, future:
# extract_target: <git url or "standalone">   # where this component is published when lifted out
```

## Rules (machine-checkable)
1. **One-way dependency.** No file under `components/<X>/` may reference a path outside it
   (no `../`, no absolute repo paths). CI guard: `grep -RnE '\.\./' components/<X>/ <source globs>`
   over source files must be empty. Cross-component interaction is allowed **only** through a contract
   in `architecture/contracts/`.
2. **Self-contained build.** `cd components/<X> && <install> && <test>` passes with the repo's OS
   directory deleted. This is the extractability test; CI runs it from the component dir via the
   `COMPONENT` selector.
3. **Single-component tasks.** A task spec's `files_allowed` must all be under one `components/<X>/`
   (plus the implicit `reports/tasks/<id>-completion.md` and the spec's Working Notes). `dispatch.sh`
   rejects a spec whose `files_allowed` spans two components or mixes a component with OS files.
4. **Post-merge audit.** After a merge, the actual changed-file set is compared to the spec's
   `files_allowed`; any file outside it is appended to `reports/metrics/ledger.csv` as
   `guardrail,<id>,<branch>,<actor>,"escaped=<paths>"`.

## The `COMPONENT` selector
Scripts and CI read `COMPONENT` (default: the sole component if exactly one exists; otherwise required).
Build/test/coverage/secret-scan run with `cd "$COMPONENT"`. No script branches on the component's
*name* or *profile* — it only `cd`s into the path and runs the canonical commands from `ci-env.sh`.
