+++
id = "reviewer-token-headroom"
title = "Verifier headroom: max_tokens 16000, and a clear error when reasoning uses up the budget"
files_allowed = ["aios/gate.py", "aios/gateway.py", "tests/test_gate_run.py", "tests/test_gateway.py"]
blast_radius = "medium"
kind = "bugfix"
budget_usd = 0.25
+++

## Goal
Fix a gate failure found gating forge-cleanup-fix. The verifier (`deepseek/deepseek-v4-pro-0813`, served by provider Alibaba)
answered with **empty content**, so the gate stopped with:
```
aios: OpenRouter HTTP 200: deepseek/deepseek-v4-pro-0813 returned non-JSON despite a schema:
```
The Lead diagnosed it with direct calls on the same prompt:

| `max_tokens` | `finish_reason` | completion tokens | reasoning tokens | content |
|---|---|---|---|---|
| 4000 (twice) | `length` | 4000 | 4000 | empty |
| 16000 | `stop` | 2476 | 2387 | a valid verdict |

A reasoning model counts its reasoning against `max_tokens`. With the gate-command value of 4000, this provider spends the
whole budget reasoning. The gate failed closed, which is correct, but it needs headroom, and the error should say what
happened.

## Context
- **Standard library only**; ASCII source; fail loud; match the existing style.
- `aios/gate.py`: `verify()` calls `gw.chat(..., schema=VERDICT_SCHEMA, max_tokens=4000)`.
- `aios/gateway.py`: `Gateway.chat()` reads `r["choices"][0]["message"]["content"]`. With a schema, it parses that as
  JSON and raises `GatewayError(200, "... returned non-JSON despite a schema: ...")` on failure.
  `r["usage"]["completion_tokens_details"]["reasoning_tokens"]` may be present.
- `tests/test_gateway.py` uses the fake HTTP server from `tests/helpers.py`. `tests/test_gate_run.py` asserts the
  `max_tokens` that `verify` passes.

## Required changes
1. **`aios/gate.py`:** add the module constant `VERIFIER_MAX_TOKENS = 16000`, with a one-line comment saying why
   (reasoning counts against it). `verify()` passes it instead of 4000.
2. **`aios/gateway.py`:** in `chat()`, before any JSON parsing, check for a reply whose content is empty **and**
   whose `choices[0].finish_reason` is `"length"`. Raise
   `GatewayError(200, f"{model} used all of max_tokens={max_tokens} before answering (reasoning tokens: <n or ?>); raise max_tokens")`.
3. **`tests/test_gate_run.py`:** the existing assertion expects `gate.VERIFIER_MAX_TOKENS`.
4. **`tests/test_gateway.py`:** add a test where the fake server returns empty content with `finish_reason` `"length"`
   and a `reasoning_tokens` count. `chat(..., schema=...)` must raise a `GatewayError` naming `max_tokens` and that count.

## Acceptance criteria
- `python3 -m unittest discover -s tests -t .` passes.
- `aios/gate.py` stays within 210 non-blank, non-comment lines.

## Out of scope
Any other change: retries, provider pinning, or the verifier prompt.

## Stop conditions
If something above is contradictory or impossible, stop and reply `ESCALATE: <reason>`.
