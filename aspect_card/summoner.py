# ============================================================
# SummonerCard: インプを起動する効果は manager が配線する。
#   ここは「インプが場に出るたび +1/+1」の効果ハンドラのみ。
# ============================================================

from aspect_card.card import CardAspect


class SummonerCard(CardAspect):
    def t_boost(self):
        self.atk += 1
        self.hp += 1
