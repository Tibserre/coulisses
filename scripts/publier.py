"""Publish a version of Coulisses.app for the friends (ADR 0040; plan step 11f), from this Mac.

    uv run python scripts/publier.py vX.Y.Z [--premiere]  prepares, sends nothing
    uv run python scripts/publier.py vX.Y.Z --envoyer     that preparation, as a pre-release
    uv run python scripts/publier.py vX.Y.Z --confirmer   the friends get it

Preparing, in this order, each step stopping the next:
1. the tag exists and this repository is clean; the tag is checked out in a worktree of the
   cache: what is published is exactly the tag;
2. every test of the tag (Python, interface, types, lint);
3. the build, signed with the certificate (`construire.py`), then the package test with
   --publication (an ad hoc signature, or no update key, fails);
4. the designated requirement is the previous publication's: otherwise the friends would
   lose their permissions (without any confirmed publication here, only --premiere goes on);
5. the previous published app makes a base with a session, the new one opens it
   (migrations), network cut, with empty models;
6. the DMG (the app inside signed, the image itself not); its EdDSA signature; the notes,
   from CHANGELOG.md; the appcast, signed too (the app requires it), without any remote
   resource.
Everything is kept in ~/Coulisses/Publications/vX.Y.Z.

Sending (--envoyer) takes that preparation as it is (never built again), pushes the tag and
makes a GitHub pre-release with the DMG and the notes, without the appcast: the friends get
nothing yet; the user installs it and uses it. A preparation once sent is never replaced.
Confirming (--confirmer) checks that the repository is public and that GitHub holds the very
DMG prepared, then uploads the appcast and makes the release the latest: the friends' apps
find it. Cut short, it can be run again. One publication at a time on this Mac.
"""

from __future__ import annotations

import argparse
import fcntl
import hashlib
import html
import json
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
SENDING = "envoi-commence"
SENT = "envoyee"
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
        say(f"   l'essai précédent de {tag} ({work}) est retiré")
        run(["git", "-C", ROOT, "worktree", "remove", "--force", work])
    run(["git", "-C", ROOT, "worktree", "add", "--detach", work, tag])
    return work


def one_at_a_time() -> object:
    """Two publications at once would remove each other's worktree."""
    CACHE.mkdir(parents=True, exist_ok=True)
    handle = (CACHE / "publication.verrou").open("a+", encoding="utf-8")
    try:
        fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        fail("une autre publication tourne déjà sur ce Mac")
    return handle


def test_everything(work: Path) -> None:
    say("2. Tous les tests de l'étiquette…")
    shown(["uv", "sync", "--offline", "--all-extras"], work)
    shown(["uv", "run", "--offline", "pytest", "-q"], work)
    shown(["uv", "run", "--offline", "ruff", "check", "."], work)
    shown(["uv", "run", "--offline", "pyright"], work)
    web = work / "web"
    shown(["npm", "ci", "--offline", "--no-audit", "--no-fund", "--ignore-scripts"], web)
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


def numbers(version: str) -> tuple[int, ...]:
    return tuple(int(n) for n in version.split("."))


def previous_publication(version: str) -> Path | None:
    """The latest confirmed publication older than this one, if any."""
    if not PUBLICATIONS.is_dir():
        return None
    older = [
        p
        for p in PUBLICATIONS.iterdir()
        if (p / CONFIRMED).is_file()
        and TAG.match(p.name)
        and numbers(p.name[1:]) < numbers(version)
    ]
    return max(older, key=lambda p: numbers(p.name[1:])) if older else None


NETWORK_CUT = """(version 1)
(allow default)
(deny network-outbound)
(allow network-outbound (remote ip "localhost:*"))
(allow network-outbound (remote unix-socket))
"""


def service(app: Path, work: Path, port: int) -> subprocess.Popen[bytes]:
    """The app's service as its launcher starts it (see essai-paquet.sh), network cut, on
    `work/donnees`, with empty models and environments: a session imported there fails
    at once instead of being processed."""
    resources = app / "Contents" / "Resources"
    for folder in ("modeles", "environnements"):
        (work / folder).mkdir(exist_ok=True)
    (work / "reseau.sb").write_text(NETWORK_CUT, encoding="utf-8")
    env = {
        "HOME": str(Path.home()),
        "TMPDIR": os.environ.get("TMPDIR", "/tmp"),
        "PATH": "/usr/bin:/bin:/usr/sbin:/sbin",
        "COULISSES_RESSOURCES": str(resources),
        "COULISSES_DATA_DIR": str(work / "donnees"),
        "COULISSES_MODELS_DIR": str(work / "modeles"),
        "COULISSES_ENVS_DIR": str(work / "environnements"),
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONNOUSERSITE": "1",
    }
    command = ["sandbox-exec", "-f", work / "reseau.sb"]
    command += [resources / "python" / "bin" / "python3", "-I", "-B", "-u", "-m"]
    command += ["coulisses_app.cli", "--sans-navigateur", "--port", str(port)]
    with (work / "service.log").open("ab") as out:
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
            run(["say", "-v", "Thomas", "-o", work / "voix.aiff", "Bonjour à tous."])
            old = service(mount / "Coulisses.app", work, 8797)
            try:
                answering(8797)
                made = run(
                    [
                        *("curl", "-s", "-f", "-F", f"fichier=@{work / 'voix.aiff'}"),
                        *("-F", "non_nommes=1", "http://127.0.0.1:8797/api/seances"),
                    ]
                ).stdout
            finally:
                stop(old)
        finally:
            run(["hdiutil", "detach", mount])
        session_id = json.loads(made)["id"]
        new = service(app, work, 8797)
        try:
            answering(8797)
            found = subprocess.run(
                ["curl", "-s", "-f", f"http://127.0.0.1:8797/api/seances/{session_id}"],
                capture_output=True,
                check=False,
            ).returncode
        finally:
            stop(new)
        if found != 0:
            print((work / "service.log").read_text(errors="replace")[-3000:], file=sys.stderr)
            fail("la séance de l'ancienne version ne se retrouve pas dans la nouvelle")
    say(f"   une séance faite par {previous.name} s'ouvre dans la nouvelle version")


def make_dmg(app: Path, target: Path) -> None:
    """The DMG, not signed itself: macOS checks a signed disk image when it opens it, and one
    signed with a certificate it does not know is blocked, a second time after the app. The
    app inside is signed with the certificate, and the DMG with the update key (EdDSA)."""
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


def replaceable(out: Path) -> bool:
    """Whether an earlier preparation of the same tag may be replaced: never once sent
    (its DMG is on GitHub and cannot be built again identically), nor once confirmed."""
    if (out / CONFIRMED).is_file():
        fail(f"{out.name} est déjà publiée pour les amis : une version se corrige par une suivante")
    if (out / SENT).is_file() or (out / SENDING).is_file():
        fail(
            f"{out.name} est déjà envoyée (ou son envoi a commencé) : reprenez avec --envoyer "
            "puis --confirmer, ou publiez une version suivante"
        )
    return out.exists()


def same_repository(origin: str, repository: str) -> bool:
    """Whether the remote `origin` is exactly github.com/<repository> (https or ssh)."""
    path = re.sub(r"^(https://github\.com/|git@github\.com:|ssh://git@github\.com/)", "", origin)
    return path.removesuffix(".git").removesuffix("/") == repository


def prepare(tag: str, first: bool) -> Path:
    version = version_of(tag)
    pinned = settings()
    out = PUBLICATIONS / tag
    replaced = replaceable(out)
    previous = previous_publication(version)
    if previous is None and not first:
        fail(
            f"aucune version confirmée avant {tag} dans {PUBLICATIONS} : sans elle, ni "
            "l'exigence désignée ni la migration ne se vérifient. Pour la toute première "
            "publication, relancez avec --premiere."
        )
    if previous is not None and first:
        fail(f"--premiere, alors que {previous.name} est déjà publiée")
    tools = CACHE / f"sparkle-{pinned['sparkle']['version']}" / "extrait" / "bin"
    if not (tools / "sign_update").is_file():
        fail(f"{tools / 'sign_update'} manque : lancez d'abord scripts/construire.py --telecharger")
    say(f"1. L'étiquette {tag}, telle quelle…")
    work = checked_out(tag)
    say(f"   (en cas d'échec, l'étiquette reste dans {work} pour comprendre)")
    test_everything(work)
    app = build_and_test(work)

    say("4. La même exigence désignée que la version publiée avant…")
    requirement = designated_requirement(app)
    if previous is None:
        say("   première publication (--premiere) : rien à comparer")
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
        say("   première publication (--premiere) : rien à migrer")
    else:
        migration_test(previous, app)

    say("6. DMG, signatures, notes et appcast…")
    if replaced:
        say(f"   la préparation précédente de {tag}, jamais envoyée, est remplacée")
        shutil.rmtree(out)
    out.mkdir(parents=True)
    dmg = out / f"Coulisses-{version}.dmg"
    make_dmg(app, dmg)
    signature, length = parse_signature(run([tools / "sign_update", dmg]).stdout)
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
    run([tools / "sign_update", feed])  # the signature goes inside it (SURequireSignedFeed)
    run([tools / "sign_update", "--verify", feed])
    run([tools / "sign_update", "--verify", dmg, signature])
    (out / "exigence.txt").write_text(requirement + "\n", encoding="utf-8")
    (out / "empreinte.txt").write_text(sha256(dmg) + "\n", encoding="utf-8")
    run(["git", "-C", ROOT, "worktree", "remove", "--force", work])
    size = run(["du", "-sh", dmg]).stdout.split()[0]
    say(
        f"Prêt : {dmg} ({size}), notes et appcast dans {out}. Rien n'est encore envoyé.\n"
        f"Pour l'envoyer en pré-version : uv run python scripts/publier.py {tag} --envoyer"
    )
    return out


# -- sending and confirming ----------------------------------------------------------------


def send(tag: str) -> None:
    """The preparation as it is (never built again), as a GitHub pre-release."""
    repository = settings()["publication"]["repository"]
    version = version_of(tag)
    out = PUBLICATIONS / tag
    dmg = out / f"Coulisses-{version}.dmg"
    if not (out / "appcast.xml").is_file() or not dmg.is_file():
        fail(f"{tag} n'est pas préparée ici : lancez d'abord scripts/publier.py {tag}")
    if (out / CONFIRMED).is_file() or (out / SENT).is_file():
        fail(f"{tag} est déjà envoyée : il reste --confirmer")
    expected = (out / "empreinte.txt").read_text(encoding="utf-8").strip()
    if sha256(dmg) != expected:
        fail(f"{dmg} a changé depuis sa préparation")
    origin = run(["git", "-C", ROOT, "remote", "get-url", "origin"]).stdout.strip()
    if not same_repository(origin, repository):
        fail(f"origin ({origin}) n'est pas {repository}")
    # Before anything leaves: from now on, this preparation is never replaced.
    (out / SENDING).write_text(datetime.now(UTC).isoformat() + "\n", encoding="utf-8")
    say(f"Envoi de la pré-version {tag} sur GitHub ({repository}), sans appcast…")
    run(["git", "-C", ROOT, "push", "origin", tag])
    existing = subprocess.run(
        ["gh", "release", "view", tag, "--repo", repository, "--json", "isPrerelease,assets"],
        capture_output=True,
        text=True,
        check=False,
    )
    if existing.returncode == 0:  # an earlier send cut short after creating the release
        fields = json.loads(existing.stdout)
        if not any(a.get("name") == dmg.name for a in fields.get("assets", [])):
            fail(
                f"la pré-version {tag} existe sur GitHub sans son DMG (envoi coupé) : "
                f"supprimez-la (gh release delete {tag} --repo {repository}), "
                "puis relancez --envoyer"
            )
        release_state(fields, dmg.name, expected)
        say("   la pré-version existait déjà, avec ce DMG : l'envoi est repris")
    else:
        run(
            [
                *("gh", "release", "create", tag, "--repo", repository, "--prerelease"),
                *("--verify-tag", "--title", f"Coulisses {version}"),
                *("--notes-file", out / "notes.md", dmg),
            ]
        )
    (out / SENT).write_text(datetime.now(UTC).isoformat() + "\n", encoding="utf-8")
    say(
        f"Pré-version {tag} envoyée. Installez-la depuis GitHub, servez-vous-en, puis :\n"
        f"   uv run python scripts/publier.py {tag} --confirmer"
    )


def release_state(fields: dict, dmg_name: str, expected_sha256: str) -> str:
    """What GitHub holds for the tag (`gh release view --json isPrerelease,assets`):
    "pre-release" or "published", with the very DMG prepared; anything else stops."""
    digests = [a.get("digest") for a in fields.get("assets", []) if a.get("name") == dmg_name]
    if digests != [f"sha256:{expected_sha256}"]:
        fail(f"le DMG sur GitHub n'est pas celui préparé ({digests or 'absent'})")
    return "pre-release" if fields.get("isPrerelease") else "published"


def confirm(tag: str) -> None:
    pinned = settings()
    repository = pinned["publication"]["repository"]
    version = version_of(tag)
    out = PUBLICATIONS / tag
    if not (out / SENT).is_file():
        fail(f"{tag} n'a pas été envoyée depuis ce Mac ({out})")
    visibility = run(
        ["gh", "repo", "view", repository, "--json", "visibility", "-q", ".visibility"]
    )
    if visibility.stdout.strip() != "PUBLIC":
        fail(f"{repository} est privé : les apps des amis ne pourraient pas lire l'appcast")
    fields = json.loads(
        run(
            [
                *("gh", "release", "view", tag, "--repo", repository),
                *("--json", "isPrerelease,assets"),
            ]
        ).stdout
    )
    expected = (out / "empreinte.txt").read_text(encoding="utf-8").strip()
    state = release_state(fields, f"Coulisses-{version}.dmg", expected)
    tools = CACHE / f"sparkle-{pinned['sparkle']['version']}" / "extrait" / "bin"
    run([tools / "sign_update", "--verify", out / "appcast.xml"])  # unchanged since signed
    say(f"Publication de {tag} pour les amis…")
    # Again after a confirmation cut short: the appcast is the one prepared, replaced.
    run(["gh", "release", "upload", tag, out / "appcast.xml", "--repo", repository, "--clobber"])
    if state == "pre-release":
        run(["gh", "release", "edit", tag, "--repo", repository, "--prerelease=false", "--latest"])
    feed = run(["curl", "-sSfL", "-m", "30", pinned["sparkle"]["feed_url"]]).stdout
    if f"<sparkle:version>{version}</sparkle:version>" not in feed:
        fail("l'appcast publié ne donne pas cette version")
    (out / CONFIRMED).write_text(datetime.now(UTC).isoformat() + "\n", encoding="utf-8")
    say(f"{tag} est publiée : les apps des amis la trouveront à leur prochaine recherche.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Publie Coulisses.app (ADR 0040).")
    parser.add_argument("etiquette", help="vX.Y.Z")
    action = parser.add_mutually_exclusive_group()
    action.add_argument("--envoyer", action="store_true", help="envoyer la pré-version préparée")
    action.add_argument("--confirmer", action="store_true", help="la publier pour les amis")
    parser.add_argument("--premiere", action="store_true", help="la toute première publication")
    args = parser.parse_args()
    if args.premiere and (args.envoyer or args.confirmer):
        parser.error("--premiere ne vaut que pour préparer")
    lock = one_at_a_time()
    try:
        if args.confirmer:
            confirm(args.etiquette)
        elif args.envoyer:
            send(args.etiquette)
        else:
            prepare(args.etiquette, args.premiere)
    finally:
        lock.close()  # type: ignore[attr-defined]


if __name__ == "__main__":
    main()
