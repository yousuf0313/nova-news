#!/usr/bin/env python3
"""Nova News server-side feed fetcher (prepared 2026-11-06).

Why: the live site fetches RSS through third-party CORS proxies
(allorigins, rss2json, codetabs, cors.lol). On 2026-11-04/05/06 the
health watch repeatedly found 2-3 of the 4 proxies down at once, leaving
rss2json as the single working route. This script fetches the same feeds
directly (server-side: no CORS problem) and writes one JSON file the
site can load from its own origin, so no proxy is needed at all.

Usage (GitHub Actions, every 10 min):
    python3 fetch_feeds.py            # writes data/feeds.json
The workflow commits data/feeds.json back to the repo; GitHub Pages
then serves it same-origin. The site patch (see nova-news-selfhosted-
patch-NOTES.md) tries data/feeds.json first and keeps the proxy list
only as a fallback for a stale/missing file.
"""
import html
import json
import re
import sys
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone

# Same feeds as LANGS in nova-news/index.html (kept in sync manually).
FEEDS = {
    "en-world": [
        ("BBC World", "https://feeds.bbci.co.uk/news/world/rss.xml"),
        ("Al Jazeera", "https://www.aljazeera.com/xml/rss/all.xml"),
        ("The Guardian", "https://www.theguardian.com/world/rss"),
    ],
    "en-pakistan": [("Dawn", "https://www.dawn.com/feeds/home")],
    "en-sports": [("BBC Sport", "https://feeds.bbci.co.uk/sport/rss.xml")],
    "en-business": [("BBC Business", "https://feeds.bbci.co.uk/news/business/rss.xml")],
    "en-technology": [("BBC Technology", "https://feeds.bbci.co.uk/news/technology/rss.xml")],
    "ur-world": [
        ("BBC Urdu", "https://feeds.bbci.co.uk/urdu/rss.xml"),
        ("BBC Urdu", "https://feeds.bbci.co.uk/urdu/pakistan/rss.xml"),
    ],
    "ar-world": [
        ("BBC Arabic", "https://feeds.bbci.co.uk/arabic/rss.xml"),
        ("BBC Arabic", "https://feeds.bbci.co.uk/arabic/middle_east/rss.xml"),
    ],
    "ja-world": [
        ("NHK News", "https://news.web.nhk/n-data/conf/na/rss/cat0.xml"),
        ("NHK International", "https://news.web.nhk/n-data/conf/na/rss/cat6.xml"),
    ],
    "zh-world": [("BBC Chinese", "https://feeds.bbci.co.uk/zhongwen/simp/rss.xml")],
}

UA = {"User-Agent": "NovaNewsFeedFetcher/1.0 (+https://yousuf0313.github.io/nova-news/)"}


def strip_html(s):
    s = re.sub(r"<[^>]+>", " ", s or "")
    return re.sub(r"\s+", " ", html.unescape(s)).strip()


def parse_rss(data, source):
    try:
        root = ET.fromstring(data)
    except ET.ParseError:
        return []
    items = []
    for it in root.iter("item"):
        def get(tag):
            el = it.find(tag)
            return (el.text or "").strip() if el is not None else ""
        img = ""
        for el in it.iter():
            if el.tag.endswith("content") or el.tag.endswith("thumbnail"):
                if el.get("url"):
                    img = el.get("url")
                    break
        if not img:
            enc = it.find("enclosure")
            if enc is not None and (enc.get("type") or "").startswith("image"):
                img = enc.get("url") or ""
        if not img:
            m = re.search(r'<img[^>]+src=["\']([^"\']+)', get("description"))
            if m:
                img = m.group(1)
        items.append({
            "title": get("title"),
            "link": get("link"),
            "desc": strip_html(get("description"))[:300],
            "date": get("pubDate") or get("dc:date"),
            "img": img,
            "source": source,
        })
    return [i for i in items if i["title"] and i["link"]]


def main():
    out = {"generated_at": datetime.now(timezone.utc).isoformat(), "feeds": {}}
    ok, fail = 0, []
    for key, feeds in FEEDS.items():
        for name, url in feeds:
            try:
                req = urllib.request.Request(url, headers=UA)
                with urllib.request.urlopen(req, timeout=20) as r:
                    items = parse_rss(r.read(), name)
                if items:
                    out["feeds"][url] = items
                    ok += 1
                else:
                    fail.append(f"{key}/{name}: empty")
            except Exception as e:  # noqa: BLE001 - report, keep going
                fail.append(f"{key}/{name}: {type(e).__name__}: {e}")
    with open("data/feeds.json", "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False)
    total = sum(len(v) for v in out["feeds"].values())
    print(f"feeds ok: {ok}, failed: {len(fail)}, total items: {total}")
    for line in fail:
        print("FAIL:", line)
    return 0 if total > 0 else 1


if __name__ == "__main__":
    sys.exit(main())
