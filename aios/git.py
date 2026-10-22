"""Thin git helpers. Every call has a timeout and keeps git's own error text (lessons #2 and #8)."""
from __future__ import annotations

import subprocess
from pathlib import Path


class GitError(RuntimeError):
    """A git command failed; the message carries git's stderr."""


def git(args: list[str], cwd: Path, timeout: int = 60) -> str:
    try:
        p = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        raise GitError(f"git {' '.join(args)} timed out after {timeout}s (in {cwd})") from None
    if p.returncode:
        raise GitError(f"git {' '.join(args)} failed in {cwd}: {(p.stderr or p.stdout).strip()}")
    return p.stdout


def toplevel(path: Path) -> Path:
    return Path(git(["rev-parse", "--show-toplevel"], path).strip())


def root_commit(repo: Path) -> str:
    return git(["rev-list", "--max-parents=0", "HEAD"], repo).split()[0]


def default_branch(repo: Path, remote: str = "origin") -> str:
    """The remote's HEAD branch if known, otherwise the branch currently checked out."""
    try:
        return git(["symbolic-ref", "--short", f"refs/remotes/{remote}/HEAD"], repo).strip().split("/", 1)[1]
    except GitError:
        return git(["rev-parse", "--abbrev-ref", "HEAD"], repo).strip()


def remote_url(repo: Path, remote: str = "origin") -> str | None:
    try:
        return git(["remote", "get-url", remote], repo).strip()
    except GitError:
        return None
