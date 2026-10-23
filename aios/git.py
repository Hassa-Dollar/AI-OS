"""Thin git helpers. Every call has a timeout and keeps git's own error text (lessons #2 and #8).

Sections:
  1. Run         a git command -> stdout, or a GitError carrying git's stderr (or a timeout note)
  2. Repo facts  a repo path -> the toplevel, the root commit, the default branch or the remote URL
"""
from __future__ import annotations

import subprocess
from pathlib import Path


class GitError(RuntimeError):
    """A git command failed; the message carries git's stderr."""


# --- 1. Run -------------------------------------------------------------------------------
# From: the caller's git arguments, a working directory and a timeout
# To:   git's stdout, or a GitError with git's own stderr (or a timeout note), for every helper here
def git(args: list[str], cwd: Path, timeout: int = 60) -> str:
    """Runs `git <args>` in `cwd`; returns stdout, and raises GitError on a non-zero exit or a timeout."""
    try:
        p = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        raise GitError(f"git {' '.join(args)} timed out after {timeout}s (in {cwd})") from None
    if p.returncode:
        raise GitError(f"git {' '.join(args)} failed in {cwd}: {(p.stderr or p.stdout).strip()}")
    return p.stdout


# --- 2. Repo facts ------------------------------------------------------------------------
# From: a repo path and, for the branch and URL, a remote's name
# To:   one repo fact (the toplevel, the root commit, the default branch or the remote URL), for the CLI
def toplevel(path: Path) -> Path:
    """The working tree root containing `path` (git rev-parse --show-toplevel)."""
    return Path(git(["rev-parse", "--show-toplevel"], path).strip())


def root_commit(repo: Path) -> str:
    """The repo's first commit (rev-list --max-parents=0 HEAD)."""
    return git(["rev-list", "--max-parents=0", "HEAD"], repo).split()[0]


def default_branch(repo: Path, remote: str = "origin") -> str:
    """The remote's HEAD branch if known, otherwise the branch currently checked out."""
    try:
        return git(["symbolic-ref", "--short", f"refs/remotes/{remote}/HEAD"], repo).strip().split("/", 1)[1]
    except GitError:
        return git(["rev-parse", "--abbrev-ref", "HEAD"], repo).strip()


def remote_url(repo: Path, remote: str = "origin") -> str | None:
    """The remote's URL, or None when the remote is missing."""
    try:
        return git(["remote", "get-url", remote], repo).strip()
    except GitError:
        return None
