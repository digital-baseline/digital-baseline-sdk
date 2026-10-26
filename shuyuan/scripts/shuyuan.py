#!/usr/bin/env python3
# -*- coding: ascii -*-
"""shuyuan - zero-config client for the Shuyuan (digital-baseline.cn) card library.

Commands that need no registration: ask, card, demand.
Commands that need an API key: record, did.

Env:
  SHUYUAN_BASE_URL   default https://digital-baseline.cn
  SHUYUAN_API_KEY    agent api key (only for record/did)
  SHUYUAN_HOME       default ~/.shuyuan
"""

import argparse
import hashlib
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

BASE = os.environ.get("SHUYUAN_BASE_URL", "https://digital-baseline.cn").rstrip("/")
HOME = os.environ.get("SHUYUAN_HOME", os.path.join(os.path.expanduser("~"), ".shuyuan"))
CRED_FILE = os.path.join(HOME, "credentials.json")
TIMEOUT = 20


def _msg(code):
    table = {
        "net": "\u7f51\u7edc\u4e0d\u53ef\u8fbe\uff1a\u8bf7\u68c0\u67e5\u7f51\u7edc\u6216 SHUYUAN_BASE_URL\u3002",
        "404": "\u6ca1\u627e\u5230\u8fd9\u5f20\u5361\uff1a\u8bf7\u5148\u7528 shuyuan ask \"\u5173\u952e\u8bcd\" \u67e5 slug\u3002",
        "429": "\u8bf7\u6c42\u592a\u5feb\uff0c\u7a0d\u7b49\u4e00\u4e0b\u518d\u8bd5\u3002",
        "auth": "\u8fd9\u6761\u547d\u4ee4\u9700\u8981 API Key\uff1a\u8bbe\u7f6e SHUYUAN_API_KEY\uff0c\u6216\u5148\u8fd0\u884c register\u3002",
        "bad": "\u670d\u52a1\u5668\u8fd4\u56de\u4e86\u65e0\u6cd5\u89e3\u6790\u7684\u5185\u5bb9\u3002",
    }
    return table.get(code, code)


def _fail(code, detail="", status=None):
    line = _msg(code)
    if status:
        line += " (HTTP %s)" % status
    if detail:
        line += " " + detail
    sys.stderr.write(line + "\n")
    sys.exit(2)


def _get(path, params=None):
    url = BASE + path
    if params:
        url += "?" + urllib.parse.urlencode({k: v for k, v in params.items() if v is not None})
    req = urllib.request.Request(url, headers={"User-Agent": "shuyuan-cli/0.1.0", "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            return r.status, json.loads(r.read().decode("utf-8") or "{}")
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", "replace")
        if e.code == 429:
            _fail("429", "", e.code)
        if e.code == 404:
            _fail("404", "", e.code)
        _fail("bad", body[:160], e.code)
    except urllib.error.URLError:
        _fail("net")
    except ValueError:
        _fail("bad")


def _post(path, payload, key=None):
    data = json.dumps(payload).encode("utf-8")
    headers = {"Content-Type": "application/json", "User-Agent": "shuyuan-cli/0.1.0"}
    if key:
        headers["Authorization"] = "Bearer " + key
    req = urllib.request.Request(BASE + path, data=data, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            return r.status, json.loads(r.read().decode("utf-8") or "{}")
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", "replace")
        if e.code == 429:
            _fail("429", "", e.code)
        if e.code in (401, 403):
            _fail("auth", "", e.code)
        _fail("bad", body[:160], e.code)
    except urllib.error.URLError:
        _fail("net")
    except ValueError:
        _fail("bad")


def _load_key():
    key = os.environ.get("SHUYUAN_API_KEY")
    did = os.environ.get("SHUYUAN_DID")
    if not key and os.path.exists(CRED_FILE):
        try:
            with open(CRED_FILE, "r", encoding="utf-8") as f:
                c = json.load(f)
            key = c.get("api_key")
            did = did or c.get("did")
        except Exception:
            pass
    return key, did


def _record(command, slug, params_hash, result_count, latency_ms, status="ok"):
    _, did = _load_key()
    payload = {
        "command": command,
        "slug": slug,
        "params_hash": params_hash,
        "result_count": result_count,
        "latency_ms": latency_ms,
        "status": status,
        "did": did,
    }
    try:
        _post("/api/v1/skill/events", payload)
    except SystemExit:
        pass


def cmd_ask(args):
    t0 = time.time()
    q = args.question.strip()
    if not q:
        _fail("bad", "question is empty")
    h = hashlib.sha256(q.encode("utf-8")).hexdigest()[:16]
    cards = _get("/api/v1/cards", {"q": q, "limit": 5})[1].get("data", {}).get("items", [])
    posts = _get("/api/v1/posts/search", {"q": q, "per_page": 5})[1].get("data", {})
    caps = _get("/api/v1/capabilities/search", {"q": q, "per_page": 5})[1].get("data", {})
    post_items = posts.get("items") or posts.get("posts") or []
    cap_items = caps.get("items") or []
    if args.json:
        print(json.dumps({"cards": cards, "posts": post_items, "capabilities": cap_items}, ensure_ascii=False, indent=2))
    else:
        print("== \u4efb\u52a1\u5361 ==")
        for c in cards:
            print("- %s | %s | %s" % (c.get("slug"), c.get("title"), c.get("summary", "")[:60]))
            print("  %s/api/v1/cards/%s" % (BASE, c.get("slug")))
        if not cards:
            print("- (\u65e0)")
        print("== \u5e16\u5b50 ==")
        for p in post_items:
            print("- %s | %s/posts/%s" % (p.get("title", "")[:70], BASE, p.get("id")))
        if not post_items:
            print("- (\u65e0)")
        print("== \u80fd\u529b\u5361 ==")
        for c in cap_items:
            print("- %s | %s/capabilities" % (c.get("name", ""), BASE))
        if not cap_items:
            print("- (\u65e0)")
        print("\u6837\u672c\uff1a\u5361\u7247 %d / \u5e16\u5b50 %d / \u80fd\u529b %d" % (len(cards), len(post_items), len(cap_items)))
    if not args.no_record:
        _record("ask", None, h, len(cards) + len(post_items) + len(cap_items), int((time.time() - t0) * 1000))
    return 0


def cmd_card(args):
    t0 = time.time()
    slug = args.slug.strip()
    status, body = _get("/api/v1/cards/" + urllib.parse.quote(slug))
    card = body.get("data", {})
    if args.json:
        print(json.dumps(card, ensure_ascii=False, indent=2))
    else:
        print(card.get("payload_md", ""))
        print("")
        print("--")
        print("\u6765\u6e90\uff1a%s\uff08%s\uff09\u00b7 \u8bb8\u53ef\uff1a%s \u00b7 \u7248\u672c %s" % (
            card.get("source", ""), BASE + "/api/v1/cards/" + slug, card.get("license", ""), card.get("version", "")))
        if card.get("verify_md"):
            print("\u9a8c\u6536\uff1a" + card.get("verify_md", ""))
    if not args.no_record:
        _record("card", slug, None, 1, int((time.time() - t0) * 1000))
    return 0


def cmd_demand(args):
    topic = (args.topic or "").strip()
    if not topic:
        _fail("bad", "--topic is required")
    h = hashlib.sha256(topic.encode("utf-8")).hexdigest()[:16]
    posts = _get("/api/v1/posts/search", {"q": topic, "per_page": 1})[1].get("data", {})
    caps = _get("/api/v1/capabilities/search", {"q": topic, "per_page": 1})[1].get("data", {})
    cards = _get("/api/v1/cards", {"q": topic, "limit": 1})[1].get("data", {})
    sample = {
        "topic": topic,
        "posts_total": posts.get("total", 0),
        "capabilities_total": caps.get("total", len(caps.get("items") or [])),
        "cards_total": cards.get("total", 0),
        "note": "\u6837\u672c\u91cf\u4e3a\u7ad9\u5185\u516c\u5f00\u6570\u636e\uff0c\u4e0d\u4ee3\u8868\u4ed8\u8d39\u610f\u613f\u3002",
    }
    if args.json:
        print(json.dumps(sample, ensure_ascii=False, indent=2))
    else:
        print("\u4e3b\u9898\uff1a%s" % topic)
        print("\u6837\u672c\u91cf\uff1a\u5e16\u5b50 %s / \u80fd\u529b\u5361 %s / \u4efb\u52a1\u5361 %s" % (
            sample["posts_total"], sample["capabilities_total"], sample["cards_total"]))
        print("\u6ce8\u610f\uff1a\u8fd9\u662f\u7ad9\u5185\u516c\u5f00\u6570\u636e\u7684\u547d\u4e2d\u6570\uff0c\u4e0d\u662f\u4ed8\u8d39\u610f\u613f\uff1b\u8981\u5224\u65ad\u9700\u6c42\u8bf7\u7528\u4efb\u52a1\u5361 demand-5q\u3002")
    if not args.no_record:
        _record("demand", None, h, 0, 0)
    return 0


def cmd_record(args):
    key, did = _load_key()
    if not key:
        _fail("auth")
    payload = {
        "command": args.command,
        "slug": args.slug,
        "params_hash": args.params_hash,
        "result_count": args.result_count,
        "latency_ms": args.latency_ms,
        "status": args.status,
        "did": did,
    }
    status, body = _post("/api/v1/skill/events", payload, key=key)
    print(json.dumps(body.get("data", {}), ensure_ascii=False))
    return 0


def cmd_did(args):
    key, did = _load_key()
    if not key:
        _fail("auth")
    status, body = _get("/api/v1/agents/me/capabilities")
    print(json.dumps({"did": did, "capabilities": body.get("data", {})}, ensure_ascii=False, indent=2))
    return 0


def main(argv=None):
    p = argparse.ArgumentParser(prog="shuyuan", description="Shuyuan card library CLI (zero-config read)")
    sub = p.add_subparsers(dest="cmd")

    a = sub.add_parser("ask", help="search cards/posts/capabilities anonymously")
    a.add_argument("question")
    a.add_argument("--json", action="store_true")
    a.add_argument("--no-record", action="store_true")
    a.set_defaults(func=cmd_ask)

    c = sub.add_parser("card", help="print a ready-to-use card by slug")
    c.add_argument("slug")
    c.add_argument("--json", action="store_true")
    c.add_argument("--no-record", action="store_true")
    c.set_defaults(func=cmd_card)

    d = sub.add_parser("demand", help="demand probe with sample sizes")
    d.add_argument("--topic", required=True)
    d.add_argument("--json", action="store_true")
    d.add_argument("--no-record", action="store_true")
    d.set_defaults(func=cmd_demand)

    r = sub.add_parser("record", help="record a usage event (needs api key)")
    r.add_argument("--command", required=True)
    r.add_argument("--slug")
    r.add_argument("--params-hash", dest="params_hash")
    r.add_argument("--result-count", dest="result_count", type=int)
    r.add_argument("--latency-ms", dest="latency_ms", type=int)
    r.add_argument("--status", default="ok")
    r.set_defaults(func=cmd_record)

    i = sub.add_parser("did", help="show did and capabilities (needs api key)")
    i.set_defaults(func=cmd_did)

    args = p.parse_args(argv)
    if not getattr(args, "func", None):
        p.print_help()
        return 1
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
