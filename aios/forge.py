"""The forge layer (ADR-0030 rule 9): merge a gated task branch into the default branch.

Two forges: `local` (--no-ff into the operator's clean checkout, the one documented exception to rule 5) and
`github` (a PR through the gh CLI, merged once every check is green). Bodies never go on the command line: they
travel through stdin or a temp file outside the repo.
"""
from __future__ import annotations

import json
import re
import subprocess
import tempfile
import time
from pathlib import Path

from . import config, git

GH_TIMEOUT_S = 120


class ForgeError(RuntimeError):
    """A forge operation failed; the message says what failed and where."""


def run_gh(args: list[str], cwd: Path, input: str | None = None) -> str:
    """One `gh` call: stdout back, a non-zero exit or a timeout as ForgeError carrying gh's own text."""
    cmd = " ".join(args[:2])
    try:
        p = subprocess.run(["gh", *args], cwd=cwd, input=input, capture_output=True, text=True, timeout=GH_TIMEOUT_S)
    except subprocess.TimeoutExpired:
        raise ForgeError(f"gh {cmd} timed out after {GH_TIMEOUT_S}s") from None
    if p.returncode:
        raise ForgeError(f"gh {cmd} failed: {(p.stderr or p.stdout).strip()}")
    return p.stdout


def _classify(entry: dict) -> str:
    """One statusCheckRollup entry as PASS | PEND | FAIL (gh 2.46: CheckRuns carry `status`, StatusContexts `state`)."""
    s, st = entry.get("status"), entry.get("state")
    if s is not None:
        if s != "COMPLETED":
            return "PEND"
        return "PASS" if entry.get("conclusion") in ("SUCCESS", "NEUTRAL", "SKIPPED") else "FAIL"
    if st is not None:
        return "PEND" if st in ("PENDING", "EXPECTED") else ("PASS" if st == "SUCCESS" else "FAIL")
    return "FAIL"


def _message(title: str, body: str) -> str:
    """The merge message in a temp file outside the repo (a body never goes on the command line)."""
    with tempfile.NamedTemporaryFile("w", suffix=".aios-msg", delete=False) as f:
        f.write(f"{title}\n\n{body}")
        return f.name


class Local:
    """A local forge: merge in the operator's main checkout, and only into a clean tree."""

    def __init__(self, proj):
        self.proj = proj

    def land(self, branch: str, title: str, body: str) -> str:
        p = self.proj
        default = p.default_branch or git.default_branch(p.root, p.remote)
        here = git.git(["rev-parse", "--abbrev-ref", "HEAD"], p.root).strip()
        if here == "HEAD" or here != default:  # detached HEAD is not the default branch either
            raise ForgeError(f"{p.root}: {here} is checked out, not the default branch {default}; aios never switches")
        if git.git(["status", "--porcelain"], p.root).strip():
            raise ForgeError(f"{p.root}: the tree is not clean; commit or clean it first (aios never stashes)")
        tmp = _message(title, body)
        try:
            try:
                git.git(["merge", "--no-ff", "--file", tmp, branch], p.root)
            except git.GitError as e:
                try:
                    git.git(["merge", "--abort"], p.root)
                except git.GitError:
                    pass
                raise ForgeError(f"{branch}: merge conflict or failure; the tree is clean again: {e}") from None
        finally:
            Path(tmp).unlink(missing_ok=True)
        return git.git(["rev-parse", "HEAD"], p.root).strip()


class GitHub:
    """A GitHub forge: push the branch, open or reuse its PR, wait for green checks, merge, delete the branch."""

    POLL_S, GRACE_S, TIMEOUT_S = 15, 90, 3600

    def __init__(self, proj, *, gh=run_gh, sleep=time.sleep, clock=time.monotonic):
        self.proj, self.gh, self.sleep, self.clock = proj, gh, sleep, clock

    def land(self, branch: str, title: str, body: str) -> str:
        p = self.proj
        git.git(["push", "--quiet", p.remote, f"{branch}:{branch}"], p.root)
        n, url = self._open_pr(branch, p.default_branch or git.default_branch(p.root, p.remote), title, body)
        started, retriggered, updated = self.clock(), False, None
        while True:
            v = self._view(n, "statusCheckRollup,mergeStateStatus")
            rollup = v.get("statusCheckRollup") or []
            if bad := [e.get("name") or e.get("context") or "?" for e in rollup if _classify(e) == "FAIL"]:
                raise ForgeError(f"checks failed: {', '.join(bad)}  {url}")
            if rollup and all(_classify(e) == "PASS" for e in rollup):
                state = v.get("mergeStateStatus") or ""
                if state == "BEHIND":
                    if updated is not None and self.clock() - updated > self.GRACE_S:
                        raise ForgeError(f"PR {n} is still BEHIND after update-branch: {url}")
                    if updated is not None:  # update-branch is async: a poll can still name the old head
                        self.sleep(self.POLL_S)
                        continue
                    updated, started = self.clock(), self.clock()  # a new head: its own grace and timeout
                    self.gh(["api", "-X", "PUT", f"repos/{self._slug(url)}/pulls/{n}/update-branch"], p.root)
                    self.sleep(self.POLL_S)
                    continue
                return self._merge(n, url, branch, state == "DIRTY")
            if self.clock() - started > self.TIMEOUT_S:
                raise ForgeError(f"checks still pending after {self.TIMEOUT_S}s: {url}")
            if not rollup and self.clock() - started >= self.GRACE_S:
                if retriggered:
                    raise ForgeError(f"no checks reported for PR {n} after {self.GRACE_S}s: {url}")
                retriggered = True
                self.gh(["pr", "close", str(n)], p.root)  # BUG-14: GitHub spawned no run; poke it once
                self.gh(["pr", "reopen", str(n)], p.root)
                started = self.clock()
            self.sleep(self.POLL_S)

    def _merge(self, n: int, url: str, branch: str, dirty: bool) -> str:
        if dirty:
            raise ForgeError(f"PR {n} has conflicts (mergeStateStatus DIRTY): {url}")
        p = self.proj
        self.gh(["pr", "merge", str(n), "--merge"], p.root)
        oid = (self._view(n, "mergeCommit").get("mergeCommit") or {}).get("oid", "")
        if not oid:
            raise ForgeError(f"PR {n}: no merge commit after the merge: {url}")
        try:
            git.git(["push", "--quiet", p.remote, "--delete", branch], p.root)
        except git.GitError as e:
            # GitHub's deleteBranchOnMerge can delete the head branch first (PR #106); either refusal means gone.
            if not ("remote ref does not exist" in str(e) or "unable to resolve reference" in str(e)):
                raise
        return oid

    def _open_pr(self, branch: str, default: str, title: str, body: str) -> tuple[int, str]:
        try:
            v = self._view(branch, "number,state,url")
            if v.get("state") == "OPEN":
                return int(v["number"]), v.get("url", "")
        except ForgeError:
            pass
        self.gh(["pr", "create", "--base", default, "--head", branch, "--title", title, "--body-file", "-"],
                self.proj.root, input=body)  # the body rides on stdin, never on the command line
        v = self._view(branch, "number,state,url")
        if v.get("state") != "OPEN":
            raise ForgeError(f"{branch}: no open PR after `gh pr create`: {v.get('url', '')}")
        return int(v["number"]), v.get("url", "")

    def _view(self, ref: str, fields: str) -> dict:
        out = self.gh(["pr", "view", str(ref), "--json", fields], self.proj.root)
        try:
            return json.loads(out)
        except ValueError:
            raise ForgeError(f"gh pr view {ref}: non-JSON output: {out[:200]}") from None

    def _slug(self, url: str) -> str:
        if m := re.search(r"github\.com[/:]([^/]+)/([^/?#]+)", url or ""):
            return f"{m[1]}/{m[2]}"
        try:
            return json.loads(self.gh(["repo", "view", "--json", "nameWithOwner"], self.proj.root))["nameWithOwner"]
        except (ForgeError, KeyError, ValueError):
            raise ForgeError(f"cannot tell owner/repo from {url!r}") from None


def for_project(proj, **kw):
    """The forge a project is configured for; anything else is a configuration error."""
    if proj.forge == "local":
        return Local(proj)
    if proj.forge == "github":
        return GitHub(proj, **kw)
    raise ForgeError(f"{proj.root}: forge {proj.forge!r} is not one of {', '.join(config.FORGES)}")
