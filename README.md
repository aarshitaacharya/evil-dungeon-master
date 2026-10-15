# Evil Dungeon Master

An adversarial environment-design project. A **Player** agent plays a small text
adventure (find the key, open the door). An **Evil DM** agent reads the Player's
trajectories, identifies where it struggles, and rigs the next round to exploit
those weaknesses: relocating the key, planting decoys, adding obstacles.

The design is inspired by Google's EnvHarness: a wrapper that changes an
environment's starting state and rules without modifying the environment's own
code. A judge verifies every rigged round is still winnable.
