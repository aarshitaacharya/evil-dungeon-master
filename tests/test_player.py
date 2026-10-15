import unittest
from game import Game
from player import VALID_COMMAND, parse_command, run_episode


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

    def test_validator_rejects_garbage(self):
        for ok in ["go north", "take iron key", "use iron key on door", "open door", "look", "north"]:
            self.assertTrue(VALID_COMMAND.match(ok), ok)
        for bad in ["look<|message|>look", "open doorgo northwe need", "use", "use iron key on",
                    "search northsearch eastgo southsearch rugtake keygo northuse key on door", ""]:
            self.assertFalse(VALID_COMMAND.match(bad), bad)

    def test_garbage_is_reasked_and_kept_out_of_history(self):
        replies = iter(["look<|message|>look", "go north"])
        seen = []
        def ask(messages):
            seen.append(messages)
            return next(replies, "look")
        trajectory = run_episode(Game(), ask=ask, max_moves=1)
        self.assertEqual(trajectory["turns"][0]["command"], "go north")
        self.assertEqual(trajectory["turns"][0]["retries"], 1)

    def test_gives_up_at_move_limit(self):
        trajectory = run_episode(Game(), ask=lambda m: "look", max_moves=5)
        self.assertFalse(trajectory["won"])
        self.assertEqual(trajectory["moves"], 5)


if __name__ == "__main__":
    unittest.main()
