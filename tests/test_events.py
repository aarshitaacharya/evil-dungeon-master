import json
import unittest
from main import run

WIN = iter([])


def player(script):
    """A scripted Player that wins in 7 moves, then repeats."""
    it = iter(script)
    return lambda messages: next(it, "look")


WIN_SCRIPT = ["go north", "go east", "take key", "go west", "use key on door", "open door", "go north"]
DM_PLAN = json.dumps({"analysis": "hide it", "actions": [
    {"tool": "stage", "op": "move_item", "item": "iron key", "to": "study/chest", "reason": "r"}]})


class EventsTest(unittest.TestCase):
    def test_event_stream_shape(self):
        events = []
        run(2, events.append, dm_ask=lambda m: DM_PLAN, player_ask=player(WIN_SCRIPT * 2))
        types = [e["type"] for e in events]
        self.assertEqual(types[0], "run_start")
        self.assertEqual(types[-1], "run_end")
        self.assertEqual(types.count("round_start"), 2)
        self.assertEqual(types.count("dm_thinking"), 1)  # round 1 is the baseline
        setup2 = [e for e in events if e["type"] == "round_setup"][1]
        self.assertEqual(setup2["world"]["items"]["iron key"]["at"], "study/chest")
        self.assertEqual(setup2["par"], 8)

    def test_turns_carry_a_drawable_state(self):
        events = []
        run(1, events.append, player_ask=player(WIN_SCRIPT))
        turns = [e for e in events if e["type"] == "turn"]
        self.assertEqual(turns[0]["state"]["room"], "hallway")
        self.assertEqual(turns[2]["state"]["items"]["iron key"], "inventory")
        self.assertTrue(turns[-1]["state"]["won"])
        json.dumps(events)  # everything must be JSON-serializable

    def test_summary(self):
        events = []
        run(2, events.append, dm_ask=lambda m: DM_PLAN, player_ask=player(WIN_SCRIPT * 2))
        rows = events[-1]["summary"]["rows"]
        self.assertEqual([r["par"] for r in rows], [7, 8])


if __name__ == "__main__":
    unittest.main()
