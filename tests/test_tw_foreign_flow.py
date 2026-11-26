import datetime as dt
import unittest
from unittest import mock

import pandas as pd

import tw_foreign_flow as tff

SAMPLE = {
    "stat": "OK",
    "fields": ["單位名稱", "買進金額", "賣出金額", "買賣差額"],
    "data": [
        ["自營商(自行買賣)", "10,802,832,920", "18,165,685,022", "-7,362,852,102"],
        ["自營商(避險)", "54,361,558,811", "59,831,923,239", "-5,470,364,428"],
        ["投信", "71,743,846,506", "16,709,122,211", "55,034,724,295"],
        ["外資及陸資(不含外資自營商)", "457,832,326,822", "581,487,124,975", "-123,654,798,153"],
        ["外資自營商", "0", "0", "0"],
        ["合計", "594,740,565,059", "676,193,855,447", "-81,453,290,388"],
    ],
}


class ForeignFlowTests(unittest.TestCase):
    def test_parse_picks_foreign_row_not_foreign_dealer(self):
        row = tff.parse_bfi82u(SAMPLE)
        self.assertEqual(row["foreign_net"], -123654798153.0)
        self.assertEqual(row["foreign_buy"], 457832326822.0)
        self.assertEqual(row["trust_net"], 55034724295.0)
        self.assertEqual(row["dealer_self_net"], -7362852102.0)
        self.assertEqual(row["dealer_hedge_net"], -5470364428.0)

    def test_parse_non_trading_day(self):
        self.assertIsNone(tff.parse_bfi82u({"stat": "很抱歉，沒有符合條件的資料!"}))
        self.assertIsNone(tff.parse_bfi82u({"stat": "OK", "data": [["投信", "1", "1", "0"]]}))

    def test_fetch_day_retries_once_when_blocked(self):
        blocked = mock.Mock()
        blocked.json.side_effect = ValueError("html")
        ok = mock.Mock()
        ok.json.return_value = SAMPLE
        session = mock.Mock(get=mock.Mock(side_effect=[blocked, ok]))
        row = tff.fetch_day(dt.date(2026, 11, 25), session=session, retry_wait=0)
        self.assertEqual(row["date"], pd.Timestamp("2026-11-25"))
        self.assertEqual(session.get.call_count, 2)

    def test_merge_history_dedupes(self):
        old = pd.DataFrame({"date": pd.to_datetime(["2026-11-24"]), "foreign_net": [1.0]}).reindex(columns=tff.COLUMNS)
        new = pd.DataFrame({"date": pd.to_datetime(["2026-11-24", "2026-11-25"]), "foreign_net": [2.0, 3.0]}).reindex(
            columns=tff.COLUMNS)
        merged = tff.merge_history(old, new)
        self.assertEqual(list(merged["foreign_net"]), [2.0, 3.0])


if __name__ == "__main__":
    unittest.main()
