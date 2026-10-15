"""The Evil DM: reads how the Player did and rigs the next round.

It never touches the game. It only emits a plan (JSON) that harness.py applies.
"""
import json
import re

from harness import TOOLS, PlanError, rig_world
from llm import chat

SYSTEM_PROMPT = """You are the Evil Dungeon Master. A Player AI is trying to escape a small text-adventure dungeon. After each round you study its trajectory, find what it is bad at, and rig the next round to exploit exactly that weakness.

The Player has only 25 moves per round. If it has not escaped by then it LOSES, and making that happen is your goal. You are evil but fair: the judge only approves dungeons that a perfect player can escape within 20 moves, so there is room to make it very hard but never impossible. Never make the key unreachable.
Stack your tricks. Lengthening the path (chain/extend_path) adds up to 8 moves of walking, hiding the key costs searches, decoys and a second key cost wasted trips, a creature with a pest costs retries. If your last plan did not stop the Player, escalate: combine more tricks and attack the weakness it showed.
Think like a coach drilling a weak backhand: if it grabs the first item it sees, plant a decoy; if it never searches things, hide the key inside something (a crate, chest or shelf); if it gives up early or wanders, make the path longer; if it relies on 'look', limit it.

Each round's plan is applied to the ORIGINAL dungeon, not to the previous rigged one. Re-include anything you still want. Use 2 to 4 actions.

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
    return (f"Round {round_record['round']}: {'WON' if t['won'] else 'LOST'} in {t['moves']} moves "
            f"(par {round_record['par']}, so {t['moves'] - round_record['par']} wasted). "
            f"Repeated commands: {repeats}. Searches: {len(searches)}.\n"
            f"Plan used: {json.dumps(round_record['plan'])}\n" + "\n".join(lines))


def extract_json(text):
    """Models wrap JSON in prose and code fences. Find the outermost {...}."""
    text = re.sub(r"```(?:json)?", "", text)
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end <= start:
        raise ValueError("no JSON object found")
    return json.loads(text[start:end + 1])


def propose_plan(history, base_world, ask=None, attempts=3, judge=None):
    """Ask the DM for a plan; validate it (and judge it, if given); feed errors back and retry.

    Returns (plan_dict, notes). Falls back to an empty plan if the DM keeps failing.
    """
    ask = ask or (lambda messages: chat("DM", messages, temperature=0.9))
    context = f"Dungeon layout and starting item locations:\n{describe_world(base_world)}\n\n"
    if history:
        context += "Previous rounds (most recent last):\n" + "\n\n".join(summarize(r) for r in history[-2:])
        context += "\n\nDesign the next round. Try something new if your last trick failed to stop the Player."
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
            if judge:
                verdict = judge(plan["actions"])
                if not verdict.winnable:
                    raise ValueError("the judge says this dungeon is UNWINNABLE (no escape within 20 moves). Be fair: a perfect player must be able to escape in 20 moves or fewer")
            return {"analysis": plan.get("analysis", ""), "actions": plan["actions"]}, notes
        except (ValueError, KeyError, AttributeError, TypeError, PlanError) as err:
            notes.append(f"DM broke format: {err}")
            messages += [{"role": "assistant", "content": reply},
                         {"role": "user", "content": f"Invalid: {err}. Reply again with ONLY the corrected JSON."}]
    return {"analysis": "(DM failed to produce a valid plan; no rigging)", "actions": []}, notes
