"""The `aios` command line."""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from . import __version__, catalog, config, doctor, gateway, git

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
profile = "{profile}"
checks = {checks}

[budget]
per_task_usd = 1.0
per_day_usd = 5.0

[privacy]
data_collection = "deny"       # never route code to providers that train on it
zdr = false
deny_vendors = []
max_tier = "T3"

[routing]
frontier_auto = false          # the escalation ladder never climbs to frontier models on its own
"""


def detect_checks(root: Path) -> tuple[str, list[str]]:
    """Guess the profile and the commands that prove a change works. Returns ("", []) when unsure."""
    pkg = root / "package.json"
    if pkg.is_file():
        scripts = json.loads(pkg.read_text(encoding="utf-8")).get("scripts", {})
        return "node", [f"npm run -s {s}" for s in ("lint", "typecheck", "test") if s in scripts]
    if (root / "pyproject.toml").is_file() or (root / "tests").is_dir():
        return "python", ["python3 -m unittest discover -s tests -t ."]
    return "", []


def cmd_init(args: argparse.Namespace) -> int:
    root = git.toplevel(Path.cwd())
    target = root / ".aios" / "project.toml"
    if target.exists():
        raise config.ConfigError(f"{target}: already exists")
    profile, checks = detect_checks(root)
    profile = args.profile or profile or "generic"
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
                                              profile=profile, checks=json.dumps(checks)), encoding="utf-8")
    config.load_project(root)  # never leave behind a config that would not load
    print(f"wrote {target.relative_to(root)} (profile {profile}, forge {forge}); review it, then commit .aios/")
    return 0


def cmd_models(args: argparse.Namespace) -> int:
    p = config.paths()
    roster = catalog.load_roster()
    if args.action == "sync":
        gw = gateway.Gateway(config.load_key(p), base=os.environ.get("AIOS_OPENROUTER_URL", gateway.BASE))
        live = catalog.sync(gw, p)
        print(f"synced {len(live)} models -> {catalog.cache_file(p)}")
    elif (live := catalog.latest(p)) is None:
        raise config.ConfigError("no catalog cached yet; run 'aios models sync'")
    by_id = {m["id"]: m for m in live}
    d = catalog.diff(roster, live)
    blocked = {e.id for e, _ in d.suspended} | {e.id for e in d.missing}
    if args.action in ("sync", "list"):
        for e in roster:
            pin, pout = catalog.price_per_m(by_id[e.id]) if e.id in by_id else (0.0, 0.0)
            print(f"{e.tier} {e.id:<34} {e.family:<11} ${pin:>5.2f}/${pout:<6.2f}/M {','.join(e.roles):<17} "
                  f"{'SUSPENDED' if e.id in blocked else 'ok':<9} {e.note}")
    if args.action in ("sync", "diff"):
        for e, slug in d.suspended:
            print(f"SUSPENDED {e.id}: now {slug}, pinned {e.canonical_slug}; re-probe before re-admitting")
        for e in d.missing:
            print(f"MISSING   {e.id}: no longer in the catalog")
        for e, when in d.expiring:
            print(f"EXPIRING  {e.id}: {when}")
        for m in d.new[:20]:
            pin, pout = catalog.price_per_m(m)
            print(f"NEW       {m['id']:<40} ${pin:.2f}/${pout:.2f}/M  (admit via a roster PR + probe)")
    return 1 if blocked else 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="aios", description="Route each software task to the cheapest model "
                                                          "that gets it merged.")
    ap.add_argument("--version", action="version", version=f"aios {__version__}")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("doctor", help="check this machine is ready (key, router, sandbox, tools)")
    p = sub.add_parser("init", help="create .aios/project.toml in the current git repo")
    p.add_argument("--name", help="project name (default: the repo directory name)")
    p.add_argument("--forge", choices=config.FORGES, help="default: github if origin is on github.com, else local")
    p.add_argument("--profile", help="stack profile (default: detected)")
    p.add_argument("--check", action="append", metavar="CMD", help="a command that verifies changes (repeatable)")
    p = sub.add_parser("models", help="the model roster vs the live OpenRouter catalog")
    p.add_argument("action", choices=("sync", "list", "diff"), help="sync: fetch + show; list: roster; diff: changes")
    args = ap.parse_args(argv)
    try:
        if args.cmd == "doctor":
            return doctor.main()
        if args.cmd == "models":
            return cmd_models(args)
        return cmd_init(args)
    except (config.ConfigError, git.GitError, gateway.GatewayError) as e:
        print(f"aios: {e}", file=sys.stderr)
        return 2
