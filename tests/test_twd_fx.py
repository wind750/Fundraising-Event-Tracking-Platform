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


class DxyDecompositionTests(unittest.TestCase):
    def _make(self, n=60, beta=0.5, seed=0):
        rng = np.random.default_rng(seed)
        idx = pd.bdate_range("2024-01-01", periods=n)
        dxy_ret = rng.normal(0, 0.004, n)
        dxy = pd.Series(100 * np.exp(np.cumsum(dxy_ret)), index=idx)
        # 台幣 D 日的報酬＝beta × 美元指數「前一天」的報酬
        twd_ret = np.concatenate([[0.0], beta * dxy_ret[:-1]])
        fx = pd.Series(30 * np.exp(np.cumsum(twd_ret)), index=idx)
        return fx, dxy

    def test_pure_dollar_move_gives_beta_and_zero_taiwan_part(self):
        fx, dxy = self._make(beta=0.5)
        result = twd_fx.dxy_decomposition(fx, dxy, window=20)
        self.assertGreater(len(result), 10)
        np.testing.assert_allclose(result["beta"], 0.5, atol=1e-9)
        np.testing.assert_allclose(result["r2"], 1.0, atol=1e-9)
        np.testing.assert_allclose(result["tw_part"], 0.0, atol=1e-12)

    def test_pairs_twd_day_with_previous_dxy_day(self):
        idx = pd.to_datetime(["2024-01-02", "2024-01-03"])
        dxy = pd.Series([100.0, 200.0], index=idx)
        fx = pd.Series([30.0, 30.0], index=idx)
        prev = twd_fx._asof_previous(fx, dxy)
        self.assertTrue(np.isnan(prev.iloc[0]))
        self.assertEqual(prev.iloc[1], 100.0)  # 1/3 配 1/2，不配同日的 200

    def test_beta_does_not_use_same_day_data(self):
        fx, dxy = self._make(n=40, beta=0.5)
        base = twd_fx.dxy_decomposition(fx, dxy, window=20)
        fx_shock = fx.copy()
        fx_shock.iloc[-1] *= 1.05  # 只改最後一天
        shocked = twd_fx.dxy_decomposition(fx_shock, dxy, window=20)
        self.assertAlmostEqual(shocked["beta"].iloc[-1], base["beta"].iloc[-1])
        self.assertGreater(shocked["tw_part"].iloc[-1], 0.04)  # 衝擊全部歸台灣因素

    def test_summary_parts_add_up(self):
        fx, dxy = self._make(n=80, beta=0.4, seed=1)
        noise = pd.Series(np.random.default_rng(2).normal(0, 0.002, 80), index=fx.index)
        fx = fx * np.exp(noise.cumsum())
        frame = twd_fx.dxy_decomposition(fx, dxy, window=20)
        summary = twd_fx.decomposition_summary(frame, days=20)
        self.assertAlmostEqual(summary["factor_pct"] + summary["tw_pct"], summary["total_pct"])
        self.assertIsNotNone(summary["tw_percentile"])

    def test_summary_none_when_short(self):
        self.assertIsNone(twd_fx.decomposition_summary(pd.DataFrame(columns=["twd_ret"]), days=20))


class DivergenceTests(unittest.TestCase):
    def test_classify_states(self):
        c = twd_fx._classify
        self.assertEqual(c(1.0, -1.0, 0.5), twd_fx.STATE_STOCK_UP_TWD_DOWN)
        self.assertEqual(c(-1.0, 1.0, 0.5), twd_fx.STATE_STOCK_DOWN_TWD_UP)
        self.assertEqual(c(1.0, 1.0, 0.5), twd_fx.STATE_BOTH_UP)
        self.assertEqual(c(-1.0, -1.0, 0.5), twd_fx.STATE_BOTH_DOWN)
        self.assertEqual(c(1.0, -0.3, 0.5), twd_fx.STATE_UNCLEAR)  # 台幣動作不夠大
        self.assertEqual(c(np.nan, 1.0, 0.5), twd_fx.STATE_UNCLEAR)

    def test_detects_stock_up_twd_down_and_sign_convention(self):
        idx = pd.bdate_range("2023-01-02", periods=300)
        rng = np.random.default_rng(3)
        ti = pd.Series(10000 * np.exp(np.cumsum(rng.normal(0, 0.01, 300))), index=idx)
        fx = pd.Series(30 * np.exp(np.cumsum(rng.normal(0, 0.003, 300))), index=idx)
        # 最後 20 天：股市大漲、USD/TWD 大漲（台幣大貶）
        ti.iloc[-20:] = ti.iloc[-21] * np.exp(np.linspace(0.01, 0.15, 20))
        fx.iloc[-20:] = fx.iloc[-21] * np.exp(np.linspace(0.002, 0.05, 20))

        frame = twd_fx.twii_fx_divergence(fx, ti, scale_days=100)

        last = frame.iloc[-1]
        self.assertGreater(last["stock_ret"], 0)
        self.assertLess(last["twd_ret"], 0)  # USD/TWD 漲＝台幣貶＝升值欄為負
        self.assertEqual(last["state"], twd_fx.STATE_STOCK_UP_TWD_DOWN)

    def test_scale_excludes_current_day(self):
        idx = pd.bdate_range("2023-01-02", periods=200)
        rng = np.random.default_rng(4)
        ti = pd.Series(10000 * np.exp(np.cumsum(rng.normal(0, 0.01, 200))), index=idx)
        fx = pd.Series(30 * np.exp(np.cumsum(rng.normal(0, 0.003, 200))), index=idx)
        base = twd_fx.twii_fx_divergence(fx, ti, scale_days=100)
        ti2 = ti.copy()
        ti2.iloc[-1] *= 1.2
        shocked = twd_fx.twii_fx_divergence(fx, ti2, scale_days=100)
        ratio_base = base["stock_ret"].iloc[-1] / base["z_stock"].iloc[-1]
        ratio_shock = shocked["stock_ret"].iloc[-1] / shocked["z_stock"].iloc[-1]
        self.assertAlmostEqual(ratio_base, ratio_shock)  # 尺度不受當天影響

    def test_state_runs_and_summary(self):
        idx = pd.bdate_range("2024-01-01", periods=6)
        states = pd.Series(["A", "A", "B", "B", "B", "A"], index=idx)
        runs = twd_fx.state_runs(states)
        self.assertEqual(list(runs["state"]), ["A", "B", "A"])
        self.assertEqual(list(runs["days"]), [2, 3, 1])
        self.assertEqual(runs["start"].iloc[1], idx[2])
        self.assertEqual(runs["end"].iloc[1], idx[4])


class AsiaSyncTests(unittest.TestCase):
    def _peers(self, n=200, seed=5):
        rng = np.random.default_rng(seed)
        idx = pd.bdate_range("2024-01-01", periods=n)
        common = rng.normal(0, 0.004, n)
        peers = {}
        for i, code in enumerate(twd_fx.ASIA_PEERS):
            own = rng.normal(0, 0.001, n)
            peers[code] = pd.Series(10 * (i + 1) * np.exp(np.cumsum(common + own)), index=idx)
        return idx, common, peers

    def test_basket_is_equal_weight_mean_of_log_returns(self):
        idx = pd.bdate_range("2024-01-01", periods=3)
        peers = {"A": pd.Series([100.0, 110.0, 110.0], index=idx),
                 "B": pd.Series([50.0, 50.0, 55.0], index=idx)}
        basket = twd_fx.asia_basket_index(peers)
        self.assertAlmostEqual(np.log(basket.iloc[1] / basket.iloc[0]), np.log(1.1) / 2)
        self.assertAlmostEqual(np.log(basket.iloc[2] / basket.iloc[1]), np.log(1.1) / 2)

    def test_basket_uses_only_days_all_peers_quote(self):
        idx = pd.bdate_range("2024-01-01", periods=4)
        peers = {"A": pd.Series([100.0, 101.0, 102.0, 103.0], index=idx),
                 "B": pd.Series([50.0, np.nan, 51.0, 52.0], index=idx)}
        basket = twd_fx.asia_basket_index(peers)
        self.assertNotIn(idx[1], basket.index)

    def test_asia_decomposition_same_day_and_pure_common_move(self):
        idx, common, peers = self._peers()
        basket = twd_fx.asia_basket_index(peers)
        basket_ret = np.log(basket).diff().fillna(0.0).values
        # 台幣＝0.6 × 同日籃子報酬，沒有自己的成分
        fx = pd.Series(30 * np.exp(np.cumsum(0.6 * basket_ret)), index=basket.index)
        frame = twd_fx.asia_decomposition(fx, peers, window=40)
        np.testing.assert_allclose(frame["beta"], 0.6, atol=1e-9)
        np.testing.assert_allclose(frame["tw_part"], 0.0, atol=1e-12)

    def test_sync_table_sign_rank_and_corr(self):
        idx, common, peers = self._peers()
        fx = pd.Series(30 * np.exp(np.cumsum(common)), index=idx)
        names = {"TWD=X": "台幣", **twd_fx.ASIA_PEERS}
        table = twd_fx.currency_sync_table(fx, peers, names, days=20, short=60, long=150)
        self.assertEqual(len(table), 5)
        twd_row = table[table["code"] == "TWD=X"].iloc[0]
        expected = -(np.log(fx.iloc[-1]) - np.log(fx.iloc[-21])) * 100  # 升值為正
        self.assertAlmostEqual(twd_row["appr_pct"], expected)
        self.assertTrue(np.isnan(twd_row["corr_short"]))
        peer_rows = table[table["code"] != "TWD=X"]
        self.assertTrue((peer_rows["corr_short"] > 0.8).all())  # 共同因素主導
        self.assertEqual(list(table["rank"]), sorted(table["rank"]))

    def test_rolling_sync_corr_columns(self):
        idx, common, peers = self._peers()
        fx = pd.Series(30 * np.exp(np.cumsum(common)), index=idx)
        corr = twd_fx.rolling_sync_corr(fx, peers, twd_fx.ASIA_PEERS, window=60)
        self.assertEqual(set(corr.columns), set(twd_fx.ASIA_PEERS.values()))
        self.assertTrue((corr.dropna() > 0.8).all().all())


class VolatilityTests(unittest.TestCase):
    def test_despike_merges_round_trip_and_keeps_net_move(self):
        idx = pd.bdate_range("2024-01-01", periods=5)
        r = pd.Series([0.001, -0.018, 0.0185, 0.002, -0.001], index=idx)
        cleaned, flagged = twd_fx.despike_returns(r)
        self.assertEqual(flagged, [idx[1]])
        self.assertAlmostEqual(cleaned.iloc[1], 0.0005)
        self.assertEqual(cleaned.iloc[2], 0.0)
        self.assertAlmostEqual(cleaned.sum(), r.sum())

    def test_despike_keeps_real_partial_reversal(self):
        # 2025-05 型：−5.2% 後 +2.8%，只回補一半，是真實波動，不得合併
        idx = pd.bdate_range("2025-05-05", periods=3)
        r = pd.Series([-0.052, 0.028, 0.013], index=idx)
        cleaned, flagged = twd_fx.despike_returns(r)
        self.assertEqual(flagged, [])
        pd.testing.assert_series_equal(cleaned, r)

    def test_percentile_excludes_today(self):
        s = pd.Series([1.0, 2.0, 3.0, 2.5], index=pd.bdate_range("2024-01-01", periods=4))
        p = twd_fx._trailing_percentile(s, days=3)
        self.assertAlmostEqual(p.iloc[-1], 200 / 3)  # 2.5 高於 1、2，不高於 3

    def test_vol_frame_detects_volatility_jump(self):
        rng = np.random.default_rng(7)
        n = 400
        idx = pd.bdate_range("2023-01-02", periods=n)
        r = rng.normal(0, 0.002, n)
        r[-10:] = rng.normal(0, 0.012, 10)  # 最後兩週突然大震
        fx = pd.Series(30 * np.exp(np.cumsum(r)), index=idx)
        frame, _ = twd_fx.vol_frame(fx)
        last = frame.iloc[-1]
        self.assertGreaterEqual(last["pct"], 95)
        self.assertGreater(last["expansion"], 2)
        self.assertEqual(twd_fx.vol_state(last["pct"]), "🚨 異常高波動")

    def test_vol_state_bounds(self):
        self.assertEqual(twd_fx.vol_state(80), "⚠️ 波動偏高")
        self.assertEqual(twd_fx.vol_state(20), "🟢 異常平靜")
        self.assertEqual(twd_fx.vol_state(50), "中性")
        self.assertEqual(twd_fx.vol_state(np.nan), "資料暖機中")


if __name__ == "__main__":
    unittest.main()
