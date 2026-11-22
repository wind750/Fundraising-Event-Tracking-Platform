"""PTT 股版情緒詞典 v1（2026-11-22 凍結；CT-20261122-03 以本檔首次提交版本為準，改詞典＝開新測試單）。

分四類，一則推文可以同時命中多類：
- BULL：看多、偏樂觀的說法
- BEAR：看空、偏悲觀的說法
- GREED：BULL 裡更極端、帶亢奮或重押的說法（貪婪）
- FEAR：BEAR 裡更極端、帶驚恐或認輸的說法（恐慌）

刻意不收的字：單字「多」「空」「套」「跑」「香」「賠」——太常出現在無關語境（套利、一套、香港…）。
"""

GREED = [
    "歐印", "all in", "allin", "梭哈", "財富自由", "賺爛", "賺爆", "賺翻", "發財", "噴爆", "飛天", "起飛",
    "無腦多", "買爆", "開槓桿", "上看", "噴到", "噴上", "噴出", "印鈔", "軋空", "嘎空", "財神", "暴富",
]
BULL = GREED + [
    "噴", "漲停", "漲爆", "大漲", "長紅", "紅k", "創高", "新高", "突破", "多軍", "多頭", "多單", "做多",
    "加碼", "上車", "抄底", "撿便宜", "撿到", "吃肉", "補漲", "止跌", "打底", "見底", "反彈", "回神",
    "紅通通", "滿江紅", "多方", "買進", "低接", "爽", "賺錢", "賺了", "穩了", "續漲", "攻擊", "強勢",
]
FEAR = [
    "斷頭", "追繳", "畢業", "救救", "救命", "跳樓", "天台", "頂樓", "完了", "末日", "股災", "血流成河",
    "血洗", "恐慌", "崩盤", "大崩", "爆崩", "跌停", "逃命", "離開股市", "哭啊", "沒救", "熔斷", "融斷",
    "黑天鵝", "砍倉", "斷頭潮", "要死", "慘賠", "賠爛", "虧爛", "賠光", "歸零",
]
BEAR = FEAR + [
    "崩", "暴跌", "大跌", "重挫", "綠油油", "綠k", "長黑", "破底", "破線", "跌破", "空軍", "空頭", "空單",
    "做空", "放空", "停損", "認賠", "套牢", "套房", "韭菜", "被割", "割肉", "下車", "快跑", "清倉",
    "出清", "賣光", "跳水", "慘", "哭", "續跌", "殺盤", "殺下去", "摜破", "賠錢", "虧錢", "凹單",
]

NEGATORS = ("不會", "不可能", "不要", "沒有", "不是", "別")


def _hits(text: str, words: list[str]) -> set[str]:
    out = set()
    for w in words:
        start = 0
        while True:
            i = text.find(w, start)
            if i < 0:
                break
            pre = text[max(0, i - 3):i]
            if not any(n in pre for n in NEGATORS):
                out.add(w)
                break
            start = i + 1
    return out


def classify(text: str) -> dict:
    """回傳一則推文的四類命中與最終傾向（bull / bear / none）。"""
    t = text.lower()
    bull, bear = _hits(t, BULL), _hits(t, BEAR)
    # 長詞已命中時，去掉被它包含的短詞，避免「漲停」又算一次「噴」這類重複不在此處發生；
    # 但「大崩」同時含「崩」——以長詞為準
    bull = {w for w in bull if not any(w != o and w in o for o in bull)}
    bear = {w for w in bear if not any(w != o and w in o for o in bear)}
    side = "bull" if len(bull) > len(bear) else "bear" if len(bear) > len(bull) else "none"
    return {
        "side": side,
        "greed": bool(_hits(t, GREED)),
        "fear": bool(_hits(t, FEAR)),
        "bull_words": bull,
        "bear_words": bear,
    }
