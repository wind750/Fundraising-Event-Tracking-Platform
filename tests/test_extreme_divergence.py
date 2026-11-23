import unittest
import io

import numpy as np
import pandas as pd
from openpyxl import Workbook

import extreme_divergence as ed


class ExtremeDivergenceTests(unittest.TestCase):
    def test_parse_spy_holdings_reads_date_and_normalizes_class_tickers(self):
        workbook = Workbook()
        sheet = workbook.active
        sheet.title = "holdings"
        sheet.append(["Fund Name:", "State Street SPDR S&P 500 ETF Trust"])
        sheet.append(["Ticker Symbol:", "SPY"])
        sheet.append(["Holdings:", "As of 19-Nov-2026"])
        sheet.append([])
        sheet.append(["Name", "Ticker", "Identifier"])
        sheet.append(["Berkshire Hathaway", "BRK.B", "084670702"])
        for index in range(399):
            sheet.append([f"Company {index}", f"T{index:03d}", str(index)])
        sheet.append(["CONTRA OLD SECURITY", "2602335D", "436CVR021"])
        content = io.BytesIO()
        workbook.save(content)

        tickers, as_of = ed.parse_spy_holdings(content.getvalue())

        self.assertEqual(as_of, "2026-11-19")
        self.assertEqual(tickers[0], "BRK-B")
        self.assertEqual(len(tickers), 400)
        self.assertNotIn("2602335D", tickers)

    def test_cftc_positioning_uses_latest_row_and_history_percentile(self):
        dates = pd.date_range("2024-01-02", periods=10, freq="7D")
        frame = pd.DataFrame(
            {
                "report_date_as_yyyy_mm_dd": dates,
                "open_interest_all": 1000,
                "asset_mgr_positions_long": np.arange(500, 600, 10),
                "asset_mgr_positions_short": 300,
            }
        )

        metric = ed.build_cftc_positioning(frame)

        self.assertTrue(metric.available)
        self.assertAlmostEqual(metric.value, 29.0)
        self.assertEqual(metric.percentile, 100.0)
        self.assertTrue(metric.danger)
        self.assertEqual(metric.as_of, "2024-03-05")

    def test_vix_term_structure_requires_common_dates(self):
        dates = pd.bdate_range("2025-01-01", periods=4)
        vix = pd.Series([18.0, 19.0, 22.0, 24.0], index=dates)
        vix3m = pd.Series([20.0, 20.0, 21.0], index=dates[1:])

        metric = ed.build_volatility_term_structure(vix, vix3m)

        self.assertTrue(metric.available)
        self.assertTrue(metric.danger)
        self.assertAlmostEqual(metric.value, 24.0 / 21.0)
        self.assertEqual(metric.as_of, dates[-1].strftime("%Y-%m-%d"))

    def test_equal_weight_breadth_is_danger_only_when_below_ma_and_at_low(self):
        dates = pd.bdate_range("2024-01-01", periods=260)
        spy = pd.Series(100.0, index=dates)
        rsp = pd.Series(np.r_[np.full(197, 100.0), np.linspace(100.0, 70.0, 63)], index=dates)

        metric = ed.build_equal_weight_breadth(rsp, spy)

        self.assertTrue(metric.available)
        self.assertTrue(metric.danger)
        self.assertIn("63 日低", metric.status)

    def test_sp500_breadth_fails_closed_when_coverage_is_too_low(self):
        dates = pd.bdate_range("2025-01-01", periods=220)
        close = pd.DataFrame(
            {
                "AAA": np.linspace(100.0, 120.0, 220),
                "BBB": np.linspace(100.0, 80.0, 220),
            },
            index=dates,
        )

        metric = ed.build_sp500_sma200_breadth(close, total_constituents=4, min_coverage=0.90)

        self.assertFalse(metric.available)
        self.assertAlmostEqual(metric.coverage, 0.5)
        self.assertIn("低於 90%", metric.detail)

    def test_sp500_breadth_counts_valid_constituents(self):
        dates = pd.bdate_range("2025-01-01", periods=220)
        close = pd.DataFrame(
            {
                "AAA": np.linspace(100.0, 140.0, 220),
                "BBB": np.linspace(140.0, 100.0, 220),
                "CCC": np.linspace(100.0, 150.0, 220),
                "DDD": np.linspace(150.0, 100.0, 220),
            },
            index=dates,
        )

        metric = ed.build_sp500_sma200_breadth(close, total_constituents=4)

        self.assertTrue(metric.available)
        self.assertAlmostEqual(metric.value, 50.0)
        self.assertFalse(metric.danger)
        self.assertEqual(metric.coverage, 1.0)

    def test_risk_pillars_do_not_double_count_correlated_metrics(self):
        red = ed.RadarMetric("red", available=True, danger=True)
        green = ed.RadarMetric("green", available=True, danger=False)
        missing = ed.unavailable_metric("missing", "test")

        summary = ed.summarize_risk_pillars(
            momentum_metrics=[red, red],
            positioning=green,
            volatility=missing,
            breadth_metrics=[red, red],
        )

        self.assertEqual(summary["danger"], 2)
        self.assertEqual(summary["available"], 3)
        self.assertFalse(summary["insufficient"])


if __name__ == "__main__":
    unittest.main()
