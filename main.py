# ============================================================
# 一人用TCG（静的AOM版 / base流・Boardなし）。
#   - 既定: 対話（コマンド入力）
#   - --selftest: 自動進行で検証
#   モデルコマンド: play <番号> / attack <スロット> f|u<敵スロット> / state / end / quit
#   ホストコマンド: spawn [p|e] <スロット>（OnBoard のサモナーからインプを実行時生成）
# ============================================================

import argparse
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stdin.reconfigure(encoding="utf-8")

from aspect_model_manager import AspectModelManager


def host_spawn(manager, line):
    # ホスト駆動のメタ操作（モデルの外）。生成は manager が行う。
    parts = line.split()
    owner = "player"
    if len(parts) == 3:
        if parts[1] in ("e", "enemy"):
            owner = "enemy"
        slot_s = parts[2]
    elif len(parts) == 2:
        slot_s = parts[1]
    else:
        print("使い方: spawn [p|e] <スロット>")
        return
    if not slot_s.isdigit():
        print("使い方: spawn [p|e] <スロット>")
        return
    roster = manager.player_roster if owner == "player" else manager.enemy_roster
    i = int(slot_s)
    if not (0 <= i < len(roster)):
        print("そのスロットは存在しません")
        return
    parent = roster[i]
    if parent is None or parent.key != "summoner" or parent.state != "OnBoard":
        print("OnBoard のサモナーを指定してください")
        return
    imp = manager.spawn_imp(owner, parent)
    imp.messageQueue.put("trig_play")
    manager.settle()
    print("生成: %s（スロット %d）" % (imp.name, imp.slot))


def run_interactive(manager):
    manager.start()
    while not manager.is_ended():
        try:
            line = input("> ")
        except EOFError:
            break
        line = line.strip()
        if line in ("quit", "exit", "q"):
            break
        if line.split()[:1] == ["spawn"]:
            host_spawn(manager, line)
            continue
        manager.inject_command(line)
        manager.settle()
    print("")
    print("=== 対戦終了 ===")


def choose_command(manager):
    # 動的コレクション: 手札を番号で選んで出す（可否は flow が GR で判定）。
    flow = manager.flow
    for i in range(len(flow.hand)):
        if flow.can_play(i):
            return "play %d" % i
    # 攻撃は名前ではなくスロットで指定（自ロスター添字。相手はフェイス固定）。
    for i, c in enumerate(manager.player_roster):
        if c is not None and c.state == "OnBoard" and c.can_attack:
            return "attack %d f" % i
    return "end"



def run_selftest(manager):
    manager.start()
    flow = manager.flow
    for _ in range(400):
        if manager.is_ended():
            break
        if flow.state == "PlayerTurn":
            cmd = choose_command(manager)
            print(">>> " + cmd)
            manager.inject_command(cmd)
        manager.settle()
    print("")
    print("=== selftest 完了 ===")


def main():
    parser = argparse.ArgumentParser(description="一人用TCG（静的AOM版 / base流・カード実体）")
    parser.add_argument("--selftest", action="store_true", help="自動進行で検証")
    args = parser.parse_args()

    manager = AspectModelManager(printer=print)

    print("========================================")
    print("   一人用TCG（静的AOM版 / base流・カード実体）")
    print("========================================")

    if args.selftest:
        run_selftest(manager)
    else:
        run_interactive(manager)


if __name__ == "__main__":
    main()
