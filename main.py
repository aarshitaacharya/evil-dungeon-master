"""The arena: Player vs Evil DM, round after round.

    python3 main.py [rounds]
"""
import json
import sys
import time
from pathlib import Path

import judge
from dm import propose_plan
from game import DEFAULT_WORLD, Game
from harness import Harness
from player import run_episode

RED, GREEN, DIM, BOLD, RESET = "\033[31m", "\033[32m", "\033[2m", "\033[1m", "\033[0m"


def play_round(n, history, run_dir):
    print(f"\n{BOLD}=== Round {n} ==={RESET}")
    if n == 1:
        plan = {"analysis": "Baseline: no rigging.", "actions": []}
    else:
        print("The DM is scheming...")
        plan, notes = propose_plan(history, DEFAULT_WORLD,
                                   judge=lambda actions: judge.check(DEFAULT_WORLD, actions))
        for note in notes:
            print(f"  {RED}! {note}{RESET}")
    verdict = judge.check(DEFAULT_WORLD, plan["actions"])
    print(f"{BOLD}DM:{RESET} {plan['analysis']}")
    for a in plan["actions"]:
        print(f"  -> {a['tool']}/{a['op']}: {a.get('reason', '')}")
    print(f"{DIM}Judge: winnable, par = {verdict.par} moves{RESET}")

    def show(t):
        print(f"  [{t['move']:>2}] {t['command']!r:<26} -> {t['result'].splitlines()[0]}")
        time.sleep(0.3)  # stay polite to free-tier rate limits

    trajectory = run_episode(Harness(Game(), plan["actions"]), on_turn=show)
    won = trajectory["won"]
    print(f"  {GREEN + 'ESCAPED' if won else RED + 'FAILED'}{RESET} ({trajectory['moves']} moves)")

    record = {"round": n, "plan": plan["actions"], "analysis": plan["analysis"],
              "par": verdict.par, "perfect_path": verdict.path, "trajectory": trajectory}
    (run_dir / f"round-{n}.json").write_text(json.dumps(record, indent=2))
    return record


def scoreboard(history):
    print(f"\n{BOLD}=== Scoreboard ==={RESET}")
    print(f"{'Rnd':<4}{'Result':<8}{'Moves':>6}{'Par':>5}{'Wasted':>8}  DM changed")
    for r in history:
        t = r["trajectory"]
        wasted = t["moves"] - r["par"]
        result = f"{GREEN}WIN {RESET}" if t["won"] else f"{RED}LOSS{RESET}"
        changes = ", ".join(a["op"] for a in r["plan"]) or "-"
        print(f"{r['round']:<4}{result:<{8 + len(GREEN + RESET)}}{t['moves']:>6}{r['par']:>5}{wasted:>8}  {changes}")
    rigged = history[1:]
    if rigged:
        wins = sum(r["trajectory"]["won"] for r in rigged)
        base = history[0]["trajectory"]["moves"] - history[0]["par"]
        avg = sum(r["trajectory"]["moves"] - r["par"] for r in rigged) / len(rigged)
        print(f"\nRigged rounds won: {wins}/{len(rigged)}. "
              f"Avg wasted moves: {avg:.1f} rigged vs {base} baseline.")


def main(rounds=5):
    history = []
    run_dir = Path("logs") / time.strftime("%Y%m%d-%H%M%S")
    run_dir.mkdir(parents=True)
    for n in range(1, rounds + 1):
        history.append(play_round(n, history, run_dir))
    scoreboard(history)


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 5)
