"""Harness bake-off: OpenCode (free, MIT) vs mini-swe-agent on real tasks.

Tasks: SH-1, SH-2 (Shrink API gaps) and AI-1 (aios/spec.py). Models: GLM-5.3, DeepSeek V4 Pro via one OpenRouter key.
Each run gets a fresh workspace copy, a sandbox, a wall-clock cap; it is scored by hidden acceptance checks the
agent never sees, plus the project's own checks. Real cost = OpenRouter /key usage delta (runs are sequential).

usage: python3 -I bakeoff.py prep | validate | run [TASK...] | report
"""
import json, os, re, shutil, subprocess, sys, time, tomllib, urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent
RUNS, TASKS_DIR, ACCEPT = ROOT / "runs", ROOT / "tasks", ROOT / "accept"
H = Path.home()
NODE_DIR = (H / ".local/share/aios/toolchains/node22").resolve()
NODE_BIN = NODE_DIR / "bin"
OC_DIR = (H / ".local/share/aios/toolchains/opencode").resolve()
MINI = H / ".local/share/aios/harness-mswea/bin/mini"
MINI_YAML = next((H / ".local/share/aios/harness-mswea/lib").glob("python3*/site-packages/minisweagent/config/mini.yaml"))
KEY = (H / ".config/aios/credentials").read_text().strip()
REPO = {"SH-1": "shrink", "SH-2": "shrink", "AI-1": "aios"}
SRC = {"shrink": H / "projects/shrink", "aios": H / "projects/AI-OS"}
MODELS = os.environ.get("BAKEOFF_MODELS", "z-ai/glm-5.3,deepseek/deepseek-v4-pro").split(",")
HARNESSES = os.environ.get("BAKEOFF_HARNESSES", "opencode,mini").split(",")
WALL_S = 25 * 60
SYS_RO = ["--ro-bind", "/usr", "/usr", "--ro-bind", "/bin", "/bin", "--ro-bind", "/lib", "/lib",
          "--ro-bind", "/lib64", "/lib64", "--ro-bind", "/etc", "/etc", "--tmpfs", "/tmp", "--proc", "/proc",
          "--dev", "/dev", "--new-session", "--die-with-parent", "--unshare-pid"]
PROTOCOL = """You are working in a git repository (your current directory). Implement the task specified below.
Rules:
- Modify only files listed in files_allowed (an entry ending in '/' grants that whole directory).
- Do not add dependencies unless listed in deps_preapproved. Do not install packages: there is no network.
- Do not run git commands that change state (commit, checkout, reset, stash, push); your changes are committed for you.
- Run the checks named in the acceptance criteria and make them pass before you finish.
- If the task cannot be done within these rules, or the spec is ambiguous in a way that blocks you, stop and reply
  with a line starting "ESCALATE:" and the reason.
- When done, reply with a short summary of what you changed.
"""


def sh(cmd, cwd=None, env=None, timeout=900):
    p = subprocess.run(cmd, cwd=cwd, env=env, timeout=timeout, capture_output=True, text=True, errors="replace")
    return p.returncode, p.stdout + p.stderr


def node_env(extra=None):
    e = {"PATH": f"{NODE_BIN}:/usr/bin:/bin", "HOME": str(H), "LANG": "C.UTF-8"}
    return e | (extra or {})


def key_usage():
    r = urllib.request.Request("https://openrouter.ai/api/v1/key", headers={"Authorization": "Bearer " + KEY})
    return float(json.load(urllib.request.urlopen(r, timeout=30))["data"]["usage"])


def spec_of(task):
    text = (TASKS_DIR / f"{task}.md").read_text()
    return text, tomllib.loads(text.split("+++")[1])


def allowed(grants, path):
    return any(path == g or (g.endswith("/") and path.startswith(g)) for g in grants)


def prep():
    RUNS.mkdir(exist_ok=True)
    for name, src in SRC.items():
        tpl = RUNS / f"_tpl_{name}"
        if tpl.exists():
            continue
        sh(["git", "clone", "-q", str(src), str(tpl)])
        if name == "shrink":
            rc, out = sh(["npm", "ci", "--no-audit", "--no-fund"], cwd=tpl / "components/api", env=node_env())
            print(f"npm ci shrink/api rc={rc}", out[-300:] if rc else "")
        print("template", tpl, sh(["git", "-C", str(tpl), "rev-parse", "--short", "HEAD"])[1].strip())


def workspace(task, run_id):
    ws = RUNS / run_id / "ws"
    if ws.exists():
        shutil.rmtree(ws)
    shutil.copytree(RUNS / f"_tpl_{REPO[task]}", ws, symlinks=True)
    return ws


def task_text(task, ws):
    text, _ = spec_of(task)
    agents = (ws / "AGENTS.md").read_text() if (ws / "AGENTS.md").exists() else ""
    return f"{PROTOCOL}\n## Repository rules (AGENTS.md)\n{agents}\n## Task spec\n{text}"


def run_opencode(ws, model, text, out):
    cfg = {"$schema": "https://opencode.ai/config.json", "autoupdate": False, "share": "disabled",
           "provider": {"openrouter": {"options": {"apiKey": "{env:OPENROUTER_API_KEY}"},
                                       "models": {m: {"options": {"provider": {"data_collection": "deny"}}} for m in MODELS}}},
           "permission": {"edit": "allow", "read": "allow", "glob": "allow", "grep": "allow", "list": "allow",
                          "lsp": "allow", "todowrite": "allow", "task": "allow", "skill": "deny", "question": "deny",
                          "webfetch": "deny", "websearch": "deny", "external_directory": "deny", "doom_loop": "deny",
                          "bash": {"*": "allow", "git push*": "deny", "git commit*": "deny", "git checkout*": "deny",
                                   "git reset*": "deny", "git stash*": "deny", "curl *": "deny", "wget *": "deny",
                                   "npm install*": "deny", "npm i *": "deny"}}}
    env = {"PATH": f"{NODE_BIN}:{OC_DIR}:/usr/bin:/bin", "HOME": "/tmp/home", "LANG": "C.UTF-8",
           "OPENROUTER_API_KEY": KEY, "OPENCODE_CONFIG_CONTENT": json.dumps(cfg),
           "OPENCODE_DISABLE_AUTOUPDATE": "1", "OPENCODE_DISABLE_CLAUDE_CODE": "1", "OPENCODE_DISABLE_LSP_DOWNLOAD": "1"}
    cmd = ["bwrap", "--unshare-user-try", *SYS_RO, "--ro-bind", "/mnt/wsl/resolv.conf", "/mnt/wsl/resolv.conf",
           "--dir", "/tmp/home", "--ro-bind", str(NODE_DIR), str(NODE_DIR), "--ro-bind", str(OC_DIR), str(OC_DIR),
           "--bind", str(ws), str(ws), "--ro-bind", str(out / "TASK.md"), str(out / "TASK.md"), "--chdir", str(ws),
           str(OC_DIR / "opencode"), "run", "--pure", "--auto", "--format", "json", "-m", f"openrouter/{model}",
           "--dir", str(ws), "Implement the task described in the attached TASK.md, following its rules exactly.",
           "-f", str(out / "TASK.md")]
    with open(out / "events.jsonl", "w") as f, open(out / "stderr.log", "w") as e:
        p = subprocess.run(cmd, env=env, stdout=f, stderr=e, stdin=subprocess.DEVNULL, timeout=WALL_S)
    steps, cost, toks, final = 0, 0.0, 0, ""
    for line in (out / "events.jsonl").read_text(errors="replace").splitlines():
        try:
            ev = json.loads(line)
        except json.JSONDecodeError:
            continue
        part = ev.get("part") or {}
        if ev.get("type") == "step_finish":
            steps += 1
            cost += float(part.get("cost") or 0)
            t = part.get("tokens") or {}
            toks += int(t.get("input") or 0) + int(t.get("output") or 0) + int(t.get("reasoning") or 0)
        elif ev.get("type") == "text":
            final = part.get("text") or final
    return {"rc": p.returncode, "steps": steps, "harness_cost": round(cost, 5), "tokens": toks, "final": final[-600:]}


def run_mini(ws, model, text, out):
    wrapper = ["--unshare-user-try", *SYS_RO, "--unshare-net", "--ro-bind", str(NODE_DIR), str(NODE_DIR)]
    tmpl = json.loads(subprocess.run([str(MINI.parent / "python"), "-c",
        "import yaml,json,sys;print(json.dumps(yaml.safe_load(open(sys.argv[1]))['agent']['instance_template']))",
        str(MINI_YAML)], capture_output=True, text=True, check=True).stdout)
    assert "{{task}}" in tmpl
    tmpl = tmpl.replace("{{task}}", "\n{% raw %}" + text + "{% endraw %}\n")
    cfg = {"agent": {"step_limit": 60, "cost_limit": 0.75, "mode": "yolo", "instance_template": tmpl},
           "model": {"model_class": "openrouter", "model_name": model,
                     "model_kwargs": {"provider": {"data_collection": "deny"}}},
           "environment": {"environment_class": "bubblewrap", "cwd": str(ws), "timeout": 180, "wrapper_args": wrapper,
                           "env": {"PATH": f"{NODE_BIN}:/usr/local/bin:/usr/bin:/bin", "HOME": "/tmp", "PAGER": "cat",
                                   "MANPAGER": "cat", "LESS": "-R", "PIP_PROGRESS_BAR": "off", "TQDM_DISABLE": "1"}}}
    (out / "mini_cfg.yaml").write_text(json.dumps(cfg))  # YAML is a superset of JSON
    (out / "mswea").mkdir(exist_ok=True)
    env = {"PATH": "/usr/bin:/bin", "HOME": str(out), "LANG": "C.UTF-8", "OPENROUTER_API_KEY": KEY,
           "MSWEA_GLOBAL_CONFIG_DIR": str(out / "mswea"), "MSWEA_CONFIGURED": "true"}
    cmd = [str(MINI), "-c", str(MINI_YAML), "-c", str(out / "mini_cfg.yaml"), "-t", "(see task above)", "-y", "--exit-immediately",
           "-o", str(out / "traj.json")]
    with open(out / "stdout.log", "w") as f:
        p = subprocess.run(cmd, env=env, stdout=f, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL, timeout=WALL_S)
    traj = json.loads((out / "traj.json").read_text()) if (out / "traj.json").exists() else {}
    info, msgs = traj.get("info", {}), traj.get("messages", [])
    stats = info.get("model_stats", {})
    final = next((m.get("content") or "" for m in reversed(msgs) if m.get("role") == "assistant"), "")
    return {"rc": p.returncode, "steps": stats.get("api_calls", sum(m.get("role") == "assistant" for m in msgs)),
            "harness_cost": round(float(stats.get("instance_cost") or 0), 5), "exit_status": info.get("exit_status"),
            "final": str(final)[-600:]}


def evaluate(task, ws):
    _, front = spec_of(task)
    rc, out = sh(["git", "status", "--porcelain", "--untracked-files=all"], cwd=ws)
    changed = sorted({ln[3:].split(" -> ")[-1] for ln in out.splitlines() if ln.strip()})
    res = {"changed": changed, "out_of_scope": [p for p in changed if not allowed(front["files_allowed"], p)]}
    sh(["git", "add", "-A"], cwd=ws)
    res["diff_lines"] = sh(["git", "diff", "--cached", "--numstat"], cwd=ws)[1].count("\n")
    (ws.parent / "diff.patch").write_text(sh(["git", "diff", "--cached"], cwd=ws)[1])
    sh(["git", "reset", "-q"], cwd=ws)
    if REPO[task] == "shrink":
        api = ws / "components/api"
        # same checks the agents were told to run; npm audit (network, can hang) is not task-discriminative here
        rc, out = sh(["bash", "-c", "npm run -s lint && npm run -s typecheck && npm run -s test && npm run -s coverage"],
                     cwd=api, env=node_env(), timeout=900)
        res["project_checks"] = rc == 0
        res["project_checks_tail"] = out[-400:] if rc else ""
        if task == "SH-1":
            rc, out = sh(["bash", str(ACCEPT / "sh1_check.sh"), str(ws), str(NODE_BIN)], timeout=300)
        else:
            dst = api / "src/sh2_cors.acceptance.test.ts"
            shutil.copy(ACCEPT / "sh2_cors.acceptance.test.ts", dst)
            rc, out = sh(["npx", "vitest", "run", "src/sh2_cors.acceptance.test.ts"], cwd=api, env=node_env(), timeout=300)
            dst.unlink()
    else:
        rc, out = sh([sys.executable, "-I", "-m", "unittest", "discover", "-s", "tests", "-t", "."], cwd=ws)
        res["project_checks"] = rc == 0
        res["project_checks_tail"] = out[-400:] if rc else ""
        src = ws / "aios/spec.py"
        res["loc"] = sum(1 for l in src.read_text().splitlines() if l.strip() and not l.strip().startswith("#")) if src.exists() else None
        shutil.copy(ACCEPT / "test_spec_acceptance.py", ws / "_acceptance_hidden.py")
        rc, out = sh([sys.executable, "-m", "unittest", "-v", "_acceptance_hidden"], cwd=ws)
        (ws / "_acceptance_hidden.py").unlink()
    res["acceptance"] = rc == 0
    res["acceptance_detail"] = "\n".join(l for l in out.splitlines() if re.search(r"PASS|FAIL|ERROR|ok$|Tests|passed|failed|Ran ", l))[-1500:]
    loc_ok = res.get("loc") is None or res["loc"] <= 220
    res["pass"] = res["acceptance"] and res["project_checks"] and not res["out_of_scope"] and loc_ok
    return res


def run(tasks):
    results_file = ROOT / "results.json"
    results = json.loads(results_file.read_text()) if results_file.exists() else {}
    for task in tasks:
        for model in MODELS:
            for harness in HARNESSES:
                run_id = f"{task}__{harness}__{model.split('/')[1]}"
                if run_id in results:
                    continue
                ws = workspace(task, run_id)
                out = ws.parent
                print(f"\n=== {run_id}", flush=True)
                u0, t0 = key_usage(), time.time()
                text = task_text(task, ws)
                (out / "TASK.md").write_text(text)
                try:
                    r = (run_opencode if harness == "opencode" else run_mini)(ws, model, text, out)
                except subprocess.TimeoutExpired:
                    r = {"rc": "timeout"}
                time.sleep(15)  # let usage accounting settle
                r |= {"task": task, "harness": harness, "model": model, "secs": round(time.time() - t0),
                      "real_cost": round(key_usage() - u0, 5)}
                r |= evaluate(task, ws)
                logs = " ".join(f.read_text(errors="replace") for f in out.glob("*") if f.suffix in (".jsonl", ".log", ".json") and f.is_file())
                r["pii_block"] = "PII detected" in logs  # OpenRouter Sensitive-Info guardrail: infra, not harness
                results[run_id] = r
                results_file.write_text(json.dumps(results, indent=1))
                print(json.dumps({k: r.get(k) for k in ("pass", "acceptance", "project_checks", "out_of_scope",
                                                        "real_cost", "harness_cost", "steps", "secs", "rc")}), flush=True)


def reeval(run_ids):
    """Re-score finished runs from their saved workspace + logs (the agent is not re-run)."""
    results_file = ROOT / "results.json"
    results = json.loads(results_file.read_text()) if results_file.exists() else {}
    full = {m.split("/", 1)[1]: m for m in ("z-ai/glm-5.3", "deepseek/deepseek-v4-pro")}
    for run_id in run_ids:
        task, harness, short = run_id.split("__")
        out = RUNS / run_id
        r = results.get(run_id, {"task": task, "harness": harness, "model": full[short]})
        if harness == "mini":
            traj = json.loads((out / "traj.json").read_text())
            info, stats = traj.get("info", {}), traj.get("info", {}).get("model_stats", {})
            r |= {"steps": stats.get("api_calls"), "harness_cost": round(float(stats.get("instance_cost") or 0), 5),
                  "exit_status": info.get("exit_status"),
                  "secs": round((out / "traj.json").stat().st_mtime - (out / "TASK.md").stat().st_mtime)}
            r.setdefault("real_cost", r["harness_cost"])  # mini records OpenRouter's exact usage.cost per call
            r.setdefault("rc", 0)
        r |= evaluate(task, out / "ws")
        results[run_id] = r
        results_file.write_text(json.dumps(results, indent=1))
        print(run_id, json.dumps({k: r.get(k) for k in ("pass", "acceptance", "project_checks", "out_of_scope",
                                                        "real_cost", "steps", "secs", "exit_status")}))


def report():
    results = json.loads((ROOT / "results.json").read_text())
    rows = sorted(results.values(), key=lambda r: (r["task"], r["model"], r["harness"]))
    print(f"{'task':<5} {'model':<22} {'harness':<9} {'pass':<5} {'acc':<5} {'chk':<5} {'$real':>8} {'steps':>5} {'secs':>5}")
    for r in rows:
        print(f"{r['task']:<5} {r['model']:<22} {r['harness']:<9} {str(r['pass']):<5} {str(r['acceptance']):<5} "
              f"{str(r['project_checks']):<5} {r['real_cost']:>8.4f} {r.get('steps', 0):>5} {r['secs']:>5}")
    for h in HARNESSES:
        rs = [r for r in rows if r["harness"] == h]
        solved = sum(r["pass"] for r in rs)
        spend = sum(r["real_cost"] for r in rs)
        print(f"{h:<9} solved {solved}/{len(rs)}  spend ${spend:.4f}  $/solved {spend / solved if solved else float('inf'):.4f}  "
              f"median secs {sorted(r['secs'] for r in rs)[len(rs) // 2]}")


def validate():
    """Acceptance checks must FAIL on the untouched base (otherwise they don't measure the task)."""
    for task in REPO:
        ws = workspace(task, f"_base_{task}")
        print(task, json.dumps({k: v for k, v in evaluate(task, ws).items() if k != "project_checks_tail"}, indent=1))


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "report"
    if cmd == "reeval":
        reeval(sys.argv[2:])
    else:
        {"prep": prep, "validate": validate, "report": report}.get(cmd, lambda: run(sys.argv[2:] or list(REPO)))()
