# 0029 — Garder ou purger l'audio, supprimer une séance pour de bon

Statut : Acceptée (2026-10-07, choix de l'utilisateur). Remplace, dans l'ADR 0018, la règle selon laquelle les sauvegardes de la base gardent le texte d'une séance supprimée.

## Contexte
La spec veut que l'audio soit gardé une durée choisie puis supprimé, avec un préavis, et que le texte ne disparaisse que par une suppression explicite de la séance (§7.10, P5, P8). L'ADR 0018 prévoyait qu'une séance supprimée reste dans les copies de sauvegarde de la base, que l'utilisateur supprime lui-même. L'utilisateur veut au contraire qu'une séance supprimée le soit vraiment, partout. Il juge aussi que « épingler » ne dit pas ce que fait l'option : garder l'audio.

## Décision
- **« Garder l'audio »** est une option de la séance (`session.keep_audio`) : son audio n'est jamais purgé. Elle remplace le terme « épinglée ».
- **Durée** : 90 jours par défaut, réglable, comptés depuis l'**entrée de la séance dans l'application** (import ou enregistrement), jamais depuis la date du fichier : un vieux fichier importé aujourd'hui n'est pas purgeable tout de suite. « Prolonger » repousse l'échéance d'une durée entière à partir d'aujourd'hui.
- **Préavis réel** : une purge est d'abord annoncée (`purge_announced_at`), par un bandeau dans l'application et une notification macOS (`osascript`, sans dépendance). Elle n'a lieu qu'une fois le préavis écoulé depuis cette annonce. Garder l'audio, prolonger ou raccourcir la durée annule l'annonce : la prochaine est faite à nouveau, avec son préavis. Ainsi rien ne disparaît sans avoir été annoncé, même en ouvrant l'application après des mois.
- La vérification se fait au démarrage du service, puis toutes les heures. Jamais de purge d'une séance dont le traitement n'a pas abouti, ni pendant un enregistrement ou un traitement.
- **La purge et la suppression de l'audio** suppriment les fichiers de `sources/` (le moteur garantit qu'une exécution finie ne contient pas d'audio). Le texte, les corrections, les chapitres et les résumés restent, et restent modifiables ; la redétection des chapitres reste possible, car elle ne lit que le texte (ADR 0024). La lecture et le retraitement de la transcription ou des voix ne le sont plus.
- **Supprimer une séance** est définitif et total, qu'elle ait été traitée ou non : ses lignes (corrections, notes, chapitres, résumés avec elles), son dossier, et ses lignes dans chaque copie de sauvegarde de la base, compactée ensuite. La base efface ce qu'elle libère (`secure_delete`) et vide son journal. La confirmation dit ce qui est perdu.
- **Journal des suppressions** : chaque purge et chaque suppression y est inscrite (date, type, fichiers et tailles). Pour une séance supprimée, aucun texte n'y reste, pas même son titre.
- Toute suppression est définitive, sans passer par la corbeille de macOS : la purge sert à libérer de la place.

## Conséquences
- Une sauvegarde de la base ne permet plus de retrouver une séance supprimée. Elle reste utile pour revenir en arrière après une mise à jour.
- À la première ouverture sur des données anciennes, rien n'est purgé avant une semaine (le préavis), et chaque séance concernée est annoncée.
- Réduire la durée de conservation n'efface rien sur-le-champ : les séances concernées sont annoncées d'abord.

## Alternatives écartées
- Compter la durée depuis la date de l'enregistrement : un import de fichiers anciens serait purgeable aussitôt.
- Purger dès l'échéance si l'annonce avait été « due » sans être vue : une séance pourrait disparaître sans préavis réel.
- Garder le texte des séances supprimées dans les sauvegardes : l'utilisateur veut une suppression totale.
- Passer par la corbeille : l'espace disque ne serait libéré qu'en la vidant.
