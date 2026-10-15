"""The arena: Player vs Evil DM, round after round.

    python3 main.py [rounds]

run() reports everything that happens as *events* (plain dicts) to an `emit`
callback. The terminal printer, the log file and (soon) the browser UI are all
just different listeners on the same event stream.
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


# --- the arena: produces events -------------------------------------------------

def play_round(n, history, emit, dm_ask=None, player_ask=None, pause=0.0):
    emit({"type": "round_start", "round": n})
    if n == 1:
        plan, notes = {"analysis": "Baseline: no rigging.", "actions": []}, []
    else:
        emit({"type": "dm_thinking", "round": n})
        plan, notes = propose_plan(history, DEFAULT_WORLD, ask=dm_ask,
                                   judge=lambda actions: judge.check(DEFAULT_WORLD, actions))
    verdict = judge.check(DEFAULT_WORLD, plan["actions"])
    harness = Harness(Game(), plan["actions"])
    emit({"type": "round_setup", "round": n, "analysis": plan["analysis"], "actions": plan["actions"],
          "notes": notes, "par": verdict.par, "perfect_path": list(verdict.path),
          "world": harness.rigged_world})

    def on_turn(turn):
        emit({"type": "turn", "round": n, **turn})
        time.sleep(pause)  # stay polite to free-tier rate limits

    trajectory = run_episode(harness, ask=player_ask, on_turn=on_turn)
    emit({"type": "round_end", "round": n, "won": trajectory["won"],
          "moves": trajectory["moves"], "par": verdict.par})
    return {"round": n, "plan": plan["actions"], "analysis": plan["analysis"],
            "par": verdict.par, "trajectory": trajectory}


def run(rounds, emit, dm_ask=None, player_ask=None, pause=0.0):
    emit({"type": "run_start", "rounds": rounds, "world": DEFAULT_WORLD})
    history = []
    for n in range(1, rounds + 1):
        history.append(play_round(n, history, emit, dm_ask, player_ask, pause))
    emit({"type": "run_end", "summary": summarize(history)})
    return history


def summarize(history):
    rows = [{"round": r["round"], "won": r["trajectory"]["won"], "moves": r["trajectory"]["moves"],
             "par": r["par"], "wasted": r["trajectory"]["moves"] - r["par"],
             "changes": [a["op"] for a in r["plan"]]} for r in history]
    rigged = rows[1:]
    return {"rows": rows,
            "rigged_wins": sum(r["won"] for r in rigged), "rigged_rounds": len(rigged),
            "avg_wasted_rigged": sum(r["wasted"] for r in rigged) / len(rigged) if rigged else None,
            "baseline_wasted": rows[0]["wasted"] if rows else None}


# --- listeners: consume events --------------------------------------------------

def terminal_printer(event):
    t = event["type"]
    if t == "round_start":
        print(f"\n{BOLD}=== Round {event['round']} ==={RESET}")
    elif t == "dm_thinking":
        print("The DM is scheming...")
    elif t == "round_setup":
        for note in event["notes"]:
            print(f"  {RED}! {note}{RESET}")
        print(f"{BOLD}DM:{RESET} {event['analysis']}")
        for a in event["actions"]:
            print(f"  -> {a['tool']}/{a['op']}: {a.get('reason', '')}")
        print(f"{DIM}Judge: winnable, par = {event['par']} moves{RESET}")
    elif t == "turn":
        print(f"  [{event['move']:>2}] {event['command']!r:<26} -> {event['result'].splitlines()[0]}")
    elif t == "round_end":
        print(f"  {GREEN + 'ESCAPED' if event['won'] else RED + 'FAILED'}{RESET} ({event['moves']} moves)")
    elif t == "run_end":
        print_scoreboard(event["summary"])


def print_scoreboard(s):
    print(f"\n{BOLD}=== Scoreboard ==={RESET}")
    print(f"{'Rnd':<4}{'Result':<8}{'Moves':>6}{'Par':>5}{'Wasted':>8}  DM changed")
    for r in s["rows"]:
        result = f"{GREEN}WIN {RESET}" if r["won"] else f"{RED}LOSS{RESET}"
        print(f"{r['round']:<4}{result:<{8 + len(GREEN + RESET)}}{r['moves']:>6}{r['par']:>5}"
              f"{r['wasted']:>8}  {', '.join(r['changes']) or '-'}")
    if s["rigged_rounds"]:
        print(f"\nRigged rounds won: {s['rigged_wins']}/{s['rigged_rounds']}. "
              f"Avg wasted moves: {s['avg_wasted_rigged']:.1f} rigged vs {s['baseline_wasted']} baseline.")


def file_recorder(run_dir):
    """Append every event to events.jsonl: the replay file the UI will play back."""
    run_dir.mkdir(parents=True, exist_ok=True)
    out = open(run_dir / "events.jsonl", "a", buffering=1)
    return lambda event: out.write(json.dumps(event) + "\n")


def main(rounds=5):
    record = file_recorder(Path("logs") / time.strftime("%Y%m%d-%H%M%S"))
    run(rounds, lambda e: (record(e), terminal_printer(e)), pause=0.3)


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 5)
