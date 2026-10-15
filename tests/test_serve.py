import unittest
from pathlib import Path
from serve import Handler, ROOT, list_replays


class ServeTest(unittest.TestCase):
    def path(self, url):
        return Path(Handler.translate_path(Handler.__new__(Handler), url))

    def test_ui_files_are_served(self):
        self.assertEqual(self.path("/"), ROOT / "ui" / "index.html")
        self.assertEqual(self.path("/app.js"), ROOT / "ui" / "app.js")

    def test_traversal_is_blocked(self):
        for url in ["/../game.py", "/%2e%2e/.env", "/replay/.env", "/replay/replays/../.env",
                    "/assets/pack/../.env"]:
            self.assertEqual(self.path(url).name, "__forbidden__", url)

    def test_replay_listing_finds_the_demo(self):
        self.assertIn("replays/demo", [r["name"] for r in list_replays()])


if __name__ == "__main__":
    unittest.main()
