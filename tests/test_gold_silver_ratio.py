import unittest

import numpy as np
import pandas as pd

import gold_silver_ratio as gsr


class GoldSilverRatioTests(unittest.TestCase):
    def test_prepare_price_frame_uses_only_common_dates(self):
        gold = pd.Series([200.0, 210.0, 220.0], index=pd.date_range("2024-01-01", periods=3))
        silver = pd.Series([2.0, 2.5], index=pd.to_datetime(["2024-01-02", "2024-01-03"]))

        result = gsr.prepare_price_frame(gold, silver)

        self.assertEqual(list(result.index), list(pd.to_datetime(["2024-01-02", "2024-01-03"])))
        self.assertAlmostEqual(result.iloc[0]["ratio"], 105.0)

    def test_forward_return_does_not_fill_unmatured_rows(self):
        dates = pd.bdate_range("2024-01-01", periods=10)
        frame = pd.DataFrame({"gold": 100.0, "silver": np.arange(10.0, 20.0), "ratio": 10.0}, index=dates)

        result = gsr.add_forward_return(frame, horizon=3)

        self.assertAlmostEqual(result.iloc[0]["silver_forward_return"], 13.0 / 10.0 - 1.0)
        self.assertTrue(result["silver_forward_return"].tail(3).isna().all())

    def test_summary_uses_crossings_with_cooldown(self):
        dates = pd.bdate_range("2024-01-01", periods=30)
        silver = pd.Series(np.linspace(10.0, 20.0, 30), index=dates)
        ratio = pd.Series(70.0, index=dates)
        ratio.iloc[[2, 5, 15]] = 85.0
        frame = pd.DataFrame({"gold": ratio * silver, "silver": silver, "ratio": ratio}, index=dates)
        frame = gsr.add_forward_return(frame, horizon=5)

        summary = gsr.summarize_conditions(frame, horizon=5, thresholds=(80.0,))
        row = summary.loc[summary["條件"] == "金銀比 ≥80"].iloc[0]

        self.assertEqual(int(row["逐日樣本"]), 3)
        self.assertEqual(int(row["獨立事件數"]), 2)

    def test_snapshot_excludes_last_horizon_rows_from_statistics(self):
        dates = pd.bdate_range("2020-01-01", periods=200)
        silver = pd.Series(np.linspace(10.0, 30.0, 200), index=dates)
        gold = silver * 85.0

        snapshot = gsr.build_dashboard_snapshot(gold, silver, horizon=20, rolling_years=10)
        baseline = snapshot["full_history"].iloc[0]

        self.assertEqual(int(baseline["逐日樣本"]), 180)
        self.assertEqual(snapshot["maturity_cutoff"], dates[-21])
        self.assertEqual(snapshot["current_state"].label, "🟠 相對低估觀察區")

    def test_rolling_history_is_not_changed_by_prices_after_evaluation_date(self):
        dates = pd.bdate_range("2022-01-03", periods=600)
        silver = pd.Series(20.0 + np.linspace(0.0, 8.0, 600), index=dates)
        ratio = pd.Series(85.0 + 8.0 * np.sin(np.arange(600) / 12.0), index=dates)
        base = gsr.add_forward_return(
            gsr.prepare_price_frame(ratio * silver, silver), horizon=20
        )

        changed_silver = silver.copy()
        changed_silver.iloc[500:] *= 3.0
        changed = gsr.add_forward_return(
            gsr.prepare_price_frame(ratio * changed_silver, changed_silver), horizon=20
        )

        base_stats = gsr.rolling_condition_statistics(base, horizon=20, window_years=2)
        changed_stats = gsr.rolling_condition_statistics(changed, horizon=20, window_years=2)
        cutoff = dates[499]
        columns = ["日期", "門檻", "逐日勝率", "事件勝率", "逐日平均報酬", "獨立事件數"]
        pd.testing.assert_frame_equal(
            base_stats.loc[base_stats["日期"] <= cutoff, columns].reset_index(drop=True),
            changed_stats.loc[changed_stats["日期"] <= cutoff, columns].reset_index(drop=True),
        )


if __name__ == "__main__":
    unittest.main()
