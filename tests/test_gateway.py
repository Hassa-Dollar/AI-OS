import json
import unittest
from types import SimpleNamespace

from aios import gateway
from tests.helpers import fake_http

OK = {"choices": [{"message": {"content": "hello"}}], "usage": {"cost": 0.0012, "prompt_tokens": 10},
      "model": "z-ai/glm-5.3", "provider": "Wafer"}


def gw(base, **kw):
    return gateway.Gateway("sk-or-v1-test", base=base, backoff=0, **kw)


class Gateway(unittest.TestCase):
    def test_models_and_key(self):
        with fake_http({"/models": (200, {"data": [{"id": "a/b"}]}), "/key": (200, {"data": {"limit": 40}})}) as base:
            self.assertEqual(gw(base).models(), [{"id": "a/b"}])
            self.assertEqual(gw(base).key_info()["limit"], 40)

    def test_chat_sends_privacy_and_cost_tracking(self):
        log = []
        with fake_http({"POST /chat/completions": (200, OK)}, log) as base:
            out = gw(base, privacy={"data_collection": "deny", "zdr": True}).chat(
                "z-ai/glm-5.3", [{"role": "user", "content": "hi"}], max_tokens=50, reasoning="low")
        self.assertEqual((out["content"], out["usd"], out["provider"]), ("hello", 0.0012, "Wafer"))
        body = log[0][2]
        self.assertEqual(body["usage"], {"include": True})
        self.assertEqual(body["provider"], {"data_collection": "deny", "zdr": True})
        self.assertEqual((body["max_tokens"], body["reasoning"]), (50, {"effort": "low"}))
        self.assertNotIn("response_format", body)

    def test_chat_with_schema_requires_parameters_and_parses(self):
        log, schema = [], {"type": "object", "properties": {"verdict": {"type": "string"}}}
        reply = dict(OK, choices=[{"message": {"content": json.dumps({"verdict": "pass"})}}])
        with fake_http({"POST /chat/completions": (200, reply)}, log) as base:
            out = gw(base).chat("m/x", [], schema=schema)
        self.assertEqual(out["json"], {"verdict": "pass"})
        body = log[0][2]
        self.assertEqual(body["response_format"]["json_schema"]["schema"], schema)
        self.assertTrue(body["provider"]["require_parameters"])
        with fake_http({"POST /chat/completions": (200, OK)}) as base:
            with self.assertRaisesRegex(gateway.GatewayError, "non-JSON"):
                gw(base).chat("m/x", [], schema=schema)

    def test_empty_content_with_finish_reason_length_reports_the_budget(self):
        schema = {"type": "object", "properties": {"verdict": {"type": "string"}}}
        reply = dict(OK, choices=[{"message": {"content": ""}, "finish_reason": "length"}],
                     usage={"cost": 0.01, "completion_tokens": 4000,
                            "completion_tokens_details": {"reasoning_tokens": 4000}})
        with fake_http({"POST /chat/completions": (200, reply)}) as base:
            with self.assertRaises(gateway.GatewayError) as cm:
                gw(base).chat("deepseek/deepseek-v4-pro-0813", [], schema=schema, max_tokens=4000)
        self.assertEqual(cm.exception.status, 200)
        self.assertIn("deepseek/deepseek-v4-pro-0813 used all of max_tokens=4000", cm.exception.body)
        self.assertIn("(reasoning tokens: 4000)", cm.exception.body)
        self.assertIn("raise max_tokens", cm.exception.body)

    def test_empty_content_without_a_reasoning_count_still_names_the_budget(self):
        reply = dict(OK, choices=[{"message": {"content": ""}, "finish_reason": "length"}],
                     usage={"cost": 0.01})
        with fake_http({"POST /chat/completions": (200, reply)}) as base:
            with self.assertRaises(gateway.GatewayError) as cm:
                gw(base).chat("m/x", [], max_tokens=16000)
        self.assertIn("(reasoning tokens: ?)", cm.exception.body)

    def test_empty_content_with_a_stop_finish_reason_stays_a_json_error(self):
        reply = dict(OK, choices=[{"message": {"content": ""}, "finish_reason": "stop"}],
                     usage={"completion_tokens_details": {"reasoning_tokens": 4000}})
        with fake_http({"POST /chat/completions": (200, reply)}) as base:
            with self.assertRaisesRegex(gateway.GatewayError, "non-JSON"):
                gw(base).chat("m/x", [], schema={"type": "object"})

    def test_retries_only_transient_errors(self):
        log = []
        with fake_http({"POST /chat/completions": [(503, {"e": 1}), (429, {"e": 2}), (200, OK)]}, log) as base:
            self.assertEqual(gw(base).chat("m/x", [])["content"], "hello")
        self.assertEqual(len(log), 3)
        log.clear()
        with fake_http({"POST /chat/completions": (400, {"error": "bad model"})}, log) as base:
            with self.assertRaises(gateway.GatewayError) as cm:
                gw(base).chat("m/x", [])
        self.assertEqual((cm.exception.status, len(log)), (400, 1))
        self.assertIn("bad model", cm.exception.body)

    def test_gives_up_and_reports_unreachable(self):
        with self.assertRaises(gateway.GatewayError) as cm:
            gw("http://127.0.0.1:9", retries=1, timeout=2).models()
        self.assertIsNone(cm.exception.status)

    def test_malformed_completion(self):
        with fake_http({"POST /chat/completions": (200, {"choices": []})}) as base:
            with self.assertRaisesRegex(gateway.GatewayError, "malformed"):
                gw(base).chat("m/x", [])

    def test_privacy_of(self):
        self.assertEqual(gateway.privacy_of(SimpleNamespace(data_collection="deny", zdr=False)),
                         {"data_collection": "deny"})
        self.assertEqual(gateway.privacy_of(SimpleNamespace(data_collection="allow", zdr=True)),
                         {"data_collection": "allow", "zdr": True})


if __name__ == "__main__":
    unittest.main()
