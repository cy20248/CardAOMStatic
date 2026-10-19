# ============================================================
# カード registry: key -> {cls, meta, spawns?}。
#   spawns = (生成するカードkey, 枚数): デッキ外で、このカードに付随して生成される。
#   新しいカードは「サブクラス1個 + この辞書に1行」で足せる。
# ============================================================

from aspect_card.summoner import SummonerCard
from aspect_card.imp import ImpCard
from aspect_card.priest import PriestCard


CARD_DEFS = {
    "summoner": {"cls": SummonerCard, "spawns": ("imp", 2),
                 "meta": {"cost": 2, "playable": True, "atk": 2, "hp": 2}},
    "priest": {"cls": PriestCard,
               "meta": {"cost": 2, "playable": True, "atk": 1, "hp": 3}},
    "imp": {"cls": ImpCard,
            "meta": {"cost": 1, "playable": False, "atk": 1, "hp": 1}},
}
