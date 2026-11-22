"""CT-20261122-03 檢驗程式：完全照凍結區規格，不得因結果修改。

用法：
    py -3.14 research/ptt_sentiment_CT-20261122-03/test_predictive.py precheck   # 開發段獨立性檢查（同日／過去報酬相關）
    py -3.14 research/ptt_sentiment_CT-20261122-03/test_predictive.py dev        # 開發段主檢定
    py -3.14 research/ptt_sentiment_CT-20261122-03/test_predictive.py val        # 驗證段主檢定（開發段定案後才准跑）

規格（凍結）：
- 訊號 net_t：t 日盤中＋盤後串、[t 08:00, 下一交易日 08:30) 的推文多空淨分數（build_daily.py 產出）。
- 報酬：fwd5 = Close[t+5] / Open[t+1] − 1；次要 fwd20 = Close[t+20] / Open[t+1] − 1（^TWII）。
- 控制：past5 = Close[t]/Close[t−5] − 1、past20 = Close[t]/Close[t−20] − 1。
- 主統計量：偏 Spearman＝對四個變數取秩，net 與 fwd 各自對 (past5, past20) 迴歸取殘差，殘差 Pearson 相關。
- 信賴區間：移動區塊 bootstrap，區塊 10 日、2,000 次、95% 百分位區間，種子固定 20261122。
- 開發段 2020-01-02～2023-04-28；驗證段 2023-05-02～最新（fwd 必須已走完）。
- 描述性附表（不參與判定）：擴張窗百分位（≥120 日歷史）≤10 與 ≥90 的日子，未來 5／20 日平均報酬。
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from ptt_sentiment.thermometer import _expanding_pct  # noqa: E402

OUT = Path(__file__).resolve().parent
DEV = ("2020-01-02", "2023-04-28")
VAL = ("2023-05-02", "2100-01-01")
SEED, BLOCK, NBOOT = 20261122, 10, 2000


def load() -> pd.DataFrame:
    s = pd.read_csv(ROOT / "ptt_sentiment" / "daily_sentiment.csv", parse_dates=["date"]).set_index("date")
    px = pd.read_csv(ROOT / "data" / "ptt_raw" / "twii.csv", index_col=0, parse_dates=True)
    px = px[["Open", "Close"]].dropna()
    o, c = px["Open"], px["Close"]
    df = pd.DataFrame(index=px.index)
    df["ret0"] = c / c.shift(1) - 1
    df["past5"] = c / c.shift(5) - 1
    df["past20"] = c / c.shift(20) - 1
    df["fwd5"] = c.shift(-5) / o.shift(-1) - 1
    df["fwd20"] = c.shift(-20) / o.shift(-1) - 1
    df = df.join(s[["net", "n_push"]], how="left")
    df["temp"] = _expanding_pct(df["net"], 120)
    return df


def partial_spearman(d: pd.DataFrame, y: str) -> float:
    r = d[["net", y, "past5", "past20"]].rank()
    X = np.column_stack([np.ones(len(r)), r["past5"], r["past20"]])
    res = lambda v: v - X @ np.linalg.lstsq(X, v, rcond=None)[0]  # noqa: E731
    a, b = res(r["net"].to_numpy()), res(r[y].to_numpy())
    return float(np.corrcoef(a, b)[0, 1])


def block_boot(d: pd.DataFrame, y: str) -> tuple[float, float]:
    rng = np.random.default_rng(SEED)
    n = len(d)
    nb = int(np.ceil(n / BLOCK))
    vals = []
    arr = d.reset_index(drop=True)
    for _ in range(NBOOT):
        starts = rng.integers(0, n - BLOCK + 1, nb)
        idx = np.concatenate([np.arange(s, s + BLOCK) for s in starts])[:n]
        vals.append(partial_spearman(arr.iloc[idx], y))
    return float(np.percentile(vals, 2.5)), float(np.percentile(vals, 97.5))


def segment(df: pd.DataFrame, seg: tuple[str, str], y: str) -> pd.DataFrame:
    d = df.loc[seg[0]:seg[1]]
    return d.dropna(subset=["net", y, "past5", "past20"])


def precheck(df):
    d = df.loc[DEV[0]:DEV[1]].dropna(subset=["net", "ret0", "past5", "past20"])
    print(f"開發段可用日 {len(d)}（交易日 {len(df.loc[DEV[0]:DEV[1]])}）")
    for col, lab in [("ret0", "同日報酬"), ("past5", "過去 5 日"), ("past20", "過去 20 日")]:
        print(f"  net 與{lab}的 Spearman：{d['net'].corr(d[col], method='spearman'):+.3f}")


def main_test(df, seg, name):
    lines = [f"=== {name} {seg[0]} ~ {seg[1]} ==="]
    for y in ("fwd5", "fwd20"):
        d = segment(df, seg, y)
        rho = partial_spearman(d, y)
        lo, hi = block_boot(d, y)
        raw = d["net"].corr(d[y], method="spearman")
        lines.append(f"{y}: n={len(d)}  偏 Spearman ρ={rho:+.4f}  95% CI [{lo:+.4f}, {hi:+.4f}]  （未控制的原始 ρ={raw:+.4f}）")
    # 描述性附表
    for y in ("fwd5", "fwd20"):
        d = segment(df, seg, y).dropna(subset=["temp"])
        allm = d[y].mean()
        lo_d, hi_d = d[d["temp"] <= 10], d[d["temp"] >= 90]
        lines.append(f"描述 {y}: 全部 {allm:+.2%}（n={len(d)}）｜最悲觀 ≤10 {lo_d[y].mean():+.2%}（n={len(lo_d)}）｜最樂觀 ≥90 {hi_d[y].mean():+.2%}（n={len(hi_d)}）")
    text = "\n".join(lines)
    print(text)
    (OUT / f"result_{name}.txt").write_text(text + "\n", encoding="utf-8")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    cmd = sys.argv[1]
    df = load()
    if cmd == "precheck":
        precheck(df)
    elif cmd == "dev":
        main_test(df, DEV, "dev")
    elif cmd == "val":
        if not (OUT / "result_dev.txt").exists():
            sys.exit("開發段尚未定案，不准開封驗證段。")
        main_test(df, VAL, "val")
