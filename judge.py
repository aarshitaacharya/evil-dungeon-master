"""The judge: is a rigged dungeon still winnable?

Without this, the DM could delete the key and call it a victory. The judge is
plain code, not an AI, so it can't be talked into anything. It searches the
rigged game (contracts included) breadth-first and returns the shortest
winning route, which also gives us "par": the minimum moves a perfect player needs.
A dungeon only counts as winnable if par <= PAR_LIMIT, so the DM cannot make a round
that is technically solvable but needs more moves than the Player is allowed.
"""
import copy
import json
from collections import deque
from dataclasses import dataclass

from game import Game
from harness import Harness

PAR_LIMIT = 20   # a perfect player must escape within this many moves (the Player gets 25)


@dataclass
class Verdict:
    winnable: bool
    par: int | None = None      # moves a perfect player needs
    path: tuple = ()            # that perfect player's commands


def _candidates(game):
    """Every command that could possibly matter from here."""
    room = game.world["rooms"][game.room]
    commands = [f"go {d}" for d in room["exits"]]
    commands += [f"take {i}" for i in game._items_at(game.room)]
    commands += [f"search {f}" for f in room["features"]]
    if game._door()[1]:
        commands.append("open door")
        commands += [f"use {i} on door" for i in game._items_at("inventory")]
    return commands


def _state_key(harness):
    g = harness.game
    # moves parity matters because look_cooldown depends on it
    return json.dumps([g.room, g.world["items"], g.world["rooms"][g.room]["exits"],
                       g.moves % 2, harness.pest_fired], sort_keys=True)


def check(base_world, plan):
    """Breadth-first search for a winning command sequence."""
    start = Harness(Game(base_world), plan)
    start.reset()
    queue, seen = deque([(start, ())]), {_state_key(start)}
    while queue:
        harness, path = queue.popleft()
        if len(path) >= PAR_LIMIT:
            continue
        for command in _candidates(harness.game):
            child = copy.deepcopy(harness)
            _, done = child.step(command)
            if done:
                return Verdict(True, len(path) + 1, path + (command,))
            key = _state_key(child)
            if key not in seen:
                seen.add(key)
                queue.append((child, path + (command,)))
    return Verdict(False)
