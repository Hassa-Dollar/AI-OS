"""Tests for the forge layer: Local merges a clean checkout, GitHub drives `gh` (faked, never the network)."""
import json
import shutil
import subprocess
import tempfile
import unittest
from unittest import mock

from aios import config, forge, git
from tests.helpers import git_repo

URL = "https://github.com/acme/widget/pull/7"
SHA = "a" * 40
OLD_HEAD = "b" * 40  # the commit a PR still reports right after a push, before GitHub moves its head
NEW_HEAD = "c" * 40  # the head update-branch makes, whose sha the forge cannot know in advance
BODY = "## Verdict\npass. Checks green.\n"


def g(*args, cwd):
    return subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True).stdout.strip()


def proj(root, forge_name="local", default="main", remote="origin"):
    return config.Project(root=root, name="demo", components=(), forge=forge_name, remote=remote,
                          default_branch=default)


def entry(status=None, conclusion=None, context=None, state=None):
    """One statusCheckRollup entry: a CheckRun when `status` is given, else a StatusContext."""
    if status is not None:
        return {"name": context or "ci", "status": status, "conclusion": conclusion}
    return {"context": context, "state": state}


def at(head, view):
    """One poll's response: `view`'s rollup and merge state, reported for the PR head `head`."""
    return {**view, "headRefOid": head}


PENDING = {"statusCheckRollup": [entry(status="IN_PROGRESS"), entry(context="lint", state="PENDING")],
           "mergeStateStatus": "CLEAN"}
PASSED = {"statusCheckRollup": [entry(status="COMPLETED", conclusion="SUCCESS"),
                                entry(context="lint", state="SUCCESS")], "mergeStateStatus": "CLEAN"}
FAILED = {"statusCheckRollup": [entry(status="COMPLETED", conclusion="FAILURE"),
                                entry(context="security", state="FAILURE")], "mergeStateStatus": "CLEAN"}
EMPTY = {"statusCheckRollup": [], "mergeStateStatus": "CLEAN"}
CLEAN = PASSED  # green checks and nothing to do
BEHIND = {"statusCheckRollup": PASSED["statusCheckRollup"], "mergeStateStatus": "BEHIND"}


class FakeGh:
    """A gh that records its calls and replays scripted JSON.

    routes maps a substring of the joined args to a response, a list of responses consumed in order (the last one
    repeats), or a callable(fake, args) run at call time. An exception value is raised rather than returned. A
    rollup that names no head reports `head`, the PR head the test assumes (the pushed branch tip by default).
    """

    def __init__(self, routes, head=SHA):
        self.routes = {k: (list(v) if isinstance(v, list) else [v]) for k, v in routes.items()}
        self.head, self.calls = head, []

    def __call__(self, args, cwd, input=None):
        self.calls.append((tuple(args), cwd, input))
        for key, seq in self.routes.items():
            if key in " ".join(args):
                r = seq.pop(0) if len(seq) > 1 else seq[0]
                if isinstance(r, Exception):
                    raise r
                if isinstance(r, str):
                    return r  # not JSON at all
                r = r(self, args) if callable(r) else r
                return json.dumps(self.headed(r))
        raise AssertionError("unexpected gh call: " + " ".join(args))

    def headed(self, view):
        """A poll response as JSON: a rollup that names no head gets `self.head`."""
        if isinstance(view, dict) and "statusCheckRollup" in view and "headRefOid" not in view:
            return {**view, "headRefOid": self.head}
        return view

    def count(self, sub):
        return sum(1 for args, _, _ in self.calls if sub in " ".join(args))


class Clock:
    """A fake clock whose sleep() advances it, so grace periods (a PR that got no CI run) and the timeout can be rehearsed."""

    def __init__(self, t=0.0, step=forge.GitHub.POLL_S):
        self.now, self.step, self.ticks = t, step, 0

    def sleep(self, _s):
        self.now += self.step
        self.ticks += 1

    def __call__(self):
        return self.now


class Temp(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="aios-forge-")
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)


class LocalTest(Temp):
    def setUp(self):
        super().setUp()
        self.root = git_repo({"README.md": "one\n"})
        self.proj = proj(self.root)
        g("checkout", "-qb", "aios/T-1", cwd=self.root)
        (self.root / "README.md").write_text("one\ntwo\n")
        (self.root / "new.txt").write_text("fresh\n")
        g("add", "-A", cwd=self.root)
        g("commit", "-qm", "task work", cwd=self.root)
        g("checkout", "-q", "main", cwd=self.root)
        self.head = g("rev-parse", "HEAD", cwd=self.root)

    def test_a_clean_main_checkout_gets_a_two_parent_merge(self):
        sha = forge.Local(self.proj).land("aios/T-1", "T-1: add two", BODY)
        self.assertEqual(sha, g("rev-parse", "HEAD", cwd=self.root))
        self.assertNotEqual(sha, self.head)
        self.assertEqual(len(g("rev-list", "--parents", "-n", "1", "HEAD", cwd=self.root).split()), 3)
        self.assertEqual(g("log", "-1", "--format=%B", cwd=self.root), f"T-1: add two\n\n{BODY}".strip())
        self.assertEqual((self.root / "README.md").read_text(), "one\ntwo\n")
        self.assertEqual(g("status", "--porcelain", cwd=self.root), "")

    def test_a_dirty_tree_raises_and_changes_nothing(self):
        (self.root / "scratch.txt").write_text("untracked\n")
        with self.assertRaises(forge.ForgeError) as raised:
            forge.Local(self.proj).land("aios/T-1", "t", BODY)
        self.assertIn("not clean", str(raised.exception))
        self.assertEqual(g("rev-parse", "HEAD", cwd=self.root), self.head)
        self.assertEqual(g("status", "--porcelain", cwd=self.root).splitlines(), ["?? scratch.txt"])

    def test_a_detached_head_raises_even_when_the_default_branch_is_derived(self):
        g("checkout", "-q", "--detach", cwd=self.root)
        with self.assertRaises(forge.ForgeError) as raised:
            forge.Local(proj(self.root, default=None)).land("aios/T-1", "t", BODY)
        self.assertIn("not the default branch", str(raised.exception))
        self.assertEqual(g("status", "--porcelain", cwd=self.root), "")

    def test_the_wrong_branch_raises_and_changes_nothing(self):
        g("checkout", "-qb", "other", cwd=self.root)
        with self.assertRaises(forge.ForgeError) as raised:
            forge.Local(self.proj).land("aios/T-1", "t", BODY)
        self.assertIn("not the default branch", str(raised.exception))
        self.assertEqual(g("rev-parse", "--abbrev-ref", "HEAD", cwd=self.root), "other")
        self.assertEqual(g("rev-parse", "HEAD", cwd=self.root), self.head)

    def test_a_conflict_raises_and_leaves_a_clean_tree(self):
        (self.root / "README.md").write_text("changed on main\n")
        g("commit", "-qam", "main moved", cwd=self.root)
        head = g("rev-parse", "HEAD", cwd=self.root)
        with self.assertRaises(forge.ForgeError) as raised:
            forge.Local(self.proj).land("aios/T-1", "t", BODY)
        self.assertIn("merge conflict", str(raised.exception))
        self.assertEqual(g("status", "--porcelain", cwd=self.root), "")
        self.assertEqual(g("rev-parse", "HEAD", cwd=self.root), head)

    def test_the_message_file_never_lands_in_the_repo(self):
        forge.Local(self.proj).land("aios/T-1", "t", BODY)
        self.assertEqual(sorted(p.name for p in self.root.iterdir()), [".git", "README.md", "new.txt"])


class GitHubTest(Temp):
    def setUp(self):
        super().setUp()
        bare = tempfile.mkdtemp(prefix="aios-bare-", dir=self.tmp) + "/remote.git"
        subprocess.run(["git", "init", "-q", "--bare", bare], check=True)
        self.root = git_repo({"README.md": "one\n"}, remote=bare)
        g("push", "-q", "origin", "main", cwd=self.root)
        self.proj = proj(self.root, forge_name="github")
        g("checkout", "-qb", "aios/T-1", cwd=self.root)
        (self.root / "README.md").write_text("one\ntwo\n")
        g("commit", "-qam", "task work", cwd=self.root)
        g("checkout", "-q", "main", cwd=self.root)
        self.branch_sha = g("rev-parse", "aios/T-1", cwd=self.root)

    def open_pr(self, routes):
        """A PR lookup that first finds nothing, then reports the fresh PR, plus the scripted rest."""
        return {"number,state,url": [forge.ForgeError("no PR yet"), {"number": 7, "state": "OPEN", "url": URL}],
                "pr create": {}, "pr close": {}, "pr reopen": {}, "update-branch": {}, **routes}

    def drive(self, routes, clock=None):
        """A GitHub forge over a scripted gh and a fake clock; the real `git push` talks to the bare remote."""
        gh, clock = FakeGh(routes, head=self.branch_sha), clock or Clock()
        return gh, clock, forge.GitHub(self.proj, gh=gh, sleep=clock.sleep, clock=clock)

    def test_the_happy_path_pushes_creates_merges_and_deletes(self):
        seen = {}

        def merging(fake, args):
            seen["remote"] = g("ls-remote", "origin", "refs/heads/aios/T-1", cwd=self.root)
            return {}

        gh, clock, f = self.drive(self.open_pr({"statusCheckRollup": [PENDING, PASSED], "pr merge": merging,
                                                "mergeCommit": {"mergeCommit": {"oid": SHA}}}))
        self.assertEqual(f.land("aios/T-1", "T-1: title", BODY), SHA)
        create = [c for c in gh.calls if "pr create" in " ".join(c[0])]
        self.assertEqual(len(create), 1)
        self.assertEqual(create[0][2], BODY)  # the body rode on stdin
        joined = " ".join(create[0][0])
        self.assertIn("--body-file", joined)
        self.assertFalse([line for line in BODY.splitlines() if line.strip() and line in joined])
        self.assertEqual(seen["remote"], f"{self.branch_sha}\trefs/heads/aios/T-1")  # the bare repo got the branch
        self.assertEqual(gh.count("pr merge"), 1)
        self.assertEqual({c[1] for c in gh.calls}, {self.root})  # every gh call ran in the project root
        self.assertGreaterEqual(clock.ticks, 1)  # the poller slept between polls
        self.assertNotIn("aios/T-1", g("ls-remote", "origin", cwd=self.root))  # the remote branch was deleted

    def test_an_existing_open_pr_is_reused(self):
        routes = {"number,state,url": {"number": 7, "state": "OPEN", "url": URL},
                  "statusCheckRollup": [PENDING, PASSED], "pr merge": {}, "mergeCommit": {"mergeCommit": {"oid": SHA}}}
        gh, _, f = self.drive(routes)
        self.assertEqual(f.land("aios/T-1", "T-1: title", BODY), SHA)
        self.assertEqual(gh.count("pr create"), 0)
        self.assertEqual(gh.count("pr merge"), 1)

    def test_a_closed_pr_is_replaced_not_reused(self):
        routes = {"number,state,url": [{"number": 5, "state": "CLOSED", "url": URL},
                                       {"number": 8, "state": "OPEN", "url": URL}],
                  "pr create": {}, "statusCheckRollup": [PENDING, PASSED], "pr merge": {},
                  "mergeCommit": {"mergeCommit": {"oid": SHA}}}
        gh, _, f = self.drive(routes)
        self.assertEqual(f.land("aios/T-1", "T-1: title", BODY), SHA)
        self.assertEqual(gh.count("pr create"), 1)
        self.assertEqual(gh.count("pr merge"), 1)

    def test_output_that_is_not_json_raises(self):
        _, _, f = self.drive(self.open_pr({"statusCheckRollup": "oops, not json"}))
        with self.assertRaises(forge.ForgeError) as raised:
            f.land("aios/T-1", "T-1: title", BODY)
        self.assertIn("non-JSON", str(raised.exception))

    def test_a_failed_check_raises_and_never_merges(self):
        gh, _, f = self.drive(self.open_pr({"statusCheckRollup": FAILED}))
        with self.assertRaises(forge.ForgeError) as raised:
            f.land("aios/T-1", "T-1: title", BODY)
        self.assertIn("checks failed: ci, security", str(raised.exception))
        self.assertIn(URL, str(raised.exception))
        self.assertEqual(gh.count("pr merge"), 0)

    def test_no_checks_at_all_is_poked_once_then_merges(self):
        def rollup(fake, args):
            return EMPTY if fake.count("pr reopen") == 0 else PASSED

        routes = self.open_pr({"statusCheckRollup": rollup, "pr merge": {},
                               "mergeCommit": {"mergeCommit": {"oid": SHA}}})
        gh, clock, f = self.drive(routes)
        self.assertEqual(f.land("aios/T-1", "T-1: title", BODY), SHA)
        self.assertEqual(gh.count("pr close"), 1)
        self.assertEqual(gh.count("pr reopen"), 1)
        self.assertGreaterEqual(clock.now, forge.GitHub.GRACE_S)

    def test_no_checks_twice_raises(self):
        gh, _, f = self.drive(self.open_pr({"statusCheckRollup": EMPTY}))
        with self.assertRaises(forge.ForgeError) as raised:
            f.land("aios/T-1", "T-1: title", BODY)
        self.assertIn("no checks reported", str(raised.exception))
        self.assertEqual(gh.count("pr close"), 1)
        self.assertEqual(gh.count("pr reopen"), 1)
        self.assertEqual(gh.count("pr merge"), 0)

    def test_behind_once_updates_the_branch_then_merges(self):
        routes = self.open_pr({"statusCheckRollup": [at(self.branch_sha, BEHIND), at(NEW_HEAD, CLEAN)],
                               "pr merge": {}, "mergeCommit": {"mergeCommit": {"oid": SHA}}})
        gh, _, f = self.drive(routes)
        self.assertEqual(f.land("aios/T-1", "T-1: title", BODY), SHA)
        self.assertEqual(gh.count("update-branch"), 1)
        api = list([c for c in gh.calls if "update-branch" in " ".join(c[0])][0][0])
        self.assertEqual(api[:4], ["api", "-X", "PUT", "repos/acme/widget/pulls/7/update-branch"])
        self.assertEqual(gh.count("pr merge"), 1)

    def test_after_an_update_the_new_head_is_waited_for(self):
        """update-branch answers 202, so a poll can still name the head it is about to replace."""
        routes = self.open_pr({"statusCheckRollup": [at(self.branch_sha, BEHIND), at(self.branch_sha, BEHIND),
                                                     at(NEW_HEAD, PENDING), at(NEW_HEAD, CLEAN)],
                               "pr merge": {}, "mergeCommit": {"mergeCommit": {"oid": SHA}}})
        gh, _, f = self.drive(routes)
        self.assertEqual(f.land("aios/T-1", "T-1: title", BODY), SHA)
        self.assertEqual(gh.count("update-branch"), 1)
        self.assertEqual(gh.count("pr merge"), 1)
        self.assertEqual(gh.count("pr close") + gh.count("pr reopen"), 0)  # no poke when GitHub starts no CI run

    def test_a_reused_pr_waits_for_the_pushed_head_before_reading_checks(self):
        """An open PR still names the previous commit's failed run seconds after a push (lesson 21)."""
        routes = {"number,state,url": {"number": 7, "state": "OPEN", "url": URL},
                  "statusCheckRollup": [at(OLD_HEAD, FAILED), at(self.branch_sha, PENDING),
                                        at(self.branch_sha, CLEAN)],
                  "pr merge": {}, "mergeCommit": {"mergeCommit": {"oid": SHA}}}
        gh, clock, f = self.drive(routes)
        self.assertEqual(f.land("aios/T-1", "T-1: title", BODY), SHA)
        self.assertEqual(gh.count("pr create"), 0)
        self.assertEqual(gh.count("pr merge"), 1)
        self.assertEqual(gh.count("pr close") + gh.count("pr reopen"), 0)  # no poke when GitHub starts no CI run
        self.assertGreaterEqual(clock.ticks, 2)  # it waited the stale head out instead of failing on it

    def test_a_head_that_never_becomes_current_raises(self):
        """GitHub never moved the PR's head off the previous commit: give up at the overall timeout."""
        step = forge.GitHub.TIMEOUT_S / 6
        gh, clock, f = self.drive(self.open_pr({"statusCheckRollup": at(OLD_HEAD, PENDING)}), Clock(step=step))
        with self.assertRaises(forge.ForgeError) as raised:
            f.land("aios/T-1", "T-1: title", BODY)
        self.assertIn("still reports head", str(raised.exception))
        self.assertIn(OLD_HEAD, str(raised.exception))
        self.assertGreater(clock.now, forge.GitHub.TIMEOUT_S)
        self.assertEqual(gh.count("update-branch"), 0)
        self.assertEqual(gh.count("pr merge"), 0)

    def test_waiting_for_the_head_spends_no_no_checks_grace(self):
        """The grace period is for a current head with no checks at all, so a stale poll must not spend it."""
        clock = Clock()
        seen = []

        def rollup(fake, args):
            head = OLD_HEAD if fake.count("statusCheckRollup") <= 3 else self.branch_sha
            seen.append((head, clock.now))  # which head GitHub reported, and when
            return at(head, EMPTY)

        gh, _, f = self.drive(self.open_pr({"statusCheckRollup": rollup}), clock)
        with self.assertRaises(forge.ForgeError) as raised:
            f.land("aios/T-1", "T-1: title", BODY)
        self.assertIn("no checks reported", str(raised.exception))
        self.assertEqual(gh.count("pr close"), 1)  # poked once, but only once the head was current
        became_current = next(t for head, t in seen if head == self.branch_sha)
        # the poke came a full grace after the head became current, and the refusal a full grace after the poke
        self.assertGreaterEqual(clock.now - became_current, 2 * forge.GitHub.GRACE_S)

    def test_behind_twice_raises(self):
        """A BEHIND on a head that has already moved is no stale poll: refuse instead of waiting it out."""
        routes = self.open_pr({"statusCheckRollup": [at(self.branch_sha, BEHIND), at(NEW_HEAD, BEHIND)]})
        gh, _, f = self.drive(routes)
        with self.assertRaises(forge.ForgeError) as raised:
            f.land("aios/T-1", "T-1: title", BODY)
        self.assertIn("still BEHIND after update-branch", str(raised.exception))
        self.assertEqual(gh.count("update-branch"), 1)
        self.assertEqual(gh.count("pr merge"), 0)

    def test_dirty_raises(self):
        dirty = {"statusCheckRollup": PASSED["statusCheckRollup"], "mergeStateStatus": "DIRTY"}
        gh, _, f = self.drive(self.open_pr({"statusCheckRollup": dirty}))
        with self.assertRaises(forge.ForgeError) as raised:
            f.land("aios/T-1", "T-1: title", BODY)
        self.assertIn("DIRTY", str(raised.exception))
        self.assertEqual(gh.count("pr merge"), 0)

    def test_the_overall_timeout_raises(self):
        step = forge.GitHub.TIMEOUT_S / 6
        gh, clock, f = self.drive(self.open_pr({"statusCheckRollup": PENDING}), Clock(step=step))
        with self.assertRaises(forge.ForgeError) as raised:
            f.land("aios/T-1", "T-1: title", BODY)
        self.assertIn("checks still pending after", str(raised.exception))
        self.assertGreater(clock.now, forge.GitHub.TIMEOUT_S)
        self.assertEqual(gh.count("pr merge"), 0)

    def test_a_gone_remote_ref_on_cleanup_is_ignored(self):
        real = forge.git.git
        calls = []

        def flaky(args, cwd, timeout=60):
            calls.append(args)
            if "--delete" in args:
                raise git.GitError("error: unable to delete 'aios/T-1': remote ref does not exist")
            return real(args, cwd, timeout)

        with mock.patch.object(forge.git, "git", flaky):
            gh, _, f = self.drive(self.open_pr({"statusCheckRollup": [PENDING, PASSED], "pr merge": {},
                                                "mergeCommit": {"mergeCommit": {"oid": SHA}}}))
            self.assertEqual(f.land("aios/T-1", "T-1: title", BODY), SHA)
        self.assertTrue(any("--delete" in " ".join(c) for c in calls))

    def test_a_delete_on_merge_rejection_is_ignored(self):
        """GitHub's deleteBranchOnMerge races the cleanup: the push is rejected with `unable to resolve reference`."""
        real = forge.git.git
        calls = []

        def flaky(args, cwd, timeout=60):
            calls.append(args)
            if "--delete" in args:
                raise git.GitError(" ! [remote rejected] aios/T-1 (cannot lock ref 'refs/heads/aios/T-1': "
                                   "unable to resolve reference 'refs/heads/aios/T-1')")
            return real(args, cwd, timeout)

        with mock.patch.object(forge.git, "git", flaky):
            gh, _, f = self.drive(self.open_pr({"statusCheckRollup": [PENDING, PASSED], "pr merge": {},
                                                "mergeCommit": {"mergeCommit": {"oid": SHA}}}))
            self.assertEqual(f.land("aios/T-1", "T-1: title", BODY), SHA)
        self.assertEqual(gh.count("pr merge"), 1)
        self.assertTrue(any("--delete" in " ".join(c) for c in calls))

    def test_any_other_cleanup_failure_raises(self):
        real = forge.git.git

        def flaky(args, cwd, timeout=60):
            if "--delete" in args:
                raise git.GitError("error: failed to push some refs to 'origin'")
            return real(args, cwd, timeout)

        with mock.patch.object(forge.git, "git", flaky):
            gh, _, f = self.drive(self.open_pr({"statusCheckRollup": [PENDING, PASSED], "pr merge": {},
                                                "mergeCommit": {"mergeCommit": {"oid": SHA}}}))
            with self.assertRaises(git.GitError):
                f.land("aios/T-1", "T-1: title", BODY)


class RunGhTest(unittest.TestCase):
    def run_gh(self, p):
        with mock.patch.object(forge.subprocess, "run", return_value=p):
            return forge.run_gh(["pr", "view", "7"], cwd="/tmp")

    def test_stdout_comes_back(self):
        p = mock.Mock(returncode=0, stdout="ok\n", stderr="")
        self.assertEqual(self.run_gh(p), "ok\n")

    def test_a_failure_carries_stderr(self):
        p = mock.Mock(returncode=1, stdout="", stderr="  no auth  ")
        with self.assertRaises(forge.ForgeError) as raised:
            self.run_gh(p)
        self.assertEqual(str(raised.exception), "gh pr view failed: no auth")

    def test_a_timeout_raises(self):
        with mock.patch.object(forge.subprocess, "run", side_effect=subprocess.TimeoutExpired("gh", 120)):
            with self.assertRaises(forge.ForgeError):
                forge.run_gh(["pr", "view", "7"], cwd="/tmp")


class ForProjectTest(Temp):
    def test_picks_the_forge_from_the_project(self):
        self.assertIsInstance(forge.for_project(proj(self.tmp, forge_name="local")), forge.Local)
        gh = FakeGh({})
        got = forge.for_project(proj(self.tmp, forge_name="github"), gh=gh)
        self.assertIsInstance(got, forge.GitHub)
        self.assertIs(got.gh, gh)
        with self.assertRaises(forge.ForgeError):
            forge.for_project(proj(self.tmp, forge_name="gitlab"))


if __name__ == "__main__":
    unittest.main()
