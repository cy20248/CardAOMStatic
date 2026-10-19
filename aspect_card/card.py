# ============================================================
# カードの基底アスペクト（静的AOM版・base流）。
#   状態機械・戦闘・イベント配送（全カード共通）のみを持つ。
#   種別ごとの挙動は、サブクラスが組む規則（EI/GR）と効果ハンドラで表現する。
#   状態: Deck / Hand / OnBoard / Dead  （インプは Dormant から OnBoard）
# ============================================================

from aspect.aspect import Aspect


class CardAspect(Aspect):
    # 規則ビルダが要求する文脈キー（manager が解決して ctx で渡す）。
    #   文字列 = 関係("parent"/"children") / (ctxキー, カードkey) = 同陣営の該当カード群
    NEEDS = ()

    # 戦闘の相手参照（manager が生成時に注入）。既定は持たない。
    opp_hero = None
    opp_units = None
    # 司祭オーラの判定数（manager が configure で注入）。
    aura_count = 0

    def __init__(self, cid, name, key, owner, meta, initial):
        super().__init__()
        self.id = cid
        self.name = name
        self.key = key
        self.owner = owner
        self.cost = meta["cost"]
        self.playable = meta["playable"]
        self.base_atk = meta["atk"]
        self.base_hp = meta["hp"]
        self.initial_state = initial
        self.printer = None
        self.reset()

    def reset(self):
        self.state = self.initial_state
        self.atk = self.base_atk
        self.hp = self.base_hp
        self.can_attack = False

    def log(self, msg):
        if self.printer:
            self.printer(msg)

    # --- 規則ビルダ（サブクラスが上書き） -------------------------
    def rulesEI(self, ctx):
        return {}

    def rulesGR(self, ctx):
        return {}

    def configure(self, ctx):
        pass

    # --- イベント配送（共通） -------------------------------------
    def run(self):
        while not self.messageQueue.empty():
            ev = self.messageQueue.get()
            if ev == "trig_play":
                self.trig_play()
            elif ev == "trig_boost":
                self.t_boost()
            elif ev == "trig_priest_aura":
                self.t_priest_aura()
            elif ev == "trig_begin_turn":
                self.t_begin_turn()
            elif ev.startswith("trig_attack#"):
                self.trig_attack(ev.split("#", 1)[1])
            elif ev.startswith("trig_damage#"):
                self.trig_damage(int(ev.split("#", 1)[1]))
            elif ev == "trig_show":
                self.trig_show()

    # --- 場に出る（共通） -----------------------------------------
    def trig_play(self):
        if self.state in ("OnBoard", "Dead"):
            return
        if not self.checkGRRules("t_play"):
            return
        self.t_play()

    def t_play(self):
        self.state = "OnBoard"
        self.atk = self.base_atk
        self.hp = self.base_hp
        self.can_attack = False
        self.checkEIRules("t_play")      # -> 種別ごとの効果（規則で配線）

    def t_begin_turn(self):
        if self.state == "OnBoard":
            self.can_attack = True

    # --- 戦闘（共通） ---------------------------------------------
    def trig_attack(self, target):
        if self.state != "OnBoard" or not self.can_attack:
            return
        self.can_attack = False          # 攻撃は1ターン1回
        if target == "f":
            if self.opp_hero is not None:
                self.opp_hero.messageQueue.put("trig_damage#%d" % self.atk)
            return
        j = int(target[1:])
        if self.opp_units is None or j >= len(self.opp_units):
            return
        foe = self.opp_units[j]
        foe.messageQueue.put("trig_damage#%d" % self.atk)
        self.messageQueue.put("trig_damage#%d" % foe.atk)   # 相互ダメージ

    def trig_damage(self, amount):
        if self.state != "OnBoard":
            return
        self.hp -= amount
        if self.hp <= 0:
            self.hp = 0
            self.state = "Dead"

    # --- 表示（自己申告・共通） -----------------------------------
    def trig_show(self):
        if self.state == "OnBoard":
            mark = " *" if self.can_attack else ""
            self.log("  [%s] %s %d/%d%s"
                     % (self.owner, self.name, self.atk, self.hp, mark))
        elif self.state == "Dead":
            self.log("  [%s] %s (死亡)" % (self.owner, self.name))
