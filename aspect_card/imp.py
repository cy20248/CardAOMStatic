# ============================================================
# ImpCard: 場に出ると親サモナーを強化し、自分の司祭オーラを判定する。
#   司祭が場に居れば +1 atk（非スタック＝最初の1体で打ち切り）。
# ============================================================

from aspect.aspect_relation_rule import InjectionEventRule, ConditionRule
from aspect_card.card import CardAspect


class ImpCard(CardAspect):
    NEEDS = ("parent", ("priests", "priest"))

    def configure(self, ctx):
        self.aura_count = len(ctx["priests"])

    def rulesEI(self, ctx):
        return {"t_play": [InjectionEventRule(ctx["parent"], "trig_boost"),
                           InjectionEventRule(self, "trig_priest_aura")]}

    def rulesGR(self, ctx):
        gr = {"t_play": [ConditionRule(ctx["parent"], "OnBoard", True)]}
        for j, p in enumerate(ctx["priests"]):
            gr["t_priest_aura_%d" % j] = [ConditionRule(p, "OnBoard", True)]
        return gr

    def t_priest_aura(self):
        for j in range(self.aura_count):
            if self.checkGRRules("t_priest_aura_%d" % j):
                self.atk += 1
                break
