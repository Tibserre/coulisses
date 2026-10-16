# Relais : lot 12b, élaguer le paquet (pour « Distribution et publication »)

De : la conversation « Alléger Coulisses » (étape 12 du plan), le 2026-10-16. Ordre validé par l'utilisateur ce jour : 12b, 12c-1 et 12d d'abord, en parallèle.

## Ce qui est demandé
Alléger `Coulisses.app` et son DMG dans `scripts/construire.py` (et `publier.py` pour le DMG), sans rien perdre de ce que l'app charge. Ton territoire : je n'y touche pas.

Mesuré dans le DMG v0.28.0 (`docs/technique/tailles/2026-10-16-v0.28.0.md`) :

| Quoi | Taille | Proposition |
|---|---|---|
| Dossiers `tests/` et `test/` des paquets | 172 Mo | retirer ; garder `torch/testing` et tout ce qu'une bibliothèque importe elle-même |
| En-têtes et sources C, Cython (`.h`, `.hpp`, `.c`, `.cpp`, `.pyx`, `.pxd`…) | 83 Mo | retirer (rien ne compile à l'exécution : pas de `torch.compile`, pas d'extension C) |
| Stubs de types (`.pyi`) | 7 Mo | retirer |
| `pip` (venu de python-build-standalone, demandé par rien) | 13 Mo | retirer, avec `ensurepip` |
| Bibliothèque standard inutile : `idlelib`, `lib2to3`, `turtledemo`, `tkinter` et ce qui va avec | ≈ 5 Mo | retirer |
| DMG en `ULFO` (lzfse) | 773 Mo | essayer `ULMO` (lzma) ; mesurer aussi le temps d'ouverture du DMG chez un ami |

Gain estimé : ≈ 0,28 Go installé (la liste des fichiers signés, 20 Mo, baisse aussi avec le nombre de fichiers), 0,1 à 0,2 Go de DMG.

**À ne pas faire maintenant** : un Python sans `.py` (les `.pyc` seuls, 285 Mo de plus). torch, numba et transformers relisent leurs sources (`inspect`) ; à reconsidérer après le lot 12c, qui peut retirer numba.

## Pourquoi
L'utilisateur trouve Coulisses « franchement lourde » ; chaque mise à jour retélécharge tout le DMG (ADR 0040).

## Mesure attendue
Avant et après, avec le relevé (dans `main`) :
```
uv run python scripts/mesurer-tailles.py --app dist/Coulisses.app --comparer docs/technique/tailles/2026-10-16-v0.28.0.json
uv run python scripts/mesurer-tailles.py --dmg <le DMG préparé> --comparer docs/technique/tailles/2026-10-16-v0.28.0.json
```
Le relevé d'après se range à côté du premier (`docs/technique/tailles/<date>-<version>.{json,md}`, commande dans la docstring du script).

## Contrat, garde-fous
- `scripts/essai-paquet.sh` passe en entier : import de chaque format, traitement jusqu'au bout, rien d'écrit dans l'app, signature valide.
- Ce qui est retiré est listé par la construction (jamais en silence, P8), et la liste des retraits est dans `construction.toml` ou le script, pas devinée.
- Aucune nouvelle dépendance. La liste des contenus de l'ADR 0040 reste juste.

## Ce qui attend l'utilisateur
Rien avant le résultat. Dis à « Alléger Coulisses » (ou à Pilotage si elle est close) le gain mesuré.
