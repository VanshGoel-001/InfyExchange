"""Offered-vs-consumed API diff (repo-root-relative; run from anywhere).

Surfaces routes the backend OFFERS but the SPA never CONSUMES (dead backend
features) and paths the SPA calls that the backend does not OFFER (broken
calls). Prefers the live server's /openapi.json; falls back to importing the
FastAPI app offline so it works without a running server/DB.

An 'offer-without-consumer' row is exactly the class of bug prose docs miss
(e.g. the contact-reveal endpoint).
"""
import json
import os
import re
import sys
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
BACKEND = os.path.join(ROOT, "backend")
API_BASE = "http://127.0.0.1:8000"
API_JS = os.path.join(ROOT, "src", "services", "api.js")

# Ops/health endpoints the SPA is not expected to call.
EXPECTED_OPS = {"/", "/health"}


def load_spec():
    try:
        with urllib.request.urlopen(f"{API_BASE}/openapi.json", timeout=3) as r:
            return json.load(r)
    except Exception:
        pass
    # config.py reads env_file=".env" relative to CWD, so import from backend/.
    os.chdir(BACKEND)
    sys.path.insert(0, BACKEND)  # engine creation is lazy; no DB connection needed
    from app.main import app  # noqa: E402
    return app.openapi()


def sig(path):
    path = path.split("?")[0]
    if path.startswith("/api"):
        path = path[len("/api"):]
    # JS template params ${id} and OpenAPI params {id} both become wildcard *.
    path = re.sub(r"\$\{[^}]*\}", "{x}", path)
    path = re.sub(r"\{[^}]*\}", "{x}", path)
    parts = []
    for seg in path.strip("/").split("/"):
        if seg == "{x}":
            parts.append("*")
        else:
            parts.append(seg)
    return "/" + "/".join(parts)


def frontend_consumed():
    consumed = set()
    pat = re.compile(r"[`'\"](/(?:api/)?[a-zA-Z0-9_/${}:.\-]+)")
    text = open(API_JS, encoding="utf-8").read()
    for m in pat.finditer(text):
        consumed.add(sig(m.group(1)))
    return consumed


def main():
    spec = load_spec()
    offered = {sig(p) for p in spec.get("paths", {})}
    consumed = frontend_consumed()
    unconsumed = sorted((offered - consumed) - EXPECTED_OPS)
    unoffered = sorted(consumed - offered - {"/*"})

    print(f"Backend offers {len(offered)} route signatures; SPA consumes {len(consumed)}.\n")
    print("OFFERED but never consumed (dead backend features):")
    print("\n".join(f"  - {u}" for u in unconsumed) or "  (none)")
    print("\nCONSUMED but not offered (broken frontend calls):")
    print("\n".join(f"  - {u}" for u in unoffered) or "  (none)")


if __name__ == "__main__":
    main()
