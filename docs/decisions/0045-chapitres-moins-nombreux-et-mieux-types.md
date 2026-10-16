# 0045 — Chapitres moins nombreux et mieux typés : « autre » posé à la main, vérification du type, regroupement

Statut : Acceptée (2026-10-16). L'utilisateur décide que « autre » ne se pose plus qu'à la main (2026-10-15), demande la vérification du type (piste D) et veut moins de chapitres, environ un toutes les 6 à 10 minutes (2026-10-16). Il retient comme réglages par défaut ceux du candidat mesuré : parties de 15 min, rappel de 3 min, 6 à 10 min par chapitre, vérification du type ; pas de regroupement. Précise les ADR 0024 et 0044.

## Contexte
Les chapitres de `qwen3.5:4b`, le petit modèle candidat pour les Mac de 16 Go (lot 11g), ont été notés contre des chapitres de référence écrits pour cinq vraies séances. Deux impros et trois réunions, soit 97 chapitres. Trois défauts ressortent :
- **Les types.** Sur l'axe utile, joué ou réel, le petit modèle prend une discussion pour du jeu pendant 11 % du temps : un résumé risque alors de traiter de vrais retours comme de la fiction. « Autre » est le type le plus flou. Même `qwen3.6:35b` ne le trouve que pour un tiers du temps où la référence le met, et les références elles-mêmes hésitent sur lui.
- **Le nombre.** Le petit modèle découpe trop fin : la moitié de ses chapitres durent moins de 1 à 2 minutes. L'utilisateur trouve le résultat peu lisible.
- **La finesse cible.** Les premières références découpaient environ toutes les 3 minutes. L'utilisateur veut plus large : un chapitre toutes les 6 à 10 minutes.

## Décision
- **« autre » ne se pose qu'à la main.** La détection ne propose plus que `scene` et `discussion` (le schéma imposé au modèle ne contient que ces deux valeurs). L'installation, une pause ou du bavardage deviennent des `discussion`. L'utilisateur garde « Autre » dans la correction des chapitres. Un « autre » que le modèle renverrait malgré tout est encore lu, rien n'est perdu.
- **Vérification du type** (`verifier_types_chapitres`). Une fois les chapitres placés, chacun est relu seul, avec ses seules répliques, pour dire s'il est joué ou non. Il y a un appel court par chapitre, toujours par l'assemblage unique (P4), et la réponse est imposée en JSON. Un type changé à la vérification est dit dans les ajustements (P8). Un chapitre trop long pour la fenêtre, ou une vérification illisible, garde son type, et c'est dit aussi. Ces appels sont de genre `review` dans la provenance : le schéma publié gagne cette valeur.
- **Regroupement** (`regrouper_chapitres`). Un dernier appel ne lit que la liste des chapitres (heure, type, durée, titre). Il regroupe les chapitres voisins qui forment un même moment, en visant l'ordre de grandeur réglé (`minutes_par_chapitre`) ; la découpe vise d'abord plus fin (`minutes_par_chapitre_decoupe`). Il ne crée aucune coupure : chaque groupe commence sur un chapitre détecté, sinon il est ramené sur le plus proche, et c'est dit. Une réponse illisible laisse les chapitres tels quels. Le regroupement compte comme un appel de `consolidation`.
- **La finesse visée** (`minutes_par_chapitre`, ADR 0044) passe de 4–10 à 6–10, la cible de l'utilisateur.
- **Les références de mesure** sont regroupées à cette finesse (`~/Coulisses/Mesures/references-larges/`, hors dépôt). Le regroupement n'y réunit que des chapitres fins, pour que les deux jeux restent comparables. La notation compte « autre » comme une discussion.

## Réglages retenus (2026-10-16)
Mesurés sur `qwen3.5:4b-mlx` contre les références larges, avec une coupure juste à 2 minutes près :
- **Viser 6 à 10 min directement**, sans regroupement : F1 de 0,50 et 0,46 selon la graine, 93 à 94 % de types justes, environ 135 s pour les cinq séances. `qwen3.6:35b` fait 0,53 et 98 %, en 200 s, pour cinq fois plus de mémoire.
- **Découper fin puis regrouper** : le petit modèle regroupe de façon irrégulière (de 8 à 2 chapitres sur une séance, de 46 à 40 sur une autre). Résultat : F1 de 0,29 à 0,36, en plus de deux fois le temps. Le réglage reste, désactivé, pour un modèle plus gros.
- `partie_chapitres_min = 15` (à la place de 25, ADR 0044), `rappel_chapitres_min = 3`, `minutes_par_chapitre = [6, 10]`, `verifier_types_chapitres = true`, `regrouper_chapitres = false`.

## Conséquences
- Une détection coûte plus d'appels : un par partie, un de regroupement s'il est activé, puis un par chapitre vérifié. Mesuré sur `qwen3.5:4b` : la vérification ajoute environ 60 % de temps, et gagne environ 5 points de types justes (88 à 91 % contre 84 à 85 %).
- Les chapitres déjà détectés ne changent pas. Une nouvelle détection suit les nouveaux réglages, et les corrections de l'utilisateur restent (ADR 0024).
- L'interface n'a rien à changer : « Autre » reste dans le choix du type.

## Alternatives écartées
- Plus de types (retours, consignes, échauffement, démo…) : plus d'erreurs pour un petit modèle, et le titre porte déjà cette nuance.
- Supprimer « autre » : l'utilisateur veut garder la possibilité de le poser.
- Une durée minimale appliquée sans LLM : l'effet est sûr, mais le chapitre fusionné garde le titre du plus long. L'utilisateur a préféré le regroupement par le modèle, qui renomme.
- Faire réfléchir le modèle (`think`) : `qwen3.5:4b` réfléchit sans fin et sa réponse est coupée, en plus de 4 minutes par séance.
