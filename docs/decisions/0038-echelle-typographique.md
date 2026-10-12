# 0038 — Une échelle typographique pour une interface, pas un rapport fixe

Statut : Acceptée (2026-10-12, plan de la revue d'interface validé par l'utilisateur). Remplace, dans l'ADR 0017, la ligne « base 15 px, rapport 1,333 ».

## Contexte
L'ADR 0017 fixe une échelle par rapport constant : base 15 px, rapport 1,333. Ce rapport convient aux titres d'une page éditoriale, mais pas à une interface :
- vers le bas, il donne 11 px pour le texte d'appoint et 8 px pour les plus petits libellés ;
- vers le haut, il donne 36 et 47 px.

La revue d'interface du 12 octobre 2026 a relevé ce déséquilibre : des titres énormes (le titre d'une séance occupait un quart de l'écran), des textes d'appoint minuscules (la colonne de gauche, les aides, les dates). L'utilisateur a validé le plan qui le corrige.

## Décision
- **Base 15 px**, inchangée, comme le transcript en 17 px avec un interligne de 1,6.
- **Rien sous 12 px.** Les plus petits libellés font 12 px, et le texte d'appoint (aides, dates, colonne de gauche) 13 px.
- **Titres** : 18, 22, 28 et 34 px. Le titre d'une séance fait 28 px, et les chiffres clés 22 px, en dessous de lui.
- L'échelle est donnée taille par taille dans le thème (`--font-size-xs` à `--font-size-5xl`), et non plus calculée par un rapport.

## Conséquences
- Toute nouvelle taille se prend dans cette échelle. Une variable de taille qui n'existe pas fait hériter la taille du parent, sans erreur : il n'y en a plus.
- La direction artistique (`docs/produit/direction-artistique.md`) décrit cette échelle.
