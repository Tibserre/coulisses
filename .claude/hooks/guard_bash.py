#!/usr/bin/env python3
"""PreToolUse guard for Bash: protects real user data and git hygiene.

Exit 2 blocks the command and sends stderr back to Claude.
"""

import json
import re
import sys

# Real user data (ADR 0010). Also the former location, in case old data remains there.
REAL_DATA_DIR = re.compile(r"Coulisses/Donn(é|e\u0301)es(?!-dev)|Application[ \\]+Support/Coulisses(?!-dev)")
DESTRUCTIVE = re.compile(
    r"\b(rm|rmdir|mv|shred|truncate|trash|unlink)\b|>\s*[^&]|\b(DELETE|DROP|UPDATE|INSERT|VACUUM)\b",
    re.IGNORECASE,
)

RULES = [
    (
        re.compile(r"\bgit\s+commit\b.*--no-verify|\bgit\s+commit\b.*\s-n\b"),
        "Le hook pre-commit protège contre le commit d'audio et de données réelles : ne le contourne pas.",
    ),
    (
        re.compile(r"\bgit\s+push\b.*(--force|\s-f\b)"),
        "Pas de push forcé.",
    ),
    (
        re.compile(r"\bgit\s+add\b.*(\s-f\b|--force)"),
        "`git add -f` contourne le .gitignore, qui empêche d'ajouter de l'audio ou des données.",
    ),
    (
        # Writes only: reading the value (--get, --list, bare key) stays allowed.
        re.compile(
            r"\bgit\s+config\b(?!.*(--get\b|--list\b|\s-l\b))(?=.*core\.hooksPath)"
            r"(?=.*(--unset|--add\b|--replace-all\b|core\.hooksPath\s+[^\s|;&]))"
        ),
        "Ne modifie pas core.hooksPath : il active le hook pre-commit du projet.",
    ),
    (
        re.compile(r"(^|[\s;&|])(pip3?|python3?\s+-m\s+pip)\s+install\b"),
        "Utilise `uv add <paquet>` (ou `uv pip` dans le venv uv), jamais pip directement.",
    ),
    (
        re.compile(r"\bpython3?\s+-m\s+venv\b|\bvirtualenv\b"),
        "L'environnement est géré par uv (`uv sync` dans engine/).",
    ),
]


def block(msg: str) -> None:
    print(f"[garde-fou Coulisses] {msg}", file=sys.stderr)
    sys.exit(2)


def main() -> None:
    payload = json.load(sys.stdin)
    cmd = payload.get("tool_input", {}).get("command", "") or ""

    if REAL_DATA_DIR.search(cmd) and DESTRUCTIVE.search(cmd):
        block(
            "P8 : commande potentiellement destructrice sur le dossier de données réel. "
            "Seule l'app (purge, suppression confirmée) touche à ces données. "
            "Travaille dans Coulisses-dev ou un dossier temporaire."
        )

    for pattern, msg in RULES:
        if pattern.search(cmd):
            block(msg)

    sys.exit(0)


if __name__ == "__main__":
    main()
