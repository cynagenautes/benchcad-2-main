"""maya/: a local Project Maya server, spoken through its Responses API.

A stand-in server on 127.0.0.1 answers the way Maya's serve/responses.py does
(github.com/mw00/project-maya, 1.1.65): SSE with response.reasoning_text.delta
for the thinking, a reasoning item whose content is reasoning_text and, when
include asks for it, an encrypted_content blob; then the message. The test
drives the harness's real openai SDK path against it -- no monkeypatched client.
"""
from __future__ import annotations

import json
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import harness.run as R                                          # noqa: E402

FENCE = "```python\nprint(1)\n```"


class _Maya(BaseHTTPRequestHandler):
    requests: list = []
    n = 0

    def log_message(self, *a):                                   # keep pytest output clean
        pass

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        type(self).requests.append({"path": self.path, "auth": self.headers.get("Authorization"), "body": body})
        type(self).n += 1
        k = type(self).n
        think = f"thinking {k}"
        reasoning = {"id": f"rs_{k}", "type": "reasoning", "status": "completed", "summary": [],
                     "content": [{"type": "reasoning_text", "text": think}]}
        if "reasoning.encrypted_content" in (body.get("include") or []):
            reasoning["encrypted_content"] = f"maya-blob-{k}"
        message = {"id": f"msg_{k}", "type": "message", "role": "assistant", "status": "completed",
                   "content": [{"type": "output_text", "text": FENCE, "annotations": []}]}
        base = {"id": f"resp_{k}", "object": "response", "created_at": 0, "model": body["model"],
                "status": "in_progress", "output": [], "parallel_tool_calls": True, "tool_choice": "auto",
                "tools": [], "error": None, "incomplete_details": None}
        done = dict(base, status="completed", output=[reasoning, message],
                    usage={"input_tokens": 100, "output_tokens": 20,
                           "input_tokens_details": {"cached_tokens": 0},
                           "output_tokens_details": {"reasoning_tokens": 5}, "total_tokens": 120})
        # The order and shapes of Maya's own lifecycle (serve/responses.py start/close).
        empty_part = {"type": "output_text", "text": "", "annotations": [], "logprobs": []}
        rs, ms = {"item_id": f"rs_{k}", "output_index": 0}, {"item_id": f"msg_{k}", "output_index": 1}
        events = [("response.created", {"response": base}),
                  ("response.in_progress", {"response": base}),
                  ("response.output_item.added", {"output_index": 0, "item": dict(reasoning, content=[],
                                                                                  status="in_progress")}),
                  ("response.reasoning_text.delta", dict(rs, content_index=0, delta=think)),
                  ("response.reasoning_text.done", dict(rs, content_index=0, text=think)),
                  ("response.output_item.done", {"output_index": 0, "item": reasoning}),
                  ("response.output_item.added", {"output_index": 1, "item": dict(message, content=[],
                                                                                  status="in_progress")}),
                  ("response.content_part.added", dict(ms, content_index=0, part=empty_part)),
                  ("response.output_text.delta", dict(ms, content_index=0, delta=FENCE, logprobs=[])),
                  ("response.output_text.done", dict(ms, content_index=0, text=FENCE, logprobs=[])),
                  ("response.content_part.done", dict(ms, content_index=0, part=message["content"][0])),
                  ("response.output_item.done", {"output_index": 1, "item": message}),
                  ("response.completed", {"response": done})]
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.end_headers()
        for seq, (name, data) in enumerate(events):
            data = dict(data, type=name, sequence_number=seq)
            self.wfile.write(f"event: {name}\ndata: {json.dumps(data)}\n\n".encode())
        self.wfile.flush()


@pytest.fixture
def maya(monkeypatch):
    _Maya.requests, _Maya.n = [], 0
    srv = ThreadingHTTPServer(("127.0.0.1", 0), _Maya)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    monkeypatch.setenv("MAYA_BASE_URL", f"http://127.0.0.1:{srv.server_address[1]}/v1")
    monkeypatch.delenv("MAYA_API_KEY", raising=False)
    monkeypatch.setattr(R.time, "sleep", lambda *_: None)
    yield _Maya.requests
    srv.shutdown()


def _png(path: Path) -> Path:
    from PIL import Image
    Image.new("RGB", (64, 32), "white").save(path)
    return path


def test_maya_carries_its_reasoning_back_and_sends_images(maya, tmp_path):
    call = R.build_call("maya/glm-5.3-flash", None, [], tmp_path, effort="high")
    turns = [{"role": "user", "text": "Begin.", "images": [_png(tmp_path / "a.png")]}]
    first = call("SYSTEM", turns)
    assert str(first) == FENCE
    turns += [{"role": "assistant", "text": first}, {"role": "user", "text": "Round 2"}]
    call("SYSTEM", turns)

    assert [r["path"] for r in maya] == ["/v1/responses", "/v1/responses"]
    one, two = maya[0]["body"], maya[1]["body"]
    assert one["model"] == "glm-5.3-flash" and one["store"] is False
    assert one["reasoning"]["effort"] == "high"
    assert one["include"] == ["reasoning.encrypted_content"]
    img = [p for p in one["input"][0]["content"] if p["type"] == "input_image"]
    assert img and img[0]["image_url"].startswith("data:image/png;base64,")
    # Round 2 sends round 1's own items back: the reasoning with Maya's blob, then the message.
    back = [it for it in two["input"] if it.get("type") in ("reasoning", "message")]
    assert back[0]["type"] == "reasoning" and back[0]["encrypted_content"] == "maya-blob-1"
    assert back[1]["content"][0]["text"] == FENCE
    assert call.effort_sent() == "high"
    assert call.auth.startswith("maya base_url=http://127.0.0.1:")
    assert "key=" not in call.auth


def test_maya_refuses_levels_it_would_round(tmp_path):
    for lvl in ("medium", "xhigh"):
        with pytest.raises(SystemExit, match="maya has no effort"):
            R.build_call("maya/glm-5.3-flash", None, [], tmp_path, effort=lvl)
    assert R.top_effort("maya/") == "max"


def test_maya_settings_from_the_environment():
    m = R.maya_settings({"MAYA_BASE_URL": "http://gpu-box:8080/v1/", "MAYA_API_KEY": "k",
                         "MAYA_IDLE_S": "120", "MAYA_CALL_BUDGET_S": "3600"})
    assert m == {"base_url": "http://gpu-box:8080/v1", "api_key": "k", "idle_s": 120.0, "call_budget_s": 3600.0}
    d = R.maya_settings({})
    assert d["base_url"] == "http://127.0.0.1:8080/v1" and d["idle_s"] == R.MAYA_IDLE_S_DEFAULT


def test_maya_key_is_sent_when_set(maya, monkeypatch, tmp_path):
    monkeypatch.setenv("MAYA_API_KEY", "secret-local")
    call = R.build_call("maya/glm-5.3-flash", None, [], tmp_path, effort="low")
    call("SYSTEM", [{"role": "user", "text": "Begin."}])
    assert maya[0]["auth"] == "Bearer secret-local"
    assert call.auth.endswith("key=set") and "secret-local" not in call.auth
