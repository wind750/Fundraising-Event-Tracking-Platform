"""股民溫度計核心（不依賴 Streamlit；UI 在 market_dashboard.py）。

溫度＝當日「多空淨分數」在**這一天以前**全部歷史中的百分位（擴張窗，不偷看未來），0＝史上最悲觀、100＝最樂觀。
多空淨分數 net＝(偏多推文數 − 偏空推文數) ÷ (偏多 + 偏空)，推文偏向由 lexicon.py 詞典判定。
"""
from __future__ import annotations

import datetime as dt
import random
import re
from collections import Counter
from pathlib import Path

import numpy as np
import pandas as pd

try:  # 套件內匯入（market_dashboard）與腳本直接執行兩種情境都要能用
    from .lexicon import classify
except ImportError:  # pragma: no cover
    from lexicon import classify

HERE = Path(__file__).resolve().parent
DAILY_CSV = HERE / "daily_sentiment.csv"
WORDS_CSV = HERE / "daily_top_words.csv"
QUOTES_CSV = HERE / "daily_quotes.csv"

MIN_HISTORY = 120  # 至少累積這麼多交易日才給溫度
ZONES = [  # (下界, 標籤, 顏色)；台股慣例：紅＝樂觀、綠＝悲觀
    (0, "極度悲觀", "#1b7f3b"),
    (10, "悲觀", "#6fbf73"),
    (30, "中性", "#9e9e9e"),
    (70, "樂觀", "#f08a7e"),
    (90, "極度樂觀", "#c62828"),
]
CHAT_RE = re.compile(r"\[閒聊\]\s*(\d{4})\s*/\s*(\d{1,2})\s*/\s*(\d{1,2})\s*(盤中|盤後)\s*閒聊")


def zone(temp: float | None) -> tuple[str, str]:
    if temp is None or pd.isna(temp):
        return "資料不足", "#9e9e9e"
    label, color = ZONES[0][1], ZONES[0][2]
    for lo, lab, col in ZONES:
        if temp >= lo:
            label, color = lab, col
    return label, color


def summarize_pushes(pushes: list[dict], seed: int = 0) -> tuple[dict, Counter, list[dict]]:
    """pushes: [{'tag','text','t': datetime}] → (計數 dict, 情緒詞 Counter, 代表推文)。"""
    c: Counter = Counter()
    words: Counter = Counter()
    greed_q, fear_q = [], []
    for p in pushes:
        r = classify(p["text"])
        ts = p["t"]
        c["n_push"] += 1
        c[f"tag_{p['tag']}"] += 1
        c[r["side"]] += 1
        c["greed"] += r["greed"]
        c["fear"] += r["fear"]
        if dt.time(9, 0) <= ts.time() <= dt.time(13, 30):
            c["n_push_session"] += 1
        for x in r["bull_words"]:
            words["+" + x] += 1
        for x in r["bear_words"]:
            words["-" + x] += 1
        if 6 <= len(p["text"]) <= 40:
            item = {"time": ts.strftime("%H:%M"), "text": p["text"]}
            if r["greed"]:
                greed_q.append({**item, "kind": "greed"})
            elif r["fear"]:
                fear_q.append({**item, "kind": "fear"})
    rnd = random.Random(seed)
    quotes = rnd.sample(greed_q, min(3, len(greed_q))) + rnd.sample(fear_q, min(3, len(fear_q)))
    return c, words, quotes


def row_from_counts(day: dt.date, c: Counter) -> dict:
    n, b, s = c["n_push"], c["bull"], c["bear"]
    return {
        "date": day.isoformat(),
        "n_push": n,
        "n_push_session": c["n_push_session"],
        "bull": b,
        "bear": s,
        "greed": c["greed"],
        "fear": c["fear"],
        "net": round((b - s) / (b + s), 4) if b + s else np.nan,
        "greed_share": round(c["greed"] / n, 4) if n else np.nan,
        "fear_share": round(c["fear"] / n, 4) if n else np.nan,
        "boo_share": round(c["tag_噓"] / n, 4) if n else np.nan,
    }


def _expanding_pct(x: pd.Series, min_history: int) -> pd.Series:
    """每一天的值，在「這一天以前」所有歷史值中的百分位（0–100），不含當天自己。"""
    vals = x.to_numpy(dtype=float)
    out = np.full(len(vals), np.nan)
    hist: list[float] = []
    for i, v in enumerate(vals):
        if len(hist) >= min_history and not np.isnan(v):
            arr = np.asarray(hist)
            out[i] = 100.0 * ((arr < v).sum() + 0.5 * (arr == v).sum()) / len(arr)
        if not np.isnan(v):
            hist.append(v)
    return pd.Series(out, index=x.index)


def add_temperature(df: pd.DataFrame, min_history: int = MIN_HISTORY) -> pd.DataFrame:
    df = df.sort_values("date").copy()
    df["net5"] = df["net"].rolling(5, min_periods=3).mean()
    df["temp"] = _expanding_pct(df["net"], min_history)
    df["temp5"] = _expanding_pct(df["net5"], min_history)
    df["fear5"] = df["fear_share"].rolling(5, min_periods=3).mean()
    df["greed5"] = df["greed_share"].rolling(5, min_periods=3).mean()
    med = df["n_push"].rolling(60, min_periods=20).median().shift(1)
    df["heat"] = df["n_push"] / med
    return df


def load_history() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    daily = pd.read_csv(DAILY_CSV, parse_dates=["date"]) if DAILY_CSV.exists() else pd.DataFrame()
    words = pd.read_csv(WORDS_CSV, parse_dates=["date"]) if WORDS_CSV.exists() else pd.DataFrame()
    quotes = pd.read_csv(QUOTES_CSV, parse_dates=["date"]) if QUOTES_CSV.exists() else pd.DataFrame()
    return daily, words, quotes


def fetch_live(after: dt.date, max_threads: int = 12) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """即時抓 PTT 搜尋頁第一頁裡、日期晚於 after 的盤中／盤後閒聊串（給部署版補最近幾天）。

    窗口簡化為：該日 08:00 起、下一個平日 08:30 前的推文。失敗時回傳空表，面板改用已提交的歷史。
    """
    try:
        from .crawl import BASE, S, parse_index, parse_pushes
    except ImportError:  # pragma: no cover
        from crawl import BASE, S, parse_index, parse_pushes

    threads: dict[dt.date, list[str]] = {}
    for q in ("盤中閒聊", "盤後閒聊"):
        r = S.get(f"{BASE}/bbs/Stock/search", params={"q": q}, timeout=10)
        r.raise_for_status()
        for row in parse_index(r.text):
            m = CHAT_RE.search(row["title"])
            if not m or row["title"].startswith(("Re:", "Fw:")):
                continue
            day = dt.date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
            if day > after:
                threads.setdefault(day, []).append(row["aid"])
    rows, wrows, qrows = [], [], []
    fetched = 0
    for day in sorted(threads):
        nxt = day + dt.timedelta(days=1)
        while nxt.weekday() >= 5:
            nxt += dt.timedelta(days=1)
        lo, hi = dt.datetime.combine(day, dt.time(8, 0)), dt.datetime.combine(nxt, dt.time(8, 30))
        pushes = []
        for aid in threads[day]:
            if fetched >= max_threads:
                break
            r = S.get(f"{BASE}/bbs/Stock/{aid}.html", timeout=15)
            fetched += 1
            if r.status_code != 200:
                continue
            for p in parse_pushes(r.text, day):
                if p["t"]:
                    t = dt.datetime.strptime(p["t"], "%Y-%m-%d %H:%M")
                    if lo <= t < hi:
                        pushes.append({**p, "t": t})
        if not pushes:
            continue
        c, w, q = summarize_pushes(pushes, seed=day.toordinal())
        rows.append({**row_from_counts(day, c), "live": True})
        for term, cnt in w.most_common(8):
            wrows.append({"date": day, "word": term[1:], "side": "bull" if term[0] == "+" else "bear", "count": cnt})
        for x in q:
            qrows.append({"date": day, **x})
    to_df = lambda r: pd.DataFrame(r).assign(date=lambda d: pd.to_datetime(d["date"])) if r else pd.DataFrame()  # noqa: E731
    return to_df(rows), to_df(wrows), to_df(qrows)
