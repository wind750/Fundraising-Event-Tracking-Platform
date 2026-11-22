"""把 data/ptt_raw/ 的閒聊推文與看板索引彙總成每日情緒表（提交進 repo 給部署版讀）。

產出：ptt_sentiment/daily_sentiment.csv、daily_top_words.csv、daily_quotes.csv
時間對齊（與 CT-20261122-03 一致）：第 t 交易日的情緒＝t 日盤中串＋盤後串裡，
推文時間落在 [t 日 08:00, 下一交易日 08:30) 的推文。交易日曆取 ^TWII 實際有收盤的日子。
"""
from __future__ import annotations

import bisect
import csv
import datetime as dt
import gzip
import json
import re
import sys
from collections import Counter
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from thermometer import DAILY_CSV, QUOTES_CSV, WORDS_CSV, row_from_counts, summarize_pushes  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "ptt_raw"
TARGET_RE = re.compile(r"^\[標的\].*?(多|空)\s*$")


def trading_days() -> list[dt.date]:
    cache = RAW / "twii.csv"
    try:
        import yfinance as yf

        df = yf.download("^TWII", start="2019-12-01", progress=False, auto_adjust=False)
        if len(df):
            df.columns = [c[0] if isinstance(c, tuple) else c for c in df.columns]
            df[["Open", "High", "Low", "Close", "Volume"]].to_csv(cache)
    except Exception as e:  # 網路失敗就用快取
        print("yfinance 失敗，改用快取：", e)
    df = pd.read_csv(cache, index_col=0, parse_dates=True)
    days = [d.date() for d in df.index]
    # 今天若尚未收盤，yfinance 還沒有這天；以平日補到今天
    d = days[-1] + dt.timedelta(days=1)
    while d <= dt.date.today():
        if d.weekday() < 5:
            days.append(d)
        d += dt.timedelta(days=1)
    return days


def assign_day(ts: dt.datetime, days: list[dt.date], starts: list[dt.datetime]) -> dt.date | None:
    i = bisect.bisect_right(starts, ts) - 1  # 最後一個「08:00 已開始」的交易日
    if i < 0:
        return None
    if i > 0 and ts < starts[i] + dt.timedelta(minutes=30):  # 下一交易日 08:00～08:30 仍屬前一交易日
        i -= 1
    return days[i]


def main():
    days = trading_days()
    day_set = set(days)
    starts = [dt.datetime.combine(d, dt.time(8, 0)) for d in days]

    pushes_by_day: dict[dt.date, list[dict]] = {}
    threads = Counter()
    for f in sorted((RAW / "chat").glob("*.jsonl.gz")):
        with gzip.open(f, "rt", encoding="utf-8") as fh:
            lines = [json.loads(x) for x in fh]
        meta = lines[0]["meta"]
        tday = dt.date.fromisoformat(meta["day"])
        if tday not in day_set:
            continue
        threads[tday] += 1
        bucket = pushes_by_day.setdefault(tday, [])
        for p in lines[1:]:
            if not p.get("t"):
                continue
            ts = dt.datetime.strptime(p["t"], "%Y-%m-%d %H:%M")
            if assign_day(ts, days, starts) == tday:
                bucket.append({**p, "t": ts})

    # 看板索引：每日發文量與 [標的] 多／空篇數
    posts, tgt = Counter(), Counter()
    if (RAW / "index.csv").exists():
        seen = set()
        with (RAW / "index.csv").open(encoding="utf-8", newline="") as fh:
            for r in csv.DictReader(fh):
                if r["aid"] in seen:
                    continue
                seen.add(r["aid"])
                ts = dt.datetime.fromtimestamp(int(r["ts"]), dt.timezone.utc).replace(tzinfo=None) + dt.timedelta(hours=8)
                d = assign_day(ts, days, starts)
                if d is None:
                    continue
                posts[d] += 1
                m = TARGET_RE.match(r["title"])
                if m:
                    tgt[(d, m.group(1))] += 1

    rows, wrows, qrows = [], [], []
    for d in sorted(pushes_by_day):
        c, w, q = summarize_pushes(pushes_by_day[d], seed=d.toordinal())
        rows.append({
            **row_from_counts(d, c),
            "posts": posts.get(d, 0),
            "target_long": tgt.get((d, "多"), 0),
            "target_short": tgt.get((d, "空"), 0),
            "threads": threads[d],
        })
        for term, cnt in w.most_common(8):
            wrows.append({"date": d.isoformat(), "word": term[1:], "side": "bull" if term[0] == "+" else "bear", "count": cnt})
        for x in q:
            qrows.append({"date": d.isoformat(), **x})
    df = pd.DataFrame(rows)
    df.to_csv(DAILY_CSV, index=False, encoding="utf-8")
    pd.DataFrame(wrows).to_csv(WORDS_CSV, index=False, encoding="utf-8")
    pd.DataFrame(qrows).to_csv(QUOTES_CSV, index=False, encoding="utf-8")
    print(f"每日情緒 {len(df)} 天 → {DAILY_CSV.name}；最新 {df['date'].iloc[-1] if len(df) else '—'}")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
