+++
id = "D1e"
title = "Gateway: a structured call whose reasoning used up max_tokens is retried once without reasoning"
files_allowed = ["aios/gateway.py", "tests/test_gateway.py"]
depends_on = ["D1d"]
blast_radius = "medium"
kind = "bugfix"
budget_usd = 0.25
+++

## Goal
The gate is blocked by a verifier provider that keeps reasoning until it runs out of tokens. Gating D2b (a 32 KB
prompt), `deepseek/deepseek-v4-pro-0813` on provider Alibaba used **all** of `max_tokens=16000` on reasoning, and
D1d's error said so.

The Lead measured the reasoning controls on that same prompt:

| Request | Provider | `finish_reason` | Reasoning tokens | Time | Cost | Verdict |
|---|---|---|---|---|---|---|
| `reasoning.effort = "low"` | Alibaba | `length` | 16000 | 204 s | $0.0335 | none |
| `reasoning.max_tokens = 6000` | Alibaba | `length` | 16000 | 196 s | $0.0287 | none |
| `reasoning.enabled = false` | Wafer | `stop` | 0 | 2 s | $0.0032 | pass (medium) |

That provider ignores reasoning budgets. When it happens, a structured call should fall back once to no reasoning.

## Context
- **Standard library only**; ASCII source; fail loud; match the existing style.
- `aios/gateway.py`, `Gateway.chat(model, messages, *, schema=None, max_tokens=None, reasoning=None)`:
  - `reasoning` currently sends `"reasoning": {"effort": reasoning}`;
  - D1d raises `GatewayError(200, "... used all of max_tokens=... before answering (reasoning tokens: ...); raise max_tokens")`
    when the content is empty and `finish_reason == "length"`;
  - the result dict has `usd` (`usage.cost`).
- `tests/test_gateway.py` uses the fake HTTP server from `tests/helpers.py`, which can script several replies.

## Required changes
1. **`reasoning="off"`** sends `"reasoning": {"enabled": False}`. Any other non-empty string still sends
   `{"effort": reasoning}`.
2. **Fallback.** A call **with `schema`** whose reply hits the D1d case (empty content, `finish_reason == "length"`)
   is retried **once**, with the same arguments and `reasoning="off"`. This applies only when `reasoning` was not
   already `"off"`.
   - The returned dict's `usd` is the sum of **both** calls' `usage.cost`, so records stay honest.
   - The returned dict gains `"reasoning_fallback": True`.
   - If the retry hits the D1d case too, raise D1d's `GatewayError`, with its message unchanged.
   - Calls **without** `schema` are unchanged: they raise exactly as in D1d.
3. **Tests** in `tests/test_gateway.py`, with the fake server:
   - First reply: empty content, `finish_reason` `"length"`, cost 0.03. Second reply: valid JSON, cost 0.003. Then
     `chat(..., schema=...)` returns the parsed JSON, `usd == 0.033` (to 6 places) and `reasoning_fallback` True, and
     the **second** request body carries `"reasoning": {"enabled": false}`.
   - Both replies hit the length case: `GatewayError` naming `max_tokens`. Exactly two requests are made.
   - Without a schema, a length reply raises after **one** request.
   - `reasoning="off"` sends `{"enabled": false}`.

## Acceptance criteria
- `python3 -m unittest discover -s tests -t .` passes.
- `aios/gateway.py` has at most 95 non-blank, non-comment lines.

## Out of scope
`aios/gate.py`; provider pinning or ignoring; any other file.

## Stop conditions
If something above is contradictory or impossible, stop and reply `ESCALATE: <reason>`.
