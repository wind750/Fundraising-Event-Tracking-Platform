"""PTT Stock 版爬蟲：看板索引（全部文章標題＋推文淨數）與每日盤中／盤後閒聊串的推文。

用法：
    py -3.14 ptt_sentiment/crawl.py index --since 2020-01-01   # 回補索引（可中斷續跑）
    py -3.14 ptt_sentiment/crawl.py chat                         # 依索引抓所有閒聊串（已抓過的跳過）
    py -3.14 ptt_sentiment/crawl.py recent                       # 日常更新：從已抓到的最後一頁續掃索引，抓新閒聊串並重抓近 7 天的串

原始資料只存在本機 data/ptt_raw/（整個 data/ 已被 .gitignore 排除），不保存任何 PTT 帳號。
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import gzip
import json
import re
import sys
import time
from html import unescape
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "ptt_raw"
INDEX_CSV = RAW / "index.csv"
CHAT_DIR = RAW / "chat"
BASE = "https://www.ptt.cc"
BOARD = "Stock"
SLEEP = 0.45  # 兩次請求間隔（秒），維持禮貌速度

TZ = dt.timezone(dt.timedelta(hours=8))
CHAT_RE = re.compile(r"\[閒聊\]\s*(\d{4})\s*/\s*(\d{1,2})\s*/\s*(\d{1,2})\s*(盤中|盤後)\s*閒聊")
ENT_RE = re.compile(r'<div class="r-ent">(.*?)<div class="mark">', re.S)
LINK_RE = re.compile(r'<a href="/bbs/Stock/(M\.(\d+)\.A\.[0-9A-F]+)\.html">([^<]+)</a>')
NREC_RE = re.compile(r'class="nrec">(?:<span[^>]*>)?([^<]*)')
PUSH_RE = re.compile(
    r'<div class="push(?: [^"]*)?"><span class="[^"]*push-tag">([^<]*)</span>'
    r'<span class="[^"]*push-userid">[^<]*</span>'
    r'<span class="[^"]*push-content">([^<]*)</span>'
    r'<span class="push-ipdatetime">([^<]*)</span>'
)
PUSH_TIME_RE = re.compile(r"(\d{1,2})/(\d{1,2})\s+(\d{1,2}):(\d{2})")

S = requests.Session()
S.headers["User-Agent"] = "Mozilla/5.0 (research crawler)"
S.cookies.set("over18", "1", domain=".ptt.cc")


def log(*a):
    print(dt.datetime.now().strftime("%H:%M:%S"), *a, flush=True)


def get(url: str) -> str | None:
    """GET with retry/backoff. 404 → None。連續失敗就拋錯讓呼叫端停下。"""
    for attempt in range(5):
        try:
            r = S.get(url, timeout=30)
        except requests.RequestException as e:
            wait = 5 * (attempt + 1)
            log(f"連線錯誤 {e!r}，{wait}s 後重試")
            time.sleep(wait)
            continue
        time.sleep(SLEEP)
        if r.status_code == 200:
            return r.text
        if r.status_code == 404:
            return None
        wait = 10 * (attempt + 1)
        log(f"HTTP {r.status_code} {url}，{wait}s 後重試")
        time.sleep(wait)
    raise RuntimeError(f"多次失敗：{url}")


def nrec_to_int(s: str) -> int:
    s = s.strip()
    if not s:
        return 0
    if s == "爆":
        return 100
    if s.startswith("X"):
        return -100 if s == "XX" else -10 * int(s[1:] or 1)
    try:
        return int(s)
    except ValueError:
        return 0


def parse_index(html: str) -> list[dict]:
    rows = []
    for blk in ENT_RE.findall(html):
        m = LINK_RE.search(blk)
        if not m:
            continue  # 已刪除文章
        n = NREC_RE.search(blk)
        rows.append({
            "aid": m.group(1),
            "ts": int(m.group(2)),
            "title": unescape(m.group(3)).strip(),
            "nrec": nrec_to_int(n.group(1) if n else ""),
        })
    return rows


def latest_page() -> int:
    html = get(f"{BASE}/bbs/{BOARD}/index.html")
    nums = [int(x) for x in re.findall(r"/bbs/Stock/index(\d+)\.html", html)]
    return max(nums) + 1


def page_min_ts(p: int) -> int | None:
    html = get(f"{BASE}/bbs/{BOARD}/index{p}.html")
    rows = parse_index(html or "")
    return min(r["ts"] for r in rows) if rows else None


def find_start_page(since: dt.date, last: int) -> int:
    target = int(dt.datetime.combine(since, dt.time(), TZ).timestamp())
    lo, hi = 1, last
    while lo < hi:
        mid = (lo + hi) // 2
        t = page_min_ts(mid)
        if t is None or t < target:
            lo = mid + 1
        else:
            hi = mid
    return max(1, lo - 2)


def load_index() -> dict[str, dict]:
    if not INDEX_CSV.exists():
        return {}
    with INDEX_CSV.open(encoding="utf-8", newline="") as f:
        return {r["aid"]: r for r in csv.DictReader(f)}


def append_index(rows: list[dict], page: int):
    new = not INDEX_CSV.exists()
    with INDEX_CSV.open("a", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["aid", "ts", "title", "nrec", "page"])
        if new:
            w.writeheader()
        for r in rows:
            w.writerow({**r, "page": page})


def crawl_index(since: dt.date | None, pages: int | None):
    RAW.mkdir(parents=True, exist_ok=True)
    seen = load_index()
    last = latest_page()
    if pages:
        # 日常續抓：從索引裡已抓到的最後一頁往回退 2 頁開始（頁尾可能有新文補進來），
        # 機器關機幾天也能自動補齊；沒有索引時才退回「最新 N 頁」。
        done = [int(r["page"]) for r in seen.values() if r.get("page")]
        start = max(1, max(done) - 2) if done else last - pages + 1
        log(f"日常續抓索引：第 {start}～{last} 頁")
    else:
        done_pages = {int(r["page"]) for r in seen.values()}
        start = find_start_page(since, last)
        log(f"{since} 起始頁 ≈ {start}，最新頁 {last}，已抓 {len(done_pages)} 頁")
    progress_file = RAW / "index_progress.txt"
    resume = int(progress_file.read_text()) + 1 if (progress_file.exists() and not pages) else start
    start = max(start, resume) if not pages else start
    for p in range(start, last + 1):
        html = get(f"{BASE}/bbs/{BOARD}/index{p}.html")
        rows = [r for r in parse_index(html or "") if r["aid"] not in seen]
        for r in rows:
            seen[r["aid"]] = r
        append_index(rows, p)
        if not pages:
            progress_file.write_text(str(p))
        if p % 100 == 0 or p == last:
            log(f"索引 {p}/{last}，累計 {len(seen)} 篇")


def chat_threads() -> list[dict]:
    out = {}
    for r in load_index().values():
        m = CHAT_RE.search(r["title"])
        if not m or r["title"].startswith(("Re:", "Fw:")):
            continue
        y, mo, d, kind = int(m.group(1)), int(m.group(2)), int(m.group(3)), m.group(4)
        try:
            day = dt.date(y, mo, d)
        except ValueError:
            continue
        key = (day, kind)
        # 同一天同類若有多串（偶有重開），全部保留
        out.setdefault(key, []).append(r)
    res = []
    for (day, kind), rs in sorted(out.items()):
        for i, r in enumerate(sorted(rs, key=lambda x: int(x["ts"]))):
            res.append({"day": day, "kind": kind, "seq": i, **r})
    return res


def parse_pushes(html: str, day: dt.date) -> list[dict]:
    out = []
    for tag, content, ipdt in PUSH_RE.findall(html):
        m = PUSH_TIME_RE.search(ipdt)
        t = None
        if m:
            mo, d, hh, mm = map(int, m.groups())
            y = day.year + (1 if (day.month == 12 and mo == 1) else 0)
            try:
                t = dt.datetime(y, mo, d, hh, mm).strftime("%Y-%m-%d %H:%M")
            except ValueError:
                t = None
        text = unescape(content).lstrip(":").strip()
        out.append({"tag": tag.strip(), "text": text, "t": t})
    return out


def crawl_chat(refresh_days: int = 0):
    """抓閒聊串。refresh_days>0 時，串日期在最近 N 天內的即使抓過也重抓——
    串在下一交易日 08:30 前都還會有人推，之前抓的是半成品（週五盤後串要到週一早上才收尾）。"""
    CHAT_DIR.mkdir(parents=True, exist_ok=True)
    threads = chat_threads()
    cutoff = dt.date.today() - dt.timedelta(days=refresh_days)
    todo = [t for t in threads
            if (refresh_days and t["day"] >= cutoff)
            or not (CHAT_DIR / f"{t['day']}_{t['kind']}_{t['seq']}.jsonl.gz").exists()]
    log(f"閒聊串共 {len(threads)}，待抓 {len(todo)}")
    for i, t in enumerate(todo, 1):
        html = get(f"{BASE}/bbs/{BOARD}/{t['aid']}.html")
        if html is None:
            log(f"已刪除：{t['day']} {t['kind']}")
            continue
        pushes = parse_pushes(html, t["day"])
        path = CHAT_DIR / f"{t['day']}_{t['kind']}_{t['seq']}.jsonl.gz"
        tmp = path.with_suffix(".tmp")
        with gzip.open(tmp, "wt", encoding="utf-8") as f:
            f.write(json.dumps({"meta": {"day": str(t["day"]), "kind": t["kind"], "aid": t["aid"], "title": t["title"]}}, ensure_ascii=False) + "\n")
            for p in pushes:
                f.write(json.dumps(p, ensure_ascii=False) + "\n")
        tmp.replace(path)
        if i % 50 == 0 or i == len(todo):
            log(f"閒聊 {i}/{len(todo)}（{t['day']} {t['kind']} 推文 {len(pushes)}）")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["index", "chat", "recent"])
    ap.add_argument("--since", default="2020-01-01")
    ap.add_argument("--pages", type=int, default=15)
    a = ap.parse_args()
    if a.cmd == "index":
        crawl_index(dt.date.fromisoformat(a.since), None)
    elif a.cmd == "chat":
        crawl_chat()
    else:
        crawl_index(None, a.pages)
        crawl_chat(refresh_days=7)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
