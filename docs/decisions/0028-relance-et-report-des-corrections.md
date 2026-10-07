# 0028 — Relancer une étape : une nouvelle version, complète ou rien, et le report des corrections par le temps mesuré

Statut : Acceptée (2026-10-07, choix de l'utilisateur sur la forme de la relance, le schéma, les seuils du report et le sélecteur de version).

## Contexte
La spec veut que chaque étape se relance seule, que l'aval soit marqué périmé et jamais supprimé, et que les corrections soient reportées sur la nouvelle version, avec la liste de ce qui ne l'a pas été (§7.4, §7.6, P5, P8). Jusqu'ici, une correction était attachée à une exécution « qui a dit quoi » précise : une nouvelle exécution repartait de zéro, et les corrections de l'ancienne n'étaient que comptées.

La spec parlait aussi de relancer « avec un autre moteur ». La V1 n'a qu'un profil, défini par le moteur.

## Décision
- **Deux relances en V1**, depuis la version affichée : **la transcription** (avec l'alignement), qui prend le glossaire de l'espace tel qu'il est et la version installée du moteur, et garde la séparation des voix ; **la séparation des voix**, avec un autre nombre de présents (toujours un minimum, P3), qui garde la transcription. L'attribution est toujours refaite. « Un autre moteur » viendra quand le moteur proposera plusieurs profils.
- Une relance est une tâche `chain` dont les paramètres disent ce qui est refait (`rerun`) et quelles exécutions de la version de départ sont reprises telles quelles (`reuse`).
- **Une version est complète ou n'est pas.** Les exécutions d'une tâche ne deviennent actives qu'ensemble, quand toutes ses étapes ont réussi. Jusque-là, la version affichée reste en place et l'on peut continuer à la corriger. Les étapes qu'une relance refait sont signalées « périmées » ; si la relance s'arrête en route, rien ne change et « Reprendre » repart de ce qui a réussi.
- **Le report** se fait dans la même transaction que l'activation, depuis la version affichée à ce moment. Il ne devine jamais. Dans le doute, une correction n'est pas reportée : elle est listée avec sa raison et reste sur sa version.
  - le nom d'une voix va à la nouvelle voix qui reprend au moins la moitié de son temps de parole ;
  - une nouvelle voix appartient au groupe de voix (fusionnées par l'utilisateur) qui en tient le plus. Une autre voix retrouvée dedans ne la reprend pas : ni son nom, ni sa fusion, qui emporteraient les répliques d'une autre personne ;
  - une fusion suit les deux voix (déjà une seule : rien à écrire) ;
  - des répliques données à une voix vont aux nouvelles répliques qui sont surtout faites d'elles, si elles en couvrent au moins la moitié du temps ; si certaines ne se retrouvent pas, le report est « en partie » et listé lui aussi ;
  - une correction de texte ne va qu'à une réplique de texte d'origine identique, au même moment ;
  - une coupure de chapitre va à la réplique qui commence à deux secondes près ;
  - seule compte la dernière correction en vigueur d'un nom ou d'un texte.
- Une correction reportée est une **copie** sur la nouvelle exécution : elle s'annule comme les autres. Le lien entre l'original et la copie, ou la raison du non-report, est dans `edit_carryover` (migration 0006).
- **Une correction dit pour quelle version elle est faite.** La page envoie la version qu'elle affiche ; le service vérifie, dans la même transaction d'écriture que le report, que c'est toujours la version affichée. Sinon rien n'est écrit, la page se met à jour et rend le texte tapé : une correction ne tombe jamais sur la réplique d'une autre version, et aucune ne se perd entre le report et la bascule.
- Les réglages d'une version (nombre de présents, glossaire) se lisent dans les paramètres que l'application a donnés à la tâche, pas dans les entrées internes du moteur.
- **Les anciennes versions restent affichables.** Afficher une version réactive son exécution « qui a dit quoi », celles dont elle vient et ses derniers chapitres. Ses corrections sont les siennes : passer d'une version à l'autre ne reporte rien.

## Conséquences
- Pendant une relance de 15 minutes, la relecture continue. Ce qui est corrigé pendant ce temps est reporté à la fin.
- Après une relance de la séparation des voix, presque tout se reporte. Après une nouvelle transcription, les corrections de texte sur les passages retranscrits différemment sont listées, avec le texte corrigé pour le reprendre à la main.
- Les chapitres sont redétectés après chaque nouvelle version ; les résumés faits sur l'ancienne se signalent comme faits sur une autre version.
- Le premier traitement suit la même règle : ses exécutions deviennent actives ensemble, à la fin.

## Alternatives écartées
- Activer chaque étape dès qu'elle réussit : une relance arrêtée en route laisserait une version incohérente (transcription nouvelle, attribution ancienne).
- Reporter le résultat (qui parle à chaque instant) plutôt que le journal : on perdrait l'annulation correction par correction, et le lien avec ce que l'utilisateur a fait.
- Reporter une correction de texte par alignement des mots sur une transcription différente : le risque d'écrire au mauvais endroit est trop grand ; la liste avec le texte d'origine est plus sûre.
- Reporter aussi en passant d'une version à l'autre : les corrections se mélangeraient entre versions sans que l'utilisateur le voie.
