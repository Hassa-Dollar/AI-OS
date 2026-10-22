"""OpenRouter client on stdlib urllib: one key for every model (ADR-0029).

Lesson #2: raw error bodies are kept, and only 429/5xx/network errors are retried. Lesson #8: every call has a
timeout. The project's privacy policy rides on every chat request.
"""
from __future__ import annotations

import json
import time
import urllib.error
import urllib.request

BASE = "https://openrouter.ai/api/v1"


class GatewayError(RuntimeError):
    def __init__(self, status: int | None, body: str):
        super().__init__(f"OpenRouter HTTP {status}: {body[:300]}" if status else f"OpenRouter unreachable: {body[:300]}")
        self.status, self.body = status, body


class Gateway:
    def __init__(self, key: str, base: str = BASE, timeout: int = 120, retries: int = 3, backoff: float = 2.0,
                 privacy: dict | None = None):
        self.key, self.base, self.timeout, self.retries, self.backoff = key, base.rstrip("/"), timeout, retries, backoff
        self.privacy = privacy if privacy is not None else {"data_collection": "deny"}

    def _call(self, method: str, path: str, payload: dict | None = None) -> dict:
        data = json.dumps(payload).encode() if payload is not None else None
        headers = {"Authorization": f"Bearer {self.key}", "Content-Type": "application/json"}
        for attempt in range(self.retries + 1):
            req = urllib.request.Request(self.base + path, data=data, method=method, headers=headers)
            try:
                with urllib.request.urlopen(req, timeout=self.timeout) as r:
                    return json.load(r)
            except urllib.error.HTTPError as e:
                body = e.read().decode("utf-8", "replace")
                e.close()
                if (e.code == 429 or e.code >= 500) and attempt < self.retries:
                    time.sleep(self.backoff * 2 ** attempt)
                    continue
                raise GatewayError(e.code, body) from None
            except (urllib.error.URLError, TimeoutError) as e:
                if attempt < self.retries:
                    time.sleep(self.backoff * 2 ** attempt)
                    continue
                raise GatewayError(None, str(e)) from None
        raise AssertionError("unreachable")

    def models(self) -> list[dict]:
        return self._call("GET", "/models")["data"]

    def key_info(self) -> dict:
        return self._call("GET", "/key")["data"]

    def chat(self, model: str, messages: list[dict], *, schema: dict | None = None, max_tokens: int | None = None,
             reasoning: str | None = None) -> dict:
        """One completion. With `schema`, the reply is validated JSON (structured outputs, ADR-0031 verifier)."""
        body: dict = {"model": model, "messages": messages, "usage": {"include": True}, "provider": dict(self.privacy)}
        if schema:
            body["response_format"] = {"type": "json_schema",
                                       "json_schema": {"name": "result", "strict": True, "schema": schema}}
            body["provider"]["require_parameters"] = True
        if max_tokens:
            body["max_tokens"] = max_tokens
        if reasoning:
            body["reasoning"] = {"effort": reasoning}
        r = self._call("POST", "/chat/completions", body)
        try:
            content = r["choices"][0]["message"].get("content") or ""
        except (KeyError, IndexError, TypeError):
            raise GatewayError(200, f"malformed completion: {json.dumps(r)[:300]}") from None
        usage = r.get("usage") or {}
        out = {"content": content, "usd": float(usage.get("cost") or 0), "usage": usage, "model": r.get("model"),
               "provider": r.get("provider")}
        if schema:
            try:
                out["json"] = json.loads(content)
            except json.JSONDecodeError:
                raise GatewayError(200, f"{model} returned non-JSON despite a schema: {content[:200]}") from None
        return out


def privacy_of(project) -> dict:
    """The provider-routing constraints a project's [privacy] section imposes on every call."""
    p = {"data_collection": project.data_collection}
    if project.zdr:
        p["zdr"] = True
    return p
