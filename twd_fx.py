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

import numpy as np
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


# ---------------------------------------------------------------------------
# 台幣漲跌拆解：美元因素 vs 台灣因素
# ---------------------------------------------------------------------------
# 模型：USD/TWD 日對數報酬 = β × 美元指數日對數報酬 + 殘差
#   β×美元指數報酬 ＝「美元因素」（全球美元強弱帶動的部分）
#   殘差           ＝「台灣因素」（美元解釋不了、台灣自己的資金流與基本面）
#
# 三個設計決定（2026-11-26 用 2021-11~2026-11 資料實測）：
# 1. 時間錯開一天：台幣 D 日配美元指數 D 之前最近一筆。同日配對相關係數只有 0.06，
#    錯開一天是 0.40——台幣在台北時間收盤，當天美元指數要到美國收盤才定案。
# 2. 不放截距：截距會把半年內持續的升貶趨勢吃掉，而那正是要看的台灣因素。
# 3. β 只用「前一天為止」的 120 個交易日估（約半年，寫碼前定死、未調參），
#    當天殘差不會用到當天自己的資料。
# 實測：美元因素樣本外約解釋台幣日波動的 15%（各年 5%~40%）；
# 台灣因素 20 日累積與加權指數同期 20 日報酬相關 −0.40，但對未來 20 日報酬相關約 0
# ——只能描述現況，不是預測訊號。
DECOMP_WINDOW = 120
DECOMP_SUM_DAYS = 20


def _ns_index(idx) -> pd.DatetimeIndex:
    """日期索引統一成奈秒精度：Yahoo 是秒、CSV／FRED 解析可能是微秒，精度不同時 merge_asof 會直接報錯
    （2026-11-26 台美利差接 Yahoo 匯率時踩到）。"""
    return pd.DatetimeIndex(idx).astype("datetime64[ns]")


def _asof_previous(base: pd.Series, other: pd.Series) -> pd.Series:
    """對 base 的每個日期，取 other 在該日期「之前」（不含同日）最近一筆的值。"""
    b = pd.DataFrame({"date": _ns_index(base.index)})
    o = pd.DataFrame({"o_date": _ns_index(other.index), "val": other.values})
    m = pd.merge_asof(b, o, left_on="date", right_on="o_date",
                      direction="backward", allow_exact_matches=False)
    return pd.Series(m["val"].values, index=base.index)


def _decompose(fx_s: pd.Series, factor_aligned: pd.Series, window: int) -> pd.DataFrame:
    """USD/TWD 日報酬 = β × 因子日報酬 + 台灣因素。β 無截距、只用前一天為止的 window 日估計。"""
    cols = ["twd_ret", "factor_ret", "beta", "r2", "factor_part", "tw_part"]
    aligned = pd.DataFrame({"twd": fx_s, "factor": factor_aligned}).dropna()
    if len(aligned) <= window:
        return pd.DataFrame(columns=cols)
    rets = np.log(aligned).diff().dropna()
    rets.columns = ["twd_ret", "factor_ret"]

    xy = (rets["twd_ret"] * rets["factor_ret"]).rolling(window).sum()
    xx = (rets["factor_ret"] ** 2).rolling(window).sum()
    yy = (rets["twd_ret"] ** 2).rolling(window).sum()
    beta_in = xy / xx.where(xx > 0)
    # 無截距 R²＝1 − 殘差平方和 ÷ y 平方和；殘差平方和 = yy − β·xy
    r2_in = 1 - (yy - beta_in * xy) / yy.where(yy > 0)

    out = rets.copy()
    out["beta"] = beta_in.shift(1)   # 只用到前一天為止的資料
    out["r2"] = r2_in.shift(1)
    out["factor_part"] = out["beta"] * out["factor_ret"]
    out["tw_part"] = out["twd_ret"] - out["factor_part"]
    return out.dropna(subset=["beta"])[cols]


def dxy_decomposition(fx: pd.Series, dxy: pd.Series, window: int = DECOMP_WINDOW) -> pd.DataFrame:
    """逐日拆解 USD/TWD 報酬（皆為對數報酬，×100 約等於 %）：

    twd_ret     台幣當日報酬（正＝台幣貶）
    factor_ret  對應的美元指數報酬（前一個美元指數交易日）
    beta / r2   用前 window 日估出的敏感度與美元解釋比例（無截距 R²）
    factor_part 美元因素＝beta × factor_ret
    tw_part     台灣因素＝twd_ret − factor_part
    """
    fx_s, dxy_s = _clean(fx), _clean(dxy)
    if fx_s.empty or dxy_s.empty:
        return pd.DataFrame(columns=["twd_ret", "factor_ret", "beta", "r2", "factor_part", "tw_part"])
    return _decompose(fx_s, _asof_previous(fx_s, dxy_s), window)


def decomposition_summary(frame: pd.DataFrame, days: int = DECOMP_SUM_DAYS) -> dict | None:
    """最近 days 日的拆解加總（%），以及台灣因素在歷史滾動 days 日加總中的百分位。"""
    if frame is None or len(frame) < days:
        return None
    tail = frame.tail(days)
    tw_roll = frame["tw_part"].rolling(days).sum().dropna()
    return {
        "date": frame.index[-1],
        "days": days,
        "total_pct": float(tail["twd_ret"].sum() * 100),
        "factor_pct": float(tail["factor_part"].sum() * 100),
        "tw_pct": float(tail["tw_part"].sum() * 100),
        "beta": float(frame["beta"].iloc[-1]),
        "r2": float(frame["r2"].iloc[-1]),
        "tw_percentile": percentile_of_last(tw_roll),
    }


# ---------------------------------------------------------------------------
# 台幣 × 加權指數背離偵測
# ---------------------------------------------------------------------------
# 正常關係：台幣升值（外資匯入）時加權指數上漲，反之亦然。
# 2026-11-26 實測（2021-11~2026-11）：兩者都在台北時間交易，「同日」配對最準
# （日報酬相關 −0.18、20 日報酬相關 −0.41；錯開一天反而變弱），所以這裡不錯開。
#
# 判定規則（寫碼前定死、未依結果調整）：
#   1. 兩邊都看 20 日對數報酬；台幣取「升值為正」＝ −USD/TWD 報酬，正常時兩者同號。
#   2. 各自除以「前一天為止 252 日內的 20 日報酬標準差」→ 標準分數 z（以近一年波動為單位）。
#   3. 兩邊 |z| 都 ≥ 0.5 才算有明顯動作；方向相反＝背離。
# 只描述現況；背離之後台股怎麼走「尚未驗證」，要驗證須先在概念測試帳本開單。
DIVERGENCE_WINDOW = 20
DIVERGENCE_SCALE_DAYS = 252
DIVERGENCE_Z = 0.5
DIVERGENCE_CORR_WINDOW = 60

STATE_STOCK_UP_TWD_DOWN = "股漲匯貶"   # 背離：上漲沒有外資匯入撐腰
STATE_STOCK_DOWN_TWD_UP = "股跌匯升"   # 背離：下跌時資金沒有外逃
STATE_BOTH_UP = "股匯齊揚"
STATE_BOTH_DOWN = "股匯齊跌"
STATE_UNCLEAR = "訊號不明顯"
DIVERGENT_STATES = (STATE_STOCK_UP_TWD_DOWN, STATE_STOCK_DOWN_TWD_UP)


def _classify(z_stock: float, z_twd: float, th: float) -> str:
    if pd.isna(z_stock) or pd.isna(z_twd):
        return STATE_UNCLEAR
    if z_stock >= th and z_twd <= -th:
        return STATE_STOCK_UP_TWD_DOWN
    if z_stock <= -th and z_twd >= th:
        return STATE_STOCK_DOWN_TWD_UP
    if z_stock >= th and z_twd >= th:
        return STATE_BOTH_UP
    if z_stock <= -th and z_twd <= -th:
        return STATE_BOTH_DOWN
    return STATE_UNCLEAR


def twii_fx_divergence(
    fx: pd.Series,
    twii: pd.Series,
    window: int = DIVERGENCE_WINDOW,
    scale_days: int = DIVERGENCE_SCALE_DAYS,
    z_th: float = DIVERGENCE_Z,
    corr_window: int = DIVERGENCE_CORR_WINDOW,
) -> pd.DataFrame:
    """逐日背離判定。回傳欄位：

    stock_ret / twd_ret  20 日對數報酬（twd_ret 升值為正）
    z_stock / z_twd      以前一年 20 日報酬波動為單位的標準分數
    state                五種狀態之一
    corr                 近 corr_window 日「日報酬」相關係數（正常為正）
    """
    cols = ["stock_ret", "twd_ret", "z_stock", "z_twd", "state", "corr"]
    fx_s, ti_s = _clean(fx), _clean(twii)
    both = pd.concat([fx_s, ti_s], axis=1, keys=["fx", "ti"], sort=True).dropna()
    if len(both) <= window:
        return pd.DataFrame(columns=cols)

    logp = np.log(both)
    out = pd.DataFrame(index=both.index)
    out["stock_ret"] = logp["ti"].diff(window)
    out["twd_ret"] = -logp["fx"].diff(window)
    for col, zcol in (("stock_ret", "z_stock"), ("twd_ret", "z_twd")):
        scale = out[col].rolling(scale_days, min_periods=scale_days // 2).std().shift(1)
        out[zcol] = out[col] / scale.where(scale > 0)
    out["state"] = [_classify(a, b, z_th) for a, b in zip(out["z_stock"], out["z_twd"])]
    daily = logp.diff()
    out["corr"] = daily["ti"].rolling(corr_window).corr(-daily["fx"])
    return out.dropna(subset=["z_stock", "z_twd"])[cols]


def state_runs(states: pd.Series) -> pd.DataFrame:
    """把連續相同狀態合併成區段：state, start, end, days。"""
    s = pd.Series(states).dropna()
    if s.empty:
        return pd.DataFrame(columns=["state", "start", "end", "days"])
    run_id = (s != s.shift()).cumsum()
    g = s.groupby(run_id)
    return pd.DataFrame({
        "state": g.first().values,
        "start": g.apply(lambda x: x.index[0]).values,
        "end": g.apply(lambda x: x.index[-1]).values,
        "days": g.size().values,
    })


def divergence_summary(frame: pd.DataFrame) -> dict | None:
    """目前狀態、已持續天數、歷史上背離日佔比。"""
    if frame is None or frame.empty:
        return None
    last = frame.iloc[-1]
    runs = state_runs(frame["state"])
    return {
        "date": frame.index[-1],
        "state": last["state"],
        "run_days": int(runs["days"].iloc[-1]),
        "stock_pct": float(last["stock_ret"] * 100),
        "twd_pct": float(last["twd_ret"] * 100),
        "z_stock": float(last["z_stock"]),
        "z_twd": float(last["z_twd"]),
        "corr": float(last["corr"]) if pd.notna(last["corr"]) else None,
        "divergent_share": float(frame["state"].isin(DIVERGENT_STATES).mean() * 100),
    }


# ---------------------------------------------------------------------------
# 亞洲貨幣同步性
# ---------------------------------------------------------------------------
# 籃子成員依經濟理由選定（2026-11-26，未依相關高低挑選）：
#   韓元＝半導體出口競爭者、日圓＝區域主要貨幣、人民幣＝最大貿易夥伴、新加坡幣＝東南亞匯率中心。
#   港幣釘住美元，排除。籃子＝四者兌美元日對數報酬等權平均（USD/XXX 方向，正＝亞洲貨幣貶）。
# 對齊：Yahoo 亞洲貨幣都在亞洲時段定價，同日配對最準（2026-11-26 實測：同日日報酬相關
#   韓元 0.53／新加坡幣 0.51／日圓 0.30／人民幣 0.20，錯開一天全部掉到 ±0.08 內），所以這裡不錯開。
# 拆解沿用 _decompose：USD/TWD 日報酬 = β × 亞洲籃子日報酬 + 台灣獨有因素。
ASIA_PEERS = {"KRW=X": "韓元", "JPY=X": "日圓", "CNY=X": "人民幣", "SGD=X": "新加坡幣"}
SYNC_CORR_SHORT = 60
SYNC_CORR_LONG = 252


def _asof_same_day(base: pd.Series, other: pd.Series) -> pd.Series:
    """對 base 的每個日期，取 other 在該日期當天或之前最近一筆的值（同日配對）。"""
    b = pd.DataFrame({"date": _ns_index(base.index)})
    o = pd.DataFrame({"o_date": _ns_index(other.index), "val": other.values})
    m = pd.merge_asof(b, o, left_on="date", right_on="o_date", direction="backward")
    return pd.Series(m["val"].values, index=base.index)


def asia_basket_index(peers: dict) -> pd.Series:
    """亞洲籃子指數（起點 100）：成員 USD/XXX 日對數報酬等權平均後累積。
    只用所有成員都有報價的日子，避免某一成員缺日時籃子組成改變。"""
    frames = {k: _clean(v) for k, v in peers.items()}
    frames = {k: v for k, v in frames.items() if not v.empty}
    if not frames:
        return pd.Series(dtype=float)
    both = pd.concat(frames, axis=1, sort=True).dropna()
    if len(both) < 2:
        return pd.Series(dtype=float)
    ret = np.log(both).diff().mean(axis=1).fillna(0.0)
    return 100 * np.exp(ret.cumsum())


def asia_decomposition(fx: pd.Series, peers: dict, window: int = DECOMP_WINDOW) -> pd.DataFrame:
    """USD/TWD 報酬拆成「亞洲共同因素」與「台灣獨有因素」，欄位同 dxy_decomposition。"""
    fx_s = _clean(fx)
    basket = asia_basket_index(peers)
    if fx_s.empty or basket.empty:
        return pd.DataFrame(columns=["twd_ret", "factor_ret", "beta", "r2", "factor_part", "tw_part"])
    return _decompose(fx_s, _asof_same_day(fx_s, basket), window)


def currency_sync_table(fx: pd.Series, peers: dict, names: dict, days: int = DECOMP_SUM_DAYS,
                        short: int = SYNC_CORR_SHORT, long: int = SYNC_CORR_LONG) -> pd.DataFrame:
    """每個貨幣：近 days 日兌美元變動（升值為正，%）、與台幣近 short／long 日的日報酬相關。
    台幣自己也列一行（相關欄留空），方便排強弱。"""
    fx_s = _clean(fx)
    twd_r = np.log(fx_s).diff()
    rows = []
    for code, series in [("TWD=X", fx)] + list(peers.items()):
        s = _clean(series)
        if len(s) <= days:
            continue
        appr = -(np.log(s.iloc[-1]) - np.log(s.iloc[-1 - days])) * 100
        row = {"code": code, "name": names.get(code, code), "appr_pct": float(appr),
               "corr_short": np.nan, "corr_long": np.nan}
        if code != "TWD=X":
            r = pd.concat([twd_r, np.log(s).diff()], axis=1, keys=["a", "b"], sort=True).dropna()
            if len(r) >= short:
                row["corr_short"] = float(r["a"].tail(short).corr(r["b"].tail(short)))
            if len(r) >= long:
                row["corr_long"] = float(r["a"].tail(long).corr(r["b"].tail(long)))
        rows.append(row)
    table = pd.DataFrame(rows)
    if table.empty:
        return table
    table["rank"] = table["appr_pct"].rank(ascending=False, method="min").astype(int)
    return table.sort_values("rank").reset_index(drop=True)


def rolling_sync_corr(fx: pd.Series, peers: dict, names: dict, window: int = SYNC_CORR_SHORT) -> pd.DataFrame:
    """台幣與各亞洲貨幣的滾動日報酬相關（同日配對），欄名用中文名稱。"""
    twd_r = np.log(_clean(fx)).diff()
    out = {}
    for code, series in peers.items():
        r = pd.concat([twd_r, np.log(_clean(series)).diff()], axis=1, keys=["a", "b"], sort=True).dropna()
        if len(r) > window:
            out[names.get(code, code)] = r["a"].rolling(window).corr(r["b"])
    return pd.DataFrame(out).dropna(how="all")


# ---------------------------------------------------------------------------
# 台幣波動率異常
# ---------------------------------------------------------------------------
# 央行干預讓台幣平常很穩，所以「波動突然放大」本身就值得注意。
# 百分位口徑與戰情室 VIX 的 IVP 相同：今天的值高於「過去 252 個交易日（不含今天）」中多少比例的天數。
#
# Yahoo 假跳動過濾（2026-11-26 以 FRED DEXTAUS 為外部標準驗證後採用，門檻事前定死）：
#   某天 |日報酬| ≥ 0.5%，且隔天反向抵銷 80% 以上（|兩天相加| ≤ 0.2 × |當天|）→ 兩天合併成一天
#   （當天＝兩天淨變動、隔天＝0），淨變動不變、只去掉來回跳。
#   2021-11~2026-11 合併 16 對；20 日波動與 FRED 相關 0.845→0.877，
#   「Yahoo 百分位 ≥80 但 FRED <60」的假警報 22→5 天；2025-05 台幣急升等真實大波動不受影響。
#   限制：最新一天若是假跳動，要等隔天報價出來才會被濾掉。
DESPIKE_MIN = 0.005
DESPIKE_CANCEL = 0.2
VOL_WINDOW = 20
VOL_RANK_DAYS = 252
VOL_SHORT = 5
VOL_LONG = 60


def despike_returns(r: pd.Series, th: float = DESPIKE_MIN, cancel: float = DESPIKE_CANCEL):
    """合併「跳出去又跳回來」的成對假跳動。回傳 (處理後報酬, 被合併的日期清單)。"""
    s = pd.Series(r).dropna()
    vals = s.to_numpy(dtype=float, copy=True)
    flagged = []
    i = 0
    while i < len(vals) - 1:
        a, b = vals[i], vals[i + 1]
        if abs(a) >= th and abs(a + b) <= cancel * abs(a):
            vals[i] = a + b
            vals[i + 1] = 0.0
            flagged.append(s.index[i])
            i += 2
        else:
            i += 1
    return pd.Series(vals, index=s.index), flagged


def _trailing_percentile(series: pd.Series, days: int = VOL_RANK_DAYS) -> pd.Series:
    """今天的值高於過去 days 個交易日（不含今天）中多少比例的天數（%）。與 VIX IVP 同口徑。"""
    return series.rolling(days + 1).apply(lambda w: (w[:-1] < w[-1]).mean() * 100, raw=True)


def vol_frame(fx: pd.Series) -> tuple[pd.DataFrame, list]:
    """回傳 (逐日波動表, 被合併的假跳動日期)。

    rv         20 日年化實現波動（%）
    pct        rv 在過去 252 日中的百分位
    expansion  近 5 日波動 ÷ 近 60 日波動（>1＝最近一週比近三個月更震）
    """
    s = _clean(fx)
    if len(s) < 3:
        return pd.DataFrame(columns=["rv", "pct", "expansion"]), []
    r, flagged = despike_returns(np.log(s).diff())
    ann = np.sqrt(252) * 100
    out = pd.DataFrame(index=r.index)
    out["rv"] = r.rolling(VOL_WINDOW).std() * ann
    out["pct"] = _trailing_percentile(out["rv"])
    out["expansion"] = r.rolling(VOL_SHORT).std() / r.rolling(VOL_LONG).std()
    return out.dropna(subset=["rv"]), flagged


def vol_state(pct: float) -> str:
    """與 VIX IVP 相同的 95／80／20 分界。"""
    if pct is None or pd.isna(pct):
        return "資料暖機中"
    if pct >= 95:
        return "🚨 異常高波動"
    if pct >= 80:
        return "⚠️ 波動偏高"
    if pct <= 20:
        return "🟢 異常平靜"
    return "中性"


def vol_peer_table(series_by_code: dict, names: dict) -> pd.DataFrame:
    """各貨幣的 20 日年化波動與 252 日百分位（同樣先過濾假跳動）。"""
    rows = []
    for code, series in series_by_code.items():
        frame, _ = vol_frame(series)
        if frame.empty:
            continue
        last = frame.iloc[-1]
        rows.append({"code": code, "name": names.get(code, code), "rv": float(last["rv"]),
                     "pct": float(last["pct"]) if pd.notna(last["pct"]) else np.nan})
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# 台美利差
# ---------------------------------------------------------------------------
# 台債：櫃買每日殖利率曲線檔（tw_govbond.py 維護 tw_govbond_data/yields.csv）。
#   主序列用櫃買擬合的「零息殖利率曲線（Cubic B-Spline）」2 年、10 年點；
#   指標公債（bm_*）是成交量加權殖利率，沒成交就沿用舊值，日資料會整段不動，只當參考並標示「幾天沒變」。
# 美債：FRED DGS2／DGS10（紐約收盤，約落後 1～2 個營業日）。
# 對齊：以台債營業日為主軸，美債取同日或之前最近一筆。
# 利差＝美債 − 台債（百分點）；正＝美債利率高，持有美元比台幣多拿的利息。
SPREAD_CHANGE_DAYS = 20


def parse_fred_csv(text: str) -> pd.Series:
    """FRED fredgraph.csv（兩欄：日期、數值；缺值為 "."）→ 數值序列。"""
    import io

    df = pd.read_csv(io.StringIO(text))
    if df.shape[1] < 2:
        return pd.Series(dtype=float)
    s = pd.Series(pd.to_numeric(df.iloc[:, 1], errors="coerce").values,
                  index=pd.to_datetime(df.iloc[:, 0], errors="coerce"))
    return _clean(s[s.index.notna()])


def unchanged_run(series: pd.Series) -> pd.Series:
    """到每一天為止，數值已經連續幾天沒變（今天有變＝0）。用來標示台債指標殖利率的「沒成交」天數。"""
    s = pd.Series(series)
    changed = s.ne(s.shift()).astype(int)
    run_id = changed.cumsum()
    return s.groupby(run_id).cumcount()


def rate_spread_frame(tw_hist: pd.DataFrame, us2: pd.Series, us10: pd.Series) -> pd.DataFrame:
    """以台債營業日為主軸的台美利差表（單位：%／百分點）。"""
    cols = ["tw2", "tw10", "tw10_bm", "us2", "us10", "spread2", "spread10", "bm10_unchanged"]
    if tw_hist is None or tw_hist.empty:
        return pd.DataFrame(columns=cols)
    tw = tw_hist.copy()
    tw["date"] = pd.to_datetime(tw["date"])
    tw = tw.set_index("date").sort_index()
    tw = tw[~tw.index.duplicated(keep="last")]
    out = pd.DataFrame(index=tw.index)
    out["tw2"] = pd.to_numeric(tw.get("zc_2y"), errors="coerce")
    out["tw10"] = pd.to_numeric(tw.get("zc_10y"), errors="coerce")
    out["tw10_bm"] = pd.to_numeric(tw.get("bm_10y"), errors="coerce")
    base = out["tw10"]
    for name, us in (("us2", us2), ("us10", us10)):
        us_s = _clean(us)
        out[name] = _asof_same_day(base, us_s) if not us_s.empty else np.nan
    out["spread2"] = out["us2"] - out["tw2"]
    out["spread10"] = out["us10"] - out["tw10"]
    out["bm10_unchanged"] = unchanged_run(out["tw10_bm"])
    return out[cols]


SPREAD_CORR_WINDOW = 252


def spread_fx_corr(spread: pd.Series, fx: pd.Series, days: int = SPREAD_CHANGE_DAYS,
                   window: int = SPREAD_CORR_WINDOW) -> pd.Series:
    """利差 days 日變動（百分點）與 USD/TWD days 日變動（%）的滾動 window 日相關。
    正＝利差擴大時台幣偏貶（利差在推台幣）；負＝關係反轉。以利差（台債營業日）為主軸、匯率同日對齊。
    2026-11-26 實測：2022～2024 多在 +0.3～+0.7，2025 起轉負。"""
    sp = _clean(spread)
    if sp.empty:
        return pd.Series(dtype=float)
    fxa = _asof_same_day(sp, _clean(fx))
    both = pd.DataFrame({"sp": sp, "fx": fxa}).dropna()
    ch = pd.DataFrame({"sp": both["sp"].diff(days), "fx": np.log(both["fx"]).diff(days) * 100}).dropna()
    return ch["sp"].rolling(window).corr(ch["fx"]).dropna()


def spread_summary(frame: pd.DataFrame, days: int = SPREAD_CHANGE_DAYS) -> dict | None:
    """最新利差、days 日變動、在整段資料中的百分位。"""
    f = frame.dropna(subset=["spread2", "spread10"]) if frame is not None and not frame.empty else None
    if f is None or len(f) <= days:
        return None
    last = f.iloc[-1]
    prev = f.iloc[-1 - days]
    return {
        "date": f.index[-1],
        "spread2": float(last["spread2"]), "spread10": float(last["spread10"]),
        "chg2": float(last["spread2"] - prev["spread2"]), "chg10": float(last["spread10"] - prev["spread10"]),
        "tw2": float(last["tw2"]), "tw10": float(last["tw10"]), "us2": float(last["us2"]), "us10": float(last["us10"]),
        "tw10_bm": float(last["tw10_bm"]), "bm10_unchanged": int(last["bm10_unchanged"]),
        "pct2": percentile_of_last(f["spread2"]), "pct10": percentile_of_last(f["spread10"]),
    }


# ---------------------------------------------------------------------------
# 外資買賣超與匯率
# ---------------------------------------------------------------------------
# 外資：證交所 BFI82U「外資及陸資(不含外資自營商)」上市買賣超（tw_foreign_flow.py 維護歷史檔），單位換成億元。
# 匯率：USD/TWD 同日對齊（正＝台幣貶）。
# 2026-11-26 實測（2021-11～2026-11）：外資日買賣超與台幣當日變動相關 −0.20、隔日 −0.18、隔兩日 −0.10（交割 T+2，
#   換匯會延續一兩天）；20 日累積外資與台幣 20 日變動相關 −0.44，2022 −0.76、2026 −0.83、2024 只有 −0.1。
# 敏感度 β：用「前一天為止」252 個交易日的 20 日累積配對估（無截距），推估「這樣的外資買賣超對應台幣該變多少」，
#   與實際變動對照——實際貶得比推估少，代表有其他買盤（央行、出口商、壽險等）在撐。
FLOW_DAYS = 20
FLOW_BETA_WINDOW = 252


def foreign_flow_frame(flow_hist: pd.DataFrame, fx: pd.Series, days: int = FLOW_DAYS,
                       window: int = FLOW_BETA_WINDOW) -> pd.DataFrame:
    """以外資資料日期為主軸。欄位：net（億）、net20（億）、fx20（USD/TWD days 日 %）、
    beta（每 1 億淨買超對應的 fx20 %，用前一天為止的資料估）、implied20（beta × net20）、corr（近 window 日相關）。"""
    cols = ["net", "net20", "fx20", "beta", "implied20", "corr"]
    if flow_hist is None or flow_hist.empty:
        return pd.DataFrame(columns=cols)
    f = flow_hist.copy()
    f["date"] = pd.to_datetime(f["date"])
    f = f.set_index("date").sort_index()
    f = f[~f.index.duplicated(keep="last")]
    out = pd.DataFrame(index=f.index)
    out["net"] = pd.to_numeric(f["foreign_net"], errors="coerce") / 1e8
    out["net20"] = out["net"].rolling(days).sum()
    fx_s = _clean(fx)
    if fx_s.empty:
        out["fx20"] = np.nan
    else:
        fxa = _asof_same_day(out["net"], fx_s)
        # 匯率最後一筆早於外資日期太多（例如 Yahoo 還沒更新）時，asof 會沿用舊值，這裡不另外處理，由顯示端標日期
        out["fx20"] = np.log(fxa).diff(days) * 100
    pair = out[["net20", "fx20"]].dropna()
    xy = (pair["net20"] * pair["fx20"]).rolling(window).sum()
    xx = (pair["net20"] ** 2).rolling(window).sum()
    out["beta"] = (xy / xx.where(xx > 0)).shift(1).reindex(out.index)
    out["implied20"] = out["beta"] * out["net20"]
    out["corr"] = pair["net20"].rolling(window).corr(pair["fx20"]).reindex(out.index)
    return out[cols]


def _signed_streak(series: pd.Series) -> int:
    """最後連續同號的天數：正＝連續買超 N 天，負＝連續賣超 N 天。"""
    s = pd.Series(series).dropna()
    if s.empty or s.iloc[-1] == 0:
        return 0
    sign = np.sign(s.iloc[-1])
    n = 0
    for v in reversed(s.values):
        if np.sign(v) != sign:
            break
        n += 1
    return int(sign * n)


def foreign_flow_summary(frame: pd.DataFrame) -> dict | None:
    if frame is None or frame.empty or frame["net20"].dropna().empty:
        return None
    last = frame.iloc[-1]
    net20_hist = frame["net20"].dropna()
    tail = frame["net"].tail(FLOW_DAYS)
    return {
        "date": frame.index[-1],
        "net": float(last["net"]),
        "net20": float(last["net20"]),
        "net20_pct": percentile_of_last(net20_hist),
        "streak": _signed_streak(frame["net"]),
        "fx20": float(last["fx20"]) if pd.notna(last["fx20"]) else None,
        "implied20": float(last["implied20"]) if pd.notna(last["implied20"]) else None,
        "beta": float(last["beta"]) if pd.notna(last["beta"]) else None,
        "corr": float(last["corr"]) if pd.notna(last["corr"]) else None,
        "max_sell_day": tail.idxmin(), "max_sell": float(tail.min()),
        "max_buy_day": tail.idxmax(), "max_buy": float(tail.max()),
    }
