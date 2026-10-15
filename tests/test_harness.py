import unittest
from dm import extract_json, propose_plan
from game import DEFAULT_WORLD, Game
from harness import Harness, PlanError, rig_world
from player import run_episode

WIN = ["go north", "go east", "take key", "go west", "use key on door", "open door", "go north"]


def play(plan, script):
    it = iter(script)
    return run_episode(Harness(Game(), plan), ask=lambda m: next(it, "look"), max_moves=len(script))


class HarnessTest(unittest.TestCase):
    def test_stage_moves_key_and_original_is_untouched(self):
        plan = [{"tool": "stage", "op": "move_item", "item": "iron key", "to": "study/chest"}]
        world = rig_world(DEFAULT_WORLD, plan)
        self.assertEqual(world["items"]["iron key"]["at"], "study/chest")
        self.assertEqual(DEFAULT_WORLD["items"]["iron key"]["at"], "study")

    def test_hidden_key_breaks_old_path(self):
        plan = [{"tool": "stage", "op": "move_item", "item": "iron key", "to": "study/chest"}]
        self.assertFalse(play(plan, WIN)["won"])
        self.assertTrue(play(plan, WIN[:2] + ["search chest"] + WIN[2:])["won"])

    def test_bad_plan_raises(self):
        with self.assertRaises(PlanError):
            rig_world(DEFAULT_WORLD, [{"tool": "stage", "op": "move_item", "item": "key", "to": "moon"}])
        with self.assertRaises(PlanError):
            rig_world(DEFAULT_WORLD, [{"tool": "chaos", "op": "x"}])

    def test_forgiving_about_tool_name_and_bare_feature(self):
        plan = [{"tool": "chain", "op": "move_item", "item": "iron key", "to": "chest"}]   # wrong tool, bare feature
        world = rig_world(DEFAULT_WORLD, plan)
        self.assertEqual(world["items"]["iron key"]["at"], "study/chest")
        self.assertEqual(plan[0]["tool"], "stage")
        with self.assertRaises(PlanError):
            rig_world(DEFAULT_WORLD, [{"op": "add_item", "item": "iron key", "at": "cell"}])  # already exists

    def test_extend_path_lengthens_route(self):
        plan = [{"tool": "chain", "op": "extend_path", "room": "hallway", "direction": "east", "count": 2}]
        script = ["go north", "go east", "go east", "go east", "take key", "go west", "go west", "go west",
                  "use key on door", "open door", "go north"]
        self.assertTrue(play(plan, script)["won"])

    def test_second_key_contract(self):
        plan = [{"tool": "stage", "op": "add_item", "item": "brass key", "at": "cell"},
                {"tool": "contract", "op": "second_key", "item": "brass key"}]
        self.assertFalse(play(plan, WIN)["won"])
        self.assertTrue(play(plan, ["take brass key"] + [c.replace("use key", "use iron key") for c in WIN])["won"])

    def test_look_cooldown_and_pest(self):
        h = Harness(Game(), [{"tool": "contract", "op": "look_cooldown"}])
        h.reset()
        self.assertIn("damp", h.step("look")[0])
        self.assertIn("head swims", h.step("look")[0])

    def test_extract_json_handles_chatty_models(self):
        self.assertEqual(extract_json('Sure!\n```json\n{"a": 1}\n```\nEnjoy'), {"a": 1})

    def test_dm_retries_then_falls_back(self):
        replies = iter(["no json here", '{"analysis": "x", "actions": [{"tool": "stage", "op": "move_item", "item": "iron key", "to": "cell/crate"}]}'])
        plan, notes = propose_plan([], DEFAULT_WORLD, ask=lambda m: next(replies))
        self.assertEqual(len(notes), 1)
        self.assertEqual(plan["actions"][0]["to"], "cell/crate")
        plan, notes = propose_plan([], DEFAULT_WORLD, ask=lambda m: "garbage", attempts=2)
        self.assertEqual(plan["actions"], [])


if __name__ == "__main__":
    unittest.main()
