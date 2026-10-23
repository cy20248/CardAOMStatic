# ============================================================
# AspectModelManager（静的AOM版・base流 / Boardなし / カード＝盤上ユニット統一）。
#   役割は「実体の生成・規則の配線・実行ループ・寿命」の統括。
#   規則（EI/GR）はこの manager が持ち、実体生成だけ model_factory に分ける。
#   aspect 同士は相互参照を持たず、協調は次の2つだけで行う:
#     - checkEIRules(遷移) -> 規則（宛先参照は規則オブジェクト側が保持）
#     - checkGRRules(遷移) -> 規則（相手の state を参照）
#   例外は戦闘の“動的なダメージ量×相手参照”。量は actor しか知らないので、
#   manager が各カードに相手参照(opp_hero/opp_units)だけを注入する。
#   カード種別は CARD_DEFS(registry) で定義。規則（EI/GR）は manager 側に置き、
#   アスペクトは状態機械と効果ハンドラのみを持つ（base流の分離）。
#   initInstances -> initRules -> start（reset + new_game + settle）。
# ============================================================

from aspect.aspect_relation_rule import InjectionEventRule, ConditionRule
from aspect_flow.flow import FlowAspect
from aspect_ai.ai import AIAspect
from aspect_card import CARD_DEFS
from aspect_hero.hero import HeroAspect

from model_factory import CardFactory, PLAYER_DECK, ENEMY_DECK


# カード種別が規則を組むのに必要な文脈（関係）の宣言。manager が解決する。
#   文字列 = 関係("parent"/"children") / (ctxキー, カードkey) = 同陣営の該当カード群
CARD_NEEDS = {
    "summoner": ("children",),
    "imp": ("parent", ("priests", "priest")),
}


class AspectModelManager:
    def __init__(self, printer=None):
        self.printer = printer
        self._reset_model()

    def _reset_model(self):
        # モデルを丸ごと作り直す（new_game もこれを使う）。
        self.factory = CardFactory(self.printer)
        self._children = {}   # 親カード -> [生成した子カード]
        self._parent = {}     # 子カード -> 親カード
        self._spawned_cards = set()   # spawns を実行済みのカード（1体につき1回）
        self.initInstances()
        self.initRules()

    # --- 実体の生成 -------------------------------------------------
    def initInstances(self):
        self.p_deck, self.player_roster = self.factory.build_side(
            "player", PLAYER_DECK, "P")
        self.e_deck, self.enemy_roster = self.factory.build_side(
            "enemy", ENEMY_DECK, "E")

        self.p_hero = HeroAspect("P_Hero", "player")
        self.e_hero = HeroAspect("E_Hero", "enemy")
        for h in (self.p_hero, self.e_hero):
            if self.printer:
                h.printer = self.printer

        # 戦闘のみ“相手の実体”への最小参照を注入（ダメージ量は actor が持つ）。
        for c in self.player_roster:
            c.opp_hero = self.e_hero
            c.opp_units = self.enemy_roster
        for c in self.enemy_roster:
            c.opp_hero = self.p_hero
            c.opp_units = self.player_roster

        # flow/ai は相手側を抱えない（自分のデッキ実体＋ロスターのみ）。
        self.flow = FlowAspect(self.p_deck, self.player_roster)
        self.flow.printer = self.printer
        self.ai = AIAspect(self.e_deck, self.enemy_roster)
        self.ai.printer = self.printer

        self.aspects = ([self.flow, self.ai] + self.player_roster
                        + self.enemy_roster + [self.p_hero, self.e_hero])

    # --- 規則の配線（manager がルール置き場） -------------------------
    def _wire_actor(self, actor, roster, opp_roster):
        # 召喚: 手札のカード実体 id ごとに遷移を列挙（条件はそのカードが Hand）。
        ei = {}
        gr = {}
        for c in actor.deck_cards:
            if c.state == "Dead":
                continue
            t = "t_play_c%d" % c.id
            ei[t] = [InjectionEventRule(c, "trig_play")]
            gr[t] = [ConditionRule(c, "Hand", True)]
        # 攻撃: (自ロスター添字, 対象) を全て静的列挙。対象は f か u<敵添字>。
        #   穴（None）は攻撃側にも対象にもしない（埋まった時点で再配線される）。
        for i, a in enumerate(roster):
            if a is None:
                continue
            tgts = ["f"] + ["u%d" % j for j, x in enumerate(opp_roster)
                            if x is not None]
            for tgt in tgts:
                t = "t_attack_a%d_%s" % (i, tgt)
                ei[t] = [InjectionEventRule(a, "trig_attack#" + tgt)]
                conds = [ConditionRule(a, "OnBoard", True)]
                if tgt.startswith("u"):
                    conds.append(
                        ConditionRule(opp_roster[int(tgt[1:])],
                                      "OnBoard", True))
                gr[t] = conds
        return ei, gr

    def _flowRules(self):
        ei, gr = self._wire_actor(
            self.flow, self.player_roster, self.enemy_roster)
        # ターン開始の一斉配信（base流ブロードキャスト＝静的列挙）。
        ei["t_begin_player"] = [
            InjectionEventRule(c, "trig_begin_turn")
            for c in self.player_roster if c is not None]
        ei["t_begin_enemy"] = [
            InjectionEventRule(c, "trig_begin_turn")
            for c in self.enemy_roster if c is not None]
        ei["t_enemy"] = [InjectionEventRule(self.ai, "trig_ai")]
        # 表示は broadcast -> 各カード／英雄が自分の行を出す（自己申告）。
        ei["t_show"] = [
            InjectionEventRule(x, "trig_show")
            for x in self.player_roster + self.enemy_roster
            + [self.p_hero, self.e_hero] if x is not None]
        return ei, gr

    def _aiRules(self):
        ei, gr = self._wire_actor(
            self.ai, self.enemy_roster, self.player_roster)
        # 敵ターン終了を flow へ。
        ei["t_act"] = [InjectionEventRule(self.flow, "trig_end_enemy")]
        return ei, gr

    def _context(self, card, roster):
        # 種別が宣言した NEEDS を解決して文脈辞書を作る。
        ctx = {}
        for need in CARD_NEEDS.get(card.key, ()):
            if isinstance(need, tuple):
                key, ckey = need
                ctx[key] = [c for c in roster if c is not None and c.key == ckey]
            elif need == "children":
                ctx["children"] = self._children.get(card, [])
            elif need == "parent":
                ctx["parent"] = self._parent.get(card)
        return ctx

    # --- カード種別の規則（base流：manager が組む） -------------------
    def _summonerRulesEI(self, card, ctx):
        return {"t_play": [InjectionEventRule(im, "trig_play")
                           for im in ctx["children"]]}

    def _summonerRulesGR(self, card, ctx):
        return {}

    def _impRulesEI(self, card, ctx):
        return {"t_play": [InjectionEventRule(ctx["parent"], "trig_boost"),
                           InjectionEventRule(card, "trig_priest_aura")]}

    def _impRulesGR(self, card, ctx):
        gr = {"t_play": [ConditionRule(ctx["parent"], "OnBoard", True)]}
        for j, p in enumerate(ctx["priests"]):
            gr["t_priest_aura_%d" % j] = [ConditionRule(p, "OnBoard", True)]
        return gr

    def _priestRulesEI(self, card, ctx):
        return {}

    def _priestRulesGR(self, card, ctx):
        return {}

    def _wire_one_card(self, c, roster):
        # 1枚ぶんの種別規則を組む。
        ctx = self._context(c, roster)
        if c.key == "summoner":
            c.classRulesEI = self._summonerRulesEI(c, ctx)
            c.classRulesGR = self._summonerRulesGR(c, ctx)
        elif c.key == "imp":
            if ctx.get("parent") is None:
                c.classRulesEI = {}
                c.classRulesGR = {}
                return
            c.aura_count = len(ctx["priests"])
            c.classRulesEI = self._impRulesEI(c, ctx)
            c.classRulesGR = self._impRulesGR(c, ctx)
        elif c.key == "priest":
            c.classRulesEI = self._priestRulesEI(c, ctx)
            c.classRulesGR = self._priestRulesGR(c, ctx)

    def _wire_cards(self, roster):
        # 規則は manager が組む（アスペクトは状態機械と効果ハンドラのみ）。
        for c in roster:
            if c is not None:
                self._wire_one_card(c, roster)

    def _wire_heroes(self):
        # 英雄: HP0 で Dead になったら flow へ（勝敗は flow が判断）。
        self.p_hero.classRulesEI = {
            "t_damage": [InjectionEventRule(self.flow, "trig_player_hero_dead")]}
        self.p_hero.classRulesGR = {}
        self.e_hero.classRulesEI = {
            "t_damage": [InjectionEventRule(self.flow, "trig_enemy_hero_dead")]}
        self.e_hero.classRulesGR = {}

    def _rewire(self):
        # 初期配線・生成・死亡のすべてが通る唯一の経路（差分実装を持たない）。
        self.flow.classRulesEI, self.flow.classRulesGR = self._flowRules()
        self.ai.classRulesEI, self.ai.classRulesGR = self._aiRules()
        self._wire_cards(self.player_roster)
        self._wire_cards(self.enemy_roster)
        self._wire_heroes()

    def initRules(self):
        self._rewire()

    # --- ライフサイクル ---------------------------------------------
    def start(self):
        # 動的生成を含む前回のモデルを捨て、実体・規則を作り直す。
        self._reset_model()
        self.flow.new_game()
        self.ai.new_game()
        self.flow.messageQueue.put("trig_start")
        self.settle()

    def inject_command(self, cmd):
        self.flow.messageQueue.put("trig_command#" + cmd)

    def is_ended(self):
        return self.flow.state == "Ended"

    def settle(self):
        while True:
            active = [a for a in self.aspects if not a.messageQueue.empty()]
            if active:
                for a in active:
                    a.run()
                continue
            if not self._auto_spawns():
                break
        self._reap()

    # --- 動的生成 ---------------------------------------------------
    def _roster(self, owner):
        return self.player_roster if owner == "player" else self.enemy_roster

    def spawn_card(self, owner, parent, key="imp", initial="Dormant", name=None):
        # 実行時にカードを1体生成し、即時束縛で配線する。
        #   イベントは発火しないので、呼び出し側が必要なら
        #   trig_play を注入して settle する。
        if parent is None:
            raise ValueError("生成カードには parent（親実体）が必要です")
        self._reap()
        if name is None:
            prefix = "P" if owner == "player" else "E"
            name = "%s_%s_dyn%d" % (prefix, key, self.factory.cid)
        card = self.factory.new_card(key, owner, name, initial)

        # 死んだスロット（None）を再利用し、無ければ末尾に追加する（添字は詰めない）。
        roster = self._roster(owner)
        if None in roster:
            i_new = roster.index(None)
            roster[i_new] = card
        else:
            i_new = len(roster)
            roster.append(card)
        card.slot = i_new

        # 戦闘の相手参照（既存カードと同じ最小参照）。
        if owner == "player":
            card.opp_hero = self.e_hero
            card.opp_units = self.enemy_roster
        else:
            card.opp_hero = self.p_hero
            card.opp_units = self.player_roster

        # 関係（親子）を登録し、規則は初期配線と同じ経路で丸ごと再導出する。
        self._parent[card] = parent
        self._children.setdefault(parent, []).append(card)
        self._rewire()

        self.aspects.append(card)
        return card

    def spawn_imp(self, owner, parent, initial="Dormant", name=None):
        return self.spawn_card(owner, parent, "imp", initial, name)

    def _auto_spawns(self):
        # 反応バッチが落ち着いた時点で、場に出たカードの spawns 指定を実行する。
        #   生成はモデルの外（実行層）の仕事。カードは要求を持たない。
        spawned = False
        for roster in (self.player_roster, self.enemy_roster):
            for c in list(roster):
                if c is None or c.state != "OnBoard":
                    continue
                if c in self._spawned_cards:
                    continue
                spec = CARD_DEFS[c.key].get("spawns")
                if not spec:
                    continue
                self._spawned_cards.add(c)
                ckey, n = spec
                for _ in range(n):
                    card = self.spawn_card(c.owner, c, ckey)
                    card.messageQueue.put("trig_play")
                    spawned = True
        return spawned

    # --- 寿命 -------------------------------------------------------
    def _reap(self):
        # 死亡したカードを盤面から外す。添字は詰めず、穴（None）として再利用する。
        changed = False
        for roster in (self.player_roster, self.enemy_roster):
            for i, c in enumerate(roster):
                if c is not None and c.state == "Dead":
                    roster[i] = None
                    if c in self.aspects:
                        self.aspects.remove(c)
                    self._detach_links(c)
                    self._spawned_cards.discard(c)
                    changed = True
        if changed:
            self._rewire()

    def _detach_links(self, card):
        # 関係だけ外す。規則は _rewire が現状から作り直す（差分実装を持たない）。
        parent = self._parent.pop(card, None)
        if parent is not None:
            kids = self._children.get(parent)
            if kids and card in kids:
                kids.remove(card)
        # 死んだ親の子は _parent を残す（OnBoard 条件が false になり安全）。
        self._children.pop(card, None)
        card.classRulesEI = {}
        card.classRulesGR = {}
