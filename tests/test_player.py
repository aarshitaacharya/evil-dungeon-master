import unittest
from game import Game
from player import parse_command, run_episode


class PlayerTest(unittest.TestCase):
    def test_parse_command(self):
        self.assertEqual(parse_command("> Go North."), "go north")
        self.assertEqual(parse_command("```\ntake key\n```"), "take key")
        self.assertEqual(parse_command("Sure!\ngo north"), "sure!")
        self.assertEqual(parse_command(""), "look")

    def test_loop_with_scripted_model(self):
        script = iter(["go north", "go east", "take key", "go west",
                       "use key on door", "open door", "go north"])
        trajectory = run_episode(Game(), ask=lambda messages: next(script))
        self.assertTrue(trajectory["won"])
        self.assertEqual(trajectory["moves"], 7)

    def test_gives_up_at_move_limit(self):
        trajectory = run_episode(Game(), ask=lambda m: "look", max_moves=5)
        self.assertFalse(trajectory["won"])
        self.assertEqual(trajectory["moves"], 5)


if __name__ == "__main__":
    unittest.main()
