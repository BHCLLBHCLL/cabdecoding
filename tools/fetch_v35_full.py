"""Fetch a V35 doc page fully and grep a pattern."""
import sys, re, html, urllib.request

def fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.read().decode("utf-8", "replace")

def strip(s):
    s = re.sub(r"<[^>]+>", " ", s)
    s = html.unescape(s)
    return re.sub(r"\s+", " ", s).strip()

url = sys.argv[1]
pats = sys.argv[2:]
text = strip(fetch(url))
print("total len:", len(text))
for p in pats:
    i = text.find(p)
    if i < 0:
        print(f"-- '{p}' not found")
        continue
    print(f"-- around '{p}':")
    print(text[max(0, i-200):i+1500])
