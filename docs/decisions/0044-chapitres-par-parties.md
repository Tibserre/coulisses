# 0044 — Les chapitres lus par parties, avec un ordre de grandeur, par un prompt généraliste

Statut : Acceptée (2026-10-14 : l'utilisateur accepte la lecture par parties, jugée à l'œil sur trois vraies séances). Précise l'ADR 0024, qui lisait la séance en un appel.

## Contexte
L'utilisateur veut un petit modèle pour les chapitres (ADR 0039, lot 11g), qui tienne sur un Mac de 16 Go. Le 2026-10-14, quatre petits modèles (`qwen3.5:2b` et `4b`, `gemma4:e2b` et `e4b`, en MLX) ont lu en un appel trois vraies séances (deux impros de 1 h 32 et 1 h 44, une réunion de 40 min). Ils sont rapides (3 à 36 s) et légers (4 à 11 Go), mais ils perdent le fil d'une longue séance. Sur l'impro de 1 h 44, un seul chapitre couvre 1 h 20, voire la séance presque entière. Le prompt, écrit pour l'impro, donnait aussi un plancher (« en général plus d'une minute ») que Gemma suit à la lettre : un chapitre par minute. Enfin, les petits modèles recopient les titres donnés en exemple : « Retours sur la scène du catch » pour une séance sans catch.

## Décision
- **Les chapitres se lisent par parties** (glossaire : `section`) d'au plus `partie_chapitres_min` minutes (25, dans `prompting/textes/reglages.toml`). Les parties d'une même séance ont toutes la même durée : 1 h 32 donne quatre parties de 23 min. Une séance plus courte qu'une partie se lit d'un coup. Une partie trop longue pour la fenêtre du modèle est encore coupée, comme avant (ADR 0022). Chaque appel passe par l'assemblage complet (P4).
- **Chaque partie connaît le dernier chapitre de la précédente.** Si elle commence par la suite de ce moment, le modèle redonne le même type et le même titre, et l'application réunit les deux. Sinon, un chapitre commence avec la partie. Dans les deux cas, la détection le dit dans ses ajustements (P8).
- **Un ordre de grandeur est donné au modèle**, d'après la durée lue : entre une coupure toutes les 10 minutes et une toutes les 4 (« ce passage dure environ 23 minutes : vise entre 2 et 6 chapitres »). Il remplace le plancher d'une minute.
- **Le prompt des chapitres est généraliste.** Un chapitre est « un moment où le groupe fait la même chose, sur le même sujet », avec des exemples d'impro et de réunion. Il ne donne aucun titre en exemple : il en décrit la forme. Les types ne changent pas (`scene`, `discussion`, `autre`).

## Conséquences
- `qwen3.5:4b-mlx` donne à l'œil des chapitres justes : 22, 20 et 12 chapitres, en 13 à 31 s, avec 5 à 8 Go en mémoire. Chaque scène jouée est nommée, et chaque point de la réunion aussi. Les deux Gemma de petite taille ignorent l'ordre de grandeur (jusqu'à 108 chapitres) : ils ne conviennent pas aux chapitres.
- `qwen3.6:35b` sépare désormais chaque scène jouée, qu'il regroupait en un appel, mais il donne plus de chapitres (20 à 28).
- Une coupure peut tomber à la limite d'une partie quand le modèle ne reconnaît pas la suite. L'utilisateur la retire d'un geste (ADR 0024).
- La durée d'une partie est gardée dans `spec.json` de la détection (P7).
- Une séance de 1 h 30 coûte quatre appels au lieu d'un. Avec un petit modèle, ils restent plus rapides que l'appel unique d'un gros.
- Choisir le modèle conseillé pour les chapitres reste à faire (lot 11g) : ces mesures le préparent.

## Alternatives écartées
- Garder un appel unique avec un modèle plus gros : trop lourd pour un Mac de 16 Go.
- Couper les parties selon les tokens plutôt que selon la durée : l'ordre de grandeur se dit en minutes, et une partie de durée fixe se comprend mieux dans les ajustements.
- Un appel de fusion après les parties : un appel de plus, pour ce qu'une comparaison de titre et de type règle.
