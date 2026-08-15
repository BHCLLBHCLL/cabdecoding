"""Fetch a V35 header and extract struct typedefs (typedef struct ... )."""
import sys, re, html, urllib.request

def fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read().decode("utf-8", "replace")

def strip(s):
    s = re.sub(r"<[^>]+>", " ", s)
    s = html.unescape(s)
    return re.sub(r"\s+", " ", s).strip()

for url in sys.argv[1:]:
    text = strip(fetch(url))
    print("=" * 30, url)
    print(text[:4500])
    print()
