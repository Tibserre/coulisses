# 0066 — Refaire le traitement : tout ou une partie, à part des versions

Statut : Acceptée (2026-10-27, demande de l'utilisateur après un essai en dév : « c'est assez moche ce parcours et pas clair… il faut que l'on puisse tout relancer ou relancer qu'une partie si on veut, fais ça plus en lien avec le style des interfaces actuelles »). Précise l'ADR 0062 (« ⋯ › Versions et traitement… ») et l'ADR 0028 (les relances).

## Contexte
Relancer passait par « ⋯ › Versions et traitement… », puis « Relancer… », puis une seconde fenêtre à boutons radio (la transcription ou la séparation des voix, jamais les deux). Pendant la relance, un bandeau montrait une roue qui tourne en boucle (contraire à la DA) et le pourcentage de la phase en cours, qui repartait de zéro à chaque phase.

## Décision
- **Une entrée à part dans « ⋯ » : « Refaire le traitement… »**, absente quand l'audio est supprimé. « Versions et traitement… » devient « Versions… » (la liste des versions, ce qui a été reporté, l'état des étapes en mode développeur ou en cas d'échec) ; son bouton « Refaire le traitement… » ouvre la même fenêtre.
- **Trois choix en tuiles**, avec les icônes des disques de l'écran de traitement : **Tout** (le texte et les voix, depuis l'audio, avec le glossaire de l'espace tel qu'il est et un nombre de présents, minimum de voix, P3), **Le texte** (les voix gardées), **Les voix** (le texte gardé, un autre nombre de présents). « Tout » est proposé d'abord. Une phrase dit ce qui est refait et gardé, la durée (mesurée la dernière fois, sinon environ 10 min par heure d'audio ; pour « Tout », la plus longue des deux, faites côte à côte), et le bouton dit l'action : « Tout refaire », « Refaire le texte », « Refaire les voix ».
- **Pendant la relance**, au-dessus du texte, un petit anneau qui avance comme ceux de l'écran de traitement (même calcul, phase par phase, sans recul), « Le texte est refait · environ N min », et la version affichée reste en place.
- Le service accepte `etape: "all"` (demandé à Service) ; la nouvelle version a pour origine « tout refait ».

## Conséquences
- La fenêtre ne s'ouvre plus par-dessus une autre.
- Tant que le service ne connaît pas `all`, « Tout refaire » est refusé et l'erreur s'affiche : la branche web n'entre dans `main` qu'avec celle de Service.

## Écarté
- Garder la relance dans la fenêtre des versions : deux fenêtres l'une sur l'autre, jugé « pas clair ».
- Des cases à cocher par étape (transcription, alignement, voix, attribution) : trop technique ; l'alignement suit le texte et l'attribution suit toujours.
