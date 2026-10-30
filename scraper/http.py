"""Minimal HTTP helpers (stdlib only) with retries and a polite User-Agent."""
from __future__ import annotations

import json
import time
import urllib.error
import urllib.request

USER_AGENT = "urheilu-tv/1.0 (personal schedule; +https://github.com)"


def request(url: str, *, method: str = "GET", data: bytes | None = None,
            headers: dict | None = None, retries: int = 3, timeout: int = 30) -> str:
    hdrs = {"User-Agent": USER_AGENT, "Accept": "application/json, text/html;q=0.9"}
    hdrs.update(headers or {})
    last: Exception | None = None
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, data=data, headers=hdrs, method=method)
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return resp.read().decode("utf-8")
        except (urllib.error.URLError, TimeoutError) as exc:
            last = exc
            # 4xx other than 429 will not get better by retrying
            if isinstance(exc, urllib.error.HTTPError) and exc.code < 500 and exc.code != 429:
                break
            time.sleep(2 ** attempt)
    raise RuntimeError(f"Haku epäonnistui: {url}: {last}")


def get_json(url: str, **kw) -> dict | list:
    return json.loads(request(url, **kw))


def post_json(url: str, payload: dict, headers: dict | None = None) -> dict:
    hdrs = {"Content-Type": "application/json"}
    hdrs.update(headers or {})
    return json.loads(request(url, method="POST", data=json.dumps(payload).encode(), headers=hdrs))
