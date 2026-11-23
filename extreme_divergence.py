"""極端背離雷達的純計算與官方資料擷取。

本模組刻意不依賴 Streamlit，讓資料口徑、失敗降級與風險計分可單獨測試。
"""

from __future__ import annotations

from dataclasses import dataclass
import io
from typing import Iterable

import pandas as pd
import requests
import yfinance as yf


CFTC_TFF_API_URL = "https://publicreporting.cftc.gov/resource/gpe5-46if.json"
CFTC_ES_CONTRACT_CODE = "13874A"
SSGA_SPY_HOLDINGS_URL = (
    "https://www.ssga.com/library-content/products/fund-data/etfs/us/"
    "holdings-daily-us-en-spy.xlsx"
)


@dataclass(frozen=True)
class RadarMetric:
    """單一雷達指標的顯示與計分結果。"""

    name: str
    available: bool
    danger: bool = False
    value: float | None = None
    percentile: float | None = None
    as_of: str | None = None
    status: str = "資料不足"
    detail: str = ""
    coverage: float | None = None


def unavailable_metric(name: str, detail: str) -> RadarMetric:
    return RadarMetric(name=name, available=False, detail=detail)


def percentile_rank(values: Iterable[float], value: float | None = None) -> float:
    """回傳 value 在有效樣本中的弱百分位（相同值計入）。"""
    series = pd.to_numeric(pd.Series(list(values)), errors="coerce").dropna()
    if series.empty:
        return float("nan")
    target = float(series.iloc[-1] if value is None else value)
    return float((series <= target).mean() * 100.0)


def build_cftc_positioning(rows: pd.DataFrame, lookback_weeks: int = 260) -> RadarMetric:
    required = {
        "report_date_as_yyyy_mm_dd",
        "open_interest_all",
        "asset_mgr_positions_long",
        "asset_mgr_positions_short",
    }
    if rows is None or rows.empty or not required.issubset(rows.columns):
        return unavailable_metric("CFTC 機構淨曝險", "CFTC 回傳欄位不完整")

    frame = rows.copy()
    frame["date"] = pd.to_datetime(frame["report_date_as_yyyy_mm_dd"], errors="coerce")
    for column in required - {"report_date_as_yyyy_mm_dd"}:
        frame[column] = pd.to_numeric(frame[column], errors="coerce")
    frame = frame.dropna(subset=["date", "open_interest_all", "asset_mgr_positions_long", "asset_mgr_positions_short"])
    frame = frame[frame["open_interest_all"] > 0].sort_values("date")
    if frame.empty:
        return unavailable_metric("CFTC 機構淨曝險", "CFTC 沒有有效部位資料")

    frame["net_pct_oi"] = (
        (frame["asset_mgr_positions_long"] - frame["asset_mgr_positions_short"])
        / frame["open_interest_all"]
        * 100.0
    )
    history = frame["net_pct_oi"].tail(lookback_weeks)
    latest = frame.iloc[-1]
    rank = percentile_rank(history, float(latest["net_pct_oi"]))
    danger = bool(rank >= 90.0)
    return RadarMetric(
        name="CFTC 機構淨曝險",
        available=True,
        danger=danger,
        value=float(latest["net_pct_oi"]),
        percentile=rank,
        as_of=latest["date"].strftime("%Y-%m-%d"),
        status="機構部位極度擁擠" if danger else "部位未達極端",
        detail=f"Asset Manager 淨部位／未平倉量；近 {len(history)} 週百分位",
    )


def fetch_cftc_positioning(timeout: int = 20) -> RadarMetric:
    params = {
        "$where": f"cftc_contract_market_code='{CFTC_ES_CONTRACT_CODE}'",
        "$order": "report_date_as_yyyy_mm_dd DESC",
        "$limit": "300",
    }
    response = requests.get(CFTC_TFF_API_URL, params=params, timeout=timeout)
    response.raise_for_status()
    return build_cftc_positioning(pd.DataFrame(response.json()))


def _clean_series(series: pd.Series) -> pd.Series:
    clean = pd.to_numeric(series, errors="coerce").dropna().sort_index()
    clean.index = pd.to_datetime(clean.index)
    return clean[~clean.index.duplicated(keep="last")]


def build_volatility_term_structure(vix: pd.Series, vix3m: pd.Series) -> RadarMetric:
    frame = pd.concat(
        [_clean_series(vix).rename("vix"), _clean_series(vix3m).rename("vix3m")],
        axis=1,
        join="inner",
    ).dropna()
    frame = frame[frame["vix3m"] > 0]
    if frame.empty:
        return unavailable_metric("VIX 期限結構", "VIX 或 VIX3M 無共同有效日期")

    ratio = frame["vix"] / frame["vix3m"]
    latest_ratio = float(ratio.iloc[-1])
    rank = percentile_rank(ratio.tail(504), latest_ratio)
    danger = bool(latest_ratio >= 1.0)
    return RadarMetric(
        name="VIX 期限結構",
        available=True,
        danger=danger,
        value=latest_ratio,
        percentile=rank,
        as_of=frame.index[-1].strftime("%Y-%m-%d"),
        status="近端恐慌／Backwardation" if danger else "期限結構正常",
        detail="VIX ÷ VIX3M；≥1 代表近端波動高於三個月波動",
    )


def build_equal_weight_breadth(rsp: pd.Series, spy: pd.Series) -> RadarMetric:
    frame = pd.concat(
        [_clean_series(rsp).rename("rsp"), _clean_series(spy).rename("spy")],
        axis=1,
        join="inner",
    ).dropna()
    frame = frame[(frame["rsp"] > 0) & (frame["spy"] > 0)]
    if len(frame) < 200:
        return unavailable_metric("等權廣度", f"共同交易日僅 {len(frame)} 筆，至少需要 200 筆")

    ratio = frame["rsp"] / frame["spy"]
    ma200 = ratio.rolling(200).mean()
    low63 = ratio.rolling(63).min()
    latest_ratio = float(ratio.iloc[-1])
    below_ma = bool(latest_ratio < float(ma200.iloc[-1]))
    at_low = bool(latest_ratio <= float(low63.iloc[-1]) * (1.0 + 1e-9))
    danger = below_ma and at_low
    if danger:
        status = "嚴重背離：等權創 63 日低且低於年線"
    elif below_ma:
        status = "廣度轉弱：等權低於年線"
    else:
        status = "結構穩健"
    return RadarMetric(
        name="等權廣度",
        available=True,
        danger=danger,
        value=latest_ratio,
        percentile=percentile_rank(ratio.tail(504), latest_ratio),
        as_of=frame.index[-1].strftime("%Y-%m-%d"),
        status=status,
        detail="RSP ÷ SPY 相對強弱；以 200 日均線與 63 日低點判讀",
    )


def extract_close_frame(downloaded: pd.DataFrame, tickers: Iterable[str]) -> pd.DataFrame:
    """正規化 yfinance 單層／多層欄位為 ticker columns。"""
    if downloaded is None or downloaded.empty:
        return pd.DataFrame()
    if isinstance(downloaded.columns, pd.MultiIndex):
        if "Close" not in downloaded.columns.get_level_values(0):
            return pd.DataFrame()
        close = downloaded["Close"].copy()
    else:
        close = downloaded.copy()
        requested = list(tickers)
        if len(requested) == 1:
            close = close.rename(columns={close.columns[0]: requested[0]})
    if isinstance(close, pd.Series):
        requested = list(tickers)
        close = close.to_frame(name=requested[0] if requested else close.name)
    close.index = pd.to_datetime(close.index)
    return close.apply(pd.to_numeric, errors="coerce").sort_index()


def fetch_market_proxy_metrics() -> tuple[RadarMetric, RadarMetric]:
    tickers = ["^VIX", "^VIX3M", "RSP", "SPY"]
    downloaded = yf.download(
        tickers,
        period="2y",
        auto_adjust=True,
        progress=False,
        threads=False,
    )
    close = extract_close_frame(downloaded, tickers)
    if close.empty:
        unavailable = unavailable_metric("市場代理", "Yahoo Finance 沒有回傳價格")
        return unavailable, unavailable
    volatility = (
        build_volatility_term_structure(close["^VIX"], close["^VIX3M"])
        if {"^VIX", "^VIX3M"}.issubset(close.columns)
        else unavailable_metric("VIX 期限結構", "缺少 VIX 或 VIX3M")
    )
    breadth = (
        build_equal_weight_breadth(close["RSP"], close["SPY"])
        if {"RSP", "SPY"}.issubset(close.columns)
        else unavailable_metric("等權廣度", "缺少 RSP 或 SPY")
    )
    return volatility, breadth


def normalize_yahoo_ticker(ticker: str) -> str:
    """State Street 使用 BRK.B；Yahoo Finance 使用 BRK-B。"""
    return str(ticker).strip().upper().replace(".", "-")


def parse_spy_holdings(content: bytes) -> tuple[list[str], str | None]:
    raw_head = pd.read_excel(io.BytesIO(content), sheet_name="holdings", header=None, nrows=5, engine="openpyxl")
    holdings = pd.read_excel(io.BytesIO(content), sheet_name="holdings", header=4, engine="openpyxl")
    if "Ticker" not in holdings.columns:
        raise ValueError("SPY 持股檔缺少 Ticker 欄位")

    tickers = []
    for _, row in holdings.iterrows():
        name = str(row.get("Name", "")).strip().upper()
        if name.startswith("CONTRA "):
            continue
        ticker = normalize_yahoo_ticker(row.get("Ticker", ""))
        if ticker and ticker not in {"USD", "N/A", "NAN", "-"}:
            tickers.append(ticker)
    tickers = list(dict.fromkeys(tickers))
    if len(tickers) < 400:
        raise ValueError(f"SPY 持股檔僅解析出 {len(tickers)} 檔股票")

    as_of = None
    for value in raw_head.astype(str).to_numpy().ravel():
        text = str(value)
        if text.startswith("As of "):
            parsed = pd.to_datetime(text.removeprefix("As of "), errors="coerce")
            if pd.notna(parsed):
                as_of = parsed.strftime("%Y-%m-%d")
                break
    return tickers, as_of


def fetch_spy_holdings(timeout: int = 30) -> tuple[list[str], str | None]:
    response = requests.get(SSGA_SPY_HOLDINGS_URL, timeout=timeout)
    response.raise_for_status()
    return parse_spy_holdings(response.content)


def build_sp500_sma200_breadth(
    close: pd.DataFrame,
    total_constituents: int,
    holdings_as_of: str | None = None,
    min_coverage: float = 0.90,
) -> RadarMetric:
    if close is None or close.empty or total_constituents <= 0:
        return unavailable_metric("S&P 500 年線廣度", "沒有成分股價格")
    clean = close.apply(pd.to_numeric, errors="coerce").sort_index()
    clean = clean.dropna(axis=0, how="all")
    if len(clean) < 200:
        return unavailable_metric("S&P 500 年線廣度", f"價格歷史僅 {len(clean)} 個交易日")

    recent = clean.ffill(limit=3).iloc[-1]
    ma200 = clean.rolling(200, min_periods=180).mean().iloc[-1]
    valid = recent.notna() & ma200.notna()
    valid_count = int(valid.sum())
    coverage = valid_count / total_constituents
    price_as_of = pd.to_datetime(clean.index[-1]).strftime("%Y-%m-%d")
    if valid_count == 0 or coverage < min_coverage:
        return RadarMetric(
            name="S&P 500 年線廣度",
            available=False,
            as_of=price_as_of,
            coverage=coverage,
            detail=f"有效 {valid_count}/{total_constituents}，低於 {min_coverage:.0%} 涵蓋門檻",
        )

    pct = float((recent[valid] > ma200[valid]).mean() * 100.0)
    danger = bool(pct < 50.0)
    holdings_note = f"；持股截至 {holdings_as_of}" if holdings_as_of else ""
    return RadarMetric(
        name="S&P 500 年線廣度",
        available=True,
        danger=danger,
        value=pct,
        as_of=price_as_of,
        status="巨頭撐盤／廣度不足" if danger else "過半成分股位於年線之上",
        detail=f"有效 {valid_count}/{total_constituents} 檔{holdings_note}",
        coverage=coverage,
    )


def fetch_sp500_sma200_breadth() -> RadarMetric:
    tickers, holdings_as_of = fetch_spy_holdings()
    downloaded = yf.download(
        tickers,
        period="1y",
        auto_adjust=True,
        progress=False,
        threads=True,
    )
    close = extract_close_frame(downloaded, tickers)
    return build_sp500_sma200_breadth(close, len(tickers), holdings_as_of)


def summarize_risk_pillars(
    momentum_metrics: Iterable[RadarMetric],
    positioning: RadarMetric,
    volatility: RadarMetric,
    breadth_metrics: Iterable[RadarMetric],
) -> dict[str, object]:
    """四支柱計分；同支柱多個高度相關指標只計一次。"""

    def combine(name: str, metrics: Iterable[RadarMetric]) -> tuple[str, bool, bool]:
        usable = [metric for metric in metrics if metric.available]
        return name, bool(usable), any(metric.danger for metric in usable)

    pillars = [
        combine("動能", momentum_metrics),
        combine("機構部位", [positioning]),
        combine("波動期限結構", [volatility]),
        combine("市場廣度", breadth_metrics),
    ]
    available = sum(is_available for _, is_available, _ in pillars)
    danger = sum(is_danger for _, is_available, is_danger in pillars if is_available)
    return {
        "available": available,
        "danger": danger,
        "pillars": pillars,
        "insufficient": available < 3,
    }
