import contextlib
import io
import json
import unittest

from aios import cli, config, git
from tests.helpers import cwd, git_repo


def run(*argv):
    err = io.StringIO()
    with contextlib.redirect_stderr(err), contextlib.redirect_stdout(io.StringIO()):
        code = cli.main(list(argv))
    return code, err.getvalue()


class Init(unittest.TestCase):
    def test_node_repo(self):
        pkg = json.dumps({"scripts": {"lint": "eslint .", "test": "vitest run", "dev": "x"}})
        root = git_repo({"package.json": pkg}, remote="https://github.com/acme/app.git")
        with cwd(root):
            self.assertEqual(run("init")[0], 0)
        p = config.load_project(root)
        self.assertEqual((p.name, p.forge, p.default_branch), (root.name, "github", "main"))
        self.assertEqual(p.components[0].profile, "node")
        self.assertEqual(p.components[0].checks, ("npm run -s lint", "npm run -s test"))
        self.assertTrue((root / ".aios" / "tasks" / ".gitkeep").exists())
        with cwd(root):
            code, err = run("init")
        self.assertEqual(code, 2)
        self.assertIn("already exists", err)

    def test_requires_a_check_when_undetectable(self):
        root = git_repo()
        with cwd(root):
            code, err = run("init")
            self.assertEqual(code, 2)
            self.assertIn("--check", err)
            self.assertEqual(run("init", "--check", "make test", "--name", "fw")[0], 0)
        p = config.load_project(root)
        self.assertEqual((p.name, p.forge, p.components[0].profile, p.components[0].checks),
                         ("fw", "local", "generic", ("make test",)))

    def test_outside_git_repo(self):
        import tempfile
        with cwd(tempfile.mkdtemp()):
            code, err = run("init", "--check", "x")
        self.assertEqual(code, 2)
        self.assertIn("git", err)


class Git(unittest.TestCase):
    def test_helpers(self):
        root = git_repo(remote="git@example.invalid:x.git")
        self.assertEqual(git.toplevel(root / ".git" / ".."), root.resolve())
        self.assertEqual(len(git.root_commit(root)), 40)
        self.assertEqual(git.default_branch(root), "main")
        self.assertEqual(git.remote_url(root), "git@example.invalid:x.git")
        self.assertIsNone(git.remote_url(root, "nope"))
        with self.assertRaises(git.GitError):
            git.git(["show", "no-such-ref"], root)


if __name__ == "__main__":
    unittest.main()
