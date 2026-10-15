import unittest
from game import Game


class GameTest(unittest.TestCase):
    def test_winning_path(self):
        g = Game()
        g.reset()
        for cmd in ["go north", "go east", "take key", "go west",
                    "use key on door", "open door", "go north"]:
            obs, done = g.step(cmd)
        self.assertTrue(done)
        self.assertEqual(g.moves, 7)

    def test_locked_door_blocks(self):
        g = Game()
        g.reset()
        g.step("go north")
        self.assertIn("locked", g.step("go north")[0])
        self.assertIn("locked", g.step("open door")[0])

    def test_hidden_item_needs_search(self):
        world = {**Game().base_world}
        world["items"] = {"iron key": {"at": "cell/crate", "desc": "", "takeable": True}}
        g = Game(world)
        self.assertNotIn("key", g.step("look")[0])
        self.assertIn("no key", g.step("take key")[0])
        g.step("search crate")
        self.assertIn("take the iron key", g.step("take key")[0])

    def test_reset_restores_world(self):
        g = Game()
        g.reset()
        g.step("go north"); g.step("go east"); g.step("take key")
        g.reset()
        self.assertEqual(g.room, "cell")
        self.assertEqual(g.moves, 0)
        self.assertEqual(g.world["items"]["iron key"]["at"], "study")


if __name__ == "__main__":
    unittest.main()
