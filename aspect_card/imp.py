# ============================================================
# ImpCard: 親サモナー強化・司祭オーラ判定の配線は manager が行う。
#   ここは「司祭が場に居れば +1 atk（非スタック＝最初の1体で打ち切り）」の
#   効果ハンドラのみ。
# ============================================================

from aspect_card.card import CardAspect


class ImpCard(CardAspect):
    def t_priest_aura(self):
        for j in range(self.aura_count):
            if self.checkGRRules("t_priest_aura_%d" % j):
                self.atk += 1
                break
