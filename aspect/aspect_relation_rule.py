# ============================================================
# AOM のアスペクト間ルール（静的版）。
#  InjectionEventRule: 対象アスペクトへイベントを注入（固定文字列のみ）。
#  ConditionRule:      対象アスペクトの状態を参照する。
# ============================================================


class InjectionEventRule:
    def __init__(self, targetClass, event):
        self.targetClass = targetClass
        self.event = event

    def send(self):
        self.targetClass.messageQueue.put(self.event, True)


class ConditionRule:
    def __init__(self, targetClass, state, judge):
        self.targetClass = targetClass
        self.state = state
        self.judge = judge

    def checkState(self):
        equal = (self.targetClass.getClassState() == self.state)
        return equal if self.judge else not equal
