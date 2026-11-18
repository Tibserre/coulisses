# 0089 — La pause et l'arrêt dans l'écran d'enregistrement, sans voile

Statut : Acceptée (2026-11-18). Consignes de l'utilisateur transmises par le rôle Design :
- aucun voile, rien d'estompé ;
- l'écran lui-même dit la pause ;
- les trois boutons restent en place, « Pause » devient « Reprendre » ;
- l'anneau fait le tour d'« Arrêter » ;
- un second appui sur « Arrêter » arrête tout de suite.

Les planches EnregD5aPause et EnregD5aArret ont ensuite été validées. Une première version, en paire de ronds sur une onde floutée, a été écartée par l'utilisateur.

Cette décision remplace l'écran d'arrêt de 0058 (la grande icône stop dans un disque, la barre de 3 s) et l'écran de pause décrit en spec §7.2 d'après 0059. Le reste de 0058 tient : pas de confirmation, 3 s pour reprendre, la relecture qui se construit.

## Contexte
Avec l'écran D5a (0088), le voile flouté de la pause et de l'arrêt couvrait tout l'écran et en changeait la forme. L'utilisateur veut voir clairement que l'enregistrement est en pause, sur l'écran d'enregistrement lui-même et sans rien estomper. Principe concerné : P8 (les alertes ne sont jamais cachées).

## Décision
- **Rien n'est voilé ni estompé.** L'écran reste net et rien ne change de place.
- **Le titre.** Le temps reste en grand, mais grisé. « En pause » ou « Arrêt » s'écrit en petit au-dessus, à la place de « Enregistrement en cours » (demande de l'utilisateur à l'essai, 2026-11-18 ; la première version mettait « En pause » en grand à la place du temps).
- **Présents, langue et espace** sont inchangés et restent réglables.
- **L'onde s'arrête.** Elle reste nette, sans barres vives, et sa tête passe du brique au gris. Sur la tête, deux disques sombres de 56 px sont empilés : le micro barré au-dessus, le son de l'ordinateur barré dessous. Dans la barre du haut, les mêmes icônes sont barrées et les niveaux à plat ; la barre est hors d'atteinte.
- **Les trois boutons gardent leur place et leur taille.**
  - « Moment » est grisé et inactif.
  - « Arrêter » ne change pas.
  - « Pause » devient « Reprendre » (triangle), avec Espace en pause, et Espace ou Échap à l'arrêt.
- **L'arrêt.** Un anneau blanc de 4 px fait le tour à l'intérieur du rond « Arrêter » pendant le délai du service, sans rien qui dépasse ; puis la séance s'ouvre. Un second appui sur « Arrêter » arrête tout de suite (`POST /api/enregistrement/arret`, la route de la barre des menus) ; les lecteurs d'écran le lisent « Arrêter tout de suite ». Si macOS demande moins d'animations, l'anneau avance par paliers d'une seconde.
- **Les alertes** restent au premier plan, comme pendant l'enregistrement.

## Conséquences
- Le flou de 0059 n'a plus d'usage dans l'enregistrement.
- Rien à l'écran n'annonce le second appui : seul le libellé d'accessibilité le dit.
- Les présents se changent aussi en pause, ce qui est utile quand quelqu'un arrive.

## Alternatives écartées
- **Le voile de 0059 par-dessus D5a** : il cachait tout l'écran.
- **Une paire de ronds Arrêter et Reprendre sur une onde floutée** (planches EnregD5aPauseA et EnregD5aArretA) : écartée par l'utilisateur, qui ne veut rien d'estompé.
