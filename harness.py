"""The rigging layer (the EnvHarness idea).

A Harness wraps a Game from the outside. It never edits game.py. Given a plan,
it does three kinds of things:

  Stage     change where things start     (move_item, add_item)
  Chain     make the run longer           (extend_path)
  Contract  change the rules during play  (look_cooldown, second_key, pest, lie)

To the Player it looks exactly like a Game: reset() and step().
A plan is a list of actions, e.g.
  [{"tool": "stage", "op": "move_item", "item": "iron key", "to": "cell/rug"}]
"""
import copy
import re


class PlanError(ValueError):
    """The plan is malformed. The message is fed back to the DM so it can fix it."""


# --- Stage and Chain: rewrite the starting world -----------------------------

def _locations(world):
    """Every valid place an item can be: 'room' or 'room/feature'."""
    places = set()
    for name, room in world["rooms"].items():
        places.add(name)
        places.update(f"{name}/{f}" for f in room["features"])
    return places


def _move_item(world, item, to):
    if item not in world["items"]:
        raise PlanError(f"move_item: no item {item!r}. Items: {sorted(world['items'])}")
    if to not in _locations(world):
        raise PlanError(f"move_item: bad location {to!r}. Valid: {sorted(_locations(world))}")
    world["items"][item]["at"] = to


def _add_item(world, item, at, desc="", takeable=True):
    if item in world["items"]:
        raise PlanError(f"add_item: {item!r} already exists")
    if at not in _locations(world):
        raise PlanError(f"add_item: bad location {at!r}. Valid: {sorted(_locations(world))}")
    world["items"][item] = {"at": at, "desc": desc or f"A {item}.", "takeable": bool(takeable)}


def _extend_path(world, room, direction, count):
    """Insert `count` filler rooms on the exit `direction` of `room`."""
    exits = world["rooms"].get(room, {}).get("exits", {})
    if direction not in exits or "door" in exits[direction]:
        raise PlanError(f"extend_path: {room!r} has no plain exit {direction!r}")
    count = int(count)
    if not 1 <= count <= 4:
        raise PlanError("extend_path: count must be 1-4")
    back = {"north": "south", "south": "north", "east": "west", "west": "east"}[direction]
    target = exits[direction]["to"]
    here, names = room, [f"{room}-passage-{i + 1}" for i in range(count)]
    for name in names:
        world["rooms"][name] = {
            "desc": "A narrow, twisting passage. The walls look identical in every direction.",
            "exits": {back: {"to": here}}, "features": {},
        }
        world["rooms"][here]["exits"][direction] = {"to": name}
        here = name
    world["rooms"][here]["exits"][direction] = {"to": target}
    world["rooms"][target]["exits"][back] = {"to": here}


def _lie(world, room, text):
    if room not in world["rooms"]:
        raise PlanError(f"lie: no room {room!r}")
    world["rooms"][room]["desc"] += " " + text


CONTRACTS = {"look_cooldown", "second_key", "pest", "lie"}

TOOLS = {  # shown to the DM so it knows its options
    "stage": [
        {"op": "move_item", "item": "<item>", "to": "<room> or <room>/<feature>"},
        {"op": "add_item", "item": "<new name>", "at": "<room> or <room>/<feature>",
         "desc": "<text>", "takeable": True},
    ],
    "chain": [{"op": "extend_path", "room": "<room>", "direction": "<dir>", "count": "1-4"}],
    "contract": [
        {"op": "look_cooldown", "note": "'look' only works on odd-numbered moves"},
        {"op": "second_key", "item": "<existing item>", "note": "door needs this item too"},
        {"op": "pest", "item": "<existing item>",
         "note": "while that item is in the player's room, the first 'take' there fails"},
        {"op": "lie", "room": "<room>", "text": "<false sentence added to the description>"},
    ],
}


def rig_world(world, plan):
    """Apply Stage/Chain/lie actions to a copy of the world; return it."""
    world = copy.deepcopy(world)
    for action in plan:
        tool, op = action.get("tool"), action.get("op")
        args = {k: v for k, v in action.items() if k not in ("tool", "op", "reason")}
        try:
            if (tool, op) == ("stage", "move_item"):
                _move_item(world, **args)
            elif (tool, op) == ("stage", "add_item"):
                _add_item(world, **args)
            elif (tool, op) == ("chain", "extend_path"):
                _extend_path(world, **args)
            elif (tool, op) == ("contract", "lie"):
                _lie(world, **args)
            elif tool == "contract" and op in CONTRACTS:
                pass  # enforced at play time by Harness.step
            else:
                raise PlanError(f"unknown action {tool}/{op}")
        except TypeError as err:
            raise PlanError(f"{tool}/{op}: bad arguments ({err})")
    for action in plan:  # contracts must refer to things that exist
        if action.get("tool") == "contract" and action.get("op") in ("second_key", "pest"):
            if action.get("item") not in world["items"]:
                raise PlanError(f"{action['op']}: no item {action.get('item')!r}")
    return world


# --- Contract: rules enforced while playing ----------------------------------

class Harness:
    """Wraps a Game. Same interface (reset/step), plus the plan's rules."""

    def __init__(self, game, plan=()):
        self.game = game
        self.plan = list(plan)
        self.base_world = game.base_world
        self.rigged_world = rig_world(self.base_world, self.plan)
        self.contracts = {a["op"]: a for a in self.plan if a.get("tool") == "contract"}

    def __getattr__(self, name):  # moves, won, room, world... come from the game
        if name == "game" or name.startswith("__"):  # avoid recursion while copying
            raise AttributeError(name)
        return getattr(self.game, name)

    def reset(self):
        self.pest_fired = False
        return self.game.reset(self.rigged_world)

    def step(self, command):
        blocked = self._contract_block(command.lower().strip())
        if blocked:
            self.game.moves += 1
            return blocked, False
        return self.game.step(command)

    def _contract_block(self, command):
        g = self.game
        if "look_cooldown" in self.contracts and command in ("look", "l") and (g.moves + 1) % 2 == 0:
            return "Your head swims. You can't look around right now."

        if "pest" in self.contracts and not self.pest_fired and command.split()[:1] in (["take"], ["get"]):
            pest = self.contracts["pest"]["item"]
            if g.world["items"][pest]["at"] == g.room:
                self.pest_fired = True
                return f"The {pest} honks furiously and lunges at your hand. You flinch."

        if "second_key" in self.contracts:
            match = re.match(r"use (.+) on door$", command)
            if match:
                held = g._items_at("inventory")
                key, extra = g._find(match.group(1), held), self.contracts["second_key"]["item"]
                _, ex = g._door()
                if ex and key == ex["door"]["locked_by"] and ex["door"]["locked"] and extra not in held:
                    return "The lock has two keyholes. One key isn't enough."
        return None
