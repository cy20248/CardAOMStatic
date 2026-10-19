# ============================================================
# AOM 基底アスペクト（静的版 / 生成コード準拠API / 単一スレッド）。
# ============================================================

import queue


class Aspect:
    def __init__(self):
        self.classRulesGR = dict()
        self.classRulesEI = dict()
        self.messageQueue = queue.Queue()
        self.state = "State1"

    def getClassState(self):
        return self.state

    def checkGRRules(self, transition):
        if len(self.classRulesGR) == 0:
            return True
        if transition in self.classRulesGR.keys():
            for entry in self.classRulesGR[transition]:
                if not entry.checkState():
                    return False
            return True
        return True

    def checkEIRules(self, transition):
        if len(self.classRulesEI) == 0:
            return
        if transition in self.classRulesEI.keys():
            for entry in self.classRulesEI[transition]:
                entry.send()

    def run(self):
        raise NotImplementedError
