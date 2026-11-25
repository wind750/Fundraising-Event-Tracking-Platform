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


# ==========================================
# 情緒雙端溫度計：恐慌悲觀 ↔ 樂觀過熱（獨立於四支柱計分）
# ==========================================
# CNN 網站背後的資料端點（非官方公開 API，需瀏覽器式標頭；失敗時一律降級為 N/A）。
CNN_FEAR_GREED_URL = "https://production.dataviz.cnn.io/index/fearandgreed/graphdata/{start}"
CNN_HISTORY_START = "2021-01-01"  # 端點實測最早只給到 2021-01（更早回 500）
CNN_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/130.0 Safari/537.36"
    ),
    "Accept": "application/json",
    "Referer": "https://edition.cnn.com/",
    "Origin": "https://edition.cnn.com",
}

# 門檻來源：
# - 恐慌端三條沿用「刀神期權學院」影片口徑（2026-11-23）：貪婪指數個位數、PCR 五日平均 ≥0.9、VIX 超過 40。
# - 過熱端無現成口徑，依 2021-01～2026-11 實測分布自訂：
#   CNN 指數 2021 起最高只到 83，鏡像的 ≥90 從未出現，改用 CNN 官方「極度貪婪」分界 75（約 5% 交易日）；
#   PCR ≤0.70、VIX <14。單看各自不算罕見，但三者同時成立 2021 起只有 4 段（2023-07、2023-12、2024-02、2024-03），
#   與恐慌端（2025-04 一段）同屬罕見；更嚴的 ≤0.62／<13 組合 2021 起從未同時成立，等於永不亮燈，已棄用。
SENTIMENT_RULES: dict[str, dict[str, object]] = {
    "fear_greed": {
        "label": "CNN 恐懼貪婪指數",
        "panic": ("<", 10.0),
        "greed": (">=", 75.0),
        "fmt": "{:.1f}",
    },
    "pcr5": {
        "label": "Put/Call 五日平均",
        "panic": (">=", 0.90),
        "greed": ("<=", 0.70),
        "fmt": "{:.3f}",
    },
    "vix": {
        "label": "VIX 收盤",
        "panic": (">", 40.0),
        "greed": ("<", 14.0),
        "fmt": "{:.2f}",
    },
}

_OPS = {
    "<": lambda a, b: a < b,
    "<=": lambda a, b: a <= b,
    ">": lambda a, b: a > b,
    ">=": lambda a, b: a >= b,
}

ZONE_PANIC = "panic"
ZONE_GREED = "greed"
ZONE_NEUTRAL = "neutral"
ZONE_NA = "na"


@dataclass(frozen=True)
class SentimentReading:
    """單一情緒指標的當前讀數與所在區域。"""

    key: str
    label: str
    value: float | None
    zone: str
    as_of: str | None = None
    detail: str = ""

    @property
    def available(self) -> bool:
        return self.zone != ZONE_NA


def rule_text(key: str, side: str) -> str:
    op, threshold = SENTIMENT_RULES[key][side]
    return f"{op} {SENTIMENT_RULES[key]['fmt'].format(threshold)}"


def classify_sentiment(key: str, value: float | None) -> str:
    """回傳 panic／greed／neutral；無效值回傳 na。"""
    if value is None or pd.isna(value):
        return ZONE_NA
    rule = SENTIMENT_RULES[key]
    panic_op, panic_threshold = rule["panic"]
    greed_op, greed_threshold = rule["greed"]
    if _OPS[panic_op](float(value), panic_threshold):
        return ZONE_PANIC
    if _OPS[greed_op](float(value), greed_threshold):
        return ZONE_GREED
    return ZONE_NEUTRAL


def parse_cnn_series(payload: dict, key: str) -> pd.Series:
    """把 CNN 的 [{x: 毫秒時間戳, y: 數值}] 轉成以日期為索引的序列；同日多點取最後一筆。"""
    block = (payload or {}).get(key) or {}
    points = block.get("data") or []
    if not points:
        return pd.Series(dtype=float)
    frame = pd.DataFrame(points)
    if not {"x", "y"}.issubset(frame.columns):
        return pd.Series(dtype=float)
    dates = pd.to_datetime(pd.to_numeric(frame["x"], errors="coerce"), unit="ms", errors="coerce").dt.normalize()
    series = pd.Series(pd.to_numeric(frame["y"], errors="coerce").to_numpy(), index=dates).dropna()
    series = series[series.index.notna()].sort_index()
    return series[~series.index.duplicated(keep="last")]


def _episodes(mask: pd.Series, gap_days: int = 10) -> list[dict[str, object]]:
    """把成立日壓成事件：相鄰成立日間隔 ≤ gap_days 個日曆日視為同一事件。"""
    hits = mask[mask].index
    if len(hits) == 0:
        return []
    episodes: list[dict[str, object]] = []
    start = prev = hits[0]
    count = 1
    for day in hits[1:]:
        if (day - prev).days <= gap_days:
            count += 1
        else:
            episodes.append({"起": start.strftime("%Y-%m-%d"), "迄": prev.strftime("%Y-%m-%d"), "天數": count})
            start, count = day, 1
        prev = day
    episodes.append({"起": start.strftime("%Y-%m-%d"), "迄": prev.strftime("%Y-%m-%d"), "天數": count})
    return episodes


def build_sentiment_extremes(
    fear_greed_now: float | None,
    fear_greed_as_of: str | None,
    fear_greed_history: pd.Series,
    pcr5: pd.Series,
    vix_close: pd.Series,
) -> dict[str, object]:
    """組合三指標的當前區域與歷史「三條件同時成立」事件。

    當前讀數：貪婪指數用 CNN 即時分數（網站顯示值）；PCR、VIX 用各自序列最後一筆。
    歷史統計：一律用 CNN 每日歷史值、PCR 序列與 VIX 收盤，三者交集日期才計算。
    """
    pcr_clean = _clean_series(pcr5) if pcr5 is not None and len(pcr5) else pd.Series(dtype=float)
    vix_clean = _clean_series(vix_close) if vix_close is not None and len(vix_close) else pd.Series(dtype=float)
    fg_hist = _clean_series(fear_greed_history) if fear_greed_history is not None and len(fear_greed_history) else pd.Series(dtype=float)
    if not vix_clean.empty:
        vix_clean.index = vix_clean.index.normalize()

    def reading(key: str, value: float | None, as_of: str | None, detail: str) -> SentimentReading:
        return SentimentReading(
            key=key,
            label=str(SENTIMENT_RULES[key]["label"]),
            value=None if value is None or pd.isna(value) else float(value),
            zone=classify_sentiment(key, value),
            as_of=as_of,
            detail=detail,
        )

    def last(series: pd.Series) -> tuple[float | None, str | None]:
        if series.empty:
            return None, None
        return float(series.iloc[-1]), series.index[-1].strftime("%Y-%m-%d")

    pcr_value, pcr_as_of = last(pcr_clean)
    vix_value, vix_as_of = last(vix_clean)
    readings = [
        reading("fear_greed", fear_greed_now, fear_greed_as_of, "CNN 七項子指標合成，0＝極度恐懼、100＝極度貪婪"),
        reading("pcr5", pcr_value, pcr_as_of, "CBOE Put/Call 五日平均（CNN 子指標原始值）"),
        reading("vix", vix_value, vix_as_of, "Yahoo ^VIX 日收盤"),
    ]
    available = sum(item.available for item in readings)
    panic = sum(item.zone == ZONE_PANIC for item in readings)
    greed = sum(item.zone == ZONE_GREED for item in readings)

    history = pd.concat(
        [fg_hist.rename("fear_greed"), pcr_clean.rename("pcr5"), vix_clean.rename("vix")],
        axis=1,
        join="inner",
        sort=True,
    ).dropna()
    zones = {key: history[key].map(lambda v, k=key: classify_sentiment(k, v)) for key in SENTIMENT_RULES} if not history.empty else {}
    if zones:
        panic_all = pd.concat([zones[k] == ZONE_PANIC for k in SENTIMENT_RULES], axis=1).all(axis=1)
        greed_all = pd.concat([zones[k] == ZONE_GREED for k in SENTIMENT_RULES], axis=1).all(axis=1)
    else:
        panic_all = greed_all = pd.Series(dtype=bool)

    if available < 3:
        verdict = "insufficient"
    elif panic == 3:
        verdict = "panic_resonance"
    elif greed == 3:
        verdict = "greed_resonance"
    elif panic and greed:
        verdict = "mixed"
    elif panic:
        verdict = "leaning_panic"
    elif greed:
        verdict = "leaning_greed"
    else:
        verdict = "neutral"

    return {
        "readings": readings,
        "available": available,
        "panic": panic,
        "greed": greed,
        "verdict": verdict,
        "history_days": int(len(history)),
        "history_start": history.index[0].strftime("%Y-%m-%d") if not history.empty else None,
        "history_end": history.index[-1].strftime("%Y-%m-%d") if not history.empty else None,
        "panic_episodes": _episodes(panic_all),
        "greed_episodes": _episodes(greed_all),
        # 各指標自己的完整歷史（不做三者交集），供折線圖使用。
        "series": {"fear_greed": fg_hist, "pcr5": pcr_clean, "vix": vix_clean},
    }


def fetch_cnn_fear_greed(start: str = CNN_HISTORY_START, timeout: int = 20) -> dict:
    response = requests.get(CNN_FEAR_GREED_URL.format(start=start), headers=CNN_HEADERS, timeout=timeout)
    response.raise_for_status()
    return response.json()


def fetch_sentiment_extremes() -> dict[str, object]:
    """抓 CNN 與 Yahoo；任一來源失敗只讓該指標變 N/A，不用估值代替。"""
    errors: list[str] = []
    fg_now = fg_as_of = None
    fg_history = pcr5 = pd.Series(dtype=float)
    try:
        payload = fetch_cnn_fear_greed()
        current = payload.get("fear_and_greed") or {}
        fg_now = pd.to_numeric(current.get("score"), errors="coerce")
        fg_now = None if pd.isna(fg_now) else float(fg_now)
        stamp = pd.to_datetime(current.get("timestamp"), errors="coerce", utc=True)
        fg_as_of = None if pd.isna(stamp) else stamp.strftime("%Y-%m-%d %H:%M UTC")
        fg_history = parse_cnn_series(payload, "fear_and_greed_historical")
        pcr5 = parse_cnn_series(payload, "put_call_options")
    except Exception as exc:  # noqa: BLE001 — 任何失敗都降級為 N/A
        errors.append(f"CNN 同步失敗：{type(exc).__name__}")

    vix_close = pd.Series(dtype=float)
    try:
        downloaded = yf.download("^VIX", start=CNN_HISTORY_START, auto_adjust=True, progress=False, threads=False)
        close = extract_close_frame(downloaded, ["^VIX"])
        if "^VIX" in close.columns:
            vix_close = close["^VIX"].dropna()
    except Exception as exc:  # noqa: BLE001
        errors.append(f"VIX 同步失敗：{type(exc).__name__}")
    if vix_close.empty and not any(e.startswith("VIX") for e in errors):
        errors.append("VIX 同步失敗：Yahoo 沒有回傳價格")

    result = build_sentiment_extremes(fg_now, fg_as_of, fg_history, pcr5, vix_close)
    result["errors"] = errors
    return result
