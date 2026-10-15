"""The Evil DM: reads how the Player did and rigs the next round.

It never touches the game. It only emits a plan (JSON) that harness.py applies.
"""
import json
import re

from harness import TOOLS, PlanError, rig_world
from llm import chat

SYSTEM_PROMPT = """You are the Evil Dungeon Master. A Player AI is trying to escape a small text-adventure dungeon. After each round you study its trajectory, find what it is bad at, and rig the next round to exploit exactly that weakness.

You are evil but fair: the dungeon must stay winnable. Never make the key unreachable.
Think like a coach drilling a weak backhand: if it grabs the first item it sees, plant a decoy; if it never searches things, hide the key under something; if it gives up early or wanders, make the path longer; if it relies on 'look', limit it.

Each round's plan is applied to the ORIGINAL dungeon, not to the previous rigged one. Re-include anything you still want. Use 1 to 3 actions.

Available actions (tool -> ops):
{tools}

Reply with ONLY a JSON object, no other text:
{{"analysis": "<what the Player is bad at, citing evidence from the log>",
  "actions": [{{"tool": "...", "op": "...", ...args, "reason": "<why this exploits the weakness>"}}]}}"""


def describe_world(world):
    rooms = {n: {"exits": list(r["exits"]), "features": list(r["features"])} for n, r in world["rooms"].items()}
    items = {n: i["at"] for n, i in world["items"].items()}
    return json.dumps({"rooms": rooms, "item_locations": items})


def summarize(round_record):
    """Compress one round into text the DM can read."""
    t = round_record["trajectory"]
    commands = [turn["command"] for turn in t["turns"]]
    lines = [f"{turn['move']}. {turn['command']} -> {turn['result'].splitlines()[0]}" for turn in t["turns"]]
    repeats = len(commands) - len(set(commands))
    searches = [c for c in commands if c.split()[0] in ("search", "examine", "inspect")]
    return (f"Round {round_record['round']}: {'WON' if t['won'] else 'LOST'} in {t['moves']} moves. "
            f"Repeated commands: {repeats}. Searches: {len(searches)}.\n"
            f"Plan used: {json.dumps(round_record['plan'])}\n" + "\n".join(lines))


def extract_json(text):
    """Models wrap JSON in prose and code fences. Find the outermost {...}."""
    text = re.sub(r"```(?:json)?", "", text)
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end <= start:
        raise ValueError("no JSON object found")
    return json.loads(text[start:end + 1])


def propose_plan(history, base_world, ask=None, attempts=3):
    """Ask the DM for a plan; validate it; feed errors back and retry.

    Returns (plan_dict, notes). Falls back to an empty plan if the DM keeps failing.
    """
    ask = ask or (lambda messages: chat("DM", messages, temperature=0.9))
    context = f"Dungeon layout and starting item locations:\n{describe_world(base_world)}\n\n"
    if history:
        context += "Previous rounds (most recent last):\n" + "\n\n".join(summarize(r) for r in history[-2:])
        context += "\n\nDesign the next round."
    else:
        context += "No rounds yet. Design the first round."
    messages = [{"role": "system", "content": SYSTEM_PROMPT.format(tools=json.dumps(TOOLS, indent=1))},
                {"role": "user", "content": context}]
    notes = []
    for _ in range(attempts):
        reply = ask(messages)
        try:
            plan = extract_json(reply)
            rig_world(base_world, plan.get("actions", []))  # validate by dry run
            return {"analysis": plan.get("analysis", ""), "actions": plan["actions"]}, notes
        except (ValueError, KeyError, AttributeError, TypeError, PlanError) as err:
            notes.append(f"DM broke format: {err}")
            messages += [{"role": "assistant", "content": reply},
                         {"role": "user", "content": f"Invalid: {err}. Reply again with ONLY the corrected JSON."}]
    return {"analysis": "(DM failed to produce a valid plan; no rigging)", "actions": []}, notes
