"""金銀比條件統計核心。

本模組不依賴 Streamlit；UI、快取與資料下載留在 market_dashboard.py。
所有前瞻統計只使用已走完指定持有期的歷史觀察值。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

import numpy as np
import pandas as pd


DEFAULT_THRESHOLDS = (80.0, 90.0, 100.0)


@dataclass(frozen=True)
class RatioState:
    label: str
    detail: str


def _clean_price_series(series: pd.Series, name: str) -> pd.Series:
    # 注意：pd.Series(data=某 Series, index=...) 是「按標籤重新索引」，索引型別一變就全成 NaN。
    # 先轉成 ndarray 再配新索引，才是真正的位置指派。
    values = pd.to_numeric(pd.Series(series).to_numpy(), errors="coerce")
    cleaned = pd.Series(values, index=pd.to_datetime(series.index, errors="coerce"))
    cleaned = cleaned[~cleaned.index.isna()].dropna()
    if cleaned.index.tz is not None:
        cleaned.index = cleaned.index.tz_localize(None)
    cleaned = cleaned[~cleaned.index.duplicated(keep="last")].sort_index()
    cleaned.name = name
    return cleaned


def prepare_price_frame(gold: pd.Series, silver: pd.Series) -> pd.DataFrame:
    """以共同交易日對齊黃金、白銀收盤價並計算金銀比。"""
    gold_clean = _clean_price_series(gold, "gold")
    silver_clean = _clean_price_series(silver, "silver")
    frame = pd.concat([gold_clean, silver_clean], axis=1, join="inner").dropna()
    frame = frame[(frame["gold"] > 0) & (frame["silver"] > 0)].copy()
    frame["ratio"] = frame["gold"] / frame["silver"]
    return frame


def add_forward_return(frame: pd.DataFrame, horizon: int = 63) -> pd.DataFrame:
    """加入白銀固定交易日持有期的前瞻報酬。"""
    if horizon <= 0:
        raise ValueError("horizon 必須為正整數")
    out = frame.copy()
    out["silver_forward_return"] = out["silver"].shift(-horizon) / out["silver"] - 1.0
    return out


def classify_ratio(ratio: float) -> RatioState:
    if ratio >= 100:
        return RatioState("🔴 稀有壓力區", "歷史樣本集中在少數危機期間，不可當成 100% 預測")
    if ratio >= 90:
        return RatioState("🔴 歷史極端區", "白銀相對黃金明顯偏低，僅作條件統計觀察")
    if ratio >= 80:
        return RatioState("🟠 相對低估觀察區", "已進入影片門檻，需同時查看獨立事件數")
    return RatioState("⚪ 一般區", "尚未觸發 80 門檻")


def _cooldown_candidates(candidate_mask: pd.Series, horizon: int) -> list[pd.Timestamp]:
    positions = np.flatnonzero(candidate_mask.to_numpy(dtype=bool))
    selected: list[int] = []
    next_allowed = 0
    for position in positions:
        if position >= next_allowed:
            selected.append(int(position))
            next_allowed = int(position) + horizon
    return [candidate_mask.index[position] for position in selected]


def summarize_conditions(
    frame: pd.DataFrame,
    *,
    horizon: int = 63,
    thresholds: Iterable[float] = DEFAULT_THRESHOLDS,
    start: pd.Timestamp | None = None,
    end: pd.Timestamp | None = None,
) -> pd.DataFrame:
    """計算逐日重疊樣本與首次穿越＋冷卻期的事件統計。"""
    if "silver_forward_return" not in frame.columns:
        frame = add_forward_return(frame, horizon=horizon)
    if frame.empty:
        return pd.DataFrame()

    in_window = pd.Series(True, index=frame.index)
    if start is not None:
        in_window &= frame.index >= pd.Timestamp(start)
    if end is not None:
        in_window &= frame.index <= pd.Timestamp(end)
    matured = in_window & frame["silver_forward_return"].notna()
    baseline = frame.loc[matured, "silver_forward_return"]
    baseline_mean = baseline.mean()

    rows: list[dict[str, float | int | str]] = []
    conditions = [("全部交易日", 0.0), *[(f"金銀比 ≥{threshold:g}", float(threshold)) for threshold in thresholds]]
    for label, threshold in conditions:
        if threshold == 0:
            condition = pd.Series(True, index=frame.index)
            event_candidates = matured
        else:
            condition = frame["ratio"].ge(threshold)
            crossings = condition & ~condition.shift(fill_value=False)
            event_candidates = matured & crossings

        daily = frame.loc[matured & condition, "silver_forward_return"]
        event_dates = _cooldown_candidates(event_candidates, horizon=horizon)
        events = frame.loc[event_dates, "silver_forward_return"].dropna()
        rows.append(
            {
                "條件": label,
                "逐日樣本": int(len(daily)),
                "占有效交易日": len(daily) / len(baseline) if len(baseline) else np.nan,
                "逐日勝率": (daily > 0).mean(),
                "逐日平均報酬": daily.mean(),
                "獨立事件數": int(len(events)),
                "事件勝率": (events > 0).mean(),
                "事件平均報酬": events.mean(),
                "相對基準增益": daily.mean() - baseline_mean,
            }
        )
    return pd.DataFrame(rows)


def rolling_condition_statistics(
    frame: pd.DataFrame,
    *,
    horizon: int = 63,
    window_years: int = 10,
    thresholds: Iterable[float] = (80.0, 90.0),
) -> pd.DataFrame:
    """按季重算尾端視窗；每個時點只納入當時已成熟的前瞻報酬。"""
    if "silver_forward_return" not in frame.columns:
        frame = add_forward_return(frame, horizon=horizon)
    if len(frame) <= horizon:
        return pd.DataFrame()

    evaluation_dates = frame.groupby(frame.index.to_period("Q")).tail(1).index
    rows: list[dict[str, float | int | pd.Timestamp]] = []
    threshold_values = tuple(float(value) for value in thresholds)
    for evaluation_date in evaluation_dates:
        evaluation_position = frame.index.get_indexer([evaluation_date])[0]
        if evaluation_position < horizon:
            continue
        maturity_cutoff = frame.index[evaluation_position - horizon]
        window_start = evaluation_date - pd.DateOffset(years=window_years)
        summary = summarize_conditions(
            frame,
            horizon=horizon,
            thresholds=threshold_values,
            start=window_start,
            end=maturity_cutoff,
        )
        for threshold in threshold_values:
            condition_label = f"金銀比 ≥{threshold:g}"
            matched = summary[summary["條件"] == condition_label]
            if matched.empty:
                continue
            item = matched.iloc[0]
            rows.append(
                {
                    "日期": evaluation_date,
                    "門檻": f"≥{threshold:g}",
                    "逐日勝率": item["逐日勝率"],
                    "事件勝率": item["事件勝率"],
                    "逐日平均報酬": item["逐日平均報酬"],
                    "獨立事件數": int(item["獨立事件數"]),
                }
            )
    return pd.DataFrame(rows)


def build_dashboard_snapshot(
    gold: pd.Series,
    silver: pd.Series,
    *,
    horizon: int = 63,
    rolling_years: int = 10,
) -> dict[str, object]:
    frame = add_forward_return(prepare_price_frame(gold, silver), horizon=horizon)
    if len(frame) <= horizon:
        raise ValueError(f"共同交易日不足 {horizon + 1} 筆")

    last_date = frame.index[-1]
    ratio_window = frame.loc[frame.index >= last_date - pd.DateOffset(years=rolling_years), "ratio"]
    percentile = ratio_window.rank(pct=True).iloc[-1] * 100.0
    maturity_cutoff = frame["silver_forward_return"].last_valid_index()
    rolling_start = last_date - pd.DateOffset(years=rolling_years)

    return {
        "frame": frame,
        "current_ratio": float(frame["ratio"].iloc[-1]),
        "current_state": classify_ratio(float(frame["ratio"].iloc[-1])),
        "rolling_percentile": float(percentile),
        "last_price_date": last_date,
        "maturity_cutoff": maturity_cutoff,
        "full_history": summarize_conditions(frame, horizon=horizon),
        "rolling_window": summarize_conditions(
            frame,
            horizon=horizon,
            start=rolling_start,
            end=maturity_cutoff,
        ),
        "rolling_stability": rolling_condition_statistics(
            frame,
            horizon=horizon,
            window_years=rolling_years,
        ),
    }
