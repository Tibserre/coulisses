# 0076 — Aucun vocabulaire d'impro imposé par défaut

Statut : Proposée (2026-11-10, Rédaction, à la demande de l'utilisateur relayée par Pilotage : « je ne veux pas qu'il y ait tout ce vocabulaire d'impro que je ne pense pas necessaire »). Précise l'ADR 0020 (« les résumés proposés d'un espace » et « scènes et discussions pour l'impro ») ; s'appuie sur l'ADR 0063, acceptée, qui n'est pas encore dans `main`.

## Contexte
L'application va être donnée à quelqu'un qui ne fait pas forcément d'impro. Ce qui suppose aujourd'hui l'impro, dans `main` :
- **À la création d'un espace**, le modèle de départ proposé d'abord est « Troupe d'impro : Résumé Impro proposé » (ADR 0020). Un nouvel utilisateur se voit donc proposer le Résumé Impro.
- **Les chapitres** ont deux types, `scene` (un moment joué) et `discussion`. Le type `scene` s'affiche « Jeu », et il est dit « jeu » au modèle dans l'en-tête de chaque chapitre (`KIND_WORD`).
- **Les résumés fournis** : sur six, trois sont propres à l'impro (Résumé Impro, Retours de jeu par comédien, Idées de scènes et personnages).
- **Les voix jouées** (« personnage joué par ») n'apparaissent que si l'utilisateur en nomme.

En revanche, ce qui part au modèle est déjà écrit pour toute séance :
- le cadre système ne parle ni d'impro ni de troupe ;
- le prompt des chapitres est généraliste (ADR 0044). Il cite la répétition et la réunion à parts égales, et une séance sans jeu n'y a que des `discussion` ;
- le titre cite « une scène jouée » parmi d'autres exemples (une décision, un invité, un objet de travail).

L'ADR 0063, acceptée le 2026-10-27, supprime déjà les modèles de départ : un nouvel espace reçoit les 4 résumés de base, qui valent pour tout type de séance (« Le raconter à quelqu'un qui n'était pas là », « Savoir qui fait quoi », « Ce que chacun a apporté », « Ce qui reste ouvert »). Elle attend, avant d'entrer dans `main`, la comparaison à l'aveugle de ces 4 résumés, dont les fiches sont prêtes depuis le 2026-10-27.

## Décision
- **Les résumés proposés par défaut sont ceux de l'ADR 0063**, sans rien y ajouter : les 4 de base, neutres. Le Résumé Impro, les Retours de jeu et les Idées de scènes restent dans la bibliothèque, à ajouter à un espace par qui en veut ; ils ne sont proposés nulle part d'eux-mêmes.
  - Conséquence : la neutralité des résumés arrive avec l'ADR 0063. Le jugement à l'aveugle de ses 4 résumés en devient la condition.
  - D'ici là, l'écran de création d'un espace ne propose plus « Troupe d'impro » en premier : « Vide » ou « Réunions de travail » par défaut (Interface, `SpacesPage`), l'impro restant possible.
- **Les types de chapitres restent `scene` et `discussion`, et leurs prompts ne changent pas.** Ces prompts sont déjà neutres, et ils ont été mesurés (ADR 0044, 0045). Une réunion ne produit que des `discussion`. Les renommer côté modèle obligerait à tout mesurer de nouveau, sans rien y gagner pour le modèle.
- **À l'écran, le type d'un chapitre ne parle d'impro que s'il y a du jeu** (Interface) :
  - une séance sans aucun chapitre `scene` ne montre pas de type ;
  - le libellé de `scene` devient plus large que « Jeu ». Interface le propose (par exemple « Mise en situation »), et l'utilisateur choisit sur maquette.
- **Les séances déjà traitées ne changent pas** (P5). Leurs chapitres, leurs types, leurs résumés, leurs onglets et leurs provenances restent ce qu'ils sont. Seuls les libellés de l'écran changent. Les espaces existants gardent leurs résumés et leur ordre (ADR 0063 : leur résumé actuel en tête, puis les 4 de base).
- **Aucune mesure n'est nécessaire** tant qu'aucun prompt ne change, et cet ADR n'en change aucun.

## Conséquences
- Un nouvel utilisateur ne voit plus le mot « impro » tant qu'il n'en fait pas : ni dans les résumés proposés, ni dans les chapitres d'une réunion.
- La fusion de l'ADR 0063 conditionne la neutralité des résumés. Sans le jugement à l'aveugle, un nouvel espace reste « Vide » (aucun résumé proposé) ou « Réunions de travail » (Compte rendu de réunion).
- Le glossaire du domaine (`glossaire-domaine.md`) garde « scène » pour l'identifiant `scene`, et gagne le libellé retenu à l'écran.
- La spec §7.9 et le passage de l'ADR 0020 sur les modèles de départ sont mis à jour avec l'ADR 0063, quand elle entre dans `main`.

## Alternatives écartées
- **Des types de chapitre neutres côté modèle** (« moment joué », « échange ») : il faudrait mesurer de nouveau la détection des chapitres et la vérification de leur type, sur les mêmes séances, pour un modèle qui comprend déjà les deux mots.
- **Un réglage d'espace « pas de jeu »** qui retirerait les types et la vérification de chaque chapitre : cela économiserait un appel court par chapitre dans une réunion, mais demanderait un prompt de plus et sa mesure. À reprendre si le temps de traitement d'une réunion le justifie.
- **Retirer les résumés d'impro de la bibliothèque** : l'utilisateur fait de l'impro, et ses espaces les utilisent.
