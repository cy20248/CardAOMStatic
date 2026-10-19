# ============================================================
# AspectModelManager（静的AOM版・base流 / Boardなし / カード＝盤上ユニット統一）。
#   マネージャ自身が全カード実体を生成し、規則を“直接参照”で配線する。
#   aspect 同士は相互参照を持たず、協調は次の2つだけで行う:
#     - checkEIRules(遷移) -> 規則（宛先参照は規則オブジェクト側が保持）
#     - checkGRRules(遷移) -> 規則（相手の state を参照）
#   例外は戦闘の“動的なダメージ量×相手参照”。量は actor しか知らないので、
#   manager が各カードに相手参照(opp_hero/opp_units)だけを注入する。
#   カード種別は CARD_DEFS(registry) で定義。manager は registry を回して
#   実体生成・規則配線するので、新カードはサブクラス＋registry 行だけで足せる。
#   種別ごとの協調（関係）は manager が文脈(ctx)として与え、規則はカード側が組む。
#   initInstances -> initRules -> start（reset + new_game + settle）。
# ============================================================

from aspect.aspect_relation_rule import InjectionEventRule, ConditionRule
from aspect_flow.flow import FlowAspect
from aspect_ai.ai import AIAspect
from aspect_card import CARD_DEFS
from aspect_hero.hero import HeroAspect


PLAYER_DECK = ["summoner", "priest", "summoner", "priest", "summoner", "priest"]
ENEMY_DECK = ["priest", "summoner", "priest", "summoner", "priest", "summoner"]


class AspectModelManager:
    def __init__(self, printer=None):
        self.printer = printer
        self._cid = 0
        self._children = {}   # 親カード -> [生成した子カード]
        self._parent = {}     # 子カード -> 親カード
        self.initInstances()
        self.initRules()

    def _new_card(self, key, owner, name, initial):
        d = CARD_DEFS[key]
        c = d["cls"](self._cid, name, key, owner, d["meta"], initial)
        self._cid += 1
        if self.printer:
            c.printer = self.printer
        return c

    def _build_side(self, owner, deck_keys, prefix):
        # デッキ（カード実体）。registry の spawns 指定に従い、付随カードを生成する。
        deck_cards = [self._new_card(k, owner, "%s_%s%d" % (prefix, k, i), "Deck")
                      for i, k in enumerate(deck_keys)]
        spawned = []
        for c in deck_cards:
            spec = CARD_DEFS[c.key].get("spawns")
            if not spec:
                continue
            ckey, n = spec
            kids = [self._new_card(ckey, owner,
                                   "%s_%s_of%d_%d" % (prefix, ckey, c.id, t),
                                   "Dormant")
                    for t in range(n)]
            self._children[c] = kids
            for kid in kids:
                self._parent[kid] = c
            spawned += kids
        roster = deck_cards + spawned
        return deck_cards, roster

    def initInstances(self):
        self.p_deck, self.player_roster = self._build_side(
            "player", PLAYER_DECK, "P")
        self.e_deck, self.enemy_roster = self._build_side(
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

    def _wire_actor(self, actor, roster, opp_roster):
        # 召喚: 手札のカード実体 id ごとに遷移を列挙（条件はそのカードが Hand）。
        for c in actor.deck_cards:
            t = "t_play_c%d" % c.id
            actor.classRulesEI[t] = [InjectionEventRule(c, "trig_play")]
            actor.classRulesGR[t] = [ConditionRule(c, "Hand", True)]
        # 攻撃: (自ロスター添字, 対象) を全て静的列挙。対象は f か u<敵添字>。
        for i, a in enumerate(roster):
            for tgt in ["f"] + ["u%d" % j for j in range(len(opp_roster))]:
                t = "t_attack_a%d_%s" % (i, tgt)
                actor.classRulesEI[t] = [
                    InjectionEventRule(a, "trig_attack#" + tgt)]
                conds = [ConditionRule(a, "OnBoard", True)]
                if tgt.startswith("u"):
                    conds.append(
                        ConditionRule(opp_roster[int(tgt[1:])], "OnBoard", True))
                actor.classRulesGR[t] = conds

    def _context(self, card, roster):
        # registry/サブクラスが宣言した NEEDS を解決して文脈辞書を作る。
        ctx = {}
        for need in card.NEEDS:
            if isinstance(need, tuple):
                key, ckey = need
                ctx[key] = [c for c in roster if c.key == ckey]
            elif need == "children":
                ctx["children"] = self._children.get(card, [])
            elif need == "parent":
                ctx["parent"] = self._parent.get(card)
        return ctx

    def _wire_card_kinds(self, roster):
        # 各カードが自分の規則を組む（効果は規則のまま）。
        for c in roster:
            ctx = self._context(c, roster)
            c.configure(ctx)
            c.classRulesEI = c.rulesEI(ctx)
            c.classRulesGR = c.rulesGR(ctx)

    def initRules(self):
        self.flow.classRulesEI = {}
        self.flow.classRulesGR = {}
        self.ai.classRulesEI = {}
        self.ai.classRulesGR = {}

        self._wire_actor(self.flow, self.player_roster, self.enemy_roster)
        self._wire_actor(self.ai, self.enemy_roster, self.player_roster)

        # flow: ターン開始の一斉配信（base流ブロードキャスト＝静的列挙）。
        self.flow.classRulesEI["t_begin_player"] = [
            InjectionEventRule(c, "trig_begin_turn") for c in self.player_roster]
        self.flow.classRulesEI["t_begin_enemy"] = [
            InjectionEventRule(c, "trig_begin_turn") for c in self.enemy_roster]
        self.flow.classRulesEI["t_enemy"] = [InjectionEventRule(self.ai, "trig_ai")]
        # flow: 表示は broadcast -> 各カード／英雄が自分の行を出す（自己申告）。
        self.flow.classRulesEI["t_show"] = [
            InjectionEventRule(x, "trig_show")
            for x in self.player_roster + self.enemy_roster
            + [self.p_hero, self.e_hero]]

        # ai: 敵ターン終了を flow へ。
        self.ai.classRulesEI["t_act"] = [
            InjectionEventRule(self.flow, "trig_end_enemy")]

        # カード種別ごとの規則（各カードが自分の規則を組む）。
        self._wire_card_kinds(self.player_roster)
        self._wire_card_kinds(self.enemy_roster)

        # 英雄: HP0 で Dead になったら flow へ（勝敗は flow が判断）。
        self.p_hero.classRulesEI = {
            "t_damage": [InjectionEventRule(self.flow, "trig_player_hero_dead")]}
        self.p_hero.classRulesGR = {}
        self.e_hero.classRulesEI = {
            "t_damage": [InjectionEventRule(self.flow, "trig_enemy_hero_dead")]}
        self.e_hero.classRulesGR = {}

    def start(self):
        for c in self.player_roster + self.enemy_roster:
            c.reset()
        self.p_hero.reset()
        self.e_hero.reset()
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
            if not active:
                break
            for a in active:
                a.run()
