# ============================================================
# FlowAspect（静的AOM版・base流 / カード＝実体）。
#   状態: Idle / PlayerTurn / EnemyTurn / Ended
#   自分のデッキ＝CardAspect 実体のリスト（Hand/Deck はカードの state が真実）。
#   他アスペクト（相手側）は一切抱えない。協調は manager が配線した規則経由のみ:
#     - checkEIRules("t_play_c<id>") -> そのカード実体へ trig_play
#     - checkEIRules("t_attack_a<i>_<t>") -> 自ロスター i 番目へ trig_attack#<t>
#     - checkGRRules(...) -> 対象（手札のカード／攻撃側・相手）の state 参照
# ============================================================

import random

from aspect.aspect import Aspect


class FlowAspect(Aspect):
    def __init__(self, deck_cards, roster):
        super().__init__()
        self.state = "Idle"
        self.turn = 0
        self.mana = 0
        self.maxMana = 3
        self.printer = None
        self.deck_cards = deck_cards   # 自分のデッキ（CardAspect 実体）
        self.roster = roster           # 自分の全カード（デッキ＋インプ）
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
        drawn = []
        for _ in range(n):
            if self.deck:
                c = self.deck.pop(0)
                c.messageQueue.put("trig_draw")
                self.hand.append(c)
                drawn.append(c)
        return drawn

    def run(self):
        while not self.messageQueue.empty():
            ev = self.messageQueue.get()
            if ev == "trig_start":
                self.t_start()
            elif ev.startswith("trig_command#"):
                self.t_command(ev.split("#", 1)[1])
            elif ev == "trig_end_enemy":
                self.t_begin_player()
            elif ev == "trig_enemy_hero_dead":
                self.t_win()
            elif ev == "trig_player_hero_dead":
                self.t_lose()

    def t_start(self):
        if self.state == "Idle":
            if self.checkGRRules("t_start"):
                self.checkEIRules("t_start")
                self.begin_player_turn()

    def t_command(self, cmd):
        if self.state == "PlayerTurn":
            if self.checkGRRules("t_command"):
                self.checkEIRules("t_command")
                self.command(cmd)

    def t_begin_player(self):
        if self.state == "EnemyTurn":
            if self.checkGRRules("t_begin_player"):
                self.checkEIRules("t_begin_player")
                self.begin_player_turn()

    def t_win(self):
        self.state = "Ended"
        self.log("")
        self.log("あなたの勝利！")

    def t_lose(self):
        self.state = "Ended"
        self.log("")
        self.log("あなたの敗北…")

    def begin_player_turn(self):
        if self.state == "Ended":
            return
        self.state = "PlayerTurn"
        self.turn += 1
        self.maxMana = min(7, self.maxMana + 1)
        self.mana = self.maxMana
        self.draw(3 if self.turn == 1 else 1)
        self.log("")
        self.log("===== ターン %d / マナ %d =====" % (self.turn, self.mana))
        self.show()

    def begin_enemy_turn(self):
        if self.state == "Ended":
            return
        self.state = "EnemyTurn"
        self.checkEIRules("t_begin_enemy")
        self.log("")
        self.log("===== 敵ターン =====")
        self.checkEIRules("t_enemy")

    def command(self, cmd):
        parts = cmd.split()
        if not parts:
            return
        op = parts[0]
        if op == "play" and len(parts) >= 2 and parts[1].isdigit():
            self.play(int(parts[1]))
        elif op == "attack" and len(parts) >= 3:
            self.attack(parts[1], parts[2])
        elif op == "state":
            self.show()
        elif op == "end":
            self.log("[ターン終了]")
            self.begin_enemy_turn()
        else:
            self.log("不明なコマンド: " + cmd)

    def can_play(self, i):
        if not (0 <= i < len(self.hand)):
            return False
        c = self.hand[i]
        if not c.playable or c.cost > self.mana:
            return False
        t = "t_play_c%d" % c.id
        if t not in self.classRulesGR:
            return False
        return self.checkGRRules(t)

    def play(self, i):
        # 手札を番号で選ぶ。実体は規則（t_play_c<id>）が解決する。
        if not (0 <= i < len(self.hand)):
            self.log("使い方: play <手札番号>")
            return
        c = self.hand[i]
        if not c.playable:
            self.log("出せません: " + c.name)
            return
        if c.cost > self.mana:
            self.log("マナ不足: %s (コスト%d)" % (c.name, c.cost))
            return
        t = "t_play_c%d" % c.id
        if t not in self.classRulesGR or not self.checkGRRules(t):
            self.log("出せません（場の状態が不正）: " + c.name)
            return
        self.mana -= c.cost
        self.hand.pop(i)
        self.checkEIRules(t)
        self.log("召喚: " + c.name)

    def attack(self, aslot, target):
        if not aslot.isdigit():
            self.log("使い方: attack <スロット> f|u<敵スロット>")
            return
        t = "t_attack_a%s_%s" % (aslot, target)
        if t not in self.classRulesGR:
            self.log("使い方: attack <スロット> f|u<敵スロット>")
            return
        if not self.checkGRRules(t):
            self.log("攻撃できません（攻撃側か相手が場にいません）")
            return
        self.checkEIRules(t)

    def show(self):
        hand_body = ", ".join("%d:%s(%d)" % (i, c.name, c.cost)
                              for i, c in enumerate(self.hand))
        self.log("手札: %s" % (hand_body or "なし"))
        self.log("デッキ残り: %d" % len(self.deck))
        self.log("コマンド: play <番号> / attack <スロット> f|u<敵スロット> / state / end")
        self.checkEIRules("t_show")
