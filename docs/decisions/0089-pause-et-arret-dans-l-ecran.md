# 0089 — La pause et l'arrêt dans l'écran d'enregistrement, sans voile

Statut : Acceptée (2026-11-18, planches EnregD5aPauseA et EnregD5aArretA validées par l'utilisateur sur la toile de maquettes, transmises par le rôle Design). Remplace l'écran d'arrêt de 0058 (« une grande icône stop dans un disque », la barre de 3 s) et l'écran de pause décrit en spec §7.2 d'après 0059 ; précise la mesure du flou de 0059 pour ces deux états. Le reste de 0058 (pas de confirmation, 3 s pour reprendre, la relecture qui se construit) et le principe de 0059 tiennent.

## Contexte
Avec l'écran D5a (0088), le voile flouté de la pause et de l'arrêt couvrait tout l'écran et changeait toute sa disposition. L'utilisateur veut voir de loin que c'est en pause ou que ça s'arrête, et que tout est coupé, sans que la page change de forme. Principes : P8 (les alertes ne sont jamais cachées).

## Décision
- **Le même écran**, sans voile : rien d'autre ne change de place.
- **Le titre** : « En pause » ou « Arrêt » prend la place du temps, à sa taille. Le temps, arrêté, passe en petit au-dessus, sans le point rouge.
- **Ce qui est coupé, en grand** : deux disques gris de 84 px (le micro barré, le son de l'ordinateur barré) prennent la place des présents, de la langue et de l'espace, à la même hauteur. Dans la barre du haut, les mêmes icônes sont barrées et les niveaux à plat ; la barre est hors d'atteinte.
- **L'onde** reste derrière, floutée (5 px) et estompée (opacité 0,34). Elle ne défile plus et ne se manipule plus.
- **Deux ronds de 80 px**, de part et d'autre du centre : « Arrêter » à gauche, « Reprendre » à droite. « Moment » disparaît.
  - Le rond plein, couleur brique, est ce qui compte maintenant.
  - En pause, « Reprendre » est plein (Espace).
  - À l'arrêt, « Arrêter » est plein et « Reprendre » est clair (Espace, Échap).
  - Les libellés sont sous les ronds. Il n'y a aucune phrase visible : « La séance s'ouvre dans un instant » est seulement lu par les lecteurs d'écran.
- **Les secondes de l'arrêt** : un anneau brique de 4 px se remplit autour du rond « Arrêter » pendant le délai du service. Il a une marge réservée de 14 px, pour ne jamais toucher le libellé. Avec moins d'animations, il avance par paliers d'une seconde.
- **Les alertes** restent au premier plan, comme pendant l'enregistrement.

## Conséquences
- Il n'y a plus de voile, donc plus de repli opaque pour `prefers-reduced-transparency` : l'onde estompée reste lisible comme un fond. Le flou de 0059 ne s'applique plus qu'à l'onde.
- Pendant la pause, les présents, la langue et l'espace ne se changent plus. Ils redeviennent accessibles à la reprise.
- Pendant l'arrêt, « Arrêter » ne fait rien de plus : l'arrêt est déjà en route.

## Alternatives écartées
- **Garder le voile de 0059 par-dessus D5a** : il cachait l'écran entier et le faisait changer de forme.
