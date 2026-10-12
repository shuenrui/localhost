"""Check a running local model server, and measure speed honestly.

Every request carries a unique nonce at the start of the prompt. Engines reuse the KV
cache for identical prompts, so without it repeat runs report cache-hit speed as
prefill speed (we measured a 979x overstatement on our own CIX P1 box).
"""
import json
import time
import urllib.request
import uuid

from .detect import running_servers


def _post_stream(url, body, timeout):
    req = urllib.request.Request(url, data=json.dumps(body).encode(), method="POST",
                                 headers={"Content-Type": "application/json", "Accept": "text/event-stream"})
    return urllib.request.urlopen(req, timeout=timeout)


def list_models(endpoint):
    with urllib.request.urlopen(endpoint.rstrip("/") + "/models", timeout=5) as r:
        return [m.get("id") for m in json.load(r).get("data", [])]


def check(endpoint=None, model=None, max_tokens=48, timeout=600):
    """Return a result dict. Never raises for server-side problems; reports them instead."""
    res = {"ok": False, "endpoint": endpoint, "model": model}
    if not endpoint:
        servers = running_servers()
        if not servers:
            res["error"] = "No local model server found on the usual ports (11434, 8080, 8000, 1234, 30000)."
            return res
        endpoint = servers[0]["endpoint"]
        res["endpoint"] = endpoint
        res["engine_guess"] = servers[0]["engine_guess"]
    try:
        models = list_models(endpoint)
    except Exception as e:
        res["error"] = "Server did not answer GET /models: %s" % e
        return res
    res["models_served"] = models
    if not model:
        if not models:
            res["error"] = "Server lists no models. Pull or load one first."
            return res
        model = models[0]
    res["model"] = model
    nonce = uuid.uuid4().hex[:12]
    body = {"model": model, "stream": True, "max_tokens": max_tokens, "temperature": 0,
            "stream_options": {"include_usage": True},
            "messages": [{"role": "user", "content": "[run %s] Count from 1 to 20, separated by spaces." % nonce}]}
    t0 = time.time()
    first = last = None
    chunks = 0
    usage = None
    text = []
    try:
        with _post_stream(endpoint.rstrip("/") + "/chat/completions", body, timeout) as r:
            for raw in r:
                line = raw.decode("utf-8", "replace").strip()
                if not line.startswith("data:"):
                    continue
                payload = line[5:].strip()
                if payload == "[DONE]":
                    break
                try:
                    ev = json.loads(payload)
                except ValueError:
                    continue
                if ev.get("usage"):
                    usage = ev["usage"]
                for ch in ev.get("choices") or []:
                    d = ch.get("delta") or {}
                    piece = d.get("content") or d.get("reasoning_content") or d.get("reasoning") or ""
                    if piece:
                        now = time.time()
                        first = first or now
                        last = now
                        chunks += 1
                        text.append(piece)
    except Exception as e:
        res["error"] = "Chat request failed: %s" % e
        return res
    if not chunks:
        res["error"] = "The model returned no text."
        return res
    n = (usage or {}).get("completion_tokens") or chunks
    res.update(ok=True, nonce=nonce, reply_preview="".join(text)[:120],
               time_to_first_token_s=round(first - t0, 2),
               decode_tok_s=round((n - 1) / (last - first), 2) if last > first and n > 1 else None,
               tokens=n, token_count_source="server usage" if usage else "stream chunks (approx.)",
               method="single stream, cold prompt (unique nonce), wall clock. First token time includes "
                      "model load if the model was not already in memory.")
    return res
