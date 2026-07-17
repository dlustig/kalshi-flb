import json

import httpx
import pytest

from kalshi_flb.api import KalshiApiError, KalshiClient


def make_client(handler, **kw):
    kw.setdefault("rps", 10_000)  # effectively unpaced in tests
    return KalshiClient(transport=httpx.MockTransport(handler), **kw)


def test_paginate_two_pages_then_stop():
    pages = {
        "": {"trades": [{"trade_id": "a"}], "cursor": "c1"},
        "c1": {"trades": [{"trade_id": "b"}], "cursor": ""},
    }
    seen_params = []

    def handler(request):
        params = dict(request.url.params)
        seen_params.append(params)
        return httpx.Response(200, json=pages[params.get("cursor", "")])

    client = make_client(handler)
    got = list(client.paginate("/markets/trades", "trades", params={"min_ts": 5}))
    assert [r["trade_id"] for recs, _ in got for r in recs] == ["a", "b"]
    assert got[0][1] == "c1" and got[1][1] == ""
    # cursor param only sent when non-empty; other params always sent
    assert "cursor" not in seen_params[0]
    assert seen_params[1]["cursor"] == "c1"
    assert all(p["min_ts"] == "5" for p in seen_params)
    assert all(p["limit"] == "1000" for p in seen_params)


def test_retry_on_429_then_success(monkeypatch):
    sleeps = []
    monkeypatch.setattr("time.sleep", lambda s: sleeps.append(s))
    calls = {"n": 0}

    def handler(request):
        calls["n"] += 1
        if calls["n"] <= 2:
            return httpx.Response(429, json={"error": "too many requests"})
        return httpx.Response(200, json={"ok": True})

    client = make_client(handler)
    assert client.get("/exchange/status") == {"ok": True}
    assert calls["n"] == 3
    assert len(sleeps) >= 2  # backed off twice


def test_4xx_raises_immediately():
    def handler(request):
        return httpx.Response(404, text="not found")

    client = make_client(handler)
    with pytest.raises(KalshiApiError, match="404"):
        client.get("/nope")


def test_retries_exhausted_raises(monkeypatch):
    monkeypatch.setattr("time.sleep", lambda s: None)

    def handler(request):
        return httpx.Response(500, text="boom")

    client = make_client(handler, max_retries=3)
    with pytest.raises(KalshiApiError, match="exhaust"):
        client.get("/exchange/status")


def test_pacing_enforces_min_interval(monkeypatch):
    waits = []
    clock = {"t": 0.0}
    monkeypatch.setattr("kalshi_flb.api.time.monotonic", lambda: clock["t"])

    def fake_sleep(s):
        waits.append(s)
        clock["t"] += s

    monkeypatch.setattr("kalshi_flb.api.time.sleep", fake_sleep)

    def handler(request):
        return httpx.Response(200, json={})

    client = KalshiClient(transport=httpx.MockTransport(handler), rps=5)
    client.get("/a")
    client.get("/b")  # zero elapsed time -> must wait ~0.2s
    assert waits and abs(waits[-1] - 0.2) < 0.01


def test_paginate_continues_through_empty_page_with_cursor():
    pages = {
        "": {"trades": [{"trade_id": "a"}], "cursor": "c1"},
        "c1": {"trades": [], "cursor": "c2"},   # filtered-empty mid-stream
        "c2": {"trades": [{"trade_id": "b"}], "cursor": ""},
    }

    def handler(request):
        return httpx.Response(
            200, json=pages[dict(request.url.params).get("cursor", "")])

    client = make_client(handler)
    got = list(client.paginate("/markets/trades", "trades"))
    assert [r["trade_id"] for recs, _ in got for r in recs] == ["a", "b"]
    assert len(got) == 3  # empty page yielded, walk not truncated


def test_paginate_raises_after_max_empty_pages():
    def handler(request):
        return httpx.Response(200, json={"trades": [], "cursor": "next"})

    client = make_client(handler)
    with pytest.raises(KalshiApiError, match="empty pages"):
        list(client.paginate("/markets/trades", "trades", max_empty_pages=3))
