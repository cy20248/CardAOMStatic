# ============================================================
# AIAspect（静的AOM版・base流 / Boardなし）。
#   他アスペクトを一切抱えない。協調は manager が配線した規則経由のみ。
#   固定順で札を出し、攻撃対象は「相手スロット0、居なければフェイス」。
#   相手の名前・一覧・数値は持たない（自分の state/deck/hand のみ）。
# ============================================================

import random

from aspect.aspect import Aspect


class AIAspect(Aspect):
    UNIT_SLOTS = 4

    def __init__(self, deck_keys, card_meta):
        super().__init__()
        self.state = "Idle"
        self.eMana = 0
        self.turn = 0
        self.printer = None
        self.deck_keys = deck_keys
        self.card_meta = card_meta     # key -> {cost, playable}
        self.deck = []
        self.hand = []

    def new_game(self):
        self.deck = list(self.deck_keys)
        random.shuffle(self.deck)
        self.hand = []

    def draw(self, n):
        for _ in range(n):
            if self.deck:
                self.hand.append(self.deck.pop(0))

    def log(self, msg):
        if self.printer:
            self.printer(msg)

    def run(self):
        while not self.messageQueue.empty():
            ev = self.messageQueue.get()
            if ev == "trig_ai":
                self.t_act()

    def t_act(self):
        if self.state == "Idle":
            if self.checkGRRules("t_act"):
                self.act()
                self.checkEIRules("t_act")      # -> Flow.trig_end_enemy

    def can_play(self, key):
        meta = self.card_meta.get(key)
        if meta is None or not meta["playable"]:
            return False
        if meta["cost"] > self.eMana:
            return False
        return self.checkGRRules("t_play_" + key)

    def act(self):
        self.turn += 1
        self.eMana = min(7, self.eMana + 1)
        self.draw(3 if self.turn == 1 else 1)
        for key in list(self.hand):
            if self.can_play(key):
                self.eMana -= self.card_meta[key]["cost"]
                self.hand.remove(key)
                self.checkEIRules("t_play_" + key)   # -> 敵ユニットへ trig_play
                self.log("[敵召喚] " + key)
        for i in range(self.UNIT_SLOTS):
            # 対象は「相手スロット0が場にいれば u0、いなければ f」（先頭固定）。
            if self.checkGRRules("t_attack_a%d_u0" % i):
                self.checkEIRules("t_attack_a%d_u0" % i)
            elif self.checkGRRules("t_attack_a%d_f" % i):
                self.checkEIRules("t_attack_a%d_f" % i)
