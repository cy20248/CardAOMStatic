# ============================================================
# SummonerCard: 場に出ると自分のインプを起動する。インプが場に出るたび +1/+1。
# ============================================================

from aspect.aspect_relation_rule import InjectionEventRule
from aspect_card.card import CardAspect


class SummonerCard(CardAspect):
    NEEDS = ("children",)

    def rulesEI(self, ctx):
        # 場に出たら、自分のインプを起動する。
        return {"t_play": [InjectionEventRule(im, "trig_play")
                           for im in ctx["children"]]}

    def t_boost(self):
        # インプが場に出るたび +1/+1。
        self.atk += 1
        self.hp += 1
