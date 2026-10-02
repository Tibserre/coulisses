"""Publish a version from the commits merged since the last one: run on `main` after each
merge (the `post-merge` hook does it), never by hand-editing a version number.

Commits follow Conventional Commits, in French after the type (see CLAUDE.md):
    feat(portée): ajoute …        -> minor version
    fix(portée): corrige …        -> patch version
    perf(portée): accélère …      -> patch version
    feat(contrat)!: …  or a « BREAKING CHANGE: » line in the body -> major version
Other types (docs, test, refactor, build, chore, style) publish nothing on their own.

What it does: computes the next version (Semantic Versioning; before 1.0.0, an
incompatible change only raises the minor number), writes it in the files listed in
`release.toml`, adds a section to CHANGELOG.md, commits « chore(version): vX.Y.Z » and
tags vX.Y.Z. Nothing to publish: it says so and changes nothing. Standard library only.
"""

from __future__ import annotations

import re
import subprocess
import sys
import tomllib
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
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
    return tags[0] if tags else None


def commits_since(tag: str | None) -> list[tuple[str, str]]:
    span = f"{tag}..HEAD" if tag else "HEAD"
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
        if not m or m["type"] == "chore" and (m["scope"] or "") == "version":
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


def write_changelog(version: str, groups: dict[str, list[str]]) -> None:
    path = ROOT / "CHANGELOG.md"
    lines = [f"## v{version} — {date.today().isoformat()}", ""]
    for key, title in SECTIONS.items():
        if groups[key]:
            lines += [f"### {title}", "", *(f"- {item}" for item in groups[key]), ""]
    section = "\n".join(lines).rstrip() + "\n"
    old = path.read_text(encoding="utf-8") if path.exists() else "# Journal des versions\n"
    first = old.find("\n## ")  # the newest version goes on top, under the title
    if first < 0:
        new = old.rstrip() + "\n\n" + section
    else:
        new = old[:first].rstrip() + "\n\n" + section + "\n" + old[first + 1 :]
    path.write_text(new, encoding="utf-8")


def main() -> None:
    if git("rev-parse", "--abbrev-ref", "HEAD") != "main":
        return  # versions are published from main only
    if git("status", "--porcelain", "--untracked-files=no"):
        sys.exit("Version non publiée : des modifications ne sont pas commitées.")
    tag = last_tag()
    groups = classify(commits_since(tag))
    version = next_version(tag or current_version(), groups)
    if version is None:
        print("Aucune version à publier (pas de feat, fix, perf ni changement incompatible).")
        return
    touched = write_version(version)
    write_changelog(version, groups)
    git("add", "CHANGELOG.md", *touched)
    git(
        "commit",
        "-q",
        "-m",
        f"chore(version): v{version}",
        "-m",
        "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>",
    )
    git("tag", "-a", f"v{version}", "-m", f"v{version}")
    print(f"Version publiée : v{version} (étiquette v{version}, CHANGELOG.md à jour)")


if __name__ == "__main__":
    main()
