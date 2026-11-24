import unittest

import pandas as pd

import extreme_divergence as ed


class SentimentExtremesTests(unittest.TestCase):
    def test_classify_boundaries(self):
        # 恐慌端：貪婪指數 <10、PCR ≥0.9、VIX >40；過熱端：≥75、≤0.70、<14
        self.assertEqual(ed.classify_sentiment("fear_greed", 9.99), ed.ZONE_PANIC)
        self.assertEqual(ed.classify_sentiment("fear_greed", 10.0), ed.ZONE_NEUTRAL)
        self.assertEqual(ed.classify_sentiment("fear_greed", 75.0), ed.ZONE_GREED)
        self.assertEqual(ed.classify_sentiment("pcr5", 0.90), ed.ZONE_PANIC)
        self.assertEqual(ed.classify_sentiment("pcr5", 0.70), ed.ZONE_GREED)
        self.assertEqual(ed.classify_sentiment("pcr5", 0.71), ed.ZONE_NEUTRAL)
        self.assertEqual(ed.classify_sentiment("pcr5", 0.75), ed.ZONE_NEUTRAL)
        self.assertEqual(ed.classify_sentiment("vix", 40.0), ed.ZONE_NEUTRAL)
        self.assertEqual(ed.classify_sentiment("vix", 40.01), ed.ZONE_PANIC)
        self.assertEqual(ed.classify_sentiment("vix", 13.99), ed.ZONE_GREED)
        self.assertEqual(ed.classify_sentiment("vix", 14.0), ed.ZONE_NEUTRAL)
        self.assertEqual(ed.classify_sentiment("vix", None), ed.ZONE_NA)
        self.assertEqual(ed.classify_sentiment("vix", float("nan")), ed.ZONE_NA)

    def test_parse_cnn_series_keeps_last_point_per_day(self):
        payload = {
            "put_call_options": {
                "data": [
                    {"x": pd.Timestamp("2026-11-20").value // 10**6, "y": 0.94},
                    {"x": pd.Timestamp("2026-11-23").value // 10**6, "y": 0.91},
                    {"x": pd.Timestamp("2026-11-23 23:14").value // 10**6, "y": 0.92},
                ]
            }
        }
        series = ed.parse_cnn_series(payload, "put_call_options")
        self.assertEqual(len(series), 2)
        self.assertAlmostEqual(series.loc["2026-11-23"], 0.92)
        self.assertTrue(ed.parse_cnn_series({}, "put_call_options").empty)

    def test_panic_resonance_and_episodes(self):
        dates = pd.to_datetime(["2025-04-03", "2025-04-04", "2025-04-07", "2025-06-02", "2026-11-20"])
        fg = pd.Series([20.0, 5.4, 4.0, 60.0, 18.6], index=dates)
        pcr = pd.Series([0.85, 0.95, 0.95, 0.70, 0.945], index=dates)
        vix = pd.Series([30.0, 45.3, 47.0, 17.0, 45.0], index=dates)

        result = ed.build_sentiment_extremes(5.0, "2026-11-20", fg, pcr, vix)

        self.assertEqual(result["verdict"], "panic_resonance")
        self.assertEqual(result["panic"], 3)
        # 歷史判定用的是歷史貪婪指數（11/20 為 18.6），不是即時分數，所以 11/20 不算同時成立。
        self.assertEqual(result["panic_episodes"], [{"起": "2025-04-04", "迄": "2025-04-07", "天數": 2}])
        self.assertEqual(result["greed_episodes"], [])
        self.assertEqual(result["history_days"], 5)

    def test_greed_side_and_mixed(self):
        dates = pd.date_range("2023-07-17", periods=3, freq="B")
        fg = pd.Series([80.0, 81.0, 50.0], index=dates)
        pcr = pd.Series([0.60, 0.61, 0.70], index=dates)
        vix = pd.Series([12.5, 12.8, 15.0], index=dates)

        greed = ed.build_sentiment_extremes(80.0, None, fg, pcr.iloc[:2], vix.iloc[:2])
        self.assertEqual(greed["verdict"], "greed_resonance")
        self.assertEqual(greed["greed_episodes"][0]["天數"], 2)

        mixed = ed.build_sentiment_extremes(5.0, None, fg, pcr.iloc[:2], vix.iloc[:2])
        self.assertEqual(mixed["verdict"], "mixed")

    def test_missing_source_is_insufficient_not_neutral(self):
        dates = pd.date_range("2026-11-02", periods=3, freq="B")
        vix = pd.Series([18.0, 19.0, 20.0], index=dates)
        result = ed.build_sentiment_extremes(None, None, pd.Series(dtype=float), pd.Series(dtype=float), vix)

        self.assertEqual(result["available"], 1)
        self.assertEqual(result["verdict"], "insufficient")
        self.assertEqual(result["panic_episodes"], [])
        self.assertIsNone(result["history_start"])


if __name__ == "__main__":
    unittest.main()
