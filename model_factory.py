# ============================================================
# カード実体の生成（ID採番・デッキ＋付随カード・スロット番号）。
#   規則もライフサイクルも持たない。manager から呼ばれるだけ。
# ============================================================

from aspect_card import CARD_DEFS


PLAYER_DECK = ["summoner", "priest", "summoner", "priest", "summoner", "priest"]
ENEMY_DECK = ["priest", "summoner", "priest", "summoner", "priest", "summoner"]


class CardFactory:
    def __init__(self, printer=None):
        self.printer = printer
        self.cid = 0

    def new_card(self, key, owner, name, initial):
        d = CARD_DEFS[key]
        c = d["cls"](self.cid, name, key, owner, d["meta"], initial)
        self.cid += 1
        if self.printer:
            c.printer = self.printer
        return c

    def build_side(self, owner, deck_keys, prefix):
        # デッキ（カード実体）。registry の spawns 指定に従い、付随カードを生成する。
        deck_cards = [self.new_card(k, owner, "%s_%s%d" % (prefix, k, i), "Deck")
                      for i, k in enumerate(deck_keys)]
        children = {}
        parents = {}
        spawned = []
        for c in deck_cards:
            spec = CARD_DEFS[c.key].get("spawns")
            if not spec:
                continue
            ckey, n = spec
            kids = [self.new_card(ckey, owner,
                                  "%s_%s_of%d_%d" % (prefix, ckey, c.id, t),
                                  "Dormant")
                    for t in range(n)]
            children[c] = kids
            for kid in kids:
                parents[kid] = c
            spawned += kids
        roster = deck_cards + spawned
        for i, c in enumerate(roster):
            c.slot = i
        return deck_cards, roster, children, parents
