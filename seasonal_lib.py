# -*- coding: utf-8 -*-
"""總統大選週期季節性運算——market_dashboard.py 與 seasonal_export.py 共用同一份算法。

從 market_dashboard.py 抽出，刻意不依賴 streamlit：
- market_dashboard.py 匯入本模組，在 @st.cache_data 包裝下互動使用。
- seasonal_export.py 匯入本模組，無頭執行後寫成 JSON 給艾略特波浪架構的
  多週期結構圖卡消費（介面待登錄 INTERFACE_REGISTRY.md）。

兩邊算出來的數字必須一致；任何行為變更都改這裡，不要在兩邊各自維護一份。
"""
import pandas as pd
import yfinance as yf

MIDTERM_CYCLE_OFFSET = 1  # (year - 2025) % 4 == 1 即為總統週期第二年／期中選舉年


def is_midterm_year(year: int) -> bool:
    return (year - 2025) % 4 == MIDTERM_CYCLE_OFFSET


def fetch_long_term_index(ticker: str) -> pd.Series:
    """長期歷史日收盤序列。與 market_dashboard.fetch_long_term_index 邏輯一致，
    差別只在這裡不掛 @st.cache_data——排程腳本沒有 streamlit 執行環境。"""
    data = yf.download(ticker, period="max", progress=False)
    if "Close" in data.columns:
        series = data["Close"]
        if isinstance(series, pd.DataFrame):
            return series.squeeze()
        return series
    return pd.Series(dtype=float)


def base_history_years(current_year: int, cycle_index: int, lookback_years: int, min_year_floor: int) -> list:
    """與 market_dashboard.py 主分頁的年份篩選邏輯逐行一致：
        start_eval_year = max(min_year_floor, current_year - lookback_years)
        base_history_years = [y for y in range(start_eval_year, current_year)
                               if (y - 2025) % 4 == cycle_index]
    current_year 本身被 range() 排除——只取歷史年份，不含當年。"""
    start_eval_year = max(min_year_floor, current_year - lookback_years)
    years = [y for y in range(start_eval_year, current_year) if (y - 2025) % 4 == cycle_index]
    years.sort(reverse=True)
    return years


def monthly_avg_returns(hist_df: pd.Series, years: list) -> dict:
    """12 個月各自的歷史平均報酬率（月對月：前月底收盤→本月底收盤）。
    回傳 {1: pct, ..., 12: pct}；某月無資料則值為 0.0（與 dashboard 長條圖一致）。
    同時回傳 matched_rets（Series，index=月底日期）供上層依月份再篩出樣本。"""
    if hist_df.empty:
        return {"by_month": {m: 0.0 for m in range(1, 13)}, "matched_rets": pd.Series(dtype=float)}

    pd_ver = tuple(int(x) for x in pd.__version__.split(".")[:2])
    monthly = hist_df.resample("ME").last() if pd_ver >= (2, 2) else hist_df.resample("M").last()
    monthly_ret = monthly.pct_change() * 100

    matched_rets = monthly_ret[monthly_ret.index.year.isin(years)]
    if matched_rets.empty:
        return {"by_month": {m: 0.0 for m in range(1, 13)}, "matched_rets": matched_rets}

    avg_by_month = matched_rets.groupby(matched_rets.index.month).mean()
    by_month = {m: float(avg_by_month.get(m, 0.0)) for m in range(1, 13)}
    return {"by_month": by_month, "matched_rets": matched_rets}


def month_stats(matched_rets: pd.Series, target_month: int) -> dict:
    """單一月份的平均報酬、上漲勝率、樣本數。month_rets 用 dropna()——
    樣本年首月因 pct_change() 產生 NaN 會被剔除，與 dashboard 一致。"""
    month_rets = matched_rets[matched_rets.index.month == target_month].dropna() if not matched_rets.empty else pd.Series(dtype=float)
    n = len(month_rets)
    if n == 0:
        return {"avg_return_pct": None, "win_rate_pct": None, "sample_n": 0}
    avg_return = float(month_rets.mean())
    win_rate = float((month_rets > 0).mean() * 100.0)
    return {"avg_return_pct": avg_return, "win_rate_pct": win_rate, "sample_n": n}


def daily_path_overlay(hist_df: pd.Series, target_month: int, years: list) -> dict:
    """逐年標準化每日路徑（該月首個交易日為基準 100）＋平均基準線。
    與 dashboard 疊加圖邏輯一致：只取該月 >1 個交易日的年份；index 用交易日序（1..N），
    不同年份天數不一時用 pandas concat 自動以 NaN 補齊、平均時自動排除 NaN。"""
    frames = []
    year_labels = []
    for year in years:
        try:
            month_daily = hist_df[(hist_df.index.year == year) & (hist_df.index.month == target_month)]
            if len(month_daily) <= 1:
                continue
            first_price = float(month_daily.iloc[0])
            normalized = (month_daily / first_price) * 100.0
            frames.append(pd.Series(normalized.values, name=str(year)))
            year_labels.append(year)
        except Exception:
            # 個別年份資料異常時跳過該年、不中斷整體計算——與 market_dashboard.py
            # 原本的逐年 try/except 行為一致；上百年資料裡偶爾一年有問題不該讓整批失敗。
            continue

    if not frames:
        return {"years": [], "daily_paths": {}, "avg_baseline": []}

    combined = pd.concat(frames, axis=1)
    combined.columns = [str(y) for y in year_labels]
    avg_baseline = combined.mean(axis=1)

    # 刻意不四捨五入：這個結果同時餵給互動圖表（要原始精度）與 JSON 匯出
    # （要固定小數位）。四捨五入是匯出格式的事，交給呼叫端在寫檔前做，
    # 不要在共用計算層就把精度丟掉——曾實測讓 dashboard 圖表產生 5e-5 誤差。
    daily_paths = {
        str(y): [None if pd.isna(v) else float(v) for v in combined[str(y)].tolist()]
        for y in year_labels
    }
    return {
        "years": year_labels,
        "daily_paths": daily_paths,
        "avg_baseline": [float(v) for v in avg_baseline.tolist()],
    }
