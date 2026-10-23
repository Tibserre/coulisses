# 0062 — Nommer les voix, guidé ; les détails de la séance à leur place

Statut : Acceptée (2026-10-23, choix de l'utilisateur sur maquettes : « la N1 est intéressante… pouvoir faire suivant ou précédent sur des répliques », puis « un truc par au-dessus, et fin veut pas dire illisible, utilise des icônes », « oui, construis »). Remplace, dans l'ADR 0060, le panneau des détails de la séance.

## Contexte
Le panneau à droite (0060) réunissait les voix à nommer, les participants, les présents, la note, les corrections et les versions. L'utilisateur : « le système pour nommer ne devrait pas ouvrir un tel panneau, et tous les détails ne s'affichent pas forcément au bon endroit… renommer et les détails de la séance, ce sont deux actions bien différentes ». Nommer une voix ne doit pas reposer sur une seule réplique tirée au hasard : il faut pouvoir en entendre plusieurs.

## Décision
- **Nommer, guidé** (forme précisée le 2026-10-23 après essai : « je peux interagir avec derrière… on peut avoir trop d'interactions », puis « M2, mais avec que des répliques de la même voix… pour les écouter à la suite ») : « N voix à nommer », à la suite des participants sous le titre, lance le nommage des voix sans nom, dans l'ordre où on les entend. Toute la page passe sous un voile (flouté, comme la pause, ADR 0059 ; opaque si la transparence est réduite) et ne répond plus. Au premier plan, une carte toujours au même endroit, avec **les répliques de cette voix, et seulement elles** : son nom, son nombre de répliques et son temps de parole, des points pour les voix faites et à faire ; une frise « où elle parle dans la séance », un trait par réplique à son heure mesurée ; ses cinq répliques les plus longues d'abord (où on l'entend le mieux), ou dans l'ordre, chacune avec sa durée mesurée, les autres sur demande ; un clic écoute une réplique, « Écouter … à la suite » les enchaîne (chacune un extrait de 8 s au plus). En bas, fixe, le champ « Qui est-ce ? » : les noms proposés s'ouvrent au-dessus, le premier contre le champ — la personne dont la voix semble être celle-ci (« voix reconnue », avec « Ce n'est pas elle », une correction qui s'annule, ADR 0057), puis les présents qui n'ont pas encore de voix, puis les autres ; un nom absent devient un invité ou un nom libre ; nommer d'après une personne qui a déjà une voix les réunit, et la liste le dit. ✓ (Entrée) nomme et passe à la voix suivante, ⏭ la passe, ✕ (Échap) quitte ; ← → écoutent la réplique d'avant ou d'après, Espace écoute ou arrête. Nommer dans le texte (« Nommer », la touche N) reste comme avant.
- **Les détails à leur place** :
  - les **participants**, en pastilles sous le titre, avec leur part du temps de parole ; un clic n'affiche que leurs répliques ;
  - les **présents**, dans le fil, à côté de l'espace et du projet (« 5 présents ▾ ») ;
  - les **corrections**, à droite de la bascule (« 3 corrections ▾ ») : les dernières, « Annuler », « Rétablir » ;
  - les **versions du traitement, les relances et l'état des étapes**, dans « ⋯ › Versions et traitement… », une fenêtre (avec, en mode développeur, les chiffres et le fichier d'origine) ;
  - la **note d'après séance**, en onglet « Ma note » de la vue Résumé, à côté des résumés, qui la lisent.

## Conséquences
- Spec §7.4, §7.6 et §7.8, et la direction artistique, mises à jour.
- Plus de panneau des détails.

## Alternatives écartées
- Un petit menu avec un champ par voix (N2), un bandeau au-dessus du texte (N3).
- Une voix à la fois, ses répliques seules dans le texte (G1) ; une fiche par voix avec la réplique et ses voisines (G2) ; une ligne insérée sous la réplique, qui pousse le texte ; une barre posée sur le texte encore actif, les autres voix estompées (essayée, écartée : trop d'interactions, tout en transparence) ; une vue dédiée (M1) ; le texte verrouillé sans voile (M3).
- Une page « À propos de la séance » réunissant les détails (D2) : un tiroir pour ce qu'on ne sait pas placer.
