"""Play the game yourself: python play.py"""
from game import Game, HELP

game = Game()
print(game.reset())
print(f"\n{HELP}\n")
done = False
while not done:
    try:
        command = input("> ")
    except (EOFError, KeyboardInterrupt):
        break
    obs, done = game.step(command)
    print(obs, "\n")
print(f"Moves taken: {game.moves}")
