"""Load the localhost directory dataset.

The live site embeds the whole dataset as one JSON blob
(<script id="data" type="application/json">). The CLI reads that same blob, so the
CLI and the site never disagree.

Lookup order:
  1. --data FILE, or $LOCALHOST_DATA (a .json blob or a saved site .html)
  2. the cache at ~/.cache/localhost/data.json, if it is younger than 24 h
  3. a fetch of the live site (falls back to a stale cache if offline)
"""
import json
import os
import re
import time
import urllib.request

SITE_URL = os.environ.get("LOCALHOST_SITE", "https://local.innstance.app/")
CACHE_DIR = os.path.join(os.path.expanduser("~"), ".cache", "localhost")
CACHE_FILE = os.path.join(CACHE_DIR, "data.json")
TTL_S = 24 * 3600
_BLOB = re.compile(r'<script id="data" type="application/json">(.*?)</script>', re.S)


class DataError(RuntimeError):
    pass


def _parse(text):
    text = text.lstrip()
    if text.startswith("{"):
        return json.loads(text)
    m = _BLOB.search(text)
    if not m:
        raise DataError("no <script id=\"data\"> blob found in the page")
    return json.loads(m.group(1))


def _fetch(url):
    req = urllib.request.Request(url + ("&" if "?" in url else "?") + "v=%d" % int(time.time()),
                                 headers={"User-Agent": "localhost-cli/0.1"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read().decode("utf-8")


def load(path=None, refresh=False):
    """Return (data, meta). meta says where the data came from."""
    path = path or os.environ.get("LOCALHOST_DATA")
    if path:
        with open(path, encoding="utf-8") as f:
            return _parse(f.read()), {"source": os.path.abspath(path), "cached": False}
    fresh = os.path.exists(CACHE_FILE) and time.time() - os.path.getmtime(CACHE_FILE) < TTL_S
    if fresh and not refresh:
        with open(CACHE_FILE, encoding="utf-8") as f:
            return json.load(f), {"source": CACHE_FILE, "cached": True, "site": SITE_URL}
    try:
        data = _parse(_fetch(SITE_URL))
    except Exception as e:  # offline: use a stale cache rather than fail
        if os.path.exists(CACHE_FILE):
            with open(CACHE_FILE, encoding="utf-8") as f:
                return json.load(f), {"source": CACHE_FILE, "cached": True, "stale": True,
                                      "site": SITE_URL, "fetch_error": str(e)}
        raise DataError("could not fetch %s and no cache exists: %s" % (SITE_URL, e))
    os.makedirs(CACHE_DIR, exist_ok=True)
    tmp = CACHE_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f)
    os.replace(tmp, CACHE_FILE)
    return data, {"source": SITE_URL, "cached": False}


class Directory:
    """Thin read-only view over the blob."""

    def __init__(self, data):
        self.raw = data
        self.models = data.get("models") or {}
        self.hardware = data.get("hardware") or {}
        self.engines = data.get("engines") or {}
        self.publishers = data.get("publishers") or {}
        self.setups = data.get("setups") or []
        self.order = data.get("model_order") or sorted(self.models)
        self._by_id = {s["id"]: s for s in self.setups}

    def setup(self, sid):
        if sid in self._by_id:
            return self._by_id[sid]
        hits = [s for s in self.setups if s["id"].startswith(sid)]
        if len(hits) == 1:
            return hits[0]
        if not hits:
            raise KeyError("no recipe with id %r" % sid)
        raise KeyError("%r matches %d recipes: %s" % (sid, len(hits), ", ".join(h["id"] for h in hits[:8])))

    def model(self, mid):
        return self.models.get(mid) or {}

    def engine_id(self, s):
        e = s.get("engine")
        return e.get("id") if isinstance(e, dict) else e

    def hw_ids(self, s):
        return [h["id"] if isinstance(h, dict) else h for h in s.get("hardware") or []]
