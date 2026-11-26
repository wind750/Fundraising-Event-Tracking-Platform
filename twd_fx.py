"""台幣匯率走勢與台積電 ADR 溢價（台股戰略分頁用）。

只放純計算，不碰 Streamlit，方便單元測試。

方向約定：USD/TWD（yfinance 代號 TWD=X）數字往上＝1 美元換更多台幣＝**台幣貶值**。

ADR 溢價的時間配對（2026-11-26 實測後定案）：
台股 D 日 13:30 收盤時，美股最近一次收盤是 D 的前一個美股交易日（台北時間清晨 4~5 點），
D 日當天的美股收盤要再等 15 個多小時才出現。
所以台股 D 日配「D 之前最近一個 ADR 收盤」，不配同日。
用 2021-11~2026-11 資料比較：同日配對的溢價日變動標準差 3.09%，前一日配對 2.38%，雜訊少約 23%。
"""

from __future__ import annotations

import pandas as pd

# 1 股 TSM ADR = 5 股台積電普通股
TSMC_ADR_RATIO = 5
FX_MA_WINDOW = 60      # 季線：與日圓區塊的 60MA 判讀一致
PREMIUM_MA_WINDOW = 20  # 溢價每天跳動大，另畫 20 日均線看趨勢


def _clean(series: pd.Series) -> pd.Series:
    """只留真實交易日、依日期排序。raw_df 是多資產聯集日曆，不可 ffill。"""
    s = pd.Series(series).dropna().astype(float)
    s = s[~s.index.duplicated(keep="last")]
    return s.sort_index()


def fx_trend_frame(fx: pd.Series, ma_window: int = FX_MA_WINDOW) -> pd.DataFrame:
    """匯率收盤與 N 日均線（均線以匯率自己的交易日計算）。"""
    s = _clean(fx)
    return pd.DataFrame({"fx": s, "ma": s.rolling(ma_window).mean()})


def fx_summary(fx: pd.Series, ma_window: int = FX_MA_WINDOW, change_days: int = 20) -> dict | None:
    """最新匯率、N 日變動（%）、對均線乖離（%）。資料不足回傳 None。"""
    s = _clean(fx)
    if len(s) <= max(ma_window, change_days):
        return None
    last = float(s.iloc[-1])
    prev = float(s.iloc[-1 - change_days])
    ma = float(s.rolling(ma_window).mean().iloc[-1])
    return {
        "date": s.index[-1],
        "last": last,
        "change_pct": (last / prev - 1) * 100,
        "ma": ma,
        "bias_pct": (last / ma - 1) * 100,
        # 數字往上＝台幣貶值
        "twd_weaker_than_ma": last > ma,
    }


def adr_premium_frame(
    adr: pd.Series,
    local: pd.Series,
    fx: pd.Series,
    ratio: int = TSMC_ADR_RATIO,
    ma_window: int = PREMIUM_MA_WINDOW,
) -> pd.DataFrame:
    """以台股交易日為主軸計算 ADR 溢價。

    premium = ADR收盤 ÷ ratio × USD/TWD ÷ 台股收盤 − 1
    ADR 取「台股日期之前」最近一個收盤（不含同日），匯率取台股日期當天或之前最近一筆。
    """
    local_s = _clean(local)
    adr_s = _clean(adr)
    fx_s = _clean(fx)
    if local_s.empty or adr_s.empty or fx_s.empty:
        return pd.DataFrame(columns=["local", "adr", "adr_date", "fx", "premium", "premium_ma"])

    base = pd.DataFrame({"date": local_s.index, "local": local_s.values})
    adr_df = pd.DataFrame({"adr_date": adr_s.index, "adr": adr_s.values})
    fx_df = pd.DataFrame({"fx_date": fx_s.index, "fx": fx_s.values})

    merged = pd.merge_asof(base, adr_df, left_on="date", right_on="adr_date",
                           direction="backward", allow_exact_matches=False)
    merged = pd.merge_asof(merged, fx_df, left_on="date", right_on="fx_date",
                           direction="backward", allow_exact_matches=True)
    merged = merged.dropna(subset=["local", "adr", "fx"]).set_index("date")
    merged["premium"] = merged["adr"] / ratio * merged["fx"] / merged["local"] - 1
    merged["premium_ma"] = merged["premium"].rolling(ma_window).mean()
    return merged[["local", "adr", "adr_date", "fx", "premium", "premium_ma"]]


def percentile_of_last(series: pd.Series) -> float | None:
    """最後一個值在整段序列中的百分位（0~100，含自己）。"""
    s = pd.Series(series).dropna()
    if len(s) < 2:
        return None
    return float((s <= s.iloc[-1]).mean() * 100)


def adr_lag_weekdays(local_date, adr_date) -> int:
    """台股日期與配對 ADR 日期之間，夾了幾個平日（不含兩端）。

    正常配對＝0（前一個平日，或週一配週五）。大於 0 代表 ADR 資料沒更新或美股休市，
    此時溢價是拿較舊的美股價格算的，畫面要提示。
    """
    start = pd.Timestamp(adr_date).normalize() + pd.Timedelta(days=1)
    end = pd.Timestamp(local_date).normalize() - pd.Timedelta(days=1)
    if end < start:
        return 0
    return len(pd.bdate_range(start, end))
