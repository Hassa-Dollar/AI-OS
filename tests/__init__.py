"""Test package. Lesson #10: tests never touch real state, so HOME and XDG dirs point at a throwaway directory."""
import os
import tempfile

_SANDBOX = tempfile.mkdtemp(prefix="aios-tests-")
for _var, _sub in (("HOME", "home"), ("XDG_CONFIG_HOME", "config"), ("XDG_CACHE_HOME", "cache"),
                   ("XDG_STATE_HOME", "state"), ("XDG_DATA_HOME", "data")):
    os.environ[_var] = os.path.join(_SANDBOX, _sub)
    os.makedirs(os.environ[_var], exist_ok=True)
