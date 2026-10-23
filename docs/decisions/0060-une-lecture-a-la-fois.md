# 0060 — Une lecture à la fois : la transcription ou les résumés

Statut : Acceptée (2026-10-23, choix de l'utilisateur sur maquettes : « R1, ouverture sur la transcription », résumés « S1 » simplifiés, « ok pour les trois, un cran suffit »). Remplace l'organisation « Deux colonnes » de l'ADR 0017 ; remplace, dans l'ADR 0025, le choix du modèle au moment de générer et la comparaison dans l'interface ordinaire ; remplace, dans l'ADR 0039, « le modèle choisi dans l'onglet Résumé devient celui des résumés » ; précise l'écran de traitement de l'ADR 0058.

## Contexte
La relecture montrait la transcription à gauche et, à droite, « Vue d'ensemble » et « Résumé ». L'utilisateur : « on lit pas la transcription ET les résumés en même temps, soit l'un soit l'autre ». La colonne de droite mêlait ce qui se lit (le résumé) et ce qui s'utilise (voix, présents, corrections, versions). Les résumés passaient par une liste « Générer », un choix de modèle et un « Historique » à cocher, jugés « un peu rincés » : « le but est que ça soit simple, pas méga techos ».

## Décision
- **Une colonne de lecture**, à la largeur du texte, sous un en-tête commun (fil, titre, frise des chapitres, lecteur en pied de page). Une bascule « Transcription | Résumé » sous la frise. La page s'ouvre sur la transcription ; un résultat de recherche dans un résumé l'ouvre sur le résumé. Chaque vue garde sa place quand on revient.
- **Les détails de la séance** (voix à nommer, participants, présents, note d'après séance, corrections, versions, traitement) sont dans un panneau qui s'ouvre à droite, par-dessus la page, en glissant : par « N voix, M à nommer » sous le titre, par le nombre de corrections, ou par l'icône des détails. ✕ ou Échap le referme.
- **Une citation d'un résumé** qui mène à une réplique ouvre la transcription à cet endroit.
- **Les résumés en onglets** : un onglet par résumé rédigé (le résumé de l'espace d'abord, puis dans l'ordre où ils ont été demandés), qui montre sa dernière version ; « + Rédiger… » pour un autre. Sans résumé : « Rédiger : » le résumé de l'espace, ou un autre.
- **Refaire** en un clic, avec le modèle de Réglages › Rédaction : le modèle ne se choisit plus dans la page.
- **Revenir à la version d'avant**, d'un cran seulement, juste sous un résumé refait. Le service ajoute une ligne `generation` qui pointe vers l'exécution d'avant, avec sa date : rien n'est effacé ni réécrit (P5), pas de changement de schéma. Une version revenue ne recule pas plus loin.
- **Toutes les versions, leur comparaison côte à côte et les prompts envoyés** restent, en mode développeur. La recherche ne lit que la version affichée de chaque résumé : un résultat ouvre ce qu'il a trouvé. Le service accepte encore un modèle nommé dans la demande (outils, développement) ; l'interface n'en envoie jamais.
- **Écrire un résumé** se dit sans rien qui tourne : une phrase et des lignes immobiles ; la version d'avant reste lisible pendant qu'une nouvelle s'écrit.
- **Pendant le traitement** (précise 0058) : deux disques immobiles, « Le texte » (transcription, puis alignement) et « Les voix » (diarisation), que le moteur fait en même temps ; seul leur anneau avance, en 400 ms, à chaque avancement publié. Puis « Qui a dit quoi · quelques secondes ». À l'arrivée, un disque montre la part de parole de chacun, avec les noms, puis s'efface (400 ms) et sa place se referme (850 ms). Les chapitres s'écrivent ensuite, dits par une phrase, sans indicateur qui tourne. Le détail est dans `docs/produit/animation-du-traitement.md`.

## Conséquences
- Spec §5, §7.4, §7.6, §7.8, §7.9 et §7.12, et la direction artistique (l'écran de relecture), mises à jour.
- Les chiffres clés d'une réunion (décisions, actions, questions) restent de côté.
- Les chapitres qui arrivent partie par partie demandent un changement du service dans `prompting/` (Rédaction et modèles) ; ils feront l'objet de leur propre ADR.

## Alternatives écartées
- Le résumé d'abord, la transcription comme source (R2) ; un seul document, résumé en tête (R3) : l'utilisateur relit et corrige surtout la transcription.
- Un document fait de blocs (S2) ; un seul résumé dont on change le type (S3) : S1 jugé le plus fonctionnel.
- Garder toutes les versions à l'écran : jugé « du stockage pour rien » à montrer ; elles restent sur le disque, comme le veut P5.
- Les détails dans un menu flottant : les listes (voix, versions) y sont trop longues ; un panneau les tient.
