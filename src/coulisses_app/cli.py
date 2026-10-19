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

from coulisses_app import lossless, system_audio
from coulisses_app.api import create_app
from coulisses_app.bundle import IncompleteAppError, Resources
from coulisses_app.capture import KeepAwake, Recorder, recover_interrupted
from coulisses_app.lock import AlreadyRunningError, hold_data_lock
from coulisses_app.paths import DataDir, RealDataRefusedError
from coulisses_app.processing import Processor
from coulisses_app.retention import Watcher
from coulisses_app.sessions import interrupted_imports
from coulisses_app.storage.db import migrate

log = logging.getLogger(__name__)

HOST = "127.0.0.1"  # never another interface (ADR 0001)
DEFAULT_PORT = 8765
# « Coulisses (dév) » beside the published app: neither service nor data shared (ADR 0040).
DEV_PORT = 8766
WEB_DIR_ENV = "COULISSES_WEB_DIR"


def default_web_dir(resources: Resources) -> Path:
    value = os.environ.get(WEB_DIR_ENV)
    if value:
        return Path(value).expanduser()
    return resources.web_dir


def _prepare_system_audio() -> None:
    try:
        system_audio.ensure_built()
    except system_audio.SystemAudioError as exc:
        # Said again, to the user, when a meeting is recorded with the computer's sound.
        log.warning("the computer's sound cannot be recorded here: %s", exc)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="coulisses-app", description="Lance Coulisses.")
    parser.add_argument("--port", type=int, default=None)
    parser.add_argument("--sans-navigateur", action="store_true", help="ne pas ouvrir l'interface")
    parser.add_argument(
        "--dev",
        action="store_true",
        help="développement : port 8766, ~/Coulisses/Données-dev, jamais les données réelles",
    )
    return parser.parse_args(argv)


def launch_settings(args: argparse.Namespace) -> tuple[DataDir, int]:
    """The data folder and the port: development never gets the real data (ADR 0040)."""
    if args.dev:
        data, port = DataDir.for_development(), DEV_PORT
    else:
        data, port = DataDir.from_env(), DEFAULT_PORT
    return data, port if args.port is None else args.port


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)

    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )
    # Offline at runtime (P1): the engine's stages cut the network themselves; the service
    # itself never needs the Hugging Face hub.
    os.environ.setdefault("HF_HUB_OFFLINE", "1")
    os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
    # From the .app: its tools on the PATH, uv's downloads under ~/Coulisses (ADR 0040).
    resources = Resources.from_env()
    try:
        resources.check()
    except IncompleteAppError as exc:
        print(exc, file=sys.stderr)
        raise SystemExit(1) from exc
    os.environ.update(resources.environment(os.environ))
    if os.environ.get("PYTHONDONTWRITEBYTECODE"):
        sys.dont_write_bytecode = True  # this process too, not only what it starts

    try:
        data, port = launch_settings(args)
    except RealDataRefusedError as exc:
        print(exc, file=sys.stderr)
        raise SystemExit(1) from exc
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
    processor = Processor(
        data,
        chain,
        keep_awake=awake,
        after_chain=lambda session_id: lossless.after_processing(data, session_id),
    )
    problems = processor.recover() + interrupted_imports(data) + recover_interrupted(data)
    for problem in problems:
        print(f"Attention : {problem}", file=sys.stderr)
    # Tracks a conversion in FLAC left half done (ADR 0046), taken up in the background.
    lossless.at_start(data)
    # Built now, in the background, so that the first meeting recorded does not wait for it.
    threading.Thread(target=_prepare_system_audio, name="system-audio-build", daemon=True).start()

    app = create_app(
        data,
        chain,
        profile=DEFAULT_PROFILE,
        processor=processor,
        web_dir=default_web_dir(resources),
        recovery_problems=problems,
        recorder=Recorder(
            data,
            keep_awake=awake,
            after_stop=lambda session_id: lossless.after_recording(data, session_id),
        ),
        watcher=Watcher(data),
    )
    url = f"http://{HOST}:{port}/"
    if not args.sans_navigateur:
        threading.Timer(1.0, webbrowser.open, args=(url,)).start()
    try:
        # Open streams (the recording page's meter) are cut after 2 s at shutdown, so that
        # the service's own shutdown always runs: the recording is closed, the stages
        # stopped (ADR 0018, 0027).
        uvicorn.run(app, host=HOST, port=port, log_level="warning", timeout_graceful_shutdown=2)
    finally:
        lock.close()


if __name__ == "__main__":  # `python -m coulisses_app.cli`, from Coulisses.app
    main()
