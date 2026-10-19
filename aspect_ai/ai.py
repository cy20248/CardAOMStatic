# ============================================================
# AIAspect（静的AOM版・base流 / カード＝実体）。
#   他アスペクト（相手側）を一切抱えない。協調は manager が配線した規則経由のみ。
#   固定順で手札を出し、攻撃は「相手ロスター先頭(u0)が場にいれば u0、いなければ f」。
# ============================================================

import random

from aspect.aspect import Aspect


class AIAspect(Aspect):
    def __init__(self, deck_cards, roster):
        super().__init__()
        self.state = "Idle"
        self.turn = 0
        self.eMana = 0
        self.printer = None
        self.deck_cards = deck_cards
        self.roster = roster
        self.deck = []
        self.hand = []

    def log(self, msg):
        if self.printer:
            self.printer(msg)

    def new_game(self):
        self.deck = list(self.deck_cards)
        random.shuffle(self.deck)
        self.hand = []

    def draw(self, n):
        for _ in range(n):
            if self.deck:
                c = self.deck.pop(0)
                c.state = "Hand"
                self.hand.append(c)

    def run(self):
        while not self.messageQueue.empty():
            ev = self.messageQueue.get()
            if ev == "trig_ai":
                self.t_act()

    def t_act(self):
        if self.state == "Idle":
            if self.checkGRRules("t_act"):
                self.act()
                self.checkEIRules("t_act")   # -> Flow.trig_end_enemy

    def can_play(self, card):
        if not card.playable:
            return False
        if card.cost > self.eMana:
            return False
        t = "t_play_c%d" % card.id
        if t not in self.classRulesGR:
            return False
        return self.checkGRRules(t)

    def act(self):
        self.turn += 1
        self.eMana = min(7, self.eMana + 1)
        self.draw(3 if self.turn == 1 else 1)
        i = 0
        while i < len(self.hand):
            c = self.hand[i]
            if self.can_play(c):
                self.eMana -= c.cost
                self.hand.pop(i)
                self.checkEIRules("t_play_c%d" % c.id)
                self.log("[敵召喚] " + c.name)
            else:
                i += 1
        for idx in range(len(self.roster)):
            tu = "t_attack_a%d_u0" % idx
            tf = "t_attack_a%d_f" % idx
            if tu in self.classRulesGR and self.checkGRRules(tu):
                self.checkEIRules(tu)
            elif tf in self.classRulesGR and self.checkGRRules(tf):
                self.checkEIRules(tf)
