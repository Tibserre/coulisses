"""Brings the sessions of one data folder (the development one) into another that has none
yet (the real one, ~/Coulisses/Données): the base, then each session's folder.

Nothing is moved: the source is only read. The base is copied compact (VACUUM INTO), so
that no text of a session deleted long ago comes along in its free pages (ADR 0029). The
target's base, if there is one, is kept in its `sauvegardes/` and what it held is said;
its deletion log is carried over. Refused if the target already holds a session (two bases
are never merged), or while Coulisses runs on either folder.

Usage: uv run python scripts/rapatrier-donnees.py <source> [cible]
"""

from __future__ import annotations

import argparse
import shutil
import sqlite3
import sys
from datetime import datetime
from pathlib import Path
from typing import NoReturn

from coulisses_app.lock import AlreadyRunningError, hold_data_lock
from coulisses_app.paths import DEFAULT_DATA_DIR, DataDir
from coulisses_app.storage.db import (
    DatabaseTooNewError,
    MigrationMismatchError,
    check,
    migrate,
)


def say(text: str) -> None:
    print(text, flush=True)


def fail(text: str) -> NoReturn:
    print(f"Refusé : {text}", file=sys.stderr)
    raise SystemExit(1)


NAMES = {
    "space": "espaces",
    "person": "personnes",
    "action_preference": "préférences de résumé",
    "action": "actions modifiées ou créées",
    "note": "notes",
    "deletion_log": "suppressions au journal (reprises)",
    "project": "projets",
    "app_setting": "réglages",
    "glossary_entry": "termes du glossaire",
}
"""How the tables are said to the user."""


def read_only(database: Path) -> sqlite3.Connection:
    return sqlite3.connect(f"file:{database}?mode=ro", uri=True)


def held_by(data: DataDir) -> dict[str, int]:
    """What the user's tables of a base hold (the search cache left out)."""
    conn = read_only(data.database)
    try:
        tables = [
            r[0]
            for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
                " AND name NOT LIKE 'sqlite_%' AND name NOT LIKE 'search_%'"
            )
        ]
        counts = {t: conn.execute(f'SELECT COUNT(*) FROM "{t}"').fetchone()[0] for t in tables}
    finally:
        conn.close()
    return {t: n for t, n in counts.items() if n}


def size_of(folder: Path) -> int:
    return sum(p.stat().st_size for p in folder.rglob("*") if p.is_file())


def main() -> None:
    parser = argparse.ArgumentParser(description="Rapatrier des séances vers un dossier vide.")
    parser.add_argument("source", type=Path)
    parser.add_argument("cible", type=Path, nargs="?", default=DEFAULT_DATA_DIR)
    args = parser.parse_args()
    source = DataDir(args.source.expanduser().resolve())
    target = DataDir(args.cible.expanduser().resolve())
    if source.root == target.root:
        fail("la source et la cible sont le même dossier.")
    if not source.database.is_file():
        fail(f"aucune base dans {source.root}.")

    try:
        locks = [hold_data_lock(source), hold_data_lock(target)]
    except AlreadyRunningError as exc:
        fail(f"{exc} Quittez Coulisses (⌘Q) et arrêtez le serveur de développement.")
    try:
        if target.database.is_file():
            # Under the lock, the target's journal is folded into its base first: nothing
            # it holds can be lost when the base is replaced, or fail to be replaced.
            settle = sqlite3.connect(target.database)
            try:
                settle.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            finally:
                settle.close()
        replaced = held_by(target) if target.database.is_file() else {}
        if replaced.get("session"):
            fail(f"{target.root} contient déjà {replaced['session']} séance(s) : rien de fusionné.")

        source_conn = read_only(source.database)
        try:
            ids = [r[0] for r in source_conn.execute("SELECT id FROM session ORDER BY recorded_at")]
        finally:
            source_conn.close()
        folders = [source.session_dir(i) for i in ids if source.session_dir(i).is_dir()]
        if len(folders) != len(ids):
            missing = sorted(set(ids) - {f.name for f in folders})
            say(f"Attention : sans dossier dans la source : {', '.join(missing)}.")
        for folder in folders:
            if target.session_dir(folder.name).exists():
                fail(f"{target.session_dir(folder.name)} existe déjà.")
        needed = sum(size_of(f) for f in folders) + source.database.stat().st_size
        free = shutil.disk_usage(target.root).free
        if needed > free * 0.9:
            fail(f"il faut {needed / 1e9:.1f} Go, il en reste {free / 1e9:.1f}.")

        stamp = datetime.now().strftime("%Y%m%dT%H%M%S-%f")
        partial = target.root / f"coulisses-rapatriee-{stamp}.db"
        copied: list[Path] = []
        # Until the base is replaced, any failure takes back what was made here (the
        # copies are ours): the target is left as it was.
        try:
            for folder in folders:
                say(f"Copie de la séance {folder.name}…")
                destination = target.session_dir(folder.name)
                shutil.copytree(folder, destination)
                copied.append(destination)

            # VACUUM INTO: a compact copy, without the free pages where text of sessions
            # deleted long ago may linger (ADR 0029). The source is only read.
            source_conn = read_only(source.database)
            try:
                source_conn.execute("VACUUM INTO ?", (str(partial),))
            finally:
                source_conn.close()
            made = sqlite3.connect(partial)
            try:
                if made.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                    raise RuntimeError("la copie de la base n'est pas intègre")
                # Before anything else is made of it (journal, copy of the base before): a
                # base this application cannot take is refused here, and said.
                try:
                    check(partial, said_as=source.database)
                except (DatabaseTooNewError, MigrationMismatchError) as exc:
                    fail(str(exc))
                if target.database.is_file():
                    # Every deletion stays in the log (ADR 0029): the target's carried over.
                    made.execute(
                        "ATTACH DATABASE ? AS before", (f"file:{target.database}?mode=ro",)
                    )
                    with made:
                        made.execute(
                            "INSERT INTO deletion_log (at, kind, session_id, session_title, detail)"
                            " SELECT at, kind, session_id, NULL, detail FROM before.deletion_log"
                        )
                    made.execute("DETACH DATABASE before")
            finally:
                made.close()

            if target.database.is_file():
                target.backups.mkdir(parents=True, exist_ok=True)
                kept = target.backups / f"coulisses-avant-rapatriement-{stamp}.db"
                old = read_only(target.database)
                try:
                    old.execute("VACUUM INTO ?", (str(kept),))
                finally:
                    old.close()
                said = ", ".join(f"{NAMES.get(t, t)} : {n}" for t, n in sorted(replaced.items()))
                say(f"La base d'avant ({said or 'vide'}) est gardée dans {kept}.")
            for leftover in ("-wal", "-shm"):
                Path(f"{target.database}{leftover}").unlink(missing_ok=True)
            partial.replace(target.database)
        except BaseException:
            for made_folder in copied:
                try:
                    shutil.rmtree(made_folder)
                except OSError as exc:
                    print(
                        f"Attention : {made_folder} n'a pas pu être retiré : {exc}", file=sys.stderr
                    )
            partial.unlink(missing_ok=True)
            raise
        try:
            migrate(target)
        except (DatabaseTooNewError, MigrationMismatchError) as exc:
            fail(str(exc))
        say(
            f"Rapatrié : {len(folders)} séance(s), {needed / 1e9:.1f} Go, dans {target.root}. "
            f"La source n'a pas bougé : {source.root}."
        )
    finally:
        for lock in locks:
            lock.close()


if __name__ == "__main__":
    main()
