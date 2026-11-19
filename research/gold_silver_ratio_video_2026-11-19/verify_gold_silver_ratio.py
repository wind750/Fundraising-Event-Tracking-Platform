from __future__ import annotations

import json
import math
from pathlib import Path
from urllib.parse import quote
from urllib.request import Request, urlopen

import pandas as pd


START = pd.Timestamp("2000-08-01", tz="UTC")
END_EXCLUSIVE = pd.Timestamp("2026-11-14", tz="UTC")
SYMBOLS = {"gold": "GC=F", "silver": "SI=F"}
THRESHOLDS = (0, 80, 90, 100)
OUTPUT_DIR = Path(__file__).resolve().parent


def fetch_yahoo_chart(symbol: str) -> pd.Series:
    url = (
        "https://query1.finance.yahoo.com/v8/finance/chart/"
        f"{quote(symbol)}?period1={int(START.timestamp())}"
        f"&period2={int(END_EXCLUSIVE.timestamp())}&interval=1d&events=history"
    )
    request = Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urlopen(request, timeout=60) as response:
        payload = json.load(response)
    result = payload["chart"]["result"][0]
    timestamps = pd.to_datetime(result["timestamp"], unit="s", utc=True).normalize()
    closes = result["indicators"]["quote"][0]["close"]
    series = pd.Series(closes, index=timestamps, name=symbol, dtype="float64")
    return series[~series.index.duplicated(keep="last")].dropna().sort_index()


def add_forward_returns(frame: pd.DataFrame) -> pd.DataFrame:
    out = frame.copy()
    out["silver_fwd_63td"] = out["silver"].shift(-63) / out["silver"] - 1

    dates = out.index
    for label, offset in (
        ("3calm", pd.DateOffset(months=3)),
        ("90cald", pd.DateOffset(days=90)),
    ):
        target_dates = dates + offset
        positions = dates.searchsorted(target_dates, side="left")
        future = pd.Series(float("nan"), index=dates)
        valid = positions < len(dates)
        future.iloc[valid] = out["silver"].iloc[positions[valid]].to_numpy()
        out[f"silver_fwd_{label}"] = future / out["silver"] - 1
    return out


def wilson_interval(successes: int, observations: int, z: float = 1.96) -> tuple[float, float]:
    if observations == 0:
        return float("nan"), float("nan")
    p = successes / observations
    denominator = 1 + z * z / observations
    centre = (p + z * z / (2 * observations)) / denominator
    margin = z * math.sqrt(
        (p * (1 - p) + z * z / (4 * observations)) / observations
    ) / denominator
    return centre - margin, centre + margin


def summarize_rows(frame: pd.DataFrame, return_column: str) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    valid_all = frame[return_column].notna()
    denominator = int(valid_all.sum())
    for threshold in THRESHOLDS:
        mask = valid_all if threshold == 0 else valid_all & (frame["ratio"] >= threshold)
        sample = frame.loc[mask, return_column]
        successes = int((sample > 0).sum())
        low, high = wilson_interval(successes, len(sample))

        threshold_mask = frame["ratio"].ge(threshold) if threshold else pd.Series(True, index=frame.index)
        event_starts = threshold_mask & ~threshold_mask.shift(fill_value=False)
        event_sample = frame.loc[event_starts & valid_all, return_column]

        nonoverlap_dates: list[pd.Timestamp] = []
        next_allowed = pd.Timestamp.min.tz_localize("UTC")
        for date in frame.index[mask]:
            if date >= next_allowed:
                nonoverlap_dates.append(date)
                next_allowed = date + pd.DateOffset(months=3)
        nonoverlap = frame.loc[nonoverlap_dates, return_column]

        rows.append(
            {
                "return_definition": return_column.removeprefix("silver_fwd_"),
                "threshold": "any_day" if threshold == 0 else f">={threshold}",
                "daily_n": int(len(sample)),
                "daily_share": len(sample) / denominator if denominator else float("nan"),
                "daily_win_rate": successes / len(sample) if len(sample) else float("nan"),
                "daily_mean_return": sample.mean(),
                "daily_median_return": sample.median(),
                "daily_win_ci95_low_naive": low,
                "daily_win_ci95_high_naive": high,
                "episode_n": int(len(event_sample)),
                "episode_win_rate": (event_sample > 0).mean(),
                "episode_mean_return": event_sample.mean(),
                "nonoverlap_n": int(len(nonoverlap)),
                "nonoverlap_win_rate": (nonoverlap > 0).mean(),
                "nonoverlap_mean_return": nonoverlap.mean(),
            }
        )
    return rows


def main() -> None:
    gold = fetch_yahoo_chart(SYMBOLS["gold"]).rename("gold")
    silver = fetch_yahoo_chart(SYMBOLS["silver"]).rename("silver")
    frame = pd.concat([gold, silver], axis=1, join="inner").dropna()
    frame = frame.loc[(frame.index >= START) & (frame.index < END_EXCLUSIVE)]
    frame["ratio"] = frame["gold"] / frame["silver"]
    frame = add_forward_returns(frame)

    summary_rows: list[dict[str, object]] = []
    for column in ("silver_fwd_63td", "silver_fwd_3calm", "silver_fwd_90cald"):
        summary_rows.extend(summarize_rows(frame, column))
    summary = pd.DataFrame(summary_rows)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    frame.to_csv(OUTPUT_DIR / "aligned_prices_and_returns.csv", index_label="date")
    summary.to_csv(OUTPUT_DIR / "summary.csv", index=False)

    diagnostics = {
        "source": "Yahoo Finance chart API",
        "symbols": SYMBOLS,
        "requested_start": START.date().isoformat(),
        "requested_end_inclusive": (END_EXCLUSIVE - pd.Timedelta(days=1)).date().isoformat(),
        "aligned_first_date": frame.index.min().date().isoformat(),
        "aligned_last_date": frame.index.max().date().isoformat(),
        "aligned_rows": int(len(frame)),
        "last_ratio": float(frame["ratio"].iloc[-1]),
        "last_gold": float(frame["gold"].iloc[-1]),
        "last_silver": float(frame["silver"].iloc[-1]),
    }
    (OUTPUT_DIR / "diagnostics.json").write_text(
        json.dumps(diagnostics, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    display = summary.copy()
    for column in display.columns:
        if "rate" in column or "share" in column or "return" in column or "ci95" in column:
            if pd.api.types.is_numeric_dtype(display[column]):
                display[column] = display[column].map(
                    lambda value: "" if pd.isna(value) else f"{value:.4%}"
                )
    print(json.dumps(diagnostics, ensure_ascii=False, indent=2))
    print(display.to_string(index=False))


if __name__ == "__main__":
    main()
