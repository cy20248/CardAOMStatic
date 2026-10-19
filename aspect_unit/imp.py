# ============================================================
# インプ。
#   サモナーの効果で「起動」される専用（手札からは出せない＝playable False）。
#   起動時: 生成主(サモナー)を +1/+1 する。
#   さらに「司祭が場にいるなら +1/+0」を、GR 条件 ConditionRule(priest,"OnBoard")
#   ＋ 自分への EI で表す（相手の状態を参照するだけ＝実体も名前も解決しない）。
#   状態: Dormant -> OnBoard -> Dead
#   他のアスペクト参照: 戦闘の相手(opp_hero/opp_units)のみ manager から注入。
# ============================================================

from aspect.aspect import Aspect


class ImpAspect(Aspect):
    playable = False
    cost = 1
    atk0 = 1
    hp0 = 1

    printer = None
    opp_hero = None
    opp_units = None

    def __init__(self, name, owner):
        super().__init__()
        self.name = name
        self.owner = owner
        self.reset()

    def reset(self):
        self.atk = self.atk0
        self.hp = self.hp0
        self.can_attack = False
        self.state = "Dormant"

    def log(self, msg):
        if self.printer:
            self.printer(msg)

    def run(self):
        while not self.messageQueue.empty():
            ev = self.messageQueue.get()
            if ev == "trig_play":
                self.t_play()
            elif ev == "trig_boost":
                self.on_boost()
            elif ev == "trig_begin_turn":
                self.on_begin_turn()
            elif ev.startswith("trig_damage#"):
                self.trig_damage(int(ev.split("#", 1)[1]))
            elif ev == "trig_priest_aura":
                self.trig_priest_aura()
            elif ev.startswith("trig_attack#"):
                self.trig_attack(ev.split("#", 1)[1])
            elif ev == "trig_show":
                self.trig_show()

    def t_play(self):
        if self.state != "Dormant":
            return
        if self.checkGRRules("t_play"):
            self.state = "OnBoard"
            self.checkEIRules("t_play")

    def on_boost(self):
        self.atk += 1
        self.hp += 1

    def on_begin_turn(self):
        if self.state == "OnBoard":
            self.can_attack = True

    def trig_priest_aura(self):
        if self.state == "OnBoard":
            self.t_priest_aura()
            return

    def t_priest_aura(self):
        # 司祭が場にいるか（GR）だけを見て +1/+0。相手を解決しない。
        if self.checkGRRules("t_priest_aura"):
            self.atk += 1

    def trig_damage(self, amount):
        if self.state != "Dead":
            self.t_damage(amount)
            return

    def t_damage(self, amount):
        self.hp -= amount
        if self.hp <= 0:
            self.hp = 0
            self.state = "Dead"

    # 戦闘: 相手参照(opp_hero/opp_units)は manager が注入（動的ダメージ量のため）。
    def trig_attack(self, spec):
        if self.state != "OnBoard" or not self.can_attack:
            self.log("攻撃できません: " + self.name)
            return
        self.t_attack(spec)

    def t_attack(self, spec):
        if spec == "f":
            if self.opp_hero is None:
                return
            self.can_attack = False
            self.opp_hero.messageQueue.put("trig_damage#%d" % self.atk)
            self.log("[攻撃] %s → 相手ヒーロー" % self.name)
            return
        if spec.startswith("u"):
            j = int(spec[1:])
            if self.opp_units is None or not (0 <= j < len(self.opp_units)):
                return
            d = self.opp_units[j]
            if d is None or d.state != "OnBoard":
                return
            self.can_attack = False
            d.messageQueue.put("trig_damage#%d" % self.atk)
            self.messageQueue.put("trig_damage#%d" % d.atk)
            self.log("[攻撃] %s → %s" % (self.name, d.name))

    def trig_show(self):
        if self.state == "OnBoard":
            self.log("%s(%d/%d)" % (self.name, self.atk, self.hp))
