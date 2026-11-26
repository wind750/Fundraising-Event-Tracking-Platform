import datetime as dt
import unittest
from unittest import mock

import pandas as pd

import tw_govbond


class TwGovBondTests(unittest.TestCase):
    def test_url_template(self):
        self.assertEqual(
            tw_govbond.URL_TMPL.format(d=dt.date(2026, 11, 25)),
            "https://www.tpex.org.tw/storage/bond_zone/tradeinfo/govbond/2026/202611/Curve.20261125-C.xls",
        )

    def test_merge_history_dedupes_and_sorts(self):
        old = pd.DataFrame({"date": pd.to_datetime(["2026-11-20", "2026-11-23"]), "bm_10y": [1.93, 1.93]})
        new = pd.DataFrame({"date": pd.to_datetime(["2026-11-23", "2026-11-24"]), "bm_10y": [1.95, 1.94]})
        merged = tw_govbond.merge_history(old.reindex(columns=tw_govbond.COLUMNS),
                                          new.reindex(columns=tw_govbond.COLUMNS))
        self.assertEqual(list(merged["date"]), list(pd.to_datetime(["2026-11-20", "2026-11-23", "2026-11-24"])))
        self.assertAlmostEqual(merged.loc[merged["date"] == "2026-11-23", "bm_10y"].iloc[0], 1.95)  # 新的蓋舊的

    def test_fetch_range_skips_weekends_and_respects_cap(self):
        calls = []

        def fake_fetch(day, session=None):
            calls.append(day)
            return {"date": pd.Timestamp(day), "bm_10y": 1.9}

        with mock.patch.object(tw_govbond, "fetch_day", side_effect=fake_fetch):
            out = tw_govbond.fetch_range(dt.date(2026, 11, 20), dt.date(2026, 11, 26), pause=0, max_requests=3)
        self.assertEqual(calls, [dt.date(2026, 11, 20), dt.date(2026, 11, 23), dt.date(2026, 11, 24)])
        self.assertEqual(len(out), 3)

    def test_fetch_day_rejects_non_excel(self):
        resp = mock.Mock(status_code=200, content=b"<html>not found</html>")
        session = mock.Mock(get=mock.Mock(return_value=resp))
        self.assertIsNone(tw_govbond.fetch_day(dt.date(2026, 11, 26), session=session))


if __name__ == "__main__":
    unittest.main()
