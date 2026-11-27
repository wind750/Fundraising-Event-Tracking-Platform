"""卡片小圖用的歷史序列（twd_fx.summary_history／percentile_history）：最後一點必須等於卡片 summary。"""
import unittest

import numpy as np
import pandas as pd

import twd_fx


def _fx(n=400, seed=1):
    rng = np.random.default_rng(seed)
    idx = pd.bdate_range("2024-01-01", periods=n)
    return pd.Series(30 * np.exp(np.cumsum(rng.normal(0, 0.003, n))), index=idx)


class SummaryHistoryTest(unittest.TestCase):
    def test_last_row_equals_summary_of_full_data(self):
        fx = _fx()
        dxy = pd.Series(100 * np.exp(np.cumsum(np.random.default_rng(2).normal(0, 0.004, len(fx)))), index=fx.index)
        frame = twd_fx.dxy_decomposition(fx, dxy)
        hist = twd_fx.summary_history(twd_fx.decomposition_summary, frame)
        full = twd_fx.decomposition_summary(frame)
        self.assertEqual(len(hist), 20)
        last = hist.iloc[-1]
        self.assertEqual(last["date"], full["date"])
        for k in ("total_pct", "factor_pct", "tw_pct", "tw_percentile"):
            self.assertAlmostEqual(last[k], full[k], places=12)
        self.assertTrue(hist["date"].is_monotonic_increasing)

    def test_each_row_equals_summary_truncated_to_that_date(self):
        fx = _fx()
        dxy = pd.Series(100 * np.exp(np.cumsum(np.random.default_rng(3).normal(0, 0.004, len(fx)))), index=fx.index)
        frame = twd_fx.dxy_decomposition(fx, dxy)
        hist = twd_fx.summary_history(twd_fx.decomposition_summary, frame)
        mid = hist.iloc[5]
        ref = twd_fx.decomposition_summary(frame.loc[:mid["date"]])
        self.assertAlmostEqual(mid["tw_pct"], ref["tw_pct"], places=12)

    def test_nan_rows_are_deduplicated_by_summary_date(self):
        # spread_summary 內部會 dropna：資料尾端有 NaN 列時，同一個資料日只出現一次
        idx = pd.bdate_range("2025-01-01", periods=60)
        frame = pd.DataFrame({
            "tw2": 1.5, "tw10": 1.6, "tw10_bm": 1.6, "us2": 4.0, "us10": np.linspace(4.0, 4.5, 60),
            "bm10_unchanged": 0,
        }, index=idx)
        frame["spread2"] = frame["us2"] - frame["tw2"]
        frame["spread10"] = frame["us10"] - frame["tw10"]
        frame.iloc[-3:, frame.columns.get_loc("spread2")] = np.nan
        hist = twd_fx.summary_history(twd_fx.spread_summary, frame)
        self.assertEqual(hist["date"].nunique(), len(hist))
        self.assertEqual(hist["date"].iloc[-1], twd_fx.spread_summary(frame)["date"])

    def test_empty_and_short_inputs(self):
        self.assertTrue(twd_fx.summary_history(twd_fx.decomposition_summary, pd.DataFrame()).empty)
        self.assertTrue(twd_fx.percentile_history(pd.Series([1.0])).empty)

    def test_percentile_history_last_point(self):
        s = _fx(100)
        hist = twd_fx.percentile_history(s)
        self.assertEqual(len(hist), 20)
        self.assertAlmostEqual(hist["pct"].iloc[-1], twd_fx.percentile_of_last(s), places=12)
        self.assertAlmostEqual(hist["pct"].iloc[0], twd_fx.percentile_of_last(s.iloc[:81]), places=12)


if __name__ == "__main__":
    unittest.main()
