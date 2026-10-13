"""Publish a version of Coulisses.app for the friends (ADR 0040; plan step 11f), from this Mac.

    uv run python scripts/publier.py vX.Y.Z              prepares, sends nothing
    uv run python scripts/publier.py vX.Y.Z --envoyer    then the pre-release on GitHub
    uv run python scripts/publier.py --confirmer vX.Y.Z  the friends get it

Preparing, in this order, each step stopping the next:
1. the tag exists and this repository is clean; the tag is checked out in a worktree of the
   cache: what is published is exactly the tag;
2. every test of the tag (Python, interface, types, lint);
3. the build, signed with the certificate (`construire.py`), then the package test with
   --publication (an ad hoc signature, or no update key, fails);
4. the designated requirement is the previous publication's: otherwise the friends would
   lose their permissions;
5. the previous published app makes a base with a session, the new one opens it
   (migrations);
6. the DMG, signed; its EdDSA signature; the notes, from CHANGELOG.md; the appcast, signed
   too (the app requires it), without any remote resource.
Everything is kept in ~/Coulisses/Publications/vX.Y.Z.

Sending (--envoyer) pushes the tag and makes a GitHub pre-release with the DMG and the
notes, without the appcast: the friends get nothing yet; the user installs it and uses it.
Confirming (--confirmer) checks that the pre-release's DMG is the one prepared, then
uploads the appcast and makes the release the latest: the friends' apps find it.
"""

from __future__ import annotations

import argparse
import hashlib
import html
import os
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import tomllib
from datetime import UTC, datetime
from email.utils import format_datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CACHE = Path.home() / "Library" / "Caches" / "Coulisses" / "construction"
PUBLICATIONS = Path.home() / "Coulisses" / "Publications"
CONFIRMED = "confirmee"
TAG = re.compile(r"^v(\d+\.\d+\.\d+)$")
SPARKLE_NS = "http://www.andymatuschak.org/xml-namespaces/sparkle"


def say(text: str) -> None:
    print(text, flush=True)


def fail(text: str) -> None:
    print(f"ÉCHEC : {text}", file=sys.stderr, flush=True)
    raise SystemExit(1)


def run(command: list[str | Path], **options: object) -> subprocess.CompletedProcess[str]:
    done = subprocess.run(
        [str(c) for c in command], capture_output=True, text=True, check=False, **options
    )
    if done.returncode != 0:
        print(done.stdout[-4000:], done.stderr[-4000:], sep="\n", file=sys.stderr)
        fail(f"{Path(str(command[0])).name} {' '.join(str(c) for c in command[1:3])} a échoué")
    return done


def shown(command: list[str | Path], cwd: Path) -> None:
    """A step whose output is long (tests, build): shown as it goes."""
    say(f"   $ {' '.join(str(c) for c in command)}")
    if subprocess.run([str(c) for c in command], cwd=cwd, check=False).returncode != 0:
        fail(f"{' '.join(str(c) for c in command[:3])} a échoué")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def settings() -> dict:
    return tomllib.loads((ROOT / "scripts" / "construction.toml").read_text(encoding="utf-8"))


# -- what is published: pure, tested (tests/test_publication.py) ------------------------------


def version_of(tag: str) -> str:
    found = TAG.match(tag)
    if found is None:
        fail(f"« {tag} » n'est pas une étiquette de version (vX.Y.Z)")
    return found.group(1)


def release_notes(changelog: str, version: str) -> str:
    """The version's section of CHANGELOG.md, without its heading (Markdown)."""
    lines = changelog.splitlines()
    start = next((i for i, line in enumerate(lines) if line.startswith(f"## v{version} ")), None)
    if start is None:
        fail(f"v{version} n'est pas dans CHANGELOG.md")
    end = next((i for i in range(start + 1, len(lines)) if lines[i].startswith("## ")), len(lines))
    return "\n".join(lines[start + 1 : end]).strip() + "\n"


def notes_html(notes: str) -> str:
    """The notes as plain HTML for Sparkle's window: headings and lists, nothing remote."""
    out: list[str] = []
    in_list = False
    for line in notes.splitlines():
        if line.startswith("- "):
            if not in_list:
                out.append("<ul>")
                in_list = True
            out.append(f"<li>{html.escape(line[2:])}</li>")
            continue
        if in_list:
            out.append("</ul>")
            in_list = False
        if line.startswith("### "):
            out.append(f"<h3>{html.escape(line[4:])}</h3>")
        elif line.strip():
            out.append(f"<p>{html.escape(line)}</p>")
    if in_list:
        out.append("</ul>")
    return "\n".join(out)


def dmg_url(repository: str, version: str) -> str:
    return f"https://github.com/{repository}/releases/download/v{version}/Coulisses-{version}.dmg"


def appcast(
    version: str, notes: str, url: str, length: int, ed_signature: str, minimum_macos: str
) -> str:
    """One item: the version published. Its notes are inline (no releaseNotesLink), the DMG
    is on github.com only; the whole feed is then signed by sign_update."""
    if not url.startswith("https://github.com/"):
        fail(f"le DMG doit être sur github.com : {url}")
    published = format_datetime(datetime.now(UTC))
    return (
        '<?xml version="1.0" encoding="utf-8"?>\n'
        f'<rss version="2.0" xmlns:sparkle="{SPARKLE_NS}">\n'
        "  <channel>\n"
        "    <title>Coulisses</title>\n"
        "    <language>fr</language>\n"
        "    <item>\n"
        f"      <title>Coulisses {version}</title>\n"
        f"      <pubDate>{published}</pubDate>\n"
        f"      <sparkle:version>{version}</sparkle:version>\n"
        f"      <sparkle:shortVersionString>{version}</sparkle:shortVersionString>\n"
        f"      <sparkle:minimumSystemVersion>{minimum_macos}</sparkle:minimumSystemVersion>\n"
        f"      <description><![CDATA[{notes_html(notes)}]]></description>\n"
        f'      <enclosure url="{html.escape(url)}" length="{length}"'
        f' type="application/octet-stream" sparkle:edSignature="{ed_signature}"/>\n'
        "    </item>\n"
        "  </channel>\n"
        "</rss>\n"
    )


def parse_signature(output: str) -> tuple[str, int]:
    """sign_update's `sparkle:edSignature="…" length="…"`."""
    found = re.search(r'sparkle:edSignature="([^"]+)"\s+length="(\d+)"', output)
    if found is None:
        fail(f"signature EdDSA illisible : {output.strip()[:200]}")
    return found.group(1), int(found.group(2))


# -- preparing ------------------------------------------------------------------------------


def checked_out(tag: str) -> Path:
    if run(["git", "-C", ROOT, "status", "--porcelain"]).stdout.strip():
        fail("le dépôt a des changements non commités : commitez ou rangez-les d'abord")
    if not run(["git", "-C", ROOT, "tag", "--list", tag]).stdout.strip():
        fail(f"l'étiquette {tag} n'existe pas (elle naît d'une fusion dans main)")
    work = CACHE / f"publication-{tag}"
    if work.exists():
        run(["git", "-C", ROOT, "worktree", "remove", "--force", work])
    run(["git", "-C", ROOT, "worktree", "add", "--detach", work, tag])
    return work


def test_everything(work: Path) -> None:
    say("2. Tous les tests de l'étiquette…")
    shown(["uv", "sync", "--offline", "--all-extras"], work)
    shown(["uv", "run", "--offline", "pytest", "-q"], work)
    shown(["uv", "run", "--offline", "ruff", "check", "."], work)
    shown(["uv", "run", "--offline", "pyright"], work)
    web = work / "web"
    shown(["npm", "ci", "--offline", "--no-audit", "--no-fund"], web)
    for script in ("typecheck", "test", "lint"):
        shown(["npm", "run", "-s", script], web)


def build_and_test(work: Path) -> Path:
    say("3. Construction signée, puis essai du paquet…")
    shown(["uv", "run", "--offline", "python", "scripts/construire.py"], work)
    app = work / "dist" / "Coulisses.app"
    shown(["scripts/essai-paquet.sh", "--publication", app], work)
    return app


def designated_requirement(app: Path) -> str:
    shown_req = run(["codesign", "--display", "--requirements", "-", app]).stdout.strip()
    line = shown_req.splitlines()[-1] if shown_req else ""
    if not line.startswith("designated =>") or "certificate leaf" not in line:
        fail(f"exigence désignée inattendue : « {line} »")
    return line


def previous_publication(version: str) -> Path | None:
    """The latest confirmed publication before this one, if any."""
    if not PUBLICATIONS.is_dir():
        return None
    older = [
        p
        for p in PUBLICATIONS.iterdir()
        if (p / CONFIRMED).is_file() and TAG.match(p.name) and p.name != f"v{version}"
    ]
    key = lambda p: tuple(int(n) for n in p.name[1:].split("."))  # noqa: E731
    return max(older, key=key) if older else None


def service(app: Path, data: Path, port: int, log: Path) -> subprocess.Popen[bytes]:
    """The app's service, as its launcher starts it (see essai-paquet.sh), on `data`."""
    resources = app / "Contents" / "Resources"
    env = {
        "HOME": str(Path.home()),
        "TMPDIR": os.environ.get("TMPDIR", "/tmp"),
        "PATH": "/usr/bin:/bin:/usr/sbin:/sbin",
        "COULISSES_RESSOURCES": str(resources),
        "COULISSES_DATA_DIR": str(data),
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONNOUSERSITE": "1",
    }
    command = [resources / "python" / "bin" / "python3", "-I", "-B", "-u", "-m"]
    command += ["coulisses_app.cli", "--sans-navigateur", "--port", str(port)]
    with log.open("ab") as out:
        return subprocess.Popen(
            [str(c) for c in command], env=env, stdout=out, stderr=out, cwd=Path.home()
        )


def answering(port: int, within: float = 120) -> str:
    deadline = time.monotonic() + within
    while time.monotonic() < deadline:
        done = subprocess.run(
            ["curl", "-s", "-m", "1", f"http://127.0.0.1:{port}/api/etat"],
            capture_output=True,
            text=True,
            check=False,
        )
        if done.returncode == 0 and done.stdout:
            return done.stdout
        time.sleep(1)
    fail(f"le service ne répond pas sur le port {port}")
    return ""


def stop(process: subprocess.Popen[bytes]) -> None:
    process.send_signal(signal.SIGINT)
    try:
        process.wait(timeout=60)
    except subprocess.TimeoutExpired:
        process.kill()
        fail("le service ne s'est pas arrêté")


def migration_test(previous: Path, app: Path) -> None:
    """The previous published app makes a base with a session; the new one opens it."""
    dmgs = sorted(previous.glob("Coulisses-*.dmg"))
    if not dmgs:
        fail(f"pas de DMG dans {previous}")
    with tempfile.TemporaryDirectory(prefix="coulisses-migration-") as work_dir:
        work = Path(work_dir)
        mount = work / "ancienne"
        run(["hdiutil", "attach", "-nobrowse", "-readonly", "-mountpoint", mount, dmgs[0]])
        try:
            data, log = work / "donnees", work / "service.log"
            run(["say", "-v", "Thomas", "-o", work / "voix.aiff", "Bonjour à tous."])
            old = service(mount / "Coulisses.app", data, 8797, log)
            try:
                answering(8797)
                run(
                    [
                        *("curl", "-s", "-f", "-F", f"fichier=@{work / 'voix.aiff'}"),
                        *("-F", "non_nommes=1", "http://127.0.0.1:8797/api/seances"),
                    ]
                )
            finally:
                stop(old)
        finally:
            run(["hdiutil", "detach", mount])
        new = service(app, data, 8797, log)
        try:
            answering(8797)
            listed = run(["curl", "-s", "-f", "http://127.0.0.1:8797/api/seances"]).stdout
        finally:
            stop(new)
        if '"id"' not in listed:
            print(log.read_text(encoding="utf-8", errors="replace")[-3000:], file=sys.stderr)
            fail("la séance de l'ancienne version ne se retrouve pas dans la nouvelle")
    say(f"   la base de {previous.name} s'ouvre dans la nouvelle version")


def make_dmg(app: Path, target: Path, identity: str) -> None:
    with tempfile.TemporaryDirectory(prefix="coulisses-dmg-") as work_dir:
        staging = Path(work_dir) / "Coulisses"
        staging.mkdir()
        run(["ditto", app, staging / "Coulisses.app"])
        (staging / "Applications").symlink_to("/Applications")
        run(
            [
                *("hdiutil", "create", "-volname", "Coulisses", "-srcfolder", staging),
                *("-fs", "APFS", "-format", "ULFO", "-ov", target),
            ]
        )
    run(["codesign", "--force", "--timestamp=none", "--sign", identity, target])


def prepare(tag: str) -> Path:
    version = version_of(tag)
    pinned = settings()
    sign_update = (
        CACHE / f"sparkle-{pinned['sparkle']['version']}" / "extrait" / "bin" / "sign_update"
    )
    if not sign_update.is_file():
        fail(f"{sign_update} manque : lancez d'abord scripts/construire.py --telecharger")
    say(f"1. L'étiquette {tag}, telle quelle…")
    work = checked_out(tag)
    out = PUBLICATIONS / tag
    if (out / CONFIRMED).is_file():
        fail(f"{tag} est déjà publiée pour les amis : une version se corrige par une suivante")
    test_everything(work)
    app = build_and_test(work)

    say("4. La même exigence désignée que la version publiée avant…")
    requirement = designated_requirement(app)
    previous = previous_publication(version)
    if previous is None:
        say("   première publication : rien à comparer")
    else:
        before = (previous / "exigence.txt").read_text(encoding="utf-8").strip()
        if before != requirement:
            fail(
                f"exigence désignée changée depuis {previous.name} : "
                "les amis perdraient leurs permissions"
            )
        say(f"   la même que {previous.name}")

    say("5. Migration depuis la version publiée avant…")
    if previous is None:
        say("   première publication : rien à migrer")
    else:
        migration_test(previous, app)

    say("6. DMG, signatures, notes et appcast…")
    if out.exists():
        shutil.rmtree(out)  # an earlier, unconfirmed preparation of the same tag
    out.mkdir(parents=True)
    dmg = out / f"Coulisses-{version}.dmg"
    make_dmg(app, dmg, pinned["signature"]["identity"])
    signature, length = parse_signature(run([sign_update, dmg]).stdout)
    notes = release_notes((work / "CHANGELOG.md").read_text(encoding="utf-8"), version)
    (out / "notes.md").write_text(notes, encoding="utf-8")
    feed = out / "appcast.xml"
    feed.write_text(
        appcast(
            version,
            notes,
            dmg_url(pinned["publication"]["repository"], version),
            length,
            signature,
            pinned["app"]["minimum_macos"],
        ),
        encoding="utf-8",
    )
    run([sign_update, feed])  # the signature goes inside the feed (SURequireSignedFeed)
    (out / "exigence.txt").write_text(requirement + "\n", encoding="utf-8")
    (out / "empreinte.txt").write_text(sha256(dmg) + "\n", encoding="utf-8")
    run(["git", "-C", ROOT, "worktree", "remove", "--force", work])
    size = run(["du", "-sh", dmg]).stdout.split()[0]
    say(f"Prêt : {dmg} ({size}), notes et appcast dans {out}. Rien n'est encore envoyé.")
    return out


# -- sending and confirming ----------------------------------------------------------------


def send(tag: str, out: Path) -> None:
    repository = settings()["publication"]["repository"]
    version = version_of(tag)
    dmg = out / f"Coulisses-{version}.dmg"
    say(f"Envoi de la pré-version {tag} sur GitHub ({repository}), sans appcast…")
    run(["git", "-C", ROOT, "push", "origin", tag])
    run(
        [
            *("gh", "release", "create", tag, "--repo", repository, "--prerelease"),
            *("--verify-tag", "--title", f"Coulisses {version}"),
            *("--notes-file", out / "notes.md", dmg),
        ]
    )
    say(
        f"Pré-version {tag} envoyée. Installez-la depuis GitHub, servez-vous-en, puis :\n"
        f"   uv run python scripts/publier.py --confirmer {tag}"
    )


def confirm(tag: str) -> None:
    pinned = settings()
    repository = pinned["publication"]["repository"]
    version = version_of(tag)
    out = PUBLICATIONS / tag
    dmg_name = f"Coulisses-{version}.dmg"
    if not (out / "appcast.xml").is_file():
        fail(f"{tag} n'a pas été préparée ici ({out})")
    visibility = run(
        ["gh", "repo", "view", repository, "--json", "visibility", "-q", ".visibility"]
    )
    if visibility.stdout.strip() != "PUBLIC":
        fail(f"{repository} est privé : les apps des amis ne pourraient pas lire l'appcast")
    shown_assets = run(
        [
            *("gh", "release", "view", tag, "--repo", repository),
            *("--json", "isPrerelease,assets", "-q"),
            f'[.isPrerelease, (.assets[] | select(.name == "{dmg_name}") | .digest)] | @tsv',
        ]
    ).stdout.split()
    expected = (out / "empreinte.txt").read_text(encoding="utf-8").strip()
    if len(shown_assets) != 2 or shown_assets[0] != "true":
        fail(f"{tag} n'est pas une pré-version avec son DMG sur GitHub")
    if shown_assets[1] != f"sha256:{expected}":
        fail(f"le DMG de la pré-version n'est pas celui préparé ({shown_assets[1]})")
    say(f"Publication de {tag} pour les amis…")
    run(["gh", "release", "upload", tag, out / "appcast.xml", "--repo", repository])
    run(["gh", "release", "edit", tag, "--repo", repository, "--prerelease=false", "--latest"])
    feed = run(["curl", "-sSfL", "-m", "30", pinned["sparkle"]["feed_url"]]).stdout
    if f"<sparkle:version>{version}</sparkle:version>" not in feed:
        fail("l'appcast publié ne donne pas cette version")
    (out / CONFIRMED).write_text(datetime.now(UTC).isoformat() + "\n", encoding="utf-8")
    say(f"{tag} est publiée : les apps des amis la trouveront à leur prochaine recherche.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Publie Coulisses.app (ADR 0040).")
    parser.add_argument("etiquette", help="vX.Y.Z")
    parser.add_argument("--envoyer", action="store_true", help="envoyer la pré-version")
    parser.add_argument("--confirmer", action="store_true", help="la publier pour les amis")
    args = parser.parse_args()
    if args.confirmer:
        confirm(args.etiquette)
        return
    out = prepare(args.etiquette)
    if args.envoyer:
        send(args.etiquette, out)


if __name__ == "__main__":
    main()
