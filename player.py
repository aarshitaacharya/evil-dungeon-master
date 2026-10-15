"""The Player AI: observe -> think -> act -> repeat.

run_episode() is the whole agent loop. It talks to the game only through
reset() and step(), and returns a trajectory: the full record of what happened.
"""
import json
import re
import sys
import time
from pathlib import Path

from game import Game
from llm import chat

MAX_MOVES = 25
MAX_REASKS = 2

SYSTEM_PROMPT = """You are an adventurer locked in a dungeon, playing a text adventure. Your goal: escape.

Each turn you are shown what you see. Reply with exactly ONE command and nothing else.
Commands: look | go <direction> | take <item> | search <thing> | open door | use <item> on door | inventory

You are curious and stubborn. You examine your surroundings, you don't give up,
and you don't repeat a command that just failed. Think about what you've learned."""


def parse_command(reply):
    """Models are chatty. Pull one clean command out of whatever they said."""
    for line in reply.strip().splitlines():
        line = re.sub(r"^[>\s*`\"'-]+|[`\"'\s.]+$", "", line.strip())
        if line:
            return line.lower()
    return "look"


_WORD = r"[a-z]{1,12}"
VALID_COMMAND = re.compile(
    rf"^(look|inventory|help|(go )?(north|south|east|west)|open door"
    rf"|(take|get|search|examine|inspect) {_WORD}( {_WORD}){{0,2}}"
    rf"|use {_WORD}( {_WORD}){{0,2}} on {_WORD}( {_WORD}){{0,2}})$"
)
REASK = ("That was not a single valid command. Reply with exactly ONE command and nothing "
         "else, for example: go north | take key | search crate | use key on door")


def run_episode(game, ask=None, max_moves=MAX_MOVES, on_turn=None):
    """Play one game. `ask(messages) -> str` is the model; defaults to the PLAYER role."""
    ask = ask or (lambda messages: chat("PLAYER", messages))
    observation = game.reset()
    messages = [{"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": observation}]
    turns, done = [], False

    while not done and game.moves < max_moves:
        reply = ask(messages)                       # think
        command, retries = parse_command(reply), 0
        while not VALID_COMMAND.match(command) and retries < MAX_REASKS:
            # Garbled output (glued commands, leaked model tokens): ask again, and
            # keep the garbage out of the history so the model can't copy itself.
            retries += 1
            reply = ask(messages + [{"role": "assistant", "content": command[:80]},
                                    {"role": "user", "content": REASK}])
            command = parse_command(reply)
        result, done = game.step(command)           # act
        turns.append({"move": game.moves, "room": game.room, "saw": observation,
                      "raw_reply": reply, "command": command, "retries": retries, "result": result})
        if on_turn:
            on_turn(turns[-1])
        messages += [{"role": "assistant", "content": command},
                     {"role": "user", "content": result}]   # observe
        observation = result

    return {"won": game.won, "moves": game.moves, "turns": turns}


def save_trajectory(trajectory, name):
    Path("logs").mkdir(exist_ok=True)
    path = Path("logs") / f"{name}-{int(time.time())}.json"
    path.write_text(json.dumps(trajectory, indent=2))
    return path


if __name__ == "__main__":
    def show(turn):
        print(f"[{turn['move']:>2}] {turn['command']!r:<24} -> {turn['result'].splitlines()[0]}")
        time.sleep(0.5)  # stay under free-tier rate limits

    trajectory = run_episode(Game(), on_turn=show)
    print("\nESCAPED!" if trajectory["won"] else "\nFailed to escape.",
          f"({trajectory['moves']} moves)")
    print("Saved", save_trajectory(trajectory, "player"))
