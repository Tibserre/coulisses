# 0033 — Autant de micros que l'on veut, ajoutés un par un

Statut : Acceptée (2026-10-08, demande de l'utilisateur). Étend l'ADR 0031 (un deuxième micro) à N micros.

## Contexte
L'ADR 0031 permettait un deuxième micro, choisi dans un menu « Deuxième micro, en même temps ». L'utilisateur trouve le dialogue « Nouvelle séance » peu clair, et rien n'impose de s'arrêter à deux : plusieurs iPhone, un micro USB, un enregistreur branché peuvent servir ensemble.

## Décision
- Le dialogue « Nouvelle séance » s'ouvre sur le choix **Enregistrer maintenant** ou **Importer un fichier**, puis l'espace, le projet et les présents. Les boutons d'action restent visibles en bas, le reste défile.
- Pour enregistrer, une liste « Ce qui est enregistré » :
  - le micro **principal** (celui qui est traité) ;
  - les micros ajoutés par **« Ajouter un micro »**, chacun retirable ;
  - en ligne ou hybride, le son de l'ordinateur (ADR 0032).
  - Un même micro ne peut être choisi qu'une fois.
- Chaque micro ajouté a sa source et son fichier : `mic2`, `mic3`, … (`sources/micN.wav`), son vumètre et ses alertes. Comme dans l'ADR 0031, un micro ajouté qui lâche n'arrête pas l'enregistrement ; un micro qui refuse de démarrer empêche le départ sans rien laisser.
- Le traitement ne lit toujours que le micro principal (mixé au son de l'ordinateur s'il y en a un).

## Conséquences
- Rien de nouveau dans le schéma.
- Chaque micro ajouté est un flux de plus pour le Mac ; aucune limite n'est imposée, le Mac dit s'il ne suit pas (pertes comptées).
- La demande au moteur (synchronisation, usage de plusieurs pistes, ADR 0006) vaut pour N pistes.
