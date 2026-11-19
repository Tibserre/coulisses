# 0093 — L'en-tête d'une séance : le dossier, le titre, les faits, la pile des voix

Statut : Acceptée (2026-11-19, maquettes de la page 4 de la toile retenues par l'utilisateur : l'ordre A, « garde le A », puis la liste des voix sur la séance, « Oui, validées »). Remplace, dans l'ADR 0062, les participants en étiquettes sous le titre et « N voix à nommer ».

## Contexte
L'en-tête d'une séance alignait le fil (espace, projet, présents, langue), le titre et ses faits, des étiquettes par voix nommée avec leur part de parole, « Fusionner les deux … » et « N voix à nommer », puis la frise des chapitres. Avec « Qui parle ? » (0090), les voix ont une pile et une liste : l'en-tête les reprend.

## Décision
- **De haut en bas** : le dossier en retrait (icône, « espace › projet », la langue seulement selon 0072, « ⋯ » au bout de la ligne) ; le titre ; les faits sur une ligne discrète (date · durée · présents, ce dernier ouvrant les présents) ; la pile des voix.
- **La pile des voix** est un seul bouton, sans libellé : les voix nommées superposées, « +N » en gris pour les voix sans nom ; « Nommer les voix » au survol. Un clic ouvre la liste de « Qui parle ? » : les voix à nommer d'abord (une voix sans nom ouvre « Qui parle ? » sur elle), un trait, puis les nommées avec leur temps de parole ; un nom n'affiche plus que ses répliques (la barre au-dessus du texte, inchangée) ; deux voix d'une même personne y sont proposées à la réunion (« Réunir les deux Marie »).
- **Les chapitres** : le chapitre lu au-dessus de la barre ; au survol, un segment s'épaissit et son infobulle donne son titre, son genre, son heure et sa durée ; « N chapitres » les liste tous par-dessus le texte, avec « Détecter à nouveau ». Le genre ne se montrera que dans un espace qui a « Jeu et personnages » (0091).

## Conséquences
- Spec §7.5 et §7.6 mises à jour.
- La part de parole en pourcentage disparaît de l'en-tête : le temps de parole est dans la liste des voix.
- Pointer une étiquette ne marque plus la voix sur la barre du lecteur ; l'afficher seule le fait toujours.

## Alternatives écartées
- L'ordre B (le dossier à côté de la pile) : retiré au profit de A.
- Garder les étiquettes des voix sous la pile : la liste fait la même chose, sans doubler.
