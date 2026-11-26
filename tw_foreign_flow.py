"""上市三大法人買賣金額（證交所 BFI82U）下載與歷史檔維護。

來源：https://www.twse.com.tw/rwd/zh/fund/BFI82U?type=day&dayDate=YYYYMMDD&response=json
  每個交易日一次請求；非交易日回 stat ≠ "OK"。type=month 只給整月合計，沒有逐日，所以歷史要逐日抓。
  外資取「外資及陸資(不含外資自營商)」列（與 CT-20261111-04 同口徑），用 startswith 比對以容忍舊年度列名差異。
  單位：新台幣元。證交所會擋太密集的請求，回補時每次間隔約 3 秒，被擋（回傳不是 JSON）就停 30 秒再試一次。

歷史檔：tw_foreign_flow_data/twse_institutional.csv（data/ 被 .gitignore 排除，所以放模組旁）。
  回補：python tw_foreign_flow.py --start 2021-11-01
  補到今天：python tw_foreign_flow.py
"""

from __future__ import annotations

import argparse
import datetime as dt
import os
import random
import time

import pandas as pd

URL_TMPL = "https://www.twse.com.tw/rwd/zh/fund/BFI82U?type=day&dayDate={d:%Y%m%d}&response=json"
HISTORY_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "tw_foreign_flow_data",
                            "twse_institutional.csv")
ROWS = {  # 列名前綴 → 欄位前綴
    "外資及陸資": "foreign",
    "投信": "trust",
    "自營商(自行買賣)": "dealer_self",
    "自營商(避險)": "dealer_hedge",
}
COLUMNS = ["date", "foreign_buy", "foreign_sell", "foreign_net", "trust_net", "dealer_self_net", "dealer_hedge_net"]
HEADERS = {"User-Agent": "Mozilla/5.0 (war-room dashboard)"}


def _num(text) -> float:
    return float(str(text).replace(",", "").strip())


def parse_bfi82u(payload: dict) -> dict | None:
    """解析 BFI82U JSON。非交易日或格式不對回傳 None。金額單位：元。"""
    if not isinstance(payload, dict) or payload.get("stat") != "OK":
        return None
    row: dict = {}
    for rec in payload.get("data", []):
        if not rec:
            continue
        name = str(rec[0]).strip()
        for prefix, key in ROWS.items():
            if name.startswith(prefix) and f"{key}_net" not in row:
                # 「外資及陸資」要排除「外資自營商」那列（它不以「外資及陸資」開頭，startswith 已自然排除）
                buy, sell, net = _num(rec[1]), _num(rec[2]), _num(rec[3])
                row[f"{key}_net"] = net
                if key == "foreign":
                    row["foreign_buy"], row["foreign_sell"] = buy, sell
    return row if "foreign_net" in row else None


def fetch_day(day: dt.date, session=None, timeout: int = 30, retry_wait: float = 30.0) -> dict | None:
    import requests

    getter = session or requests
    for attempt in range(2):
        resp = getter.get(URL_TMPL.format(d=day), timeout=timeout, headers=HEADERS)
        try:
            payload = resp.json()
        except ValueError:
            if attempt == 0:
                if retry_wait:
                    time.sleep(retry_wait)  # 疑似被擋（回 HTML），停一下再試
                continue
            raise
        row = parse_bfi82u(payload)
        if row is None:
            return None
        row["date"] = pd.Timestamp(day)
        return row
    return None


def load_history(path: str = HISTORY_PATH) -> pd.DataFrame:
    if not os.path.exists(path):
        return pd.DataFrame(columns=COLUMNS)
    df = pd.read_csv(path, parse_dates=["date"])
    return df.sort_values("date").drop_duplicates("date", keep="last").reset_index(drop=True)


def fetch_range(start: dt.date, end: dt.date, pause: float = 3.0, max_requests: int | None = None,
                log=print) -> pd.DataFrame:
    import requests

    rows, n = [], 0
    with requests.Session() as s:
        day = start
        while day <= end:
            if day.weekday() < 5:
                if max_requests is not None and n >= max_requests:
                    break
                try:
                    row = fetch_day(day, session=s)
                except Exception as exc:  # noqa: BLE001 — 單日失敗不中斷，下次再補
                    log(f"{day} 失敗：{type(exc).__name__}")
                    row = None
                n += 1
                if row:
                    rows.append(row)
                if pause:
                    time.sleep(pause + random.uniform(0, 0.5))
            day += dt.timedelta(days=1)
    return pd.DataFrame(rows, columns=COLUMNS)


def merge_history(old: pd.DataFrame, new: pd.DataFrame) -> pd.DataFrame:
    frames = [f for f in (old, new) if f is not None and not f.empty]
    if not frames:
        return pd.DataFrame(columns=COLUMNS)
    both = pd.concat(frames, ignore_index=True)
    both["date"] = pd.to_datetime(both["date"])
    return both.sort_values("date").drop_duplicates("date", keep="last").reset_index(drop=True)[COLUMNS]


def main():
    ap = argparse.ArgumentParser(description="下載證交所三大法人買賣金額並更新歷史檔")
    ap.add_argument("--start", help="起始日 YYYY-MM-DD；省略則從歷史檔最後一天的隔天開始")
    ap.add_argument("--end", help="結束日 YYYY-MM-DD；省略則到今天")
    ap.add_argument("--path", default=HISTORY_PATH)
    args = ap.parse_args()

    hist = load_history(args.path)
    if args.start:
        start = dt.date.fromisoformat(args.start)
    elif not hist.empty:
        start = hist["date"].max().date() + dt.timedelta(days=1)
    else:
        start = dt.date(2021, 11, 1)
    end = dt.date.fromisoformat(args.end) if args.end else dt.date.today()

    new = fetch_range(start, end)
    merged = merge_history(hist, new)
    os.makedirs(os.path.dirname(args.path), exist_ok=True)
    tmp = args.path + ".tmp"
    merged.to_csv(tmp, index=False, float_format="%.0f")
    os.replace(tmp, args.path)
    print(f"新增 {len(new)} 天，歷史檔共 {len(merged)} 天"
          + (f"（{merged['date'].min():%Y-%m-%d}～{merged['date'].max():%Y-%m-%d}）" if len(merged) else ""))


if __name__ == "__main__":
    main()
