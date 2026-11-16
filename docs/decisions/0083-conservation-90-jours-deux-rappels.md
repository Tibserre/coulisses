# 0083 — Conservation de l'audio : 90 jours au plus, deux rappels fixes

Statut : Acceptée (2026-11-12, choix de l'utilisateur sur maquettes : R3 parmi des propositions inspirées d'autres applications, après des jauges jugées peu claires). Remplace, dans l'ADR 0029, la durée « réglable » sans plafond et le préavis réglable ; remplace, dans l'ADR 0051, le réglage de la conservation et du préavis par « − » et « + » enregistré en quittant la ligne, « un réglage, une ligne » pour l'onglet Séances, et les lignes « Bientôt supprimés » (« Aucun ») et « Déjà supprimés » (leur nombre). Une durée déjà réglée au-delà de 90 jours descend à 90 jours (choix de l'utilisateur, 2026-11-16 ; voir Conséquences).

## Contexte
L'onglet Réglages › Séances alignait des lignes « libellé · compteur » toutes pareilles et de longs paragraphes ; l'utilisateur le trouvait peu clair et voulait le rythme de l'onglet Transcription. Les maquettes ont montré qu'un dessin de la durée (cercle, barre) ne se lit pas : le préavis, à l'échelle de la durée, disparaît dès 120 jours. Ailleurs (Messages d'iOS, Google, Slack, Photos), personne ne dessine la durée : on la choisit dans une courte liste, une phrase dit la suite, et chaque élément montre les jours qu'il lui reste. L'utilisateur juge aussi inutile de régler le préavis, et ne veut pas garder l'audio plus de 90 jours.

## Décision
- **Durée** : un choix parmi 7, 14, 30, 60 et 90 jours, **90 au plus**, 90 par défaut, toujours comptés depuis l'entrée de la séance (0029). Un sélecteur à segments ; un clic est une décision, écrite aussitôt. Chaque clic annonce donc de nouveau les purges proches : passer de 90 à 7 puis à 30 jours fait deux annonces. C'est accepté (un segment n'a pas de valeur intermédiaire, à l'inverse des « − » et « + » que craignait 0051).
- **Rappels fixes** : 7 jours, puis 3 jours avant la purge, chacun par le bandeau et la notification macOS. Le préavis ne se règle plus. La règle de 0029 demeure : la purge n'a lieu qu'une fois le préavis écoulé depuis le premier rappel.
- **L'onglet Séances** (maquette R3) : la durée sur une ligne ; « Bientôt supprimés » en carte, avec les rappels en une ligne et chaque séance annoncée, la plus proche d'abord : sa date, une pastille « dans N jours » (pleine à 3 jours ou moins) et « Garder » ; une phrase dit combien de séances n'ont déjà plus leur audio, « Voir » ouvre le journal. Les réglages d'enregistrement en deux cartes (« Silence », « Rappel »), le dossier d'export en carte.

## Conséquences
- Service : le second rappel passe par le bandeau (`coming`) et la notification macOS, avec le même texte que le premier ; `GET /api/conservation` donne `reminder_days`, les rappels réellement faits ([7, 3], ou le préavis seul s'il fait 3 jours ou moins).
- Seul le premier rappel retient la purge (0029) : une application fermée pendant les 3 derniers jours purge à sa vérification suivante, sans second rappel. Le second rappel est un confort, pas une garantie.
- Interface : sans `reminder_days` (un service plus ancien), l'onglet ne dit que le préavis réel (« Rappel 7 jours avant ») : jamais un rappel qui n'existe pas. Le préavis gardé est renvoyé tel quel, jamais au-dessus de la durée.
- **Une durée déjà réglée au-delà de 90 jours descend à 90 jours** (choix de l'utilisateur, 2026-11-16 : « on les descend à 90 jours »), par la migration qui ajoute le second rappel, et le préavis avec elle s'il dépassait 90 jours. Comme pour une durée raccourcie à la main (0029), les purges proches sont annoncées de nouveau, avec tout leur préavis : rien ne disparaît sans annonce. Le Service refuse ensuite toute durée au-delà de 90 jours.
- « Prolonger » reste dans le menu de la séance ; l'onglet ne propose que « Garder ».

## Alternatives écartées
- Une jauge circulaire ou une barre proportionnelle à la durée : illisibles pour les longues durées, et trompeuses pour les courtes (à 7 jours, tout est « préavis »).
- Une jauge fixe sur 90 jours : lisible, mais jugée peu claire par l'utilisateur.
- Des cartes à cocher par durée (R2), des segments avec une phrase (R1) : moins utiles que la liste des séances proches, qui dit ce qui va réellement disparaître.
