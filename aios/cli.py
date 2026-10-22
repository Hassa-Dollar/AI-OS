"""The `aios` command line."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import __version__, config, doctor, git

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
    args = ap.parse_args(argv)
    try:
        if args.cmd == "doctor":
            return doctor.main()
        return cmd_init(args)
    except (config.ConfigError, git.GitError) as e:
        print(f"aios: {e}", file=sys.stderr)
        return 2
