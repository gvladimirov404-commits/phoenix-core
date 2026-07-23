#!/usr/bin/env python3
"""Patch phoenix_core/telegram/bot.py so long AI responses are split into
multiple Telegram messages instead of crashing with 'Message is too long'.

Safe to run multiple times (idempotent — checks if already patched).
Creates a .bak backup before writing.
"""
import re
import sys

PATH = "phoenix_core/telegram/bot.py"

with open(PATH, "r", encoding="utf-8") as f:
    content = f.read()

if "_split_for_telegram" in content:
    print("Already patched — no changes made.")
    sys.exit(0)

helper = '''

TELEGRAM_MESSAGE_LIMIT = 4096


def _split_for_telegram(text: str, limit: int = TELEGRAM_MESSAGE_LIMIT) -> list[str]:
    """Split text into chunks that fit Telegram's per-message character limit.

    Prefers splitting on paragraph/line boundaries; falls back to a hard
    cut only if a single line itself exceeds the limit.
    """
    if len(text) <= limit:
        return [text]

    chunks: list[str] = []
    current = ""
    for line in text.split("\\n"):
        candidate = f"{current}\\n{line}" if current else line
        if len(candidate) <= limit:
            current = candidate
        else:
            if current:
                chunks.append(current)
            if len(line) <= limit:
                current = line
            else:
                for i in range(0, len(line), limit):
                    chunks.append(line[i : i + limit])
                current = ""
    if current:
        chunks.append(current)
    return chunks
'''

import_matches = list(re.finditer(r"^(from .+|import .+)$", content, re.MULTILINE))
if not import_matches:
    print("ERROR: could not find import block to anchor the helper function.")
    sys.exit(1)
last_import_end = import_matches[-1].end()
content = content[:last_import_end] + helper + content[last_import_end:]

pattern = re.compile(r"^([ \t]*)await message\.reply_text\(response\)[ \t]*$", re.MULTILINE)
match = pattern.search(content)
if not match:
    print("ERROR: could not find 'await message.reply_text(response)' line to patch.")
    sys.exit(1)

indent = match.group(1)
replacement = (
    f"{indent}for _chunk in _split_for_telegram(response):\n"
    f"{indent}    await message.reply_text(_chunk)"
)
content = pattern.sub(replacement, content, count=1)

with open(PATH + ".bak", "w", encoding="utf-8") as f:
    f.write(open(PATH, encoding="utf-8").read())

with open(PATH, "w", encoding="utf-8") as f:
    f.write(content)

print("Patched successfully. Backup saved to", PATH + ".bak")
