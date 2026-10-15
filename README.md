# Evil Dungeon Master

An adversarial environment-design project. A **Player** agent plays a small text
adventure (find the key, open the door). An **Evil DM** agent reads the Player's
trajectories, identifies where it struggles, and rigs the next round to exploit
those weaknesses: relocating the key, planting decoys, adding obstacles.

The design is inspired by Google's EnvHarness: a wrapper that changes an
environment's starting state and rules without modifying the environment's own
code. A judge verifies every rigged round is still winnable.

## Run

```bash
cp .env.example .env     # add your API keys (any OpenAI-compatible provider)
python3 main.py 5        # play 5 rounds in the terminal; writes logs/<run>/events.jsonl
python3 play.py          # or play the dungeon yourself
python3 -m unittest discover -s tests -t .
```

## Watch a replay in the browser

```bash
python3 serve.py         # then open http://localhost:8000
```

The viewer plays back any `events.jsonl` (a bundled demo is in `replays/`). It makes no AI calls.
Controls: space = pause, slider = scrub, `?speed=4` sets playback speed.

The pixel art is the [Pixel_Poem Dungeon Asset Pack](https://pixel-poem.itch.io/dungeon-assetpuck),
which cannot be redistributed. Download it and unzip it into the project root so these folders exist:
`2D Pixel Dungeon Asset Pack/` and `Enemy_Animations_Set/`.
