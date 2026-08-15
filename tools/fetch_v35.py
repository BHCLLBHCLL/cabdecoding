"""Fetch a q-solid V35 doc page and dump its text."""
import sys, re, html, urllib.request

def fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read().decode("utf-8", "replace")

def strip(s):
    s = re.sub(r"<[^>]+>", " ", s)
    s = html.unescape(s)
    return re.sub(r"\s+", " ", s).strip()

url = sys.argv[1]
text = strip(fetch(url))
# print the first N chars
print(text[:6000])
