#!/usr/bin/env python3
"""PreToolUse guard for Write/Edit/MultiEdit in the application: P1, P4, P6, P8.

The application never touches a model: it uses the engine (coulisses-moteur) by its
contract. So no model library anywhere, network only in the LLM client (prompting/).

Exit 2 blocks the edit and sends stderr back to Claude.
"""

import json
import re
import sys

# Real user data (ADR 0010). Also the former location, in case old data remains there.
REAL_DATA_DIR = re.compile(
    r"Coulisses/Donn(é|é)es(/|$)|Library/Application Support/Coulisses(?!-dev)(/|$)"
)

# P1: network clients only in the LLM client (Ollama on 127.0.0.1). Models are the engine's.
NETWORK_ALLOWED = ("/prompting/", "/src/coulisses_app/bridge.py")
NETWORK_PATTERN = re.compile(
    r"^\s*(import|from)\s+(requests|httpx|aiohttp|urllib\.request|urllib3|http\.client|socket|websocket)\b"
    r"|\b(snapshot_download|hf_hub_download)\s*\(",
    re.MULTILINE,
)

# P4: only the prompting module may talk to the LLM.
LLM_PATTERN = re.compile(
    r"^\s*(import|from)\s+ollama\b|/api/(chat|generate)\b|\bollama\.(chat|generate)\s*\(",
    re.MULTILINE,
)

# P6: only engines may import model libraries.
MODEL_LIBS = re.compile(
    r"^\s*(import|from)\s+(mlx_whisper|parakeet_mlx|mlx_audio|mlx_qwen3_asr|whisperx|faster_whisper|"
    r"pywhispercpp|pyannote\.audio|nemo|diarizen|wespeaker|nara_wpe|transformers|moshi_mlx|"
    r"torch|torchaudio|mlx|ctc_forced_aligner|clearvoice|qwen_asr|huggingface_hub)\b",
    re.MULTILINE,
)

# P1 on the web side: no remote assets or trackers.
WEB_REMOTE = re.compile(
    r"fonts\.googleapis|fonts\.gstatic|unpkg\.com|cdn\.jsdelivr|cdnjs\.|googletagmanager|google-analytics|"
    r"sentry\.io|posthog|segment\.(io|com)|plausible\.io|fetch\(\s*['\"`]https?://(?!(127\.0\.0\.1|localhost))",
)


def new_text(tool_input: dict) -> str:
    if "content" in tool_input:
        return tool_input["content"] or ""
    if "new_string" in tool_input:
        return tool_input["new_string"] or ""
    return "\n".join(e.get("new_string", "") for e in tool_input.get("edits", []))


def block(msg: str) -> None:
    print(f"[garde-fou Coulisses] {msg}", file=sys.stderr)
    sys.exit(2)


def main() -> None:
    payload = json.load(sys.stdin)
    tool_input = payload.get("tool_input", {})
    path = tool_input.get("file_path", "") or ""
    text = new_text(tool_input)

    if REAL_DATA_DIR.search(path):
        block(
            "P8 : écriture interdite dans le dossier de données réel. "
            "Utilise `coulisses-app --dev` (~/Coulisses/Données-dev) ou tmp_path."
        )

    is_code = path.endswith(".py") and "/.venv/" not in path and "/node_modules/" not in path

    if is_code and not any(a in path for a in NETWORK_ALLOWED) and NETWORK_PATTERN.search(text):
        block(
            "P1 : client réseau hors du module prompting/. L'app tourne en mode avion ; les "
            "modèles se téléchargent par le moteur (coulisses-models). Demande à l'utilisateur "
            "(nouvel ADR) si c'est vraiment nécessaire."
        )

    if is_code and "/prompting/" not in path and LLM_PATTERN.search(text):
        block(
            "P4 : appel LLM hors de prompting/. Toute génération passe par l'assemblage unique, "
            "qui garantit la consigne de langue française."
        )

    if is_code and MODEL_LIBS.search(text):
        block(
            "P6 : l'application n'importe aucune bibliothèque de modèle. Elle passe par le moteur "
            "(coulisses.chain, coulisses-traiter) ; un nouveau modèle s'ajoute dans coulisses-moteur."
        )

    if path.endswith((".ts", ".tsx", ".js", ".jsx", ".css", ".html")) and "/node_modules/" not in path and WEB_REMOTE.search(text):
        block(
            "P1 : ressource distante ou traceur dans l'interface. Embarque la ressource localement ; "
            "l'API est sur 127.0.0.1."
        )

    sys.exit(0)


if __name__ == "__main__":
    main()
