# ============================================================
# AspectModelManager（静的AOM版・base流 / Boardなし）。
#   マネージャ自身が全実体を生成し、規則を“直接参照”で配線する（base AOM 方式）。
#   aspect 同士は相互参照を持たず、協調は次の2つだけで行う:
#     - checkEIRules(遷移) -> 規則（宛先参照は規則オブジェクト側が保持）
#     - checkGRRules(遷移) -> 規則（相手の state を参照）
#   例外は戦闘の“動的なダメージ量”のみ。量は actor しか知らないので、
#   manager が attacker に相手参照(opp_hero/opp_units)だけを注入する。
#   initInstances -> initRules -> start（reset + new_game + settle）。
# ============================================================

from aspect.aspect_relation_rule import InjectionEventRule, ConditionRule
from aspect_flow.flow import FlowAspect
from aspect_ai.ai import AIAspect
from aspect_unit.summoner import SummonerAspect
from aspect_unit.imp import ImpAspect
from aspect_unit.priest import PriestAspect
from aspect_hero.hero import HeroAspect


# カード種メタ（cost/playable）。実体を持たない“データ”。flow/ai に注入する。
CARD_META = {
    "summoner": {"cost": 2, "playable": True},
    "imp": {"cost": 1, "playable": False},
    "priest": {"cost": 2, "playable": True},
}


class AspectModelManager:
    # 攻撃遷移の対象指定（f=フェイス, u<j>=相手スロット j）。スロット数は4。
    TARGETS = ["f", "u0", "u1", "u2", "u3"]

    def __init__(self, printer=None):
        self.printer = printer
        self.initInstances()
        self.initRules()

    def initInstances(self):
        # 実体をここで生成（＝ manager が集合を持つ。base AOM と同じ）。
        self.p_summoner = SummonerAspect("P_Summoner", "player")
        self.p_imp1 = ImpAspect("P_Imp1", "player")
        self.p_imp2 = ImpAspect("P_Imp2", "player")
        self.p_priest = PriestAspect("P_Priest", "player")
        self.e_summoner = SummonerAspect("E_Summoner", "enemy")
        self.e_imp1 = ImpAspect("E_Imp1", "enemy")
        self.e_imp2 = ImpAspect("E_Imp2", "enemy")
        self.e_priest = PriestAspect("E_Priest", "enemy")

        self.player_units = [self.p_summoner, self.p_imp1, self.p_imp2, self.p_priest]
        self.enemy_units = [self.e_summoner, self.e_imp1, self.e_imp2, self.e_priest]
        self.all_units = self.player_units + self.enemy_units
        self.p_hero = HeroAspect("P_Hero", "player")
        self.e_hero = HeroAspect("E_Hero", "enemy")

        self.card_table = {
            "player": {"summoner": self.p_summoner, "imp": self.p_imp1,
                       "priest": self.p_priest},
            "enemy": {"summoner": self.e_summoner, "imp": self.e_imp1,
                      "priest": self.e_priest},
        }
        self.player_deck_keys = ["summoner", "priest", "summoner",
                                 "priest", "summoner", "priest"]
        self.enemy_deck_keys = ["priest", "summoner", "priest",
                                "summoner", "priest", "summoner"]

        # 表示（自己申告）用のプリンタを全アスペクトへ配る。
        for a in self.all_units + [self.p_hero, self.e_hero]:
            a.printer = self.printer

        # 戦闘のみ“相手の実体”への最小参照を注入（ダメージ量は actor が持つ）。
        for u in self.player_units:
            u.opp_hero = self.e_hero
            u.opp_units = self.enemy_units
        for u in self.enemy_units:
            u.opp_hero = self.p_hero
            u.opp_units = self.player_units

        # flow/ai は他アスペクトを一切持たない（自分の状態＋カードメタのみ）。
        self.flow = FlowAspect(self.player_deck_keys, CARD_META)
        self.flow.printer = self.printer
        self.ai = AIAspect(self.enemy_deck_keys, CARD_META)
        self.ai.printer = self.printer

        self.aspects = ([self.flow, self.ai] + self.all_units
                        + [self.p_hero, self.e_hero])

    def _wire_actions(self, actor, side_units, opp_units, cards):
        # 召喚: key -> unit。条件はその unit が Dormant であること（GR）。
        for key, unit in cards.items():
            t = "t_play_" + key
            actor.classRulesEI[t] = [InjectionEventRule(unit, "trig_play")]
            actor.classRulesGR[t] = [ConditionRule(unit, "Dormant", True)]
        # 攻撃: (自スロット, 対象) を全て静的列挙（動的選択は無い）。
        for i, a in enumerate(side_units):
            for tgt in self.TARGETS:
                t = "t_attack_a%d_%s" % (i, tgt)
                actor.classRulesEI[t] = [
                    InjectionEventRule(a, "trig_attack#" + tgt)]
                conds = [ConditionRule(a, "OnBoard", True)]
                if tgt.startswith("u"):
                    conds.append(
                        ConditionRule(opp_units[int(tgt[1:])], "OnBoard", True))
                actor.classRulesGR[t] = conds

    def initRules(self):
        # 規則は“直接参照”で配線（base AOM 方式）。
        self.flow.classRulesEI = {}
        self.flow.classRulesGR = {}
        self.ai.classRulesEI = {}
        self.ai.classRulesGR = {}

        # flow / ai: 召喚・攻撃の遷移を全列挙（相手参照は規則側が保持）。
        self._wire_actions(self.flow, self.player_units, self.enemy_units,
                           self.card_table["player"])
        self._wire_actions(self.ai, self.enemy_units, self.player_units,
                           self.card_table["enemy"])

        # flow: ターン開始の一斉配信（base流ブロードキャスト＝静的列挙）。
        self.flow.classRulesEI["t_begin_player"] = [
            InjectionEventRule(u, "trig_begin_turn") for u in self.player_units]
        self.flow.classRulesEI["t_begin_enemy"] = [
            InjectionEventRule(u, "trig_begin_turn") for u in self.enemy_units]
        self.flow.classRulesEI["t_enemy"] = [InjectionEventRule(self.ai, "trig_ai")]
        # flow: 表示は broadcast -> 各アスペクトが自分の行を出す（自己申告）。
        self.flow.classRulesEI["t_show"] = [
            InjectionEventRule(x, "trig_show")
            for x in self.all_units + [self.p_hero, self.e_hero]]

        # ai: 敵ターン終了を flow へ。
        self.ai.classRulesEI["t_act"] = [
            InjectionEventRule(self.flow, "trig_end_enemy")]

        # units: サモナー -> インプ2体を起動。
        def summoner_rules(summ, imp1, imp2):
            summ.classRulesEI = {
                "t_play": [InjectionEventRule(imp1, "trig_play"),
                           InjectionEventRule(imp2, "trig_play")]}
            summ.classRulesGR = {}

        # units: インプ起動条件（サモナーが場）＋司祭オーラ（状態参照のみ）。
        def imp_rules(imp, summ, priest):
            imp.classRulesGR = {
                "t_play": [ConditionRule(summ, "OnBoard", True)],
                "t_priest_aura": [ConditionRule(priest, "OnBoard", True)]}
            imp.classRulesEI = {
                "t_play": [InjectionEventRule(summ, "trig_boost"),
                           InjectionEventRule(imp, "trig_priest_aura")]}

        summoner_rules(self.p_summoner, self.p_imp1, self.p_imp2)
        imp_rules(self.p_imp1, self.p_summoner, self.p_priest)
        imp_rules(self.p_imp2, self.p_summoner, self.p_priest)
        self.p_priest.classRulesEI = {}
        self.p_priest.classRulesGR = {}

        summoner_rules(self.e_summoner, self.e_imp1, self.e_imp2)
        imp_rules(self.e_imp1, self.e_summoner, self.e_priest)
        imp_rules(self.e_imp2, self.e_summoner, self.e_priest)
        self.e_priest.classRulesEI = {}
        self.e_priest.classRulesGR = {}

        # heroes: HP0 で Dead になったら flow へ（勝敗は flow が判断）。
        self.p_hero.classRulesEI = {
            "t_damage": [InjectionEventRule(self.flow, "trig_player_hero_dead")]}
        self.p_hero.classRulesGR = {}
        self.e_hero.classRulesEI = {
            "t_damage": [InjectionEventRule(self.flow, "trig_enemy_hero_dead")]}
        self.e_hero.classRulesGR = {}

    def start(self):
        for u in self.all_units:
            u.reset()
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
