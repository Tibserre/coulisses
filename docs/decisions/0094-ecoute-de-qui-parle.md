# 0094 — L'écoute de « Qui parle ? » : l'onde de la réplique et la ligne de la séance

Statut : Acceptée (2026-11-23, planches de « Qui parle ? » de la page 5 de la toile validées par l'utilisateur). Remplace, dans l'ADR 0090, l'onde de toute la séance sous ▶ ; précise l'ADR 0092 (son onde mesurée sert désormais à dessiner la réplique écoutée, et plus aucune onde n'est dessinée d'après les temps des répliques).

## Contexte
Après essai en dév, l'utilisateur : la visualisation « marche mal, notamment si la transcription est longue, les barres sont trop épaisses, c'est pas super clair ». Sur une séance de 1 h 12, une réplique de six secondes fait moins d'un pixel sur l'onde de la séance : on ne voit ni ce que joue ▶, ni où l'on en est.

## Décision
- **L'onde de la réplique écoutée**, sous ▶, sur la largeur de la colonne : 40 px de haut, une barre fine de 1,5 px tous les 3 px, encre à 72 %. Elle montre ce que joue ▶ : la réplique depuis son début, jusqu'à sa fin ou 8 s. Pendant l'écoute, la partie entendue passe en brique ; un clic dans l'onde reprend l'écoute à cet endroit.
- **Mesurée seulement** (P2) : les niveaux sont ceux de l'onde de la séance (0092), pris entre le début et la fin de ce qui est joué, chaque barre la plus haute crête de ses niveaux. Une réplique courte a moins de barres : l'onde ne s'étire pas et rien n'est inventé. Tant que l'onde n'est pas mesurée, ou s'il n'y en a pas, rien n'est dessiné (le dessin d'après les temps des répliques disparaît).
- **Dessous, la séance entière en une ligne**, 12 px de haut, 14 px plus bas : un filet (encre à 12 %), un trait de 8 px de haut là où cette voix parle (encre à 50 %, jamais moins de 2 px de large, même sur trois heures) et un point brique cerné de blanc sur la réplique écoutée. Un clic prend la réplique la plus proche et l'écoute ; au survol d'un trait, son heure dans la séance.

## Conséquences
- Spec §7.6 mise à jour.
- L'application demande au service l'onde du seul passage joué (`debut`, `fin`, 0092 précisé le 2026-11-27), 132 niveaux au plus : une crête par tranche de 50 ms jusqu'à 6,6 s de passage, quelle que soit la longueur de la séance.

## Alternatives écartées
- Garder l'onde de la séance en l'affinant : sur une longue séance, une réplique y reste invisible.
- Étirer l'onde d'une réplique courte sur toute la largeur : elle ferait croire à des détails qu'aucune mesure ne donne.
