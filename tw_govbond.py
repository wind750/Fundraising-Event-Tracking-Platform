"""台灣公債殖利率（櫃買中心每日殖利率曲線檔）下載與歷史檔維護。

來源：櫃買中心「債券 > 日統計 > 殖利率曲線」，每個營業日一個 Excel：
  https://www.tpex.org.tw/storage/bond_zone/tradeinfo/govbond/YYYY/YYYYMM/Curve.YYYYMMDD-C.xls
  （頁面 https://www.tpex.org.tw/zh-tw/bond/info/statistics-gb/day/yield.html 背後的 POST /www/zh-tw/bond/govDaily2 列出檔名）
  第 1 個工作表＝2／5／10／20／30 年指標公債的「等殖系統成交量加權平均殖利率」；
  第 3 個工作表＝櫃買擬合的零息殖利率曲線（Cubic B-Spline 與 Svensson，小數表示）。
  2021-11～2026-11 抽樣檢查格式一致（2026-11-26）。

⚠ 台債流動性差：指標公債當天沒成交時，櫃買沿用最近一次成交的殖利率（例：2026-11-02 的 30 年期 1.886%
  是約三個月前的成交）。所以「殖利率連續好幾天完全不變」多半代表沒成交，不是市場真的不動。

歷史檔：tw_govbond_data/yields.csv（一個營業日一列；data/ 被 .gitignore 排除，所以不放那裡）。
  回補：python tw_govbond.py --start 2021-11-01
  補到今天：python tw_govbond.py
"""

from __future__ import annotations

import argparse
import datetime as dt
import os
import time

import pandas as pd

URL_TMPL = ("https://www.tpex.org.tw/storage/bond_zone/tradeinfo/govbond/"
            "{d:%Y}/{d:%Y%m}/Curve.{d:%Y%m%d}-C.xls")
HISTORY_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "tw_govbond_data", "yields.csv")
TENORS = {"2年": "2y", "5年": "5y", "10年": "10y", "20年": "20y", "30年": "30y"}
ZC_TENORS = {2.0: "zc_2y", 10.0: "zc_10y"}
COLUMNS = (["date"] + [f"bm_{v}" for v in TENORS.values()] + [f"code_{v}" for v in TENORS.values()]
           + list(ZC_TENORS.values()))
XLS_MAGIC = b"\xd0\xcf\x11\xe0"
HEADERS = {"User-Agent": "Mozilla/5.0 (war-room dashboard)"}


def parse_curve_xls(content: bytes) -> dict:
    """解析一天的殖利率曲線檔。殖利率一律為「%」（零息曲線原檔是小數，這裡 ×100）。"""
    import xlrd

    book = xlrd.open_workbook(file_contents=content)
    row: dict = {}
    bench = book.sheet_by_index(0)
    for r in range(1, bench.nrows):
        tenor_cell = str(bench.cell_value(r, 1))
        for zh, key in TENORS.items():
            if tenor_cell.startswith(zh):
                y = bench.cell_value(r, 2)
                if isinstance(y, (int, float)):
                    row[f"bm_{key}"] = float(y)
                    row[f"code_{key}"] = str(bench.cell_value(r, 0)).strip()
    if book.nsheets >= 3:
        zc = book.sheet_by_index(2)
        for r in range(zc.nrows):
            tenor = zc.cell_value(r, 0)
            if isinstance(tenor, (int, float)) and float(tenor) in ZC_TENORS:
                v = zc.cell_value(r, 1)  # Cubic B-Spline 欄
                if isinstance(v, (int, float)):
                    row[ZC_TENORS[float(tenor)]] = round(float(v) * 100, 4)
    return row


def fetch_day(day: dt.date, session=None, timeout: int = 30) -> dict | None:
    """下載並解析一天。非營業日或檔案不存在回傳 None。"""
    import requests

    getter = session or requests
    resp = getter.get(URL_TMPL.format(d=day), timeout=timeout, headers=HEADERS)
    if resp.status_code != 200 or not resp.content.startswith(XLS_MAGIC):
        return None
    row = parse_curve_xls(resp.content)
    if "bm_10y" not in row:
        return None
    row["date"] = pd.Timestamp(day)
    return row


def load_history(path: str = HISTORY_PATH) -> pd.DataFrame:
    if not os.path.exists(path):
        return pd.DataFrame(columns=COLUMNS)
    df = pd.read_csv(path, parse_dates=["date"], dtype={f"code_{v}": str for v in TENORS.values()})
    return df.sort_values("date").drop_duplicates("date", keep="last").reset_index(drop=True)


def fetch_range(start: dt.date, end: dt.date, pause: float = 0.4, max_requests: int | None = None,
                log=print) -> pd.DataFrame:
    """逐個平日下載 [start, end]。max_requests 限制最多發幾次請求（儀表板即時補缺時用）。"""
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
                    time.sleep(pause)
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
    ap = argparse.ArgumentParser(description="下載櫃買公債殖利率曲線並更新歷史檔")
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
    merged.to_csv(tmp, index=False)
    os.replace(tmp, args.path)
    print(f"新增 {len(new)} 天，歷史檔共 {len(merged)} 天"
          + (f"（{merged['date'].min():%Y-%m-%d}～{merged['date'].max():%Y-%m-%d}）" if len(merged) else ""))


if __name__ == "__main__":
    main()
