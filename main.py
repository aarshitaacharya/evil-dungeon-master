"""The arena: Player vs Evil DM, round after round.

    python3 main.py [rounds]
"""
import json
import sys
import time
from pathlib import Path

from dm import propose_plan
from game import DEFAULT_WORLD, Game
from harness import Harness
from player import run_episode


def main(rounds=3):
    history = []
    run_dir = Path("logs") / time.strftime("%Y%m%d-%H%M%S")
    run_dir.mkdir(parents=True)

    for n in range(1, rounds + 1):
        print(f"\n=== Round {n} ===")
        if n == 1:
            plan = {"analysis": "Baseline: no rigging.", "actions": []}
        else:
            print("The DM is scheming...")
            plan, notes = propose_plan(history, DEFAULT_WORLD)
            for note in notes:
                print("  !", note)
        print("DM:", plan["analysis"])
        for action in plan["actions"]:
            print(f"  -> {action['tool']}/{action['op']}: {action.get('reason', '')}")

        game = Harness(Game(), plan["actions"])
        trajectory = run_episode(game, on_turn=lambda t: (
            print(f"  [{t['move']:>2}] {t['command']!r:<24} -> {t['result'].splitlines()[0]}"), time.sleep(0.3)))
        print("  ESCAPED" if trajectory["won"] else "  FAILED", f"({trajectory['moves']} moves)")

        record = {"round": n, "plan": plan["actions"], "analysis": plan["analysis"], "trajectory": trajectory}
        history.append(record)
        (run_dir / f"round-{n}.json").write_text(json.dumps(record, indent=2))

    print("\n=== Scoreboard ===")
    for r in history:
        t = r["trajectory"]
        changes = ", ".join(f"{a['op']}" for a in r["plan"]) or "none"
        print(f"Round {r['round']}: {'WIN ' if t['won'] else 'LOSS'} {t['moves']:>2} moves | DM changed: {changes}")


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 3)
