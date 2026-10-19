# ============================================================
# HeroAspect。
#   カードではないが盤上の「実体」なので、アスペクトとして扱う。
#   状態: Alive / Dead
#   関連: 攻撃(フェイス)が trig_damage#<量> を注入し、HP 0 以下で Dead になり
#         Flow へ（EI規則で）自陣の hero_dead を注入する（＝勝敗判定）。
# ============================================================

from aspect.aspect import Aspect


class HeroAspect(Aspect):
    HP0 = 12

    printer = None

    def __init__(self, name, owner):
        super().__init__()
        self.name = name
        self.owner = owner
        self.reset()

    def reset(self):
        self.hp = self.HP0
        self.state = "Alive"      # Alive -> Dead

    def log(self, msg):
        if self.printer:
            self.printer(msg)

    def run(self):
        while not self.messageQueue.empty():
            ev = self.messageQueue.get()
            if ev.startswith("trig_damage#"):
                self.trig_damage(int(ev.split("#", 1)[1]))
            elif ev == "trig_show":
                self.trig_show()

    def trig_damage(self, amount):
        if self.state == "Alive":
            self.t_damage(amount)
            return

    def t_damage(self, amount):
        self.hp -= amount
        if self.hp <= 0:
            self.hp = 0
            self.state = "Dead"
            self.checkEIRules("t_damage")     # -> Flow.trig_<side>_hero_dead

    def trig_show(self):
        self.log("%s HP %d" % (self.name, self.hp))
