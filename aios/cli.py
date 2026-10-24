"""The `aios` command line.

Sections:
  1. Init       the repo root + the flags -> .aios/project.toml with the detected toolchains and checks
  2. Catalog    the stored key and the cached catalog -> the synced models and their candidates
  3. Spec       spec files -> each task's validity, the overlaps, and one spec's routing decision
  4. Main       argv -> the chosen subcommand's exit code (2 when a known error escapes)
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from . import __version__, calibrate, catalog, config, doctor, forge, gate, gateway, git, harness, \
                  land, run, spec, status, toolchains

PROJECT_TEMPLATE = """\
# AI-OS project config. Contract: architecture/contracts/project.schema.md in the AI-OS repo.
schema = 1
name = "{name}"
forge = "{forge}"              # github | local
remote = "origin"
default_branch = "{branch}"

[[components]]
name = "app"
path = "./"                    # repo root. In a monorepo, add one [[components]] per directory, e.g. "api/"
toolchain = {toolchain}
checks = {checks}

[budget]
per_task_usd = 1.0
per_day_usd = 5.0

[privacy]
data_collection = "deny"       # never route code to providers that train on it
zdr = false
deny_vendors = []

# [models]                       # optional: this project's model policy (contract: models.schema.md)
# levels = {{ junior = 40, mid = 45, senior = 52 }}
"""


# --- 1. Init ------------------------------------------------------------------------------
# From: the repo root (package.json, pyproject.toml, tests/) and the --toolchain/--check/--forge flags
# To:   .aios/project.toml, or a ConfigError when it already exists or nothing can be detected
def detect_checks(root: Path) -> tuple[dict[str, str], list[str]]:
    """Guess the toolchain table and the commands that prove a change works. Returns ({}, []) when unsure."""
    pkg = root / "package.json"
    if pkg.is_file():
        scripts = json.loads(pkg.read_text(encoding="utf-8")).get("scripts", {})
        checks = [f"npm run -s {s}" for s in ("lint", "typecheck", "test") if s in scripts]
        return {"node": toolchains.KNOWN["node"].default}, checks
    if (root / "pyproject.toml").is_file() or (root / "tests").is_dir():
        return {"python": toolchains.KNOWN["python"].default}, ["python3 -m unittest discover -s tests -t ."]
    return {}, []


def toolchain_table(pairs: list[str] | None) -> dict[str, str]:
    """Parse repeated NAME=VERSION flags into a table; raise ConfigError on a value without '='."""
    table = {}
    for pair in pairs or []:
        if "=" not in pair:
            raise config.ConfigError("--toolchain must be NAME=VERSION, e.g. node=22")
        name, version = pair.split("=", 1)
        table[name] = version
    return table


def inline_table(table: dict[str, str]) -> str:
    """Render a toolchain table as TOML inline table, for example { python = "3.11" }, or {} when empty."""
    if not table:
        return "{}"
    return "{ " + ", ".join(f'{k} = "{v}"' for k, v in table.items()) + " }"


def cmd_init(args: argparse.Namespace) -> int:
    """`aios init`: write .aios/project.toml from the detected toolchains, checks and forge; returns 0."""
    root = git.toplevel(Path.cwd())
    target = root / ".aios" / "project.toml"
    if target.exists():
        raise config.ConfigError(f"{target}: already exists")
    detected, checks = detect_checks(root)
    table = toolchain_table(args.toolchain) if args.toolchain else detected
    checks = args.check or checks
    if not checks:
        raise config.ConfigError("could not detect how to verify changes here; pass --check '<command>' "
                                 "(repeatable), e.g. --check 'make test'")
    url = git.remote_url(root) or ""
    forge = args.forge or ("github" if "github.com" in url else "local")
    for d in ("tasks", "records"):
        (root / ".aios" / d).mkdir(parents=True, exist_ok=True)
        (root / ".aios" / d / ".gitkeep").touch()
    target.write_text(PROJECT_TEMPLATE.format(name=args.name or root.name, forge=forge, branch=git.default_branch(root),
                                              toolchain=inline_table(table), checks=json.dumps(checks)),
                              encoding="utf-8")
    config.load_project(root)  # never leave behind a config that would not load
    named = ", ".join(f"{k} {v}" for k, v in table.items()) or "none"
    print(f"wrote {target.relative_to(root)} (toolchain {named}, forge {forge}); review it, then commit .aios/")
    return 0


# --- 2. Catalog ---------------------------------------------------------------------------
# From: the stored OpenRouter key, the cached catalog and the project's privacy settings
# To:   the printed candidates, the refreshed cache, and each model's calibration verdict
def _gateway(p: config.Paths) -> gateway.Gateway | None:
    """The OpenRouter client when a key is stored, else None (list then works from the cache)."""
    if not p.credentials.exists():
        return None
    return gateway.Gateway(config.load_key(p), base=os.environ.get("AIOS_OPENROUTER_URL", gateway.BASE))


def show_candidates(live: list[dict]) -> None:
    """Print the three cheapest candidates per role and level, then credit the source of the quality scores."""
    policy = catalog.load_policy()
    for role in catalog.ROLE_NEEDS:
        for level in catalog.LEVELS:
            rows = [f"{c.id} (score {c.score:.1f}, ${c.usd_in:.2f}/${c.usd_out:.2f} per M, "
                    f"~${c.est_usd:.2f} per task)" for c in catalog.candidates(live, role=role, level=level,
                                                                              policy=policy)[:3]]
            print(f"{role} {level}: {' | '.join(rows) if rows else '(none)'}")
    print("Quality scores: Artificial Analysis (artificialanalysis.ai), via OpenRouter.")


def _calibration_gateway(p: config.Paths) -> gateway.Gateway:
    """The reviewer client for calibration: the stored key, plus the project's privacy settings inside a project."""
    if not p.credentials.exists():
        raise config.ConfigError(f"{p.credentials}: missing; store your OpenRouter key there (docs/INSTALL.md, step 2)")
    root = config.find_root(Path.cwd())
    privacy = gateway.privacy_of(config.load_project(root)) if root else None
    return gateway.Gateway(config.load_key(p), base=os.environ.get("AIOS_OPENROUTER_URL", gateway.BASE),
                           privacy=privacy)


def cmd_calibrate(args: argparse.Namespace) -> int:
    """`aios models calibrate <model>`: judge the known changes with the real reviewer call, then cache the result."""
    if not args.models:
        raise config.ConfigError("usage: aios models calibrate <model> [<model> ...]")
    p = config.paths()
    cases, gw, ok = calibrate.load_cases(), _calibration_gateway(p), True
    for model in args.models:
        js = calibrate.run(gw, model, cases, repeat=args.repeat)
        for j in js:
            line = (f"{model} | {j.case} | want {j.expected} got {j.got} | {'RIGHT' if j.right else 'WRONG'} | "
                    f"${j.usd:.4f} | {j.secs}s")
            print(f"{line} | {j.note[:100]}" if j.note else line)  # a clean pass has nothing to report
        calibrate.save(p, model, js, cases)
        may = calibrate.passed(p, model, cases)
        print(f"{model}: {sum(j.right for j in js)}/{len(js)} right, ${sum(j.usd for j in js):.4f}, "
              f"{sum(j.secs for j in js)}s -> {'may review' if may else 'may not review'}")
        ok = ok and may
    return 0 if ok else 1


def cmd_models(args: argparse.Namespace) -> int:
    """`aios models sync|list|calibrate`: refresh or show the catalog, or calibrate reviewers."""
    if args.action == "calibrate":
        return cmd_calibrate(args)
    p = config.paths()
    gw = _gateway(p)
    if args.action == "sync":
        if gw is None:
            raise config.ConfigError(f"{p.credentials}: missing; store your OpenRouter key there "
                                     "(docs/INSTALL.md, step 2)")
        live = catalog.sync(gw, p)
        print(f"synced {len(live)} models -> {catalog.cache_file(p)}")
    elif (live := catalog.latest(p, gateway=gw)) is None:
        raise config.ConfigError("no catalog cached yet; run 'aios models sync'")
    show_candidates(live)
    return 0


# --- 3. Spec ------------------------------------------------------------------------------
# From: the spec files on the command line, the spec's own checks and the cached catalog
# To:   the printed per-file verdicts, overlaps, and the routing decision for one spec
def cmd_spec(args: argparse.Namespace) -> int:
    """Validate specs, check each task's name, and report file-grant overlaps between them."""
    specs, problems = [], 0
    for f in args.files:
        try:
            s = spec.load_spec(f)
        except (spec.SpecError, OSError) as e:
            problems += 1
            print(f"FAIL    {e}")
            continue
        specs.append(s)
        problem = spec.name_problem(s, f)
        if problem:
            problems += 1
            print(f"FAIL    {f}: {problem}")
        else:
            print(f"ok      {f}  {s.id}: {s.title}")
    if not args.names:
        for i, a in enumerate(specs):
            for b in specs[i + 1:]:
                for pair in spec.overlaps(a, b):
                    problems += 1
                    print(f"OVERLAP {a.id} / {b.id}: {pair}")
    return 2 if problems else 0


def cmd_route(args: argparse.Namespace) -> int:
    """Classify one spec and run the decision table (ADR-0031). Exit 3 when the router refuses it."""
    s = spec.load_spec(args.file)
    root = config.find_root(Path(args.file).resolve().parent)
    d = run.route(s, config.load_project(root) if root else None)
    answers = d.answers
    if args.json:
        print(json.dumps(d.record(), indent=1))
    else:
        sig = ", ".join(f"{label} {answers[k]['noul']:.2f}" for label, k in
                        (("security", "security_sensitive"), ("irreversible", "irreversible"),
                         ("hardware", "needs_hardware"), ("contract", "contract_change_needed"), ("ambiguity", "ambiguity")))
        print(f"{s.id}: {d.action.upper()}  gate {d.gate}  level {d.level}  "
              f"class {d.task_class} ({d.confidence:.2f}, {d.router})\n  signals: {sig}")
        for role, r in d.roles.items():
            print(f"  {role:<11} {r['model']} [{r['family']}]  score {r['score']:.1f}  "
                  f"~${r['est_usd']:.2f} per task  ({r['why']})")
        for reason in d.reasons:
            print(f"  - {reason}")
    return 0 if d.action == "dispatch" else 3


# --- 4. Main ------------------------------------------------------------------------------
# From: argv (the command line), via argparse
# To:   the chosen subcommand's exit code, or 2 when a known error escapes
def main(argv: list[str] | None = None) -> int:
    """Parse argv, run the chosen subcommand, and return its exit code (2 when a known error escapes)."""
    ap = argparse.ArgumentParser(prog="aios", description="Route each software task to the cheapest model "
                                                          "that gets it merged.")
    ap.add_argument("--version", action="version", version=f"aios {__version__}")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("doctor", help="check this machine is ready (key, router, sandbox, harness, tools)")
    p.add_argument("--fix", action="store_true", help="install what can be installed (the pinned worker harness)")
    p = sub.add_parser("init", help="create .aios/project.toml in the current git repo")
    p.add_argument("--name", help="project name (default: the repo directory name)")
    p.add_argument("--forge", choices=config.FORGES, help="default: github if origin is on github.com, else local")
    p.add_argument("--toolchain", action="append", metavar="NAME=VERSION",
                   help="a toolchain minimum, e.g. node=22 (repeatable; replaces the detected table)")
    p.add_argument("--check", action="append", metavar="CMD", help="a command that verifies changes (repeatable)")
    p = sub.add_parser("models", help="the live catalog candidates for each role and level")
    p.add_argument("action", nargs="?", choices=("sync", "list", "calibrate"),
                   help="sync: fetch + show; list (default): candidates; "
                        "calibrate: judge the known changes before a model may review")
    p.add_argument("models", nargs="*", help="with calibrate: one or more OpenRouter model ids")
    p.add_argument("--repeat", type=int, default=1, metavar="N",
                   help="with calibrate: judgments per case (default 1)")
    p = sub.add_parser("spec", help="validate task specs, check task names, report overlapping file grants")
    p.add_argument("files", nargs="+")
    p.add_argument("--names", action="store_true", help="check task names only; skip the overlap report")
    p = sub.add_parser("route", help="classify a spec and show the routing decision (ADR-0031)")
    p.add_argument("file")
    p.add_argument("--json", action="store_true", help="print the decision record")
    p = sub.add_parser("dispatch", help="route a spec and run the sandboxed worker in a fresh worktree")
    p.add_argument("file")
    p.add_argument("--dry-run", action="store_true", help="show the route and worktree plan only")
    p = sub.add_parser("gate", help="check a dispatched task: the deterministic checks, a cross-family "
                                     "verifier, and the task record")
    p.add_argument("file")
    p = sub.add_parser("fix", help="run the next fix round on a gated task: the ladder picks the model (ADR-0031)")
    p.add_argument("file")
    p.add_argument("--review", metavar="FILE",
                   help="a file with the Lead's review or decision, for a needs_decision verdict")
    p.add_argument("--model", metavar="ID", help="the Lead's model override for this round")
    p = sub.add_parser("approve", help="record the operator's or the Lead's approval on a gated task")
    p.add_argument("file")
    p.add_argument("--by", choices=("operator", "lead"), required=True, help="who is approving")
    p.add_argument("--note", required=True, help="why this is approved (never empty)")
    p.add_argument("--override", help="operator only: why a failing review is overruled (raises the gate to LEAD)")
    p = sub.add_parser("land", help="merge a gated task branch through the forge, then remove its worktree")
    p.add_argument("file")
    p = sub.add_parser("rollback", help="revert a landed task: the revert itself merges through the forge")
    p.add_argument("file")
    p = sub.add_parser("status", help="one line per task: what needs you, what is in flight, what is ready")
    p = sub.add_parser("brief", help="start-of-session summary: the tasks, what landed, and the spend")
    args = ap.parse_args(argv)
    try:
        if args.cmd == "doctor":
            return doctor.main(fix=args.fix)
        if args.cmd == "dispatch":
            return run.dispatch(Path(args.file), dry_run=args.dry_run)
        if args.cmd == "gate":
            return gate.run_gate(Path(args.file))
        if args.cmd == "fix":
            return run.fix(Path(args.file), review=Path(args.review) if args.review else None, model=args.model)
        if args.cmd == "approve":
            return land.approve(Path(args.file), by=args.by, note=args.note, override=args.override)
        if args.cmd == "land":
            return land.land(Path(args.file))
        if args.cmd == "rollback":
            return land.rollback(Path(args.file))
        if args.cmd == "models":
            return cmd_models(args)
        if args.cmd in ("spec", "route"):
            return {"spec": cmd_spec, "route": cmd_route}[args.cmd](args)
        if args.cmd in ("status", "brief"):
            root = config.find_root(Path.cwd())
            if root is None:
                raise config.ConfigError(f"{Path.cwd()}: not inside a project with .aios/project.toml "
                                         "(run 'aios init')")
            return {"status": status.status, "brief": status.brief}[args.cmd](root)
        return cmd_init(args)
    except (config.ConfigError, git.GitError, gateway.GatewayError, spec.SpecError, harness.HarnessError,
            forge.ForgeError, run.SetupError, run.BudgetError, ValueError, OSError) as e:
        print(f"aios: {e}", file=sys.stderr)
        return 2
