# 0057 — Reconnaître les voix d'une séance à l'autre : des profils recalculés, jamais stockés, une proposition toujours confirmée

Statut : Acceptée (2026-10-21). Choix de l'utilisateur, à l'étape 13c-2 : profils recalculés plutôt qu'une table, « Non » retenu dans le journal des corrections, la proposition sous la voix dans « À nommer » avec une coche, une croix et le nom qui ouvre la liste des personnes, la voix reconnue en tête du panneau de nommage et déjà choisie (Entrée confirme). Pas de pourcentage de confiance (question de l'utilisateur) : la distance n'est pas une probabilité calibrée, elle n'est montrée qu'en mode développeur. S'appuie sur le moteur v1.12.0 (ADR 0055 du moteur).

## Contexte
Dans une troupe, ce sont presque toujours les mêmes personnes : nommer chaque voix à chaque séance est répétitif. Depuis la v1.12.0, le moteur garde une empreinte vocale par voix de chaque diarisation (même modèle quelle que soit la voie, 256 dimensions, conservée après la purge de l'audio) et fournit de quoi faire un profil par personne (`add_to_voice_profile`, `remove_from_voice_profile`) et comparer une voix aux profils (`match_voice`, sous 0,25 de distance cosinus). Mesuré au banc à l'intérieur d'une séance : 83 % des paires d'une même voix sous le seuil, 2,9 % des paires de voix différentes ; entre deux séances de la troupe, rien n'est encore mesuré. Le réglage d'espace « Reconnaître les voix d'une séance à l'autre » existait déjà (ADR 0020), sans effet. Principes : P3 (sur-segmenter plutôt que fusionner : un nom ne se pose jamais seul), P5 (les corrections ne se perdent pas), P8 (aucune perte silencieuse).

## Décision
- **Seulement dans les espaces où la reconnaissance des voix est activée.** Ailleurs, les voix ne sont jamais comparées.
- **Aucun profil n'est stocké.** Le profil d'une personne est refait à chaque affichage de la relecture. On part de la version affichée de chaque séance de l'espace : les voix confirmées dans son journal des corrections, et leurs empreintes, lues dans la diarisation dont vient cette version (`read_speaker_embeddings`). On les additionne avec `add_to_voice_profile`, chaque voix étant désignée par `séance/exécution/étiquette`.
  - Annuler un nommage, afficher une autre version ou supprimer une séance change donc le profil, sans rien à tenir à jour.
  - Désactiver la reconnaissance ne laisse aucune donnée vocale à effacer.
  - À l'activation, les nommages déjà faits servent tout de suite.
  - Les empreintes d'une diarisation, immuable une fois finie, sont lues une fois par processus.
- **Ce qui compte comme une confirmation** : une voix de la version affichée nommée d'après une personne de l'espace, ou fusionnée dans une voix ainsi nommée (nommer une deuxième voix « Marie » est une fusion). Un nom libre ou un personnage joué n'en est pas une (la voix d'un personnage peut être travestie). Une proposition n'en est jamais une. Une voix sans empreinte ne compte pas : trop peu de parole seule, ou diarisation d'avant la v1.12.0 (il faut alors refaire la séparation des voix).
- **La proposition.** Pour chaque voix non nommée qui a une empreinte, `match_voice` donne le profil le plus proche sous le seuil du moteur. Les personnes archivées et celles que l'utilisateur a refusées pour cette voix sont écartées. La vue la porte (`Speaker.proposal` : la personne, sa couleur, la distance). Elle n'est jamais appliquée seule.
- **Dans « À nommer »** : sous la voix, « C'est Marie ? », le nom dans la couleur de Marie, puis une coche et une croix.
  - La coche nomme la voix (`assign_speaker`). Le nommage devient une fusion si Marie a déjà une voix dans la séance, comme pour tout nommage.
  - Un clic sur le nom ouvre le panneau de nommage.
  - La croix inscrit le refus.
- **Dans le panneau de nommage** : la personne reconnue vient en tête de la liste, avec la note « voix reconnue », séparée des autres par un filet. Elle est déjà choisie : Entrée confirme, et taper filtre comme avant.
- **« Non » est une correction** : un nouveau genre, `reject_voice_match` (`{speaker, person_id}`), dans le journal `edit`. Il est décrit « Locuteur 3 : pas Marie », s'annule par Cmd-Z, et il est reporté sur une nouvelle version par le temps mesuré, comme un nommage (ADR 0028). Il n'y a pas de migration : `edit.kind` est vérifié dans le code.
- **Une empreinte illisible** (fichier modifié ou supprimé dans le Finder) n'empêche jamais la relecture. La séance concernée ne compte pas, et « À nommer » dit lesquelles n'ont pas pu être lues (`voices_problem`, P8).
- **Mode développeur** : la distance de chaque proposition.

## Conséquences
- Le calcul se refait à chaque affichage de la vue corrigée : il lit le journal de chaque séance de l'espace et une empreinte par diarisation. C'est quelques millisecondes par séance. Il se mettra en cache si l'usage le demande, sans changer de décision.
- Le seuil est celui du moteur : à remesurer entre séances réelles de la troupe. Un faux « C'est Marie ? » ne coûte qu'un clic sur la croix, et ne nomme jamais rien.
- Une voix dont certaines répliques ont été données à une autre voix garde l'empreinte calculée par le moteur sur toute la voix d'origine.
- Glossaire : « Profil vocal » (`voice_profile`), « Voix reconnue » (`voice_proposal`).
- Schéma de données : le genre `reject_voice_match` dans `edit`. Les profils sont absents de la base.
- Le texte du réglage d'espace ne dit plus « plus tard ».
