import unittest

import numpy as np
import pandas as pd

import extreme_divergence as ed


class RadarHistoryTests(unittest.TestCase):
    def test_volatility_history_marks_backwardation_days(self):
        dates = pd.date_range("2026-01-01", periods=4, freq="B")
        vix = pd.Series([20.0, 25.0, 31.0, 18.0], index=dates)
        vix3m = pd.Series([22.0, 25.0, 30.0, 20.0], index=dates)

        metric = ed.build_volatility_term_structure(vix, vix3m)

        self.assertEqual(metric.threshold, 1.0)
        self.assertEqual(list(metric.history["danger"]), [False, True, True, False])
        self.assertAlmostEqual(metric.history["value"].iloc[-1], metric.value)

    def test_equal_weight_history_has_ma_reference_and_matches_latest(self):
        dates = pd.date_range("2025-01-01", periods=260, freq="B")
        spy = pd.Series(100.0, index=dates)
        rsp = pd.Series(np.linspace(30.0, 28.0, len(dates)), index=dates)  # 一路走弱

        metric = ed.build_equal_weight_breadth(rsp, spy)

        self.assertIn("200 日均線", metric.history.columns)
        self.assertTrue(metric.history["danger"].iloc[-1])
        self.assertEqual(bool(metric.history["danger"].iloc[-1]), metric.danger)

    def test_sp500_breadth_history_last_point_equals_card(self):
        dates = pd.date_range("2025-01-01", periods=230, freq="B")
        up = pd.Series(np.linspace(10.0, 20.0, len(dates)), index=dates)
        down = pd.Series(np.linspace(20.0, 10.0, len(dates)), index=dates)
        close = pd.DataFrame({"A": up, "B": up, "C": down, "D": up})

        metric = ed.build_sp500_sma200_breadth(close, total_constituents=4)

        self.assertEqual(metric.threshold, 50.0)
        self.assertAlmostEqual(metric.history["value"].iloc[-1], metric.value)
        self.assertAlmostEqual(metric.value, 75.0)
        self.assertFalse(metric.history["danger"].iloc[-1])

    def test_history_is_excluded_from_equality(self):
        a = ed.RadarMetric("x", available=True, history=pd.DataFrame({"value": [1.0]}))
        b = ed.RadarMetric("x", available=True)
        self.assertEqual(a, b)


if __name__ == "__main__":
    unittest.main()
