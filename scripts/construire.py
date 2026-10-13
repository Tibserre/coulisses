"""Build Coulisses.app, the app given to friends (ADR 0040, 0041), on this Mac.

Everything comes from pinned versions (`scripts/construction.toml`), kept in
~/Library/Caches/Coulisses/construction and downloaded only with --telecharger. The .app
holds:
- a standalone Python with the app, the engine at its tag and their locked dependencies,
  precompiled so that nothing is written there at run time;
- the built interface;
- its tools: ffmpeg and ffprobe (built here, audio only, LGPL), uv, the computer's sound
  program;
- Sparkle, for its updates (in the launcher only, never in the service);
- the licences of what it carries.
Every binary inside, then the .app, is signed with the self-signed certificate named in
`construction.toml` (ADR 0040; no hardened runtime, no notarization, no timestamp server):
macOS keeps the friends' permissions from one version to the next. --ad-hoc signs for
this Mac only, for a try: such a build is never published.

Usage: uv run python scripts/construire.py [--telecharger] [--ad-hoc] [--sortie dossier]
Then: scripts/essai-paquet.sh dist/Coulisses.app
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import plistlib
import shutil
import subprocess
import sys
import tarfile
import tempfile
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CACHE = Path.home() / "Library" / "Caches" / "Coulisses" / "construction"
LAUNCHER = ROOT / "native" / "lanceur"
SYSTEM_LIBRARIES = ("/usr/lib/", "/System/Library/")
MACH_O = (b"\xcf\xfa\xed\xfe", b"\xfe\xed\xfa\xcf", b"\xca\xfe\xba\xbe", b"\xbe\xba\xfe\xca")
COMPONENTS = ("protocols", "demuxers", "decoders", "parsers", "encoders", "muxers", "filters")


def say(text: str) -> None:
    print(text, flush=True)


def fail(text: str) -> None:
    print(f"ÉCHEC : {text}", file=sys.stderr, flush=True)
    raise SystemExit(1)


def run(command: list[str | Path], **options: object) -> subprocess.CompletedProcess[str]:
    """Runs a step; its output is shown only if it fails."""
    done = subprocess.run(
        [str(c) for c in command], capture_output=True, text=True, check=False, **options
    )
    if done.returncode != 0:
        print(done.stdout[-4000:], done.stderr[-4000:], sep="\n", file=sys.stderr)
        fail(f"{Path(str(command[0])).name} a échoué (code {done.returncode})")
    return done


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def only_system_libraries(binary: Path) -> None:
    """A tool copied into the .app must not need anything from this Mac (Homebrew…)."""
    linked = run(["otool", "-L", binary]).stdout.splitlines()[1:]
    foreign = [line.split()[0] for line in linked if not line.strip().startswith(SYSTEM_LIBRARIES)]
    if foreign:
        fail(f"{binary.name} dépend de bibliothèques de ce Mac : {', '.join(foreign)}")


# -- what is downloaded, once ---------------------------------------------------------------


def ffmpeg_archive(config: dict, download: bool) -> Path:
    archive = CACHE / f"ffmpeg-{config['version']}" / Path(config["url"]).name
    if not archive.is_file():
        if not download:
            fail(f"{archive} manque : relancez avec --telecharger (une fois).")
        archive.parent.mkdir(parents=True, exist_ok=True)
        partial = archive.with_name(archive.name + ".partiel")
        say(f"Téléchargement de {config['url']}…")
        run(["curl", "-sSfL", "-o", partial, config["url"]])
        os.replace(partial, archive)
    found = sha256(archive)
    if found != config["sha256"]:
        fail(f"{archive} n'a pas l'empreinte attendue ({found}) : supprimez-le, puis relancez.")
    return archive


def pinned_uv(config: dict) -> Path:
    found = shutil.which("uv")
    if found is None:
        fail("uv est introuvable sur ce Mac")
    version = run([found, "--version"]).stdout.split()[1]
    if version != config["version"]:
        fail(f"uv {version} sur ce Mac, {config['version']} attendu (scripts/construction.toml)")
    return Path(found).resolve()


def sparkle_framework(config: dict, download: bool) -> Path:
    """The folder holding Sparkle.framework (and its publishing tools, kept here)."""
    folder = CACHE / f"sparkle-{config['version']}"
    archive = folder / Path(config["url"]).name
    if not archive.is_file():
        if not download:
            fail(f"{archive} manque : relancez avec --telecharger (une fois).")
        folder.mkdir(parents=True, exist_ok=True)
        partial = archive.with_name(archive.name + ".partiel")
        say(f"Téléchargement de {config['url']}…")
        run(["curl", "-sSfL", "-o", partial, config["url"]])
        os.replace(partial, archive)
    found = sha256(archive)
    if found != config["sha256"]:
        fail(f"{archive} n'a pas l'empreinte attendue ({found}) : supprimez-le, puis relancez.")
    extracted = folder / "extrait"
    if not (extracted / "Sparkle.framework").is_dir():
        partial = folder / "extrait.partiel"
        shutil.rmtree(partial, ignore_errors=True)
        partial.mkdir()
        with tarfile.open(archive) as tar:
            tar.extractall(partial, filter="data")
        os.replace(partial, extracted)
    return extracted


def update_settings(config: dict, ad_hoc: bool) -> dict[str, object]:
    """Sparkle's keys in Info.plist (ADR 0040). Always: no automatic download nor
    install, no system profile sent, one check a day at most. With the feed and
    the key only: the app may look for its updates (after consent, or on demand)."""
    keys: dict[str, object] = {
        "SUEnableSystemProfiling": False,
        "SUAllowsAutomaticUpdates": False,
        "SUAutomaticallyUpdate": False,
        "SUScheduledCheckInterval": 86400,
        "SUVerifyUpdateBeforeExtraction": True,
    }
    if not config["public_key"]:
        if not ad_hoc:
            fail(
                "la clé publique des mises à jour manque dans scripts/construction.toml "
                "(docs/technique/certificat.md), ou construisez avec --ad-hoc pour un essai."
            )
        say("Sans clé des mises à jour : cette app ne cherchera pas les siennes.")
        return keys
    if not config["feed_url"].startswith("https://github.com/"):
        fail(f"flux des mises à jour inattendu : {config['feed_url']}")
    return {**keys, "SUFeedURL": config["feed_url"], "SUPublicEDKey": config["public_key"]}


def standalone_python(config: dict, download: bool) -> Path:
    folder = CACHE / "python" / f"cpython-{config['version']}-macos-aarch64-none"
    if not (folder / "bin" / "python3").is_file():
        if not download:
            fail(f"{folder} manque : relancez avec --telecharger (une fois).")
        say(f"Téléchargement de Python {config['version']} (python-build-standalone)…")
        run(
            ["uv", "python", "install", config["version"], "--no-bin"],
            env={**os.environ, "UV_PYTHON_INSTALL_DIR": str(CACHE / "python")},
        )
    return folder


# -- what is built here ----------------------------------------------------------------------


def configure_flags(config: dict, minimum_macos: str) -> list[str]:
    flags = [
        "--disable-everything",
        "--disable-autodetect",  # nothing of this Mac linked in (Homebrew, SDL…)
        "--disable-network",
        "--disable-doc",
        "--disable-debug",
        "--disable-ffplay",
        "--enable-ffmpeg",
        "--enable-ffprobe",
        "--disable-shared",
        "--enable-static",
        "--arch=arm64",
        "--target-os=darwin",
        "--cc=clang",
        f"--extra-cflags=-mmacosx-version-min={minimum_macos}",
        f"--extra-ldflags=-mmacosx-version-min={minimum_macos}",
    ]
    for kind in COMPONENTS:
        flags.append(f"--enable-{kind[:-1]}={','.join(config[kind])}")
    return flags


def build_ffmpeg(config: dict, archive: Path, minimum_macos: str) -> Path:
    """ffmpeg and ffprobe, built once per configuration (kept in the cache)."""
    flags = configure_flags(config, minimum_macos)
    key = hashlib.sha256(json.dumps([config["sha256"], flags]).encode()).hexdigest()[:12]
    built = archive.parent / f"construit-{key}"
    if (built / "ffmpeg").is_file() and (built / "ffprobe").is_file():
        return built
    say(f"Compilation de ffmpeg {config['version']} (audio seul, LGPL, sans réseau)…")
    with tempfile.TemporaryDirectory(prefix="ffmpeg-") as work:
        with tarfile.open(archive) as tar:
            tar.extractall(work, filter="data")
        source = Path(work) / f"ffmpeg-{config['version']}"
        # configure ignores a name it does not know: each one is checked first.
        for kind in COMPONENTS:
            known = set(run(["./configure", f"--list-{kind}"], cwd=source).stdout.split())
            unknown = sorted(set(config[kind]) - known)
            if unknown:
                fail(f"ffmpeg ne connaît pas ces {kind} : {', '.join(unknown)}")
        configured = run(["./configure", *flags], cwd=source).stdout
        if "License: LGPL" not in configured:
            fail("ffmpeg n'est pas configuré sous LGPL")
        run(["make", f"-j{os.cpu_count() or 4}", "ffmpeg", "ffprobe"], cwd=source)
        partial = built.with_name(built.name + ".partiel")
        shutil.rmtree(partial, ignore_errors=True)
        partial.mkdir()
        for name in ("ffmpeg", "ffprobe", "COPYING.LGPLv2.1"):
            shutil.copy2(source / name, partial / name)
        (partial / "configuration.txt").write_text(" ".join(flags) + "\n", encoding="utf-8")
        os.replace(partial, built)
    for tool in ("ffmpeg", "ffprobe"):
        only_system_libraries(built / tool)
    return built


def build_interface() -> Path:
    web = ROOT / "web"
    if not (web / "node_modules").is_dir():
        say("Dépendances de l'interface (depuis le cache de npm, sans réseau)…")
        run(["npm", "ci", "--offline", "--no-audit", "--no-fund"], cwd=web)
    say("Construction de l'interface…")
    run(["npm", "run", "build"], cwd=web)
    return web / "dist"


def app_version() -> str:
    return tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"][
        "version"
    ]


def install_python(python_dir: Path, target: Path) -> None:
    """The standalone Python, then the locked dependencies and the app, from uv's cache."""
    shutil.copytree(python_dir, target, symlinks=True)
    python = target / "bin" / "python3"
    exported = run(
        [
            *("uv", "export", "--frozen", "--no-dev", "--no-emit-project"),
            "--format",
            "requirements-txt",
        ],
        cwd=ROOT,
    ).stdout
    # Each package with the digests of uv.lock, checked at install; the engine, a git
    # source without digest, pinned by its commit.
    blocks: list[list[str]] = []
    for line in exported.splitlines():
        if line and not line.startswith((" ", "#")):
            blocks.append([])
        if blocks and line and not line.lstrip().startswith("#"):
            blocks[-1].append(line)
    engine = [b for b in blocks if b[0].startswith("coulisses @ git+")]
    hashed = [b for b in blocks if b not in engine]
    if len(engine) != 1 or any("--hash=" not in " ".join(b) for b in hashed):
        fail("l'export de uv.lock n'a pas la forme attendue (moteur, empreintes)")
    say("Dépendances Python (depuis le cache de uv, sans réseau, empreintes vérifiées)…")
    with tempfile.TemporaryDirectory() as work:
        requirements = Path(work) / "dependances.txt"
        requirements.write_text("\n".join("\n".join(b) for b in hashed) + "\n", encoding="utf-8")
        common = ["uv", "pip", "install", "--offline", "--python", python, "--no-deps"]
        common.append("--break-system-packages")
        run([*common, "--require-hashes", "-r", requirements], cwd=ROOT)
        run([*common, engine[0][0].split(" ;")[0]], cwd=ROOT)
        run([*common, ROOT], cwd=ROOT)
    say("Précompilation du Python (rien ne s'écrira dans l'app)…")
    done = subprocess.run(
        [
            *(python, "-m", "compileall", "-q", "-j", "0"),
            *("--invalidation-mode", "unchecked-hash", str(target / "lib")),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    # Files that are not Python 3 (examples, templates) cannot be compiled; never imported,
    # they are listed, not hidden.
    refused = [line for line in done.stdout.splitlines() if line.startswith("***")]
    if done.returncode != 0 and not refused:
        print(done.stdout[-4000:], done.stderr[-4000:], sep="\n", file=sys.stderr)
        fail("la précompilation a échoué")
    if refused:
        say(f"   {len(refused)} fichiers non compilables (pas du Python 3), laissés tels quels :")
        for line in refused[:20]:
            say(f"   {line}")


def build_launcher(
    contents: Path,
    app: dict,
    version: str,
    minimum_macos: str,
    sparkle: Path,
    updates: dict[str, object],
) -> None:
    (contents / "MacOS").mkdir(parents=True)
    # Sparkle, without what only a sandboxed app needs (its XPC services) nor what only the
    # compiler reads (headers, modules).
    framework = contents / "Frameworks" / "Sparkle.framework"
    framework.parent.mkdir()
    shutil.copytree(sparkle / "Sparkle.framework", framework, symlinks=True)
    for unused in ("XPCServices", "Headers", "PrivateHeaders", "Modules"):
        (framework / unused).unlink()
        shutil.rmtree(framework / "Versions" / "B" / unused)
    run(
        [
            *(
                "swiftc",
                "-O",
                "-swift-version",
                "5",
                "-target",
                f"arm64-apple-macosx{minimum_macos}",
            ),
            *("-D", "COULISSES_SPARKLE", "-F", sparkle, "-framework", "Sparkle"),
            *("-Xlinker", "-rpath", "-Xlinker", "@executable_path/../Frameworks"),
            *(LAUNCHER / "main.swift", "-o", contents / "MacOS" / app["name"]),
        ]
    )
    with tempfile.TemporaryDirectory() as work:
        iconset = Path(work) / "Coulisses.iconset"
        run(["swift", LAUNCHER / "icone.swift", iconset])
        run(["iconutil", "-c", "icns", iconset, "-o", contents / "Resources" / "Coulisses.icns"])
    with (LAUNCHER / "Info.plist").open("rb") as stream:
        plist = plistlib.load(stream)
    plist.update(
        CFBundleName=app["name"],
        CFBundleDisplayName=app["name"],
        CFBundleExecutable=app["name"],
        CFBundleIdentifier=app["identifier"],
        CFBundleShortVersionString=version,
        CFBundleVersion=version,
        LSMinimumSystemVersion=minimum_macos,
        NSHumanReadableCopyright="Coulisses — local, sur ce Mac. Licence MIT.",
        # Run from the .app (its Python), not from a repository: the launcher sees it.
        CoulissesVariante="",
        CoulissesProjet="",
        CoulissesUV="",
        CoulissesPATH="",
        **updates,
    )
    with (contents / "Info.plist").open("wb") as stream:
        plistlib.dump(plist, stream)


def copy_tools(resources: Path, ffmpeg: Path, uv: Path, minimum_macos: str) -> None:
    from coulisses_app import system_audio  # the dev environment's (`uv run`)
    from coulisses_app.bundle import SYSTEM_AUDIO_PROGRAM

    tools = resources / "bin"
    tools.mkdir()
    for name in ("ffmpeg", "ffprobe"):
        shutil.copy2(ffmpeg / name, tools / name)
    shutil.copy2(uv, tools / "uv")
    only_system_libraries(tools / "uv")
    system_audio.compile_program(tools / SYSTEM_AUDIO_PROGRAM, minimum_macos)


def write_licences(resources: Path, ffmpeg: Path, python: Path, uv: Path, sparkle: Path) -> None:
    licences = resources / "licences"
    licences.mkdir()
    if not (ROOT / "LICENSE").is_file():
        fail("LICENSE manque à la racine du dépôt")
    shutil.copy2(ROOT / "LICENSE", licences / "Coulisses.txt")
    shutil.copy2(ffmpeg / "COPYING.LGPLv2.1", licences / "ffmpeg-LGPL-2.1.txt")
    shutil.copy2(ffmpeg / "configuration.txt", licences / "ffmpeg-configuration.txt")
    shutil.copy2(python / "lib" / "python3.12" / "LICENSE.txt", licences / "Python.txt")
    shutil.copy2(sparkle / "LICENSE", licences / "Sparkle.txt")
    uv_home = uv.parents[1]
    uv_licences = sorted(uv_home.glob("LICENSE*"))
    if not uv_licences:
        fail(f"licence de uv introuvable dans {uv_home}")
    for found in uv_licences:
        shutil.copy2(found, licences / f"uv-{found.name}.txt")
    (licences / "LISEZMOI.txt").write_text(
        "Licences de ce que contient Coulisses.app.\n\n"
        "- Coulisses : licence MIT (Coulisses.txt).\n"
        "- ffmpeg et ffprobe : LGPL 2.1 ou ultérieure, construits depuis les sources "
        "officielles, sans modification (ffmpeg-LGPL-2.1.txt, ffmpeg-configuration.txt).\n"
        "- Python : PSF (Python.txt).\n"
        "- uv : MIT ou Apache 2.0 (uv-*.txt).\n"
        "- Sparkle (mises à jour) : MIT (Sparkle.txt).\n"
        "- Les paquets Python : chacun avec sa licence, dans "
        "python/lib/python3.12/site-packages/*.dist-info/.\n",
        encoding="utf-8",
    )


def signing_identity(config: dict, ad_hoc: bool) -> str:
    """The certificate's name, checked before anything is built; "-" for --ad-hoc."""
    if ad_hoc:
        say("Signature ad hoc : pour un essai sur ce Mac, jamais publiée.")
        return "-"
    identity = config["identity"]
    found = run(["security", "find-identity", "-p", "codesigning"]).stdout
    if f'"{identity}"' not in found:
        fail(
            f"le certificat « {identity} » n'est pas dans le trousseau : créez-le "
            "(docs/technique/certificat.md), ou construisez avec --ad-hoc pour un essai."
        )
    return identity


def binaries(folder: Path) -> list[Path]:
    """The Mach-O files inside (libraries, programs), deepest first: signed before what
    holds them."""
    found = []
    for path in folder.rglob("*"):
        if path.is_file() and not path.is_symlink():
            with path.open("rb") as stream:
                if stream.read(4) in MACH_O:
                    found.append(path)
    return sorted(found, key=lambda p: len(p.parts), reverse=True)


def sign(app: Path, identity: str) -> None:
    """Each binary inside, then the launcher and the .app. No timestamp server (nothing
    leaves this Mac), no hardened runtime (ADR 0040)."""
    inside = binaries(app / "Contents" / "Resources")
    say(f"Signature de {len(inside)} binaires, puis de l'app ({identity})…")
    command = ["codesign", "--force", "--timestamp=none", "--sign", identity]
    for start in range(0, len(inside), 100):
        run([*command, *inside[start : start + 100]])
    sparkle = app / "Contents" / "Frameworks" / "Sparkle.framework"
    if sparkle.is_dir():  # its helpers, then the framework, as Sparkle documents it
        version = sparkle / "Versions" / "B"
        for part in (version / "Updater.app", version / "Autoupdate", sparkle):
            run([*command, part])
    run([*command, app])  # with its launcher, the main executable
    run(["codesign", "--verify", "--deep", "--strict", app])
    for start in range(0, len(inside), 100):
        run(["codesign", "--verify", "--strict", *inside[start : start + 100]])
    requirement = run(["codesign", "--display", "--requirements", "-", app]).stdout.strip()
    say(f"   exigence désignée : {requirement.splitlines()[-1] if requirement else '?'}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Construit Coulisses.app (ADR 0040).")
    parser.add_argument("--telecharger", action="store_true", help="télécharger ce qui manque")
    parser.add_argument("--ad-hoc", action="store_true", help="signer pour ce Mac seulement")
    parser.add_argument("--sortie", type=Path, default=ROOT / "dist")
    args = parser.parse_args()

    settings = tomllib.loads((ROOT / "scripts" / "construction.toml").read_text(encoding="utf-8"))
    app, minimum_macos = settings["app"], settings["app"]["minimum_macos"]
    version = app_version()

    identity = signing_identity(settings["signature"], args.ad_hoc)
    uv = pinned_uv(settings["uv"])
    archive = ffmpeg_archive(settings["ffmpeg"], args.telecharger)
    python_dir = standalone_python(settings["python"], args.telecharger)
    sparkle = sparkle_framework(settings["sparkle"], args.telecharger)
    updates = update_settings(settings["sparkle"], args.ad_hoc)
    ffmpeg = build_ffmpeg(settings["ffmpeg"], archive, minimum_macos)
    interface = build_interface()

    args.sortie.mkdir(parents=True, exist_ok=True)
    final = args.sortie / f"{app['name']}.app"
    if final.exists() and not args.sortie.resolve().is_relative_to(ROOT):
        # Outside the repository it may be an installed app: never replaced here.
        fail(f"{final} existe déjà hors du dépôt : déplacez-la vous-même, puis relancez.")
    partial = args.sortie / f"{app['name']}.app.partiel"
    shutil.rmtree(partial, ignore_errors=True)
    contents = partial / "Contents"
    resources = contents / "Resources"
    resources.mkdir(parents=True)

    say(f"Assemblage de {app['name']} {version}…")
    install_python(python_dir, resources / "python")
    shutil.copytree(interface, resources / "web")
    copy_tools(resources, ffmpeg, uv, minimum_macos)
    write_licences(resources, ffmpeg, resources / "python", uv, sparkle)
    build_launcher(contents, app, version, minimum_macos, sparkle, updates)
    sign(partial, identity)

    if final.exists():
        shutil.rmtree(final)  # the previous build of this script, in its own output folder
    os.replace(partial, final)
    size = run(["du", "-sh", final]).stdout.split()[0]
    say(f"{final} ({size}) est prêt. Essai : scripts/essai-paquet.sh {final}")


if __name__ == "__main__":
    main()
