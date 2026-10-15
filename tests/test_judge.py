import unittest
from dm import propose_plan
from game import DEFAULT_WORLD
from judge import check

UNFAIR = [{"tool": "stage", "op": "add_item", "item": "brass key", "at": "cell", "takeable": False},
          {"tool": "contract", "op": "second_key", "item": "brass key"}]


class JudgeTest(unittest.TestCase):
    def test_default_world_par_is_7(self):
        v = check(DEFAULT_WORLD, [])
        self.assertTrue(v.winnable)
        self.assertEqual(v.par, 7)

    def test_hidden_key_adds_a_search(self):
        plan = [{"tool": "stage", "op": "move_item", "item": "iron key", "to": "cell/crate"}]
        self.assertIn("search crate", check(DEFAULT_WORLD, plan).path)

    def test_chain_lengthens_par(self):
        plan = [{"tool": "chain", "op": "extend_path", "room": "hallway", "direction": "east", "count": 2}]
        self.assertEqual(check(DEFAULT_WORLD, plan).par, 11)

    def test_catches_unwinnable(self):
        self.assertFalse(check(DEFAULT_WORLD, UNFAIR).winnable)

    def test_dm_is_sent_back_when_judge_rejects(self):
        import json
        bad = json.dumps({"analysis": "mwahaha", "actions": UNFAIR})
        good = json.dumps({"analysis": "ok", "actions": []})
        replies = iter([bad, good])
        plan, notes = propose_plan([], DEFAULT_WORLD, ask=lambda m: next(replies),
                                   judge=lambda a: check(DEFAULT_WORLD, a))
        self.assertEqual(plan["analysis"], "ok")
        self.assertIn("UNWINNABLE", notes[0])


if __name__ == "__main__":
    unittest.main()
