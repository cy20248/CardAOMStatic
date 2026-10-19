# ============================================================
# FlowAspect（静的AOM版・base流 / Boardなし）。
#   状態: Idle / PlayerTurn / EnemyTurn / Ended
#   他アスペクトを一切抱えない。協調は manager が配線した規則経由のみ:
#     - checkEIRules("t_play_<key>")  -> 対象ユニットへ trig_play
#     - checkEIRules("t_attack_a<i>_<t>") -> 攻撃側へ trig_attack#<t>
#     - checkGRRules(...)             -> 対象が Dormant/OnBoard か（相手の状態）
#   相手の名前・一覧・数値は持たない（自分の state/deck/hand/mana のみ）。
# ============================================================

import random

from aspect.aspect import Aspect


class FlowAspect(Aspect):
    UNIT_SLOTS = 4

    def __init__(self, deck_keys, card_meta):
        super().__init__()
        self.state = "Idle"
        self.turn = 0
        self.mana = 0
        self.maxMana = 3          # 初回 begin_player_turn で +1 され 4 になる
        self.printer = None
        self.deck_keys = deck_keys
        self.card_meta = card_meta    # key -> {cost, playable}（カードのデータ）
        self.deck = []
        self.hand = []

    def log(self, msg):
        if self.printer:
            self.printer(msg)

    def new_game(self):
        self.deck = list(self.deck_keys)
        random.shuffle(self.deck)
        self.hand = []

    def draw(self, n):
        for _ in range(n):
            if self.deck:
                self.hand.append(self.deck.pop(0))

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
        self.checkEIRules("t_begin_enemy")   # -> 各敵ユニットへ trig_begin_turn
        self.log("")
        self.log("===== 敵ターン =====")
        self.checkEIRules("t_enemy")         # -> AI.trig_ai

    def command(self, cmd):
        parts = cmd.split()
        if not parts:
            return
        op = parts[0]
        if op == "play" and len(parts) >= 2:
            self.play(parts[1])
        elif op == "attack" and len(parts) >= 3:
            self.attack(parts[1], parts[2])
        elif op == "state":
            self.show()
        elif op == "end":
            self.log("[ターン終了]")
            self.begin_enemy_turn()
        else:
            self.log("不明なコマンド: " + cmd)

    def meta_of(self, key):
        return self.card_meta.get(key)

    def can_play(self, i):
        if not (0 <= i < len(self.hand)):
            return False
        key = self.hand[i]
        meta = self.meta_of(key)
        if meta is None or not meta["playable"]:
            return False
        if meta["cost"] > self.mana:
            return False
        return self.checkGRRules("t_play_" + key)

    def play(self, arg):
        # 動的コレクション: 手札は番号で選ぶ。実体は規則が解決する。
        if not arg.isdigit():
            self.log("使い方: play <番号>（例: play 0）")
            return
        i = int(arg)
        if not (0 <= i < len(self.hand)):
            self.log("その番号は手札にありません")
            return
        key = self.hand[i]
        meta = self.meta_of(key)
        if meta is None or not meta["playable"]:
            self.log("出せません: " + key)
            return
        if meta["cost"] > self.mana:
            self.log("マナ不足: %s (コスト%d)" % (key, meta["cost"]))
            return
        if not self.checkGRRules("t_play_" + key):
            # GR が「そのユニットが Dormant か」を判定（相手の state を参照）。
            self.log("出せません（既に別の %s が場にいます）" % key)
            return
        self.mana -= meta["cost"]
        self.hand.pop(i)
        self.checkEIRules("t_play_" + key)     # -> 対象ユニットへ trig_play
        self.log("召喚: " + key)

    def attack(self, aslot, target):
        # 名前ではなくスロット指定（実体は規則が解決）。target: f か u<敵スロット>。
        if not aslot.isdigit() or not self.valid_target(target):
            self.log("使い方: attack <スロット> f|u<スロット>")
            return
        t = "t_attack_a%s_%s" % (aslot, target)
        if not self.checkGRRules(t):
            self.log("攻撃できません（攻撃側か相手が場にいません）")
            return
        self.checkEIRules(t)     # -> 攻撃側へ trig_attack#<target>

    def valid_target(self, target):
        if target == "f":
            return True
        return (target.startswith("u") and target[1:].isdigit()
                and int(target[1:]) < self.UNIT_SLOTS)

    def show(self):
        def cost_of(key):
            m = self.meta_of(key)
            return m["cost"] if m else 0
        hand_body = ", ".join("%d:%s(%d)" % (i, k, cost_of(k))
                              for i, k in enumerate(self.hand))
        self.log("手札: %s" % (hand_body or "なし"))
        self.log("デッキ残り: %d" % len(self.deck))
        self.log("コマンド: play <番号> / attack <スロット> f|u<敵スロット> / state / end")
        # 盤面は各アスペクトが自分で申告する（broadcast）。
        self.checkEIRules("t_show")
