# 0064 — La version de l'application se numérote à la publication, pas à chaque fusion

Statut : Acceptée (2026-10-27, choix de l'utilisateur : la version se numérote à la publication ; les étiquettes v0.35.0 à v0.37.1 sont supprimées, option B). Remplace, pour l'application seulement, la règle « à chaque fusion » de l'ADR 0016 et l'étape 1 de la publication de l'ADR 0040. Le moteur ne change pas.

## Contexte
- Depuis l'ADR 0016, chaque fusion dans `main` qui apporte un `feat`, un `fix` ou un `perf` pose une version et son étiquette (`scripts/release.py`, hook `post-merge`).
- Entre deux publications, les numéros s'empilent : v0.35.0, v0.36.0, v0.37.0 puis v0.37.1 depuis v0.34.0, la dernière publiée. Les amis voient donc des sauts de numéro entre deux mises à jour.
- Ces quatre étiquettes n'existent que sur ce Mac : GitHub s'arrête à v0.34.0.
- Contraintes :
  - Sparkle compare des numéros (`CFBundleVersion`) : chaque version publiée doit dépasser la précédente ;
  - P7 : on doit savoir quel code a produit un résultat, y compris entre deux publications.

## Décision
- **Une fusion dans `main` ne pose plus ni version ni étiquette.** Le hook `post-merge` (`scripts/release.py`) réécrit la section « ## Non publié » en tête de `CHANGELOG.md`, toujours d'après les Conventional Commits faits depuis la dernière version, et la commite (`chore(changelog): …`). Sans rien de nouveau, rien ne se passe. Si la section avait été réécrite à la main, elle est remplacée et le hook le dit (P8) ; l'ancien texte reste dans git.
- **La version naît à la publication** : `scripts/publier.py --numeroter`, sur `main` propre.
  - La version suivante est calculée en SemVer à partir de tous les commits depuis la dernière version, comme avant. Plusieurs `feat` donnent donc une seule version mineure.
  - Elle est écrite dans les fichiers de `release.toml` (`pyproject.toml`, `web/package.json`) et dans `uv.lock`.
  - « Non publié » devient « ## vX.Y.Z — date ». Le script commite `chore(version): vX.Y.Z` et pose l'étiquette.
  - Distribution réécrit ensuite cette section pour les utilisateurs et la commite. Puis `publier.py vX.Y.Z` prépare, envoie et confirme comme aujourd'hui (ADR 0040).
- **Entre deux versions, le code se nomme par `git describe`** (`scripts/release.py --identifiant`) :
  - `v0.38.0` sur une version, `v0.38.0-12-gabc1234` douze commits après, avec `-modifie` si des fichiers suivis ont changé ;
  - `pyproject.toml`, `package.json` et `uv.lock` gardent la dernière version publiée ; `CFBundleVersion` aussi, donc Sparkle ne voit que des versions publiées.
- **Où s'affiche l'identifiant :**
  - `construire.py` l'écrit dans l'app (`Contents/Resources/identifiant-de-version`) ;
  - la préparation d'une publication refuse une app qui ne se dit pas exactement `vX.Y.Z` ;
  - le service le donne à côté de la version (`/api/etat`). Il le lit dans l'app, à défaut par `git describe` dans le dépôt (`--dev`), à défaut il donne la version du paquet ;
  - les Réglages montrent la version, et l'identifiant s'il diffère (en mode développeur) ;
  - la provenance des générations (`prompting/`) garde l'identifiant (P7).
- **Les étiquettes v0.35.0 à v0.37.1**, jamais poussées, sont supprimées de ce Mac (2026-10-27). Leurs sections de `CHANGELOG.md` sont fondues dans « Non publié ». La prochaine publiée est v0.35.0 : aucun saut pour les amis. Jusque-là, `pyproject.toml` dit encore 0.37.1, et l'identifiant dit `v0.34.0-…`. Elles visaient 44b7aa2, 74a3914, b11df44 et 92a452a, pour les reposer s'il le fallait.

## Conséquences
- Moins de bruit dans `main` (plus de `chore(version)` à chaque fusion). En contrepartie, un `chore(changelog)` à chaque fusion qui apporte du nouveau.
- Une version numérotée puis ratée avant l'envoi garde son étiquette (jamais déplacée, règle `v*`) : on corrige, et la suivante sera corrective.
- Les notes « réécrites pour les utilisateurs » se font après la numérotation, dans la section de la version. Une réécriture de « Non publié » est remplacée à la fusion suivante, avec un avertissement.
- Hors de Distribution, une fois l'ADR acceptée : l'identifiant dans `/api/etat` (Service), son affichage dans les Réglages (Interface), dans la provenance (Rédaction).
- **P7 : la branche des scripts n'est fusionnée qu'avec l'identifiant dans `/api/etat` et dans la provenance.** Sans eux, une génération faite entre deux publications porterait le numéro de la précédente.

## Alternatives écartées
- Garder une version à chaque fusion : c'est ce qui donne les sauts.
- Mettre l'identifiant `git describe` dans `CFBundleVersion` : Sparkle ne sait pas comparer ce format.
- Garder les étiquettes v0.35.0 à v0.37.1 : la prochaine publiée aurait été v0.38.0, un dernier saut depuis v0.34.0.
