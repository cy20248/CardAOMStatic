# ============================================================
# SummonerCard: インプ生成は manager（実行層）が場への登場を観測して行う。
#   ここは「インプが場に出るたび +1/+1」の効果ハンドラのみ。
# ============================================================

from aspect_card.card import CardAspect


class SummonerCard(CardAspect):
    def t_boost(self):
        self.atk += 1
        self.hp += 1
