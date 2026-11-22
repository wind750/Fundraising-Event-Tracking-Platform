import datetime as dt
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "ptt_sentiment"))

from ptt_sentiment.lexicon import classify  # noqa: E402
from ptt_sentiment import thermometer as th  # noqa: E402
from ptt_sentiment.build_daily import assign_day  # noqa: E402
from ptt_sentiment.crawl import nrec_to_int, parse_pushes  # noqa: E402


def test_classify_basic_sides():
    assert classify("今天噴爆 歐印")["side"] == "bull"
    assert classify("今天噴爆 歐印")["greed"]
    assert classify("又跌停 斷頭了 救救我")["side"] == "bear"
    assert classify("又跌停 斷頭了 救救我")["fear"]
    assert classify("午餐吃什麼")["side"] == "none"


def test_classify_long_word_absorbs_short():
    r = classify("大崩")
    assert r["bear_words"] == {"大崩"}  # 「崩」被長詞吸收，不重複計


def test_classify_negation():
    assert classify("不會崩啦")["side"] == "none"
    assert classify("沒有斷頭")["fear"] is False


def test_expanding_pct_has_no_lookahead():
    x = pd.Series([1.0, 2.0, 3.0, 0.0, 10.0])
    p = th._expanding_pct(x, min_history=3)
    assert np.isnan(p.iloc[:3]).all()
    assert p.iloc[3] == 0.0  # 0 比過去 1,2,3 都小
    assert p.iloc[4] == 100.0  # 10 比過去全部大
    # 改動未來值不影響過去的百分位
    x2 = x.copy()
    x2.iloc[4] = -99
    assert th._expanding_pct(x2, 3).iloc[3] == p.iloc[3]


def test_zone_boundaries():
    assert th.zone(5)[0] == "極度悲觀"
    assert th.zone(10)[0] == "悲觀"
    assert th.zone(50)[0] == "中性"
    assert th.zone(70)[0] == "樂觀"
    assert th.zone(95)[0] == "極度樂觀"
    assert th.zone(np.nan)[0] == "資料不足"


def test_assign_day_window():
    days = [dt.date(2026, 11, 20), dt.date(2026, 11, 23)]  # 週五、下週一
    starts = [dt.datetime.combine(d, dt.time(8, 0)) for d in days]
    f = lambda s: assign_day(dt.datetime.fromisoformat(s), days, starts)  # noqa: E731
    assert f("2026-11-20 08:00") == days[0]
    assert f("2026-11-22 20:31") == days[0]  # 週末推文歸週五
    assert f("2026-11-23 08:15") == days[0]  # 下一交易日 08:30 前仍歸前一日
    assert f("2026-11-23 08:30") == days[1]
    assert f("2026-11-20 07:59") is None


def test_nrec_and_push_parsing():
    assert nrec_to_int("爆") == 100 and nrec_to_int("X3") == -30 and nrec_to_int("XX") == -100 and nrec_to_int("") == 0
    html = ('<div class="push"><span class="hl push-tag">推 </span><span class="f3 hl push-userid">someone</span>'
            '<span class="f3 push-content">: 噴啦 &amp; 歐印</span><span class="push-ipdatetime"> 01/02 09:05\n</span></div>')
    p = parse_pushes(html, dt.date(2025, 12, 31))
    assert p == [{"tag": "推", "text": "噴啦 & 歐印", "t": "2026-01-02 09:05"}]  # 跨年推文年份 +1
    assert "someone" not in str(p)  # 不保存帳號
