"""`coulisses-app`: start the local service and open the interface."""

from __future__ import annotations

import argparse
import logging
import os
import sys
import threading
import webbrowser
from pathlib import Path

import uvicorn
from coulisses.api import DEFAULT_PROFILE, ChainConfig, load_profile, profile_path

from coulisses_app import system_audio
from coulisses_app.api import create_app
from coulisses_app.capture import KeepAwake, Recorder, recover_interrupted
from coulisses_app.lock import AlreadyRunningError, hold_data_lock
from coulisses_app.paths import DataDir
from coulisses_app.processing import Processor
from coulisses_app.retention import Watcher
from coulisses_app.sessions import interrupted_imports
from coulisses_app.storage.db import migrate

log = logging.getLogger(__name__)

HOST = "127.0.0.1"  # never another interface (ADR 0001)
DEFAULT_PORT = 8765
WEB_DIR_ENV = "COULISSES_WEB_DIR"


def default_web_dir() -> Path:
    value = os.environ.get(WEB_DIR_ENV)
    if value:
        return Path(value).expanduser()
    return Path(__file__).resolve().parents[2] / "web" / "dist"


def _prepare_system_audio() -> None:
    try:
        system_audio.ensure_built()
    except system_audio.SystemAudioError as exc:
        # Said again, to the user, when a meeting is recorded with the computer's sound.
        log.warning("the computer's sound cannot be recorded here: %s", exc)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="coulisses-app", description="Lance Coulisses.")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--sans-navigateur", action="store_true", help="ne pas ouvrir l'interface")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )
    # Offline at runtime (P1): the engine's stages cut the network themselves; the service
    # itself never needs the Hugging Face hub.
    os.environ.setdefault("HF_HUB_OFFLINE", "1")
    os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")

    data = DataDir.from_env()
    print(f"Coulisses — données : {data.root}", file=sys.stderr)
    try:
        lock = hold_data_lock(data)
    except AlreadyRunningError as exc:
        print(exc, file=sys.stderr)
        raise SystemExit(1) from exc
    for backup in migrate(data):
        print(f"Base sauvegardée avant mise à jour : {backup}", file=sys.stderr)

    chain = ChainConfig.from_profile(load_profile(profile_path(DEFAULT_PROFILE)))
    awake = KeepAwake()
    processor = Processor(data, chain, keep_awake=awake)
    problems = processor.recover() + interrupted_imports(data) + recover_interrupted(data)
    for problem in problems:
        print(f"Attention : {problem}", file=sys.stderr)
    # Built now, in the background, so that the first meeting recorded does not wait for it.
    threading.Thread(target=_prepare_system_audio, name="system-audio-build", daemon=True).start()

    app = create_app(
        data,
        chain,
        profile=DEFAULT_PROFILE,
        processor=processor,
        web_dir=default_web_dir(),
        recovery_problems=problems,
        recorder=Recorder(data, keep_awake=awake),
        watcher=Watcher(data),
    )
    url = f"http://{HOST}:{args.port}/"
    if not args.sans_navigateur:
        threading.Timer(1.0, webbrowser.open, args=(url,)).start()
    try:
        # Open streams (the recording page's meter) are cut after 2 s at shutdown, so that
        # the service's own shutdown always runs: the recording is closed, the stages
        # stopped (ADR 0018, 0027).
        uvicorn.run(
            app, host=HOST, port=args.port, log_level="warning", timeout_graceful_shutdown=2
        )
    finally:
        lock.close()
