#!/usr/bin/env python3
"""Mock-SSE tests for agent_bench.py (task T20). Stdlib only.

Run: python3 bench/test_agent_bench.py
"""

import asyncio
import json
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import agent_bench


def sse(obj) -> bytes:
    return b"data: " + json.dumps(obj).encode() + b"\n\n"


def delta_chunk(text):
    return {"choices": [{"delta": {"content": text}}]}


def usage_chunk(completion, prompt=100):
    return {"choices": [],
            "usage": {"completion_tokens": completion, "prompt_tokens": prompt}}


class MockHandler(BaseHTTPRequestHandler):
    """Behavior selected by the model name in the request body."""

    def log_message(self, *a):
        pass

    def do_GET(self):
        if self.path == "/v1/models":
            body = json.dumps({"data": [{"id": "mock"}]}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(body)
        else:
            self.send_response(404)
            self.end_headers()

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        req = json.loads(self.rfile.read(length))
        mode = req["model"]
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.end_headers()
        w = self.wfile
        if mode == "normal":
            # 5 deltas, usage says 20 tokens (multi-token deltas, spec-decode style)
            for i in range(5):
                w.write(sse(delta_chunk(f"tok{i} ")))
            w.write(sse(usage_chunk(20)))
            w.write(b"data: [DONE]\n\n")
        elif mode == "no-usage":
            for i in range(7):
                w.write(sse(delta_chunk(f"t{i}")))
            w.write(b"data: [DONE]\n\n")
        elif mode == "empty":
            w.write(b"data: [DONE]\n\n")
        elif mode == "error-json":
            # 200 status but an error body, no stream
            w.write(json.dumps({"error": {"message": "boom"}}).encode())
        elif mode == "malformed":
            w.write(b"data: {not json}\n\n")
            w.write(b"garbage line\n\n")
            w.write(sse(delta_chunk("ok ")))
            w.write(sse(usage_chunk(3)))
            w.write(b"data: [DONE]\n\n")


class Args:
    model = "normal"
    max_tokens = 32
    temperature = 1.0
    top_p = 0.95
    api_key = ""
    warmup_seconds = 0
    measure_seconds = 2
    gpu_ssh_host = ""


class Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), MockHandler)
        cls.base = f"http://127.0.0.1:{cls.server.server_port}/v1"
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()

    def one(self, mode, wall_cap_delta=60):
        import time
        return agent_bench.stream_request(
            self.base, mode, "hello", 32, 1.0, 0.95, "",
            time.monotonic() + wall_cap_delta)

    def test_usage_tokens_beat_delta_count(self):
        res = self.one("normal")
        self.assertTrue(res["ok"])
        self.assertEqual(res["gen_tokens"], 20)      # usage, not 5 deltas
        self.assertEqual(res["token_source"], "usage")
        self.assertEqual(res["prompt_tokens"], 100)
        self.assertIsNotNone(res["prefill_tok_s"])

    def test_delta_fallback_flagged(self):
        res = self.one("no-usage")
        self.assertTrue(res["ok"])
        self.assertEqual(res["gen_tokens"], 7)
        self.assertEqual(res["token_source"], "deltas")

    def test_empty_stream_is_error(self):
        res = self.one("empty")
        self.assertFalse(res["ok"])
        self.assertIn("zero tokens", res["error"])

    def test_error_json_body_is_error(self):
        res = self.one("error-json")
        self.assertFalse(res["ok"])

    def test_malformed_lines_counted_not_fatal(self):
        res = self.one("malformed")
        self.assertTrue(res["ok"])
        self.assertEqual(res["gen_tokens"], 3)
        self.assertGreaterEqual(res["skipped_lines"], 2)

    def test_preflight_normalizes_missing_v1(self):
        base = self.base[:-3]  # strip /v1
        self.assertEqual(agent_bench.preflight(base, None), self.base)

    def test_preflight_dead_server_exits(self):
        with self.assertRaises(SystemExit):
            agent_bench.preflight("http://127.0.0.1:1", None)

    def test_run_point_counts_only_window_tokens(self):
        args = Args()
        point, errors = asyncio.run(
            agent_bench.run_point(2, args, self.base, ["prompt one"]))
        self.assertGreater(point["requests_ok"], 0)
        self.assertEqual(point["window_s"], 2)
        self.assertEqual(point["token_source"], "usage")
        self.assertGreater(point["aggregate_tok_s"], 0)

    def test_run_point_dead_model_records_errors(self):
        args = Args()
        args.model = "empty"
        args.measure_seconds = 1
        point, errors = asyncio.run(
            agent_bench.run_point(1, args, self.base, ["prompt"]))
        self.assertEqual(point["requests_ok"], 0)
        self.assertGreater(point["requests_err"], 0)
        self.assertTrue(errors[0]["error"])
        self.assertTrue(point["first_error_ts"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
