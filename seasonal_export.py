# -*- coding: utf-8 -*-
"""總統大選週期季節性——無頭匯出腳本。

輸出 data/seasonal/seasonal_YYYYMM.json + manifest_YYYYMM.json，供艾略特波浪架構
的多週期結構圖卡唯讀消費（跨專案介面，待登錄 INTERFACE_REGISTRY.md）。

固定口徑（與 market_dashboard.py「🗓️ 歷史週期」分頁預設選項逐項一致，已用真實
^GSPC 資料核對：2026年9月 → 12 年樣本、平均 -1.69%、勝率 42%，與截圖相符）：
    基準 = ^GSPC（標普 500）
    範圍 = 期中選舉年（總統週期第二年）
    回溯 = 50 年、下限年份 1927
不做其他基準或範圍——這支腳本只服務一個消費者、一種口徑；要多種口徑是另一個任務。

排程：建議每月最後一個交易日盤後跑一次，預設輸出「下個月」的季節性，讓圖卡在
新月份開始前就有資料可用。也可用 --month/--year 手動指定，用於初次部署或重跑。

用法：
    python seasonal_export.py                  # 預設：下個月
    python seasonal_export.py --month 9         # 指定月份，年份預設今年
    python seasonal_export.py --month 9 --year 2026
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import sys
from datetime import datetime

import pytz

import seasonal_lib as sl

try:  # Windows 主控台預設 cp950，直接印中文會亂碼
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:  # pragma: no cover
    pass

TW_TZ = pytz.timezone("Asia/Taipei")
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
OUT_DIR = os.path.join(BASE_DIR, "data", "seasonal")

BASIS_TICKER = "^GSPC"
BASIS_LABEL = "美股 S&P 500 (^GSPC)"
SCOPE = "midterm"
LOOKBACK_YEARS = 50
MIN_YEAR_FLOOR = 1927


def _default_target():
    now = datetime.now(TW_TZ)
    if now.month == 12:
        return 1, now.year + 1
    return now.month + 1, now.year


def build_payload(target_month: int, target_year: int) -> dict:
    cycle_index = (target_year - 2025) % 4
    if cycle_index != sl.MIDTERM_CYCLE_OFFSET:
        raise ValueError(
            f"{target_year} 年不是期中選舉年（cycle_index={cycle_index}，"
            f"預期 {sl.MIDTERM_CYCLE_OFFSET}）。本腳本口徑固定為期中選舉年，"
            "不支援其他週期年份——換年份前請先確認這是你要的。"
        )

    hist = sl.fetch_long_term_index(BASIS_TICKER)
    if hist.empty:
        raise RuntimeError(f"{BASIS_TICKER} 歷史資料下載失敗或為空，不寫檔——不得用空資料覆蓋既有輸出。")

    years = sl.base_history_years(target_year, cycle_index, LOOKBACK_YEARS, MIN_YEAR_FLOOR)
    if not years:
        raise RuntimeError(f"目標年份 {target_year} 找不到任何期中選舉年歷史樣本，不寫檔。")

    monthly = sl.monthly_avg_returns(hist, years)
    stats = sl.month_stats(monthly["matched_rets"], target_month)
    overlay = sl.daily_path_overlay(hist, target_month, years)

    if stats["sample_n"] == 0:
        raise RuntimeError(f"{target_year}-{target_month:02d} 月報酬樣本為 0，不寫檔——避免下游拿到全空統計當成有效資料。")

    return {
        "interface": "seasonal-midterm-v1",
        "basis": BASIS_TICKER,
        "basis_label": BASIS_LABEL,
        "scope": SCOPE,
        "scope_label": "期中選舉年（總統週期第二年）",
        "target_year": target_year,
        "month": target_month,
        "lookback_years": LOOKBACK_YEARS,
        "min_year_floor": MIN_YEAR_FLOOR,
        "sample_years": years,
        "sample_n": stats["sample_n"],
        "avg_return_pct": round(stats["avg_return_pct"], 4),
        "win_rate_pct": round(stats["win_rate_pct"], 2),
        # 四捨五入到小數 4 位在這裡做（JSON 匯出邊界），不在 seasonal_lib 裡做——
        # 那份會同時被互動圖表引用，過早四捨五入會讓圖表數字偏離真實計算值。
        "daily_paths": {
            year: [None if v is None else round(v, 4) for v in path]
            for year, path in overlay["daily_paths"].items()
        },
        "avg_baseline": [round(v, 4) for v in overlay["avg_baseline"]],
        "data_range": {
            "first_date": hist.index.min().strftime("%Y-%m-%d"),
            "last_date": hist.index.max().strftime("%Y-%m-%d"),
        },
        "generated_at": datetime.now(TW_TZ).strftime("%Y-%m-%dT%H:%M:%S%z"),
    }


def write_payload(payload: dict, out_dir: str) -> tuple:
    os.makedirs(out_dir, exist_ok=True)
    stamp = f"{payload['target_year']}{payload['month']:02d}"
    data_path = os.path.join(out_dir, f"seasonal_{stamp}.json")
    manifest_path = os.path.join(out_dir, f"manifest_{stamp}.json")

    body = json.dumps(payload, ensure_ascii=False, indent=2)
    # 原子寫入：先寫暫存檔再替換，避免消費端讀到寫一半的檔案。
    tmp_path = data_path + ".tmp"
    with io.open(tmp_path, "w", encoding="utf-8") as handle:
        handle.write(body)
    os.replace(tmp_path, data_path)

    manifest = {
        "interface": payload["interface"],
        "filename": os.path.basename(data_path),
        "target_year": payload["target_year"],
        "month": payload["month"],
        "sample_n": payload["sample_n"],
        "generated_at": payload["generated_at"],
        "sha256": hashlib.sha256(body.encode("utf-8")).hexdigest(),
        "size_bytes": len(body.encode("utf-8")),
    }
    manifest_body = json.dumps(manifest, ensure_ascii=False, indent=2)
    tmp_manifest = manifest_path + ".tmp"
    with io.open(tmp_manifest, "w", encoding="utf-8") as handle:
        handle.write(manifest_body)
    os.replace(tmp_manifest, manifest_path)

    return data_path, manifest_path


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--month", type=int, default=None, help="目標月份 1-12；預設下個月")
    parser.add_argument("--year", type=int, default=None, help="目標年份；預設隨 --month 推算，須為期中選舉年")
    parser.add_argument("--out-dir", default=OUT_DIR, help=f"輸出目錄，預設 {OUT_DIR}")
    args = parser.parse_args(argv)

    default_month, default_year = _default_target()
    target_month = args.month or default_month
    target_year = args.year or (default_year if args.month is None else datetime.now(TW_TZ).year)

    if not (1 <= target_month <= 12):
        parser.error("--month 必須是 1-12")

    print(f"目標：{target_year}-{target_month:02d}　基準：{BASIS_LABEL}　範圍：期中選舉年　回溯：{LOOKBACK_YEARS}年")
    payload = build_payload(target_month, target_year)
    data_path, manifest_path = write_payload(payload, args.out_dir)

    print(f"樣本年份 n={payload['sample_n']}: {payload['sample_years']}")
    print(f"平均報酬 {payload['avg_return_pct']:+.2f}%　勝率 {payload['win_rate_pct']:.0f}%")
    print(f"已寫入 {data_path}")
    print(f"已寫入 {manifest_path}")


if __name__ == "__main__":
    main()
