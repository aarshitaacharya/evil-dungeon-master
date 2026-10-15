"""The world: a tiny text adventure with no AI in it.

The world is plain data (a dict). A Game holds one copy of it and exposes the
standard environment interface:

    reset(world=None) -> observation
    step(command)     -> (observation, done)

Everything the Evil DM can later change (item locations, door rules, extra
objects) lives in the world dict, so it can be rigged from the outside without
touching this file.
"""
import copy

DIRECTIONS = ("north", "south", "east", "west")

# Items whose "at" is "<room>" lie in the open. "<room>/<feature>" means hidden
# inside that feature until the player searches it. "inventory" means carried.
DEFAULT_WORLD = {
    "start": "cell",
    "rooms": {
        "cell": {
            "desc": "A damp stone cell. The only way out is a doorway to the north.",
            "exits": {"north": {"to": "hallway"}},
            "features": {"crate": "A splintered wooden crate sits in the corner."},
        },
        "hallway": {
            "desc": "A dusty hallway lit by flickering torches.",
            "exits": {
                "south": {"to": "cell"},
                "east": {"to": "study"},
                "north": {
                    "to": "outside",
                    "door": {"locked_by": "iron key", "locked": True, "open": False},
                },
            },
            "features": {"shelf": "A crooked shelf of dusty flasks leans against the wall."},
        },
        "study": {
            "desc": "A cramped study smelling of old ink.",
            "exits": {"west": {"to": "hallway"}},
            "features": {"chest": "A heavy iron-banded chest sits against the wall."},
        },
    },
    "items": {
        "iron key": {"at": "study", "desc": "A heavy iron key.", "takeable": True},
        "candle": {"at": "cell", "desc": "A stub of candle.", "takeable": True},
    },
}

HELP = (
    "Commands: look | go <direction> | take <item> | search <thing> | "
    "open door | use <item> on door | inventory | help"
)


class Game:
    def __init__(self, world=None):
        self.base_world = world if world is not None else DEFAULT_WORLD
        self.reset()

    # -- environment interface ------------------------------------------------

    def reset(self, world=None):
        """Start a fresh game and return the first observation."""
        if world is not None:
            self.base_world = world
        self.world = copy.deepcopy(self.base_world)
        self.room = self.world["start"]
        self.moves = 0
        self.won = False
        return self._describe()

    def step(self, command):
        """Run one command. Returns (observation, done)."""
        if self.won:
            return "The game is over. You already escaped.", True
        self.moves += 1
        words = command.lower().strip().split()
        if not words:
            return "Say something.", False
        verb, rest = words[0], " ".join(words[1:])

        if verb in ("look", "l") and not rest:
            obs = self._describe()
        elif verb == "go" or verb in DIRECTIONS:
            obs = self._go(rest if verb == "go" else verb)
        elif verb in ("take", "get"):
            obs = self._take(rest)
        elif verb in ("search", "examine", "inspect") or (verb == "look" and rest):
            obs = self._search(rest.removeprefix("under ").removeprefix("at "))
        elif verb == "open" and rest == "door":
            obs = self._open_door()
        elif verb == "use":
            obs = self._use(rest)
        elif verb in ("inventory", "inv", "i"):
            held = self._items_at("inventory")
            obs = "You carry: " + ", ".join(held) + "." if held else "You carry nothing."
        elif verb == "help":
            obs = HELP
        else:
            obs = f"You can't do that. {HELP}"
        return obs, self.won

    def snapshot(self):
        """Everything a viewer needs to draw the current state (no game logic required)."""
        doors = {f"{room}:{d}": dict(ex["door"])
                 for room, r in self.world["rooms"].items()
                 for d, ex in r["exits"].items() if "door" in ex}
        return {"room": self.room, "moves": self.moves, "won": self.won,
                "items": {n: i["at"] for n, i in self.world["items"].items()}, "doors": doors}

    # -- helpers ----------------------------------------------------------------

    def _items_at(self, place):
        return [n for n, i in self.world["items"].items() if i["at"] == place]

    def _find(self, name, candidates):
        """Match 'key' to 'iron key': exact name first, then a unique word match."""
        name = name.strip()
        if name in candidates:
            return name
        hits = [c for c in candidates if name and name in c.split()]
        return hits[0] if len(hits) == 1 else None

    def _door(self):
        """The (direction, exit) of this room's door, or (None, None)."""
        for direction, ex in self.world["rooms"][self.room]["exits"].items():
            if "door" in ex:
                return direction, ex
        return None, None

    def _describe(self):
        room = self.world["rooms"][self.room]
        lines = [room["desc"]]
        lines += room["features"].values()
        for name in self._items_at(self.room):
            lines.append(f"You see a {name} here.")
        for direction, ex in room["exits"].items():
            door = ex.get("door")
            if door:
                state = "locked" if door["locked"] else "open" if door["open"] else "closed"
                lines.append(f"A {state} door leads {direction}.")
            else:
                lines.append(f"An exit leads {direction}.")
        return "\n".join(lines)

    def _go(self, direction):
        ex = self.world["rooms"][self.room]["exits"].get(direction)
        if ex is None:
            return "You can't go that way."
        door = ex.get("door")
        if door and door["locked"]:
            return "The door is locked."
        if door and not door["open"]:
            return "The door is closed."
        if ex["to"] == "outside":
            self.won = True
            return "You step through the door into the open air. You escaped!"
        self.room = ex["to"]
        return self._describe()

    def _take(self, name):
        item = self._find(name, self._items_at(self.room))
        if item is None:
            return f"There is no {name} here."
        if not self.world["items"][item]["takeable"]:
            return f"You can't take the {item}."
        self.world["items"][item]["at"] = "inventory"
        return f"You take the {item}."

    def _search(self, name):
        room = self.world["rooms"][self.room]
        feature = self._find(name, room["features"])
        if feature is None:
            item = self._find(name, self._items_at(self.room) + self._items_at("inventory"))
            if item:
                return self.world["items"][item]["desc"]
            return f"You see no {name} to search."
        found = self._items_at(f"{self.room}/{feature}")
        for item in found:
            self.world["items"][item]["at"] = self.room
        if found:
            return f"You search the {feature} and find: {', '.join(found)}."
        return f"You search the {feature}. Nothing."

    def _open_door(self):
        direction, ex = self._door()
        if ex is None:
            return "There is no door here."
        door = ex["door"]
        if door["locked"]:
            return "The door is locked."
        if door["open"]:
            return "The door is already open."
        door["open"] = True
        return f"The door swings open to the {direction}."

    def _use(self, rest):
        if " on " not in rest:
            return "Use what on what? Try: use <item> on door"
        name, target = (s.strip() for s in rest.split(" on ", 1))
        item = self._find(name, self._items_at("inventory"))
        if item is None:
            return f"You don't have a {name}."
        if target != "door":
            return "That does nothing."
        _, ex = self._door()
        if ex is None:
            return "There is no door here."
        door = ex["door"]
        if not door["locked"]:
            return "The door is not locked."
        if door["locked_by"] != item:
            return f"The {item} doesn't fit."
        door["locked"] = False
        return f"The {item} turns with a click. The door is unlocked."
