"""Measures how much room Coulisses takes on a Mac (plan step 12a): the reference to beat,
measured again after each lot of step 12.

What is measured, read only:
- the DMG (published, or given) and its format;
- the app inside it (or a built .app): by part (Python, interface, tools, frameworks, the
  signature's list of files), by kind of file (native libraries, .py, .pyc, Metal code,
  tests, headers and C sources, stubs, static libraries), by Python package (each file given
  to the package that installed it, its .pyc with its .py), and what removing each package
  would save with all it alone pulls in. That comes from the packages' own metadata: the
  extras the app asks for, the markers evaluated by this interpreter (the same Python as the
  app's: a different one is said);
- the engine's models and environments, as the engine itself takes stock of them
  (`coulisses.api.installed()`, its contract), with an environment's interpreter kept
  outside its folder, and the biggest packages of each environment;
- the Ollama models (their manifests: nothing is asked of Ollama), the default one marked;
- the audio: what the app records per hour, then the sessions of a data folder by file and
  by kind of session, recorded or imported (~/Coulisses/Données-dev by default; never the
  real data). A file that cannot be measured is said on stderr.

Sizes of files are what they take on disk, in decimal units, as the Finder shows them
(1 Mo = 10^6 bytes, 1 Go = 10^9); those of the engine are the engine's. A DMG is mounted
read-only, in a temporary folder, then detached. The JSON keeps no path, no session name
and only totals of the sessions: it is kept in the repository to compare against.

Usage:
    uv run python scripts/mesurer-tailles.py [--dmg X.dmg | --app X.app] [--donnees D]
                                             [--json releve.json] [--comparer avant.json]
After a lot of step 12, the new reference beside the previous one:
    cd docs/technique/tailles && uv run python ../../../scripts/mesurer-tailles.py \
        --json <date>-<version>.json --comparer <précédent>.json > <date>-<version>.md
"""

from __future__ import annotations

import argparse
import json
import os
import plistlib
import re
import shutil
import sqlite3
import struct
import subprocess
import sys
import tempfile
import tomllib
import traceback
from collections import defaultdict
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import date
from email.parser import HeaderParser
from pathlib import Path
from urllib.parse import quote

from packaging.requirements import InvalidRequirement, Requirement
from packaging.utils import canonicalize_name

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from coulisses_app.paths import DEV_DATA_DIR, is_real_data  # noqa: E402

PUBLICATIONS = Path.home() / "Coulisses" / "Publications"
APP_PROJECT = "coulisses-app"
TEST_DIRS = {"tests", "test"}
SOURCE_SUFFIXES = {".h", ".hpp", ".hxx", ".cuh", ".inc", ".inl", ".c", ".cc", ".cpp", ".cu"}
SOURCE_SUFFIXES |= {".pyx", ".pxd", ".pxi"}
AUDIO_SUFFIXES = {".wav", ".w64", ".aiff", ".aif", ".caf", ".m4a", ".aac", ".mp3", ".flac"}
AUDIO_SUFFIXES |= {".ogg", ".opus", ".webm", ".mkv", ".mp4", ".mov"}
MACH_O = (b"\xcf\xfa\xed\xfe", b"\xfe\xed\xfa\xcf", b"\xca\xfe\xba\xbe", b"\xbe\xba\xfe\xca")
KINDS = {
    "native": "bibliothèques et programmes natifs",
    "metal": "code GPU (Metal, MLX)",
    "py": "sources Python (.py)",
    "pyc": "Python compilé (.pyc)",
    "tests": "tests (dossiers tests/ et test/)",
    "sources": "en-têtes et sources C, Cython",
    "stubs": "stubs de types (.pyi)",
    "static": "bibliothèques statiques (.a)",
    "other": "autres (données, licences, métadonnées…)",
}
TRACK_RATE, TRACK_BYTES = 48_000, 3  # what the app records (capture.py, wav.py)
MONO_TRACK = "une piste mono"


def fail(text: str) -> None:
    print(f"ÉCHEC : {text}", file=sys.stderr, flush=True)
    raise SystemExit(1)


def warn(text: str) -> None:
    print(f"   attention : {text}", file=sys.stderr, flush=True)


def tool(command: list[str | Path]) -> subprocess.CompletedProcess[bytes]:
    """Runs a macOS tool; if it fails, says why and stops."""
    done = subprocess.run([str(c) for c in command], capture_output=True, check=False)
    if done.returncode != 0:
        reason = done.stderr.decode(errors="replace").strip()
        fail(f"{command[0]} {command[1]} a échoué (code {done.returncode}) : {reason}")
    return done


def human(size: float) -> str:
    """Decimal units, as the Finder: 1 Go = 10^9 bytes. French decimal comma."""
    sign = "-" if size < 0 else ""
    size = abs(size)
    for unit, scale in (("Go", 1e9), ("Mo", 1e6), ("ko", 1e3)):
        if size >= scale:
            value = size / scale
            text = (
                f"{value:.2f}" if value < 10 else f"{value:.1f}" if value < 100 else f"{value:.0f}"
            )
            return f"{sign}{text.replace('.', ',')} {unit}"
    return f"{sign}{size:.0f} o"


def hours(seconds: float) -> str:
    return f"{seconds / 3600:.2f} h".replace(".", ",")


# -- files on disk ---------------------------------------------------------------------------


def files(folder: Path) -> Iterator[Path]:
    """Regular files under `folder`, symbolic links not followed, each inode once."""
    seen: set[tuple[int, int]] = set()
    for base, _dirs, names in os.walk(folder):
        for name in names:
            path = Path(base, name)
            info = path.lstat()
            if not path.is_symlink() and (info.st_dev, info.st_ino) not in seen:
                seen.add((info.st_dev, info.st_ino))
                yield path


def on_disk(path: Path) -> int:
    return path.lstat().st_blocks * 512


def folder_size(folder: Path) -> int:
    return sum(on_disk(p) for p in files(folder)) if folder.is_dir() else 0


def kind_of(path: Path, inside: Path) -> str:
    parts = path.relative_to(inside).parts
    if TEST_DIRS & set(parts[:-1]):
        return "tests"
    suffix = path.suffix.lower()
    if suffix == ".pyc":
        return "pyc"
    if suffix == ".py":
        return "py"
    if suffix == ".pyi":
        return "stubs"
    if suffix == ".metallib":
        return "metal"
    if suffix == ".a":
        return "static"
    if suffix in SOURCE_SUFFIXES:
        return "sources"
    if suffix in (".so", ".dylib"):
        return "native"
    with path.open("rb") as stream:
        return "native" if stream.read(4) in MACH_O else "other"


# -- Python packages -------------------------------------------------------------------------


def site_packages(python: Path) -> Path | None:
    found = sorted(python.glob("lib/python3*/site-packages"))
    return found[0] if found else None


def distributions(site: Path) -> dict[str, dict]:
    """Each installed package: its name, version, requirements and files (from RECORD)."""
    found: dict[str, dict] = {}
    for info in sorted(site.glob("*.dist-info")):
        metadata = info / "METADATA"
        if not metadata.is_file():
            warn(f"{info.name} n'a pas de METADATA : ses fichiers comptent « sans paquet »")
            continue
        headers = HeaderParser().parsestr(metadata.read_text(encoding="utf-8", errors="replace"))
        name = canonicalize_name(headers["Name"])
        listed = {p.resolve() for p in info.rglob("*") if p.is_file()}
        record = info / "RECORD"
        if record.is_file():
            for line in record.read_text(encoding="utf-8", errors="replace").splitlines():
                if line.strip():
                    listed.add((site / line.rsplit(",", 2)[0]).resolve())
        found[name] = {
            "version": headers["Version"],
            "requires": headers.get_all("Requires-Dist") or [],
            "files": listed,
        }
    return found


def owner_of(path: Path, owners: dict[Path, str]) -> str | None:
    """The package that installed `path`; a .pyc compiled after install goes with its .py."""
    resolved = path.resolve()
    if resolved in owners:
        return owners[resolved]
    if resolved.suffix == ".pyc" and resolved.parent.name == "__pycache__":
        source = resolved.parent.parent / (resolved.name.split(".")[0] + ".py")
        return owners.get(source)
    return None


def package_sizes(site: Path, dists: dict[str, dict]) -> tuple[dict[str, int], int]:
    owners = {p: name for name, d in dists.items() for p in d["files"]}
    sizes: dict[str, int] = defaultdict(int)
    unowned = 0
    for path in files(site):
        owner = owner_of(path, owners)
        if owner is None:
            unowned += on_disk(path)
        else:
            sizes[owner] += on_disk(path)
    return dict(sizes), unowned


def parse_requirements(dists: dict[str, dict]) -> None:
    """Each package's requirements, parsed; one that cannot be read is said, not hidden."""
    for name, dist in dists.items():
        requirements = []
        for line in dist["requires"]:
            try:
                requirements.append(Requirement(line))
            except InvalidRequirement:
                warn(f"exigence illisible de {name}, ignorée : {line}")
        dist["parsed"] = requirements


def reachable(
    dists: dict[str, dict], root: str, without: str | None = None
) -> tuple[set[str], dict[str, set[str]]]:
    """The packages installed because of `root`, as pip would pull them (`without` left
    out), and for each one the packages that pull it."""
    done: dict[str, set[str]] = defaultdict(set)
    pulled_by: dict[str, set[str]] = defaultdict(set)
    pending = [(root, frozenset[str](), "")]
    while pending:
        name, extras, parent = pending.pop()
        if name == without or name not in dists:
            continue
        if parent:
            pulled_by[name].add(parent)
        wanted = {""} | set(extras)
        if name in done and wanted <= done[name]:
            continue
        done[name] |= wanted
        for requirement in dists[name]["parsed"]:
            if requirement.marker is None or any(
                requirement.marker.evaluate({"extra": e}) for e in wanted
            ):
                child = canonicalize_name(requirement.name)
                pending.append((child, frozenset(requirement.extras), name))
    return set(done), pulled_by


def python_packages(python: Path, root: str) -> dict:
    site = site_packages(python)
    if site is None:
        fail(f"pas de site-packages dans {python}")
        raise AssertionError
    if site.parent.name != f"python{sys.version_info.major}.{sys.version_info.minor}":
        warn(
            f"l'app a {site.parent.name}, ce relevé tourne sous un autre Python : les "
            "marqueurs des dépendances sont évalués pour le sien, les gains peuvent être faux"
        )
    dists = distributions(site)
    parse_requirements(dists)
    sizes, unowned = package_sizes(site, dists)
    result: dict = {
        "unowned": unowned,
        "packages": {n: {"version": dists[n]["version"], "size": s} for n, s in sizes.items()},
    }
    if root not in dists:
        warn(
            f"{root} n'est pas installé dans l'app : "
            "pas de calcul de ce que retirer un paquet ferait gagner"
        )
        return result
    everything, pulled_by = reachable(dists, root)
    exclusive = {}
    for name in everything - {root}:
        gone = everything - reachable(dists, root, without=name)[0]
        exclusive[name] = {
            "size": sum(sizes.get(n, 0) for n in gone),
            "with": sorted(gone - {name}, key=lambda n: -sizes.get(n, 0)),
        }
    result["exclusive"] = exclusive
    result["required_by"] = {n: sorted(p - {n}) for n, p in pulled_by.items()}
    result["not_required"] = sorted(set(dists) - everything)
    return result


# -- the DMG and the app ---------------------------------------------------------------------


def version_key(folder: Path) -> tuple[int, ...]:
    found = re.fullmatch(r"v(\d+)\.(\d+)\.(\d+)", folder.name)
    return tuple(int(n) for n in found.groups()) if found else (-1,)


def latest_dmg() -> Path:
    folders = sorted(
        (f for f in PUBLICATIONS.glob("v*") if version_key(f) != (-1,)), key=version_key
    )
    for folder in reversed(folders):
        dmgs = sorted(folder.glob("*.dmg"))
        if len(dmgs) > 1:
            fail(f"{folder} contient plusieurs DMG : donnez celui à mesurer avec --dmg")
        if dmgs:
            return dmgs[0]
    fail(f"aucun DMG dans {PUBLICATIONS} : donnez --dmg ou --app")
    raise AssertionError


@contextmanager
def mounted(dmg: Path) -> Iterator[Path]:
    """The DMG mounted read-only in a temporary folder, detached after, even on an error."""
    mount = Path(tempfile.mkdtemp(prefix="coulisses-dmg-"))
    try:
        tool(
            ["hdiutil", "attach", "-nobrowse", "-readonly", "-noverify", "-mountpoint", mount, dmg]
        )
    except SystemExit:
        mount.rmdir()
        raise
    try:
        yield mount
    finally:
        detached = subprocess.run(["hdiutil", "detach", mount], capture_output=True, check=False)
        if detached.returncode != 0:
            detached = subprocess.run(
                ["hdiutil", "detach", "-force", mount], capture_output=True, check=False
            )
        if detached.returncode != 0:
            reason = detached.stderr.decode(errors="replace").strip()
            failed = sys.exc_info()[1]
            if failed is not None and not isinstance(failed, SystemExit):
                traceback.print_exception(failed)  # the first error, not hidden by this one
            fail(
                f"le DMG reste monté ({reason}) : "
                f"détachez-le avec « hdiutil detach -force {mount} »"
            )
        mount.rmdir()


def dmg_facts(dmg: Path) -> dict:
    info = plistlib.loads(tool(["hdiutil", "imageinfo", "-plist", dmg]).stdout)
    return {"size": dmg.stat().st_size, "format": info.get("Format", "?")}


def part_of(relative: Path, python: Path, site: Path | None, path: Path) -> str:
    if "_CodeSignature" in relative.parts:
        return "signature (liste des fichiers signés)"
    if path.is_relative_to(python):
        if site and path.is_relative_to(site):
            return "Python : paquets (site-packages)"
        if path.is_relative_to(python / "lib"):
            return "Python : bibliothèque standard"
        return "Python : interpréteur et le reste"
    if relative.parts[:2] == ("Resources", "bin"):
        return f"outil : {path.name}"
    if relative.parts[:2] == ("Resources", "web"):
        return "interface (web)"
    if relative.parts[0] == "Frameworks" and len(relative.parts) > 1:
        return f"framework : {relative.parts[1]}"
    return "lanceur, icône, licences"


def app_facts(app: Path) -> dict:
    contents = app / "Contents"
    python = contents / "Resources" / "python"
    version = (
        tool(["plutil", "-extract", "CFBundleShortVersionString", "raw", contents / "Info.plist"])
        .stdout.decode()
        .strip()
    )
    parts: dict[str, int] = defaultdict(int)
    kinds: dict[str, int] = defaultdict(int)
    stdlib_kinds: dict[str, int] = defaultdict(int)
    site = site_packages(python)
    for path in files(app):
        size = on_disk(path)
        part = part_of(path.relative_to(contents), python, site, path)
        parts[part] += size
        if part.startswith("Python"):
            kind = kind_of(path, python)
            kinds[kind] += size
            if part == "Python : bibliothèque standard":
                stdlib_kinds[kind] += size
    stdlib_dirs: dict[str, int] = {}
    for lib in sorted(python.glob("lib/python3*"))[:1]:
        for child in lib.iterdir():
            if child.is_dir() and child.name != "site-packages":
                stdlib_dirs[child.name] = folder_size(child)
    return {
        "version": version,
        "size": sum(parts.values()),
        "parts": dict(parts),
        "kinds": dict(kinds),
        "stdlib_kinds": dict(stdlib_kinds),
        "stdlib_dirs": dict(sorted(stdlib_dirs.items(), key=lambda kv: -kv[1])[:8]),
        "python": python_packages(python, APP_PROJECT),
    }


# -- the engine, Ollama ----------------------------------------------------------------------


def engine_facts() -> dict:
    """What the engine has installed, by its own stock taking (its contract)."""
    from coulisses.api import installed

    stock = installed()
    environments = {}
    outside_seen: set[Path] = set()
    for env in stock.environments:
        facts: dict = {
            "size": env.size_bytes,
            "current": env.current,
            "installed": env.installed,
            "outside": 0,
        }
        if env.interpreter_outside and env.interpreter is not None:
            # …/cpython-3.10.x-macos-aarch64-none/bin/python3.10: the whole Python install,
            # counted once if several environments share it.
            home = Path(env.interpreter).parents[1]
            if home not in outside_seen:
                outside_seen.add(home)
                facts["outside"] = folder_size(home)
        site = next(iter(sorted(Path(env.path).glob("lib/python3*/site-packages"))), None)
        if site is not None:
            sizes, _ = package_sizes(site, distributions(site))
            facts["packages"] = dict(sorted(sizes.items(), key=lambda kv: -kv[1])[:6])
        environments[Path(env.path).name] = facts
    for partial in stock.partial_downloads:
        warn(f"téléchargement interrompu d'un modèle, non compté : {partial}")
    return {
        "models": {m.key: m.size_bytes for m in stock.models},
        "environments": environments,
        "uv_stores": {s.kind: s.size_bytes for s in stock.uv_stores},
        "total": stock.total_bytes,
    }


def ollama_facts() -> dict:
    models = Path(os.environ.get("OLLAMA_MODELS", Path.home() / ".ollama" / "models"))
    manifests = models / "manifests"
    settings = tomllib.loads(
        (ROOT / "src/coulisses_app/prompting/textes/reglages.toml").read_text(encoding="utf-8")
    )
    found: dict[str, int] = {}
    if manifests.is_dir():
        for manifest in sorted(p for p in manifests.rglob("*") if p.is_file()):
            relative = manifest.relative_to(manifests).parts
            name = (
                f"{relative[-2]}:{relative[-1]}"
                if relative[:2] == ("registry.ollama.ai", "library")
                else "/".join(relative)
            )
            content = json.loads(manifest.read_text(encoding="utf-8"))
            layers = [content.get("config", {}), *content.get("layers", [])]
            found[name] = sum(int(layer.get("size", 0)) for layer in layers)
    else:
        warn(f"pas de modèles Ollama dans {models}")
    return {
        "default": settings.get("modele_par_defaut", ""),
        "models": found,
        "blobs": folder_size(models / "blobs"),
    }


# -- audio -----------------------------------------------------------------------------------


def wav_duration(path: Path) -> float | None:
    """Seconds of audio in a RIFF WAV, read from its chunks; None if it is not one."""
    with path.open("rb") as stream:
        head = stream.read(12)
        if len(head) < 12 or head[:4] != b"RIFF" or head[8:12] != b"WAVE":
            return None
        byte_rate = None
        while True:
            chunk = stream.read(8)
            if len(chunk) < 8:
                return None
            tag, length = chunk[:4], struct.unpack("<I", chunk[4:])[0]
            if tag == b"fmt ":
                fmt = stream.read(length)
                byte_rate = struct.unpack("<I", fmt[8:12])[0]
                stream.seek(length % 2, 1)
            elif tag == b"data":
                return length / byte_rate if byte_rate else None
            else:
                stream.seek(length + length % 2, 1)


def probed_duration(path: Path) -> float | None:
    if shutil.which("ffprobe") is None:
        return None
    done = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", path],
        capture_output=True,
        text=True,
        check=False,
    )
    try:
        return float(done.stdout.strip())
    except ValueError:
        return None


def origins(data: Path) -> dict[tuple[str, str], str]:
    """(session, file) → `captured` or `imported`, from the base, opened read-only."""
    base = data / "coulisses.db"
    if not base.is_file():
        warn(f"pas de base dans {data} : l'origine des sources est inconnue")
        return {}
    with sqlite3.connect(f"file:{quote(str(base))}?mode=ro", uri=True) as connection:
        rows = connection.execute(
            "SELECT session_id, file_name, origin FROM audio_source WHERE removed_at IS NULL"
        ).fetchall()
    return {(s, f): o for s, f, o in rows}


def audio_facts(data: Path) -> dict:
    per_hour = TRACK_RATE * TRACK_BYTES * 3600
    known = origins(data)
    total = lambda: {"bytes": 0, "seconds": 0.0, "count": 0}  # noqa: E731
    by_file: dict[str, dict] = defaultdict(total)
    by_kind: dict[str, dict] = defaultdict(total)
    for session in sorted((data / "sessions").glob("*")):
        sources = session / "sources"
        if not sources.is_dir():
            continue
        stored, longest, kinds = 0, 0.0, set()
        for path in sorted(files(sources)):
            size = on_disk(path)
            stored += size
            if path.suffix.lower() not in AUDIO_SUFFIXES:
                continue
            origin = known.get((session.name, path.name))
            kinds.add(origin)
            seconds = wav_duration(path) if path.suffix.lower() == ".wav" else None
            seconds = seconds if seconds is not None else probed_duration(path)
            if not seconds:
                warn(f"durée illisible, non compté : {session.name}/sources/{path.name}")
                continue
            longest = max(longest, seconds)
            label = (
                f"importé ({path.suffix.lower()})"
                if origin == "imported"
                else path.name
                if origin == "captured"
                else f"dérivé : {path.name}"
                if path.name.startswith(("mix", "listening"))
                else f"origine inconnue : {path.name}"
            )
            entry = by_file[label]
            entry["bytes"] += size
            entry["seconds"] += seconds
            entry["count"] += 1
        if not longest:
            warn(f"séance sans audio mesurable, non comptée : {session.name}")
            continue
        kind = (
            "enregistrée dans l'app"
            if "captured" in kinds
            else "importée"
            if kinds == {"imported"}
            else "d'origine inconnue"
        )
        by_kind[kind]["bytes"] += stored
        by_kind[kind]["seconds"] += longest
        by_kind[kind]["count"] += 1
    return {
        "track_per_hour": {
            MONO_TRACK: per_hour,
            # A meeting with the computer's sound: the microphone, the computer's sound (mono,
            # system_audio.py), the mix the engine hears and the listening mix (ADR 0032, 0037).
            "une réunion avec le son de l'ordinateur (4 pistes mono)": 4 * per_hour,
        },
        "by_file": dict(sorted(by_file.items())),
        "by_session_kind": dict(sorted(by_kind.items())),
    }


# -- report ----------------------------------------------------------------------------------


def table(rows: list[tuple[str, ...]], header: tuple[str, ...]) -> str:
    lines = ["| " + " | ".join(header) + " |", "|" + "---|" * len(header)]
    lines += ["| " + " | ".join(row) + " |" for row in rows]
    return "\n".join(lines)


def value_at(facts: dict, path: list[str]) -> object:
    value: object = facts
    for key in path:
        value = value.get(key) if isinstance(value, dict) else None
    return value


def summary(facts: dict, before: dict | None) -> list[str]:
    rows: list[tuple[list[str], str]] = []
    if "dmg" in facts:
        rows.append((["dmg", "size"], f"DMG ({facts['dmg']['format']})"))
    rows += [
        (["app", "size"], f"App installée ({facts['app']['version']})"),
        (["totals", "models"], "Modèles du moteur"),
        (["totals", "environments"], "Environnements du moteur (et leur Python)"),
        (
            ["totals", "ollama_default"],
            f"Modèle de langage par défaut ({facts['ollama']['default']})",
        ),
        (["totals", "audio_hour"], "Une heure d'enregistrement (une piste mono)"),
    ]
    header = ("", "Taille", "Écart") if before else ("", "Taille")
    lines = ["| " + " | ".join(header) + " |", "|" + "---|" * len(header)]
    for path, label in rows:
        new = value_at(facts, path)
        cells = [label, human(new) if isinstance(new, (int, float)) else "—"]
        if before is not None:
            old = value_at(before, path)
            if isinstance(old, (int, float)) and isinstance(new, (int, float)):
                cells.append(human(new - old) if new != old else "=")
            else:
                cells.append("—")
        lines.append("| " + " | ".join(cells) + " |")
    return lines


def report(facts: dict, before: dict | None) -> str:
    out: list[str] = [f"# Relevé des tailles de Coulisses ({facts['date']})", ""]
    measured = facts["measured"]
    line = f"Mesuré sur {measured['app']}, ce Mac, et les séances de {measured['data']}"
    if before is not None:
        line += f" ; comparé au relevé du {before['date']} ({before['app']['version']})"
    out += [line + ".", ""]
    out += [
        "Tailles des fichiers sur le disque, en unités décimales (1 Go = 10⁹ octets), comme le "
        "Finder ; modèles et environnements selon le moteur (`installed()`), le Python d'un "
        "environnement rangé hors de son dossier mesuré ici sur le disque.",
        "",
        "## En bref",
        "",
        *summary(facts, before),
        "",
    ]

    app = facts["app"]
    out += ["## L'app, par partie", ""]
    out.append(
        table(
            [(k, human(v)) for k, v in sorted(app["parts"].items(), key=lambda kv: -kv[1])],
            ("Partie", "Taille"),
        )
    )
    out += ["", "## Le Python de l'app, par sorte de fichier", ""]
    out.append(
        table(
            [
                (KINDS[k], human(v), human(app["stdlib_kinds"].get(k, 0)))
                for k, v in sorted(app["kinds"].items(), key=lambda kv: -kv[1])
            ],
            ("Sorte", "Taille", "dont bibliothèque standard"),
        )
    )
    out += [
        "",
        "Plus gros dossiers de la bibliothèque standard : "
        + ", ".join(f"`{k}` {human(v)}" for k, v in app["stdlib_dirs"].items())
        + ".",
        "",
    ]

    python = app["python"]
    top = sorted(python["packages"].items(), key=lambda kv: -kv[1]["size"])[:20]
    required_by = python.get("required_by", {})
    out += ["## Les paquets Python, les plus gros", ""]
    out.append(
        table(
            [
                (f"{n} {p['version']}", human(p["size"]), ", ".join(required_by.get(n, [])) or "—")
                for n, p in top
            ],
            ("Paquet", "Taille", "Demandé par"),
        )
    )
    out += ["", f"Fichiers sans paquet dans site-packages : {human(python['unowned'])}.", ""]
    exclusive = python.get("exclusive", {})
    if exclusive:
        gains = sorted(exclusive.items(), key=lambda kv: -kv[1]["size"])[:20]
        out += [
            "## Ce que retirer un paquet ferait gagner",
            "",
            "Si plus rien ne le demandait : le paquet et tout ce que lui seul fait installer "
            "(ce qu'un autre demande aussi reste).",
            "",
        ]
        out.append(
            table(
                [
                    (
                        n,
                        human(g["size"]),
                        (", ".join(g["with"][:8]) + (" …" if len(g["with"]) > 8 else "")) or "—",
                    )
                    for n, g in gains
                ],
                ("Paquet", "Gain", "Emporte aussi"),
            )
        )
        if python["not_required"]:
            out += ["", "Installés sans être demandés : " + ", ".join(python["not_required"]) + "."]
        out.append("")

    engine = facts["engine"]
    out += ["## Modèles du moteur", ""]
    out.append(
        table(
            [(k, human(v)) for k, v in sorted(engine["models"].items(), key=lambda kv: -kv[1])],
            ("Modèle", "Taille"),
        )
    )
    out += ["", "## Environnements du moteur", ""]
    out.append(
        table(
            [
                (
                    k
                    + ("" if v["current"] else " (ancien)")
                    + ("" if v["installed"] else " (installation interrompue)"),
                    human(v["size"]),
                    human(v["outside"]) if v["outside"] else "—",
                    ", ".join(f"{n} {human(s)}" for n, s in v.get("packages", {}).items()),
                )
                for k, v in engine["environments"].items()
            ]
            + [
                (
                    f"uv : {k}",
                    human(v),
                    "—",
                    "non compté : ses fichiers sont clonés dans les environnements"
                    if k == "cache"
                    else "",
                )
                for k, v in engine["uv_stores"].items()
            ],
            ("Environnement", "Taille", "Son Python, hors du dossier", "Plus gros paquets"),
        )
    )
    ollama = facts["ollama"]
    out += ["", "## Modèles de langage (Ollama)", ""]
    out.append(
        table(
            [
                (k + (" (par défaut)" if k == ollama["default"] else ""), human(v))
                for k, v in sorted(ollama["models"].items(), key=lambda kv: -kv[1])
            ],
            ("Modèle", "Taille"),
        )
    )
    out += ["", f"Sur le disque, tous modèles confondus : {human(ollama['blobs'])}.", ""]

    audio = facts["audio"]
    out += ["## Audio", ""]
    out.append(
        "Enregistré par l'app (WAV, 48 kHz, 24 bits), par heure : "
        + " ; ".join(f"{k}, {human(v)}" for k, v in audio["track_per_hour"].items())
        + "."
    )
    if audio["by_file"]:
        out += ["", "Mesuré dans le dossier de données, par fichier de `sources/` :", ""]
        out.append(
            table(
                [
                    (
                        k,
                        str(v["count"]),
                        hours(v["seconds"]),
                        human(v["bytes"] * 3600 / v["seconds"]),
                    )
                    for k, v in audio["by_file"].items()
                ],
                ("Fichier", "Fichiers", "Durée", "Par heure"),
            )
        )
        out += ["", "Et par séance, tout `sources/` compris :", ""]
        out.append(
            table(
                [
                    (
                        k,
                        str(v["count"]),
                        hours(v["seconds"]),
                        human(v["bytes"] * 3600 / v["seconds"]),
                    )
                    for k, v in audio["by_session_kind"].items()
                ],
                ("Séance", "Séances", "Durée", "Par heure"),
            )
        )
    return "\n".join(out) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description="Relevé des tailles de Coulisses (étape 12a).")
    given = parser.add_mutually_exclusive_group()
    given.add_argument("--dmg", type=Path, help="un DMG (défaut : la dernière publication)")
    given.add_argument("--app", type=Path, help="une Coulisses.app construite, sans DMG")
    parser.add_argument("--donnees", type=Path, default=DEV_DATA_DIR, help="séances à mesurer")
    parser.add_argument("--json", type=Path, help="écrire le relevé en JSON (fichier nouveau)")
    parser.add_argument("--remplacer", action="store_true", help="remplacer le JSON existant")
    parser.add_argument("--comparer", type=Path, help="un relevé JSON d'avant")
    args = parser.parse_args()

    if is_real_data(args.donnees):
        fail(f"{args.donnees} est le dossier des données réelles : on n'y lit rien.")
    if args.json and args.json.exists() and not args.remplacer:
        fail(f"{args.json} existe déjà : donnez un autre nom, ou --remplacer.")
    before = json.loads(args.comparer.read_text(encoding="utf-8")) if args.comparer else None

    facts: dict = {"date": date.today().isoformat()}
    if args.app:
        app = args.app.resolve()
        facts["measured"] = {"app": app.name, "data": args.donnees.name}
        facts["app"] = app_facts(app)
    else:
        dmg = (args.dmg or latest_dmg()).resolve()
        facts["measured"] = {"app": dmg.name, "data": args.donnees.name}
        facts["dmg"] = dmg_facts(dmg)
        with mounted(dmg) as mount:
            apps = sorted(mount.glob("*.app"))
            if len(apps) != 1:
                fail(f"{dmg.name} ne contient pas une app et une seule")
            facts["app"] = app_facts(apps[0])
    facts["engine"] = engine_facts()
    facts["ollama"] = ollama_facts()
    facts["audio"] = audio_facts(args.donnees)
    environments = facts["engine"]["environments"].values()
    facts["totals"] = {
        "models": sum(facts["engine"]["models"].values()),
        "environments": sum(e["size"] + e["outside"] for e in environments)
        # The cache is not counted, as in the engine's total: on APFS its files are cloned
        # into the environments, counted there (model-inventory.schema.json).
        + sum(v for k, v in facts["engine"]["uv_stores"].items() if k != "cache"),
        "ollama_default": facts["ollama"]["models"].get(facts["ollama"]["default"]),
        "audio_hour": facts["audio"]["track_per_hour"][MONO_TRACK],
    }
    if args.json:
        args.json.write_text(
            json.dumps(facts, ensure_ascii=False, indent=1) + "\n", encoding="utf-8"
        )
    print(report(facts, before), end="")


if __name__ == "__main__":
    main()
