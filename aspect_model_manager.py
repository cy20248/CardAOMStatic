# ============================================================
# AspectModelManager（静的AOM版・base流 / Boardなし / カード＝盤上ユニット統一）。
#   マネージャ自身が全カード実体を生成し、規則を“直接参照”で配線する。
#   aspect 同士は相互参照を持たず、協調は次の2つだけで行う:
#     - checkEIRules(遷移) -> 規則（宛先参照は規則オブジェクト側が保持）
#     - checkGRRules(遷移) -> 規則（相手の state を参照）
#   例外は戦闘の“動的なダメージ量×相手参照”。量は actor しか知らないので、
#   manager が各カードに相手参照(opp_hero/opp_units)だけを注入する。
#   カード種別は CARD_DEFS(registry) で定義。manager は registry を回して
#   実体生成・規則配線する。規則（EI/GR）は manager 側に置き、アスペクトは
#   状態機械と効果ハンドラのみを持つ（base流の分離）。
#   種別ごとの協調（関係）は manager が文脈(ctx)として解決し、規則を組む。
#   initInstances -> initRules -> start（reset + new_game + settle）。
# ============================================================

from aspect.aspect_relation_rule import InjectionEventRule, ConditionRule
from aspect_flow.flow import FlowAspect
from aspect_ai.ai import AIAspect
from aspect_card import CARD_DEFS
from aspect_hero.hero import HeroAspect


PLAYER_DECK = ["summoner", "priest", "summoner", "priest", "summoner", "priest"]
ENEMY_DECK = ["priest", "summoner", "priest", "summoner", "priest", "summoner"]

# カード種別が規則を組むのに必要な文脈（関係）の宣言。manager が解決する。
#   文字列 = 関係("parent"/"children") / (ctxキー, カードkey) = 同陣営の該当カード群
CARD_NEEDS = {
    "summoner": ("children",),
    "imp": ("parent", ("priests", "priest")),
}


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
        ei = {}
        gr = {}
        for c in actor.deck_cards:
            t = "t_play_c%d" % c.id
            ei[t] = [InjectionEventRule(c, "trig_play")]
            gr[t] = [ConditionRule(c, "Hand", True)]
        # 攻撃: (自ロスター添字, 対象) を全て静的列挙。対象は f か u<敵添字>。
        for i, a in enumerate(roster):
            for tgt in ["f"] + ["u%d" % j for j in range(len(opp_roster))]:
                t = "t_attack_a%d_%s" % (i, tgt)
                ei[t] = [InjectionEventRule(a, "trig_attack#" + tgt)]
                conds = [ConditionRule(a, "OnBoard", True)]
                if tgt.startswith("u"):
                    conds.append(
                        ConditionRule(opp_roster[int(tgt[1:])], "OnBoard", True))
                gr[t] = conds
        return ei, gr

    def _flowRules(self):
        ei, gr = self._wire_actor(
            self.flow, self.player_roster, self.enemy_roster)
        # ターン開始の一斉配信（base流ブロードキャスト＝静的列挙）。
        ei["t_begin_player"] = [
            InjectionEventRule(c, "trig_begin_turn") for c in self.player_roster]
        ei["t_begin_enemy"] = [
            InjectionEventRule(c, "trig_begin_turn") for c in self.enemy_roster]
        ei["t_enemy"] = [InjectionEventRule(self.ai, "trig_ai")]
        # 表示は broadcast -> 各カード／英雄が自分の行を出す（自己申告）。
        ei["t_show"] = [
            InjectionEventRule(x, "trig_show")
            for x in self.player_roster + self.enemy_roster
            + [self.p_hero, self.e_hero]]
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
                ctx[key] = [c for c in roster if c.key == ckey]
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

    def _wire_cards(self, roster):
        # 規則は manager が組む（アスペクトは状態機械と効果ハンドラのみ）。
        for c in roster:
            ctx = self._context(c, roster)
            if c.key == "summoner":
                c.classRulesEI = self._summonerRulesEI(c, ctx)
                c.classRulesGR = self._summonerRulesGR(c, ctx)
            elif c.key == "imp":
                c.aura_count = len(ctx["priests"])
                c.classRulesEI = self._impRulesEI(c, ctx)
                c.classRulesGR = self._impRulesGR(c, ctx)
            elif c.key == "priest":
                c.classRulesEI = self._priestRulesEI(c, ctx)
                c.classRulesGR = self._priestRulesGR(c, ctx)

    def initRules(self):
        # add rules（base流：クラスごとに EI/GR を組んで代入）
        self.flow.classRulesEI, self.flow.classRulesGR = self._flowRules()
        self.ai.classRulesEI, self.ai.classRulesGR = self._aiRules()

        # カード種別ごとの規則（各カード実体に割り当て）。
        self._wire_cards(self.player_roster)
        self._wire_cards(self.enemy_roster)

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
