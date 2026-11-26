import unittest

import numpy as np
import pandas as pd

import twd_fx


class AdrPremiumTests(unittest.TestCase):
    def test_pairs_local_day_with_previous_adr_close_not_same_day(self):
        # 台股 1/3 應配美股 1/2 收盤（100），不是同日的 1/3（200）
        adr = pd.Series([100.0, 200.0], index=pd.to_datetime(["2024-01-02", "2024-01-03"]))
        local = pd.Series([600.0], index=pd.to_datetime(["2024-01-03"]))
        fx = pd.Series([30.0], index=pd.to_datetime(["2024-01-03"]))

        result = twd_fx.adr_premium_frame(adr, local, fx)

        self.assertEqual(result.iloc[0]["adr"], 100.0)
        self.assertEqual(result.iloc[0]["adr_date"], pd.Timestamp("2024-01-02"))
        # 100 / 5 * 30 / 600 - 1 = 0
        self.assertAlmostEqual(result.iloc[0]["premium"], 0.0)

    def test_monday_uses_friday_adr_across_weekend(self):
        adr = pd.Series([110.0], index=pd.to_datetime(["2024-01-05"]))  # 週五
        local = pd.Series([600.0], index=pd.to_datetime(["2024-01-08"]))  # 週一
        fx = pd.Series([30.0], index=pd.to_datetime(["2024-01-05"]))

        result = twd_fx.adr_premium_frame(adr, local, fx)

        self.assertEqual(result.iloc[0]["adr_date"], pd.Timestamp("2024-01-05"))
        self.assertAlmostEqual(result.iloc[0]["premium"], 110.0 / 5 * 30.0 / 600.0 - 1)

    def test_drops_local_days_without_any_earlier_adr(self):
        adr = pd.Series([100.0], index=pd.to_datetime(["2024-01-03"]))
        local = pd.Series([600.0, 600.0], index=pd.to_datetime(["2024-01-03", "2024-01-04"]))
        fx = pd.Series([30.0, 30.0], index=pd.to_datetime(["2024-01-03", "2024-01-04"]))

        result = twd_fx.adr_premium_frame(adr, local, fx)

        self.assertEqual(list(result.index), [pd.Timestamp("2024-01-04")])

    def test_ignores_union_calendar_nan_rows(self):
        # 模擬 raw_df 聯集日曆：週末列是 NaN，不得被當成交易日
        idx = pd.date_range("2024-01-01", periods=7)
        adr = pd.Series([100, 100, 100, 100, 100, np.nan, np.nan], index=idx, dtype=float)
        local = pd.Series([600, 600, 600, 600, 600, np.nan, np.nan], index=idx, dtype=float)
        fx = pd.Series([30, 30, 30, 30, 30, np.nan, np.nan], index=idx, dtype=float)

        result = twd_fx.adr_premium_frame(adr, local, fx)

        self.assertEqual(len(result), 4)  # 第一天沒有更早的 ADR
        self.assertFalse(result["premium"].isna().any())

    def test_adr_lag_weekdays(self):
        # 週二配週一：正常
        self.assertEqual(twd_fx.adr_lag_weekdays("2026-11-24", "2026-11-23"), 0)
        # 週一配週五：跨週末仍正常
        self.assertEqual(twd_fx.adr_lag_weekdays("2026-11-23", "2026-11-20"), 0)
        # 週四配週二：中間夾了週三
        self.assertEqual(twd_fx.adr_lag_weekdays("2026-11-26", "2026-11-24"), 1)


class FxSummaryTests(unittest.TestCase):
    def test_summary_direction_and_change(self):
        idx = pd.bdate_range("2024-01-01", periods=80)
        fx = pd.Series(np.linspace(30.0, 32.0, 80), index=idx)

        result = twd_fx.fx_summary(fx)

        self.assertAlmostEqual(result["last"], 32.0)
        self.assertAlmostEqual(result["change_pct"], (32.0 / fx.iloc[-21] - 1) * 100)
        self.assertTrue(result["twd_weaker_than_ma"])  # 一路往上＝台幣一路貶

    def test_summary_returns_none_when_history_too_short(self):
        fx = pd.Series([30.0] * 10, index=pd.bdate_range("2024-01-01", periods=10))
        self.assertIsNone(twd_fx.fx_summary(fx))

    def test_percentile_of_last(self):
        self.assertAlmostEqual(twd_fx.percentile_of_last(pd.Series([1.0, 2.0, 3.0, 4.0])), 100.0)
        self.assertAlmostEqual(twd_fx.percentile_of_last(pd.Series([4.0, 3.0, 2.0, 1.0])), 25.0)
        self.assertIsNone(twd_fx.percentile_of_last(pd.Series([1.0])))


if __name__ == "__main__":
    unittest.main()
