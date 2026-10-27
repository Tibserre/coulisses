"""Versions of the app, numbered at publication only (ADR 0064), never by hand-editing a
version number.

Commits follow Conventional Commits, in French after the type (see CLAUDE.md):
    feat(portée): ajoute …        -> minor version
    fix(portée): corrige …        -> patch version
    perf(portée): accélère …      -> patch version
    feat(contrat)!: …  or a « BREAKING CHANGE: » line in the body -> major version
Other types (docs, test, refactor, build, chore, style) bring no version on their own.

    release.py            after each merge into main (the `post-merge` hook): rewrites the
                          « Non publié » section of CHANGELOG.md from the commits since the
                          last version, and commits it; no version, no tag
    release.py --apercu   says the version a publication would take now, writes nothing
    release.py --publier  numbers the publication (`publier.py --numeroter` runs it): the
                          next version (Semantic Versioning; before 1.0.0, an incompatible
                          change only raises the minor number) in the files of
                          `release.toml`, the « Non publié » section becomes its own,
                          « chore(version): vX.Y.Z », tag vX.Y.Z
    release.py --identifiant   the identifier of this checkout between two versions
                          (`git describe`, e.g. v0.38.0-12-gabc1234, « -modifie » if tracked
                          files are changed)

Only main is numbered, from a clean checkout. Standard library only.
"""

from __future__ import annotations

import re
import subprocess
import sys
import tomllib
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
UNRELEASED = "## Non publié"
HEADER = re.compile(r"^(?P<type>[a-z]+)(?:\((?P<scope>[^)]+)\))?(?P<bang>!)?: (?P<desc>.+)$")
SECTIONS = {
    "breaking": "Changements incompatibles",
    "feat": "Nouveautés",
    "fix": "Corrections",
    "perf": "Performances",
}


def git(*args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(ROOT), *args], capture_output=True, text=True, check=True
    ).stdout.strip()


def last_tag() -> str | None:
    tags = git("tag", "--list", "v*", "--sort=-v:refname").splitlines()
    tags = [tag for tag in tags if re.fullmatch(r"v\d+\.\d+\.\d+", tag)]
    return tags[0] if tags else None


def identifier() -> str:
    """This checkout between two versions: `vX.Y.Z` on a version, else
    `vX.Y.Z-<commits since>-g<commit>`, `-modifie` when tracked files are changed."""
    return git(
        "describe", "--tags", "--match", "v[0-9]*.[0-9]*.[0-9]*", "--dirty=-modifie", "--always"
    )


def commits_since(tag: str | None, end: str = "HEAD") -> list[tuple[str, str]]:
    span = f"{tag}..{end}" if tag else end
    raw = git("log", span, "--no-merges", "--format=%s%x1f%b%x1e")
    out: list[tuple[str, str]] = []
    for record in raw.split("\x1e"):
        if record.strip():
            subject, _, body = record.strip().partition("\x1f")
            out.append((subject.strip(), body))
    return out


def classify(commits: list[tuple[str, str]]) -> dict[str, list[str]]:
    groups: dict[str, list[str]] = {key: [] for key in SECTIONS}
    for subject, body in commits:
        m = HEADER.match(subject)
        if not m or (m["type"] == "chore" and (m["scope"] or "") == "version"):
            continue
        scope = f" ({m['scope']})" if m["scope"] else ""
        line = f"{m['desc']}{scope}"
        if m["bang"] or "BREAKING CHANGE:" in body:
            groups["breaking"].append(line)
        elif m["type"] in groups:
            groups[m["type"]].append(line)
    return groups


def next_version(current: str, groups: dict[str, list[str]]) -> str | None:
    major, minor, patch = (int(x) for x in current.lstrip("v").split("."))
    if groups["breaking"]:
        return f"{major + 1}.0.0" if major >= 1 else f"0.{minor + 1}.0"
    if groups["feat"]:
        return f"{major}.{minor + 1}.0"
    if groups["fix"] or groups["perf"]:
        return f"{major}.{minor}.{patch + 1}"
    return None


def current_version() -> str:
    """Before the first tag: the version written in the first file of release.toml (so a
    repository that starts at 1.0.0 never falls back to 0.x)."""
    config = tomllib.loads((ROOT / "release.toml").read_text(encoding="utf-8"))
    for entry in config.get("fichiers", []):
        m = re.search(entry["motif"], (ROOT / entry["chemin"]).read_text(encoding="utf-8"), re.M)
        if m:
            return m.group(1)
    return "0.0.0"


def write_version(version: str) -> list[str]:
    """Each `[[fichiers]]` of release.toml: a path and a regex whose group 1 is replaced."""
    config = tomllib.loads((ROOT / "release.toml").read_text(encoding="utf-8"))
    touched: list[str] = []
    for entry in config.get("fichiers", []):
        path = ROOT / entry["chemin"]
        text = path.read_text(encoding="utf-8")
        pattern = re.compile(entry["motif"], re.MULTILINE)
        if not pattern.search(text):
            sys.exit(f"Version introuvable dans {entry['chemin']} (motif {entry['motif']!r})")
        new = pattern.sub(lambda m: m.group(0).replace(m.group(1), version), text, count=1)
        path.write_text(new, encoding="utf-8")
        touched.append(entry["chemin"])
    return touched


def relock() -> list[str]:
    """Each folder of `verrous` in release.toml: its uv.lock records the project's own
    version, so it is refreshed (offline) in the same commit as the new version."""
    config = tomllib.loads((ROOT / "release.toml").read_text(encoding="utf-8"))
    touched: list[str] = []
    for folder in config.get("verrous", []):
        result = subprocess.run(
            ["uv", "lock", "--offline", "--quiet"],
            cwd=ROOT / folder,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            sys.exit(f"Verrou non mis à jour dans {folder} : {result.stderr.strip()}")
        touched.append(f"{folder}/uv.lock")
    return touched


def section(title: str, groups: dict[str, list[str]]) -> str:
    lines = [title, ""]
    for key, heading in SECTIONS.items():
        if groups[key]:
            lines += [f"### {heading}", "", *(f"- {item}" for item in groups[key]), ""]
    return "\n".join(lines).rstrip() + "\n"


def unreleased_section() -> str | None:
    """The « Non publié » section as it is in CHANGELOG.md, if any."""
    path = ROOT / "CHANGELOG.md"
    text = path.read_text(encoding="utf-8") if path.exists() else ""
    start = text.find("\n" + UNRELEASED + "\n")
    if start < 0 or text.find("\n## ") != start:
        return None
    following = text.find("\n## ", start + 1)
    return text[start + 1 : following + 1 if following >= 0 else None].rstrip() + "\n"


def written_by_hand(tag: str | None) -> bool:
    """« Non publié » is not what this script wrote at its last change of CHANGELOG.md:
    someone rewrote it, and the next rewrite replaces it (git keeps it)."""
    found = unreleased_section()
    if found is None:
        return False
    last = git("log", "-1", "--format=%H", "--", "CHANGELOG.md")
    if not last:
        return True
    return found != section(UNRELEASED, classify(commits_since(tag, last)))


def write_changelog(text: str | None) -> bool:
    """Puts `text` (a section, or None for none) where « Non publié » is: on top, under the
    title, in place of the former one. True if CHANGELOG.md changed."""
    path = ROOT / "CHANGELOG.md"
    old = path.read_text(encoding="utf-8") if path.exists() else "# Journal des versions\n"
    head, sections = old, ""
    first = old.find("\n## ")
    if first >= 0:
        head, sections = old[:first].rstrip() + "\n", old[first + 1 :]
    if sections.startswith(UNRELEASED + "\n") or sections.rstrip() == UNRELEASED:
        following = sections.find("\n## ")
        sections = sections[following + 1 :] if following >= 0 else ""
    parts = [head.rstrip() + "\n"]
    if text:
        parts.append(text)
    if sections:
        parts.append(sections)
    new = "\n".join(parts)
    if new == old:
        return False
    path.write_text(new, encoding="utf-8")
    return True


def commit(message: str, *paths: str) -> None:
    git("add", *paths)
    git(
        "commit",
        "-q",
        "-m",
        message,
        "-m",
        "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>",
    )


def on_clean_main() -> bool:
    if git("rev-parse", "--abbrev-ref", "HEAD") != "main":
        return False
    if git("status", "--porcelain", "--untracked-files=no"):
        sys.exit("CHANGELOG.md non mis à jour : des modifications ne sont pas commitées.")
    return True


def unreleased() -> None:
    """After a merge: the « Non publié » section says what the next publication brings."""
    if not on_clean_main():
        return  # versions are numbered from main only
    tag = last_tag()
    by_hand = written_by_hand(tag)
    groups = classify(commits_since(tag))
    text = section(UNRELEASED, groups) if any(groups.values()) else None
    if write_changelog(text):
        if by_hand:
            print(
                "ATTENTION : la section « Non publié » avait été réécrite à la main ; elle est "
                "remplacée par celle des commits (l'ancienne reste dans git : "
                "git log -p CHANGELOG.md). Réécrire les notes après publier.py --numeroter.",
                file=sys.stderr,
            )
        commit("chore(changelog): met à jour la section « Non publié »", "CHANGELOG.md")
        print("CHANGELOG.md : section « Non publié » mise à jour (aucune version posée)")


def upcoming() -> tuple[str | None, dict[str, list[str]]]:
    tag = last_tag()
    groups = classify(commits_since(tag))
    return next_version(tag or current_version(), groups), groups


def number() -> str:
    """The publication's version: files, CHANGELOG.md, commit and tag. Exits if none."""
    if not on_clean_main():
        sys.exit("Une version ne se numérote que sur main.")
    version, groups = upcoming()
    if version is None:
        sys.exit("Aucune version à publier (pas de feat, fix, perf ni changement incompatible).")
    touched = write_version(version)
    touched += relock()
    write_changelog(section(f"## v{version} — {date.today().isoformat()}", groups))
    commit(f"chore(version): v{version}", "CHANGELOG.md", *touched)
    git("tag", "-a", f"v{version}", "-m", f"v{version}")
    print(f"Version numérotée : v{version} (étiquette v{version}, CHANGELOG.md à jour)")
    return version


def main() -> None:
    action = sys.argv[1] if len(sys.argv) > 1 else None
    if action is None:
        unreleased()
    elif action == "--publier":
        number()
    elif action == "--apercu":
        version, _ = upcoming()
        print(f"v{version}" if version else "Aucune version à publier.")
    elif action == "--identifiant":
        print(identifier())
    else:
        sys.exit(f"Option inconnue : {action} (--apercu, --publier, --identifiant)")


if __name__ == "__main__":
    main()
