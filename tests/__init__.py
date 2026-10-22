"""Test package.

Lesson #10: tests never touch real state, so HOME and the XDG dirs point at a throwaway directory (_SANDBOX).
H1: tests must not leak temp dirs either, so every temp dir -- made here, by a test module, or by a
subprocess a test starts -- is redirected into <_SANDBOX>/tmp, and _SANDBOX is deleted on interpreter exit.
"""
import atexit
import os
import shutil
import tempfile

_SANDBOX = tempfile.mkdtemp(prefix="aios-tests-")  # the real system temp dir, cleaned up on exit
_TMP = os.path.join(_SANDBOX, "tmp")
os.makedirs(_TMP, exist_ok=True)
tempfile.tempdir = _TMP
os.environ["TMPDIR"] = _TMP
atexit.register(shutil.rmtree, _SANDBOX, ignore_errors=True)

for _var, _sub in (("HOME", "home"), ("XDG_CONFIG_HOME", "config"), ("XDG_CACHE_HOME", "cache"),
                   ("XDG_STATE_HOME", "state"), ("XDG_DATA_HOME", "data")):
    os.environ[_var] = os.path.join(_SANDBOX, _sub)
    os.makedirs(os.environ[_var], exist_ok=True)
