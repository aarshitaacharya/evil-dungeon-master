"""One tiny client for any OpenAI-compatible chat API (Groq, OpenRouter, NIM, ...).

Each AI role ("PLAYER", "DM") is configured by three env vars, so swapping a
model or provider is a one-line change in .env:

    <ROLE>_BASE_URL, <ROLE>_API_KEY, <ROLE>_MODEL
"""
import json
import os
import re
import time
import urllib.error
import urllib.request
from pathlib import Path


def load_env(path=".env"):
    """Read KEY=VALUE lines from .env into os.environ (real env vars win)."""
    file = Path(__file__).parent / path
    if not file.exists():
        return
    for line in file.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip())


def chat(role, messages, temperature=0.7, retries=6):
    """Send chat messages as the given role; return the reply text."""
    load_env()
    base = os.environ[f"{role}_BASE_URL"].rstrip("/")
    key = os.environ.get(f"{role}_API_KEY", "")
    if not key:
        raise RuntimeError(f"{role}_API_KEY is empty. Fill it in .env")
    body = json.dumps({
        "model": os.environ[f"{role}_MODEL"],
        "messages": messages,
        "temperature": temperature,
    }).encode()
    request = urllib.request.Request(
        f"{base}/chat/completions",
        data=body,
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json",
                 "User-Agent": "evil-dungeon-master/0.1"},
    )
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                return json.load(response)["choices"][0]["message"]["content"]
        except urllib.error.HTTPError as err:
            # Free tiers rate-limit hard: back off and retry on 429 / 5xx.
            detail = err.read().decode()
            if err.code in (429, 500, 502, 503) and attempt < retries - 1:
                hint = re.search(r"try again in ([\d.]+)s", detail)  # servers often say how long
                time.sleep(float(hint.group(1)) + 1 if hint else 2 ** attempt * 2)
                continue
            raise RuntimeError(f"{role} API error {err.code}: {detail[:300]}")
