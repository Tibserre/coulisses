# 0086 — L'écran d'enregistrement : le temps, les présents, l'onde et trois gestes

Statut : Acceptée (2026-11-18, maquette D5a validée par l'utilisateur sur la toile de maquettes : l'écran, sa colonne, le survol des présents, douze présents, et la feuille « Qui est là ? » en six états ; règles tranchées par l'utilisateur : toucher quelqu'un quand tout est nommé fait monter le nombre, − retire d'abord une place vide, « Passer membre » depuis la feuille, « Nouvelle note » gardé mais neutre). Choix de mise en œuvre proposés par la session des maquettes, non contredits : le projet avec l'espace, la croix au survol pour retirer, l'échelle de l'onde, les alertes par-dessus. Remplace la partie « L'écran » de 0056 et y précise « Le contexte se corrige en enregistrant ».

## Contexte
L'écran de 0056 (une barre avec tous les boutons, la frise, le déroulé au centre) était jugé peu clair : on ne voyait pas que l'enregistrement tournait, et Arrêter se perdait parmi les autres boutons. L'utilisateur voulait voir que ça avance, garder les deux ou trois gestes principaux en avant (pour ne pas oublier d'arrêter), un écran peu chargé, et les moments et annotations intégrés plutôt que posés à côté. Principes : P2 (temps mesurés), P3 (les présents sont un minimum), P8 (rien de perdu ni de caché).

## Décision
- **La barre**, fine et discrète : les micros (ADR 0067), le son de l'ordinateur, Jeu ⇄ Discussion. ★ Moment, Pause et Arrêter en sortent.
- **Le centre** : « Enregistrement en cours » qui bat (« En pause » en pause), le temps en grand, les présents (− N + et leurs pastilles), puis la langue et « Espace / Projet », une seule liste où chaque espace a ses projets dessous.
- **Qui est là ?** : un clic sur les pastilles ouvre la feuille : le nombre et les places, les personnes de l'espace à toucher, « Chercher ou ajouter un nom » (un nom inconnu devient un invité coché ; « Annuler » le décoche, retire la place que son ajout avait créée et l'archive, sans le supprimer), « Passer membre » sur un invité (avec « Annuler »). Chaque changement est enregistré aussitôt (`PUT /presents`).
- **L'onde** remplace la frise et le déroulé : elle montre le niveau mesuré du micro, avec une barre par 2 s, à 2 px par seconde. Le présent est à droite, et le passé s'estompe à gauche (environ 6 min en vue). Le mode en cours, les moments clés, les annotations et les événements de micros y sont posés au temps donné par le service, et partent avec elle. Une période sans niveau reçu n'a pas de barre.
- **Trois gestes** sous l'onde : ★ Moment (M), Arrêter (rond plein, le plus grand), Pause (Espace). Les voiles de pause et d'arrêt (0058, 0059) restent.
- **Annoter** : « Annoter… » (N) sous l'onde devient un champ sans cadre ; l'heure reste celle de la première lettre.
- **Retirer** un moment ou une annotation : par la croix au survol, tant qu'ils sont en vue, puis « Annuler ».
- **Les alertes** s'affichent par-dessus l'écran, sous les micros, et ne décalent rien.
- **« Nouvelle note »** reste dans l'en-tête, en bouton neutre, pendant l'enregistrement.

## Conséquences
- **L'onde de la page.** La page ne garde que les niveaux reçus depuis son ouverture. Quittée puis rouverte, l'onde repart de là. Les temps, les marques et les annotations, eux, viennent du service. Si cela gêne, il faudra que le service garde un historique des niveaux.
- **Moins de marques à retirer en cours d'enregistrement.** Un moment ou une annotation sortis de l'onde, après environ 6 min, ne se retirent plus pendant l'enregistrement. Un changement Jeu ⇄ Discussion posé par erreur ne se retire plus non plus. Le déroulé permettait les deux.
- **Le texte en direct.** Prévu par 0056 dans le déroulé, il n'a plus de place désignée. Il faudra la choisir quand le moteur le donnera.
- **La spec.** §7.1 et §7.2 sont réécrites dans le même changement.

## Alternatives écartées
- **Pistes A, B, C et D1 à D4** (toile de maquettes, page 3) : D5a est celle que l'utilisateur a retenue.
- **Garder le déroulé sous l'onde** : l'écran redevenait chargé, contre la demande de l'utilisateur.
