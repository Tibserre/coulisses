# Notes de version prêtes : de v0.34.0 (dernière publiée) à v0.35.0

À recopier, juste après `publier.py --numeroter` (ADR 0064), dans la section de la version de `CHANGELOG.md`
(titre « Nouveautés depuis la 0.34.0 », comme pour v0.33.1) : `scripts/publier.py` lit
ces notes dans `CHANGELOG.md`, pas ici. Ce fichier disparaît une fois la version publiée.

Écrites d'après `main` du 2026-10-28 (6b30218) : ADR 0054, 0056 à 0062, 0066, 0067, moteur v1.13.0.
Les résumés par objectif (`feat/vue-resume-objectifs`) n'y sont pas.

---

### Nouveautés depuis la 0.34.0

- **Enregistrer en un geste.** « Nouvelle note » (⌘N) démarre l'enregistrement aussitôt, avec le micro du Mac et le son de l'ordinateur, dans l'espace où vous êtes. L'espace, le projet et les présents se corrigent pendant qu'on enregistre. Au centre, le déroulé de la séance : vos annotations, les moments marqués d'une ★ et les passages du jeu à la discussion, à leur heure.
- **Les micros pendant l'enregistrement.** Coupez un micro, tous les micros ou le son de l'ordinateur à tout moment : du silence est enregistré à sa place, sans décaler le reste. Ajoutez un micro en cours de route, ou retirez celui que vous aviez ajouté (ce qu'il a déjà enregistré est gardé). Chaque nouvelle note repart du micro du Mac et du son de l'ordinateur ; un autre micro s'ajoute à la demande.
- **Pause et arrêt plus clairs.** Une grande icône, au premier plan. « Arrêter » ne demande plus de confirmation : vous avez 3 secondes pour reprendre (Espace ou Échap).
- **Un enregistrement oublié ne passe plus inaperçu.** Pendant un enregistrement, la barre des menus montre « ● » et sa durée, avec Pause, Arrêter et Ouvrir Coulisses, même fenêtre fermée. Après un long silence (5 minutes par défaut) ou une longue durée (1 h 30 par défaut), une notification demande s'il faut arrêter : « Arrêter » ou « Continuer ». Coulisses n'arrête jamais un enregistrement de lui-même. Les deux délais se règlent dans Réglages > Séances. macOS demande l'autorisation des notifications au premier enregistrement ; si vous la refusez, le rappel reste visible dans la barre des menus.
- **Le traitement se suit.** Deux disques, « Le texte » et « Les voix », avancent étape par étape, sans jamais reculer. Le texte apparaît dès qu'il est transcrit, puis les noms se posent. S'il y a moins de voix que de présents cochés, Coulisses le dit et propose de relancer avec le bon nombre.
- **Une lecture à la fois.** La transcription ou les résumés, en une colonne. Les résumés sont en onglets ; « Refaire » utilise le modèle choisi dans Réglages > Rédaction, et « Revenir à la version d'avant » annule le dernier. Votre note d'après séance est dans l'onglet « Ma note ».
- **Nommer les voix, guidé.** « N voix à nommer », sous le titre, passe d'une voix à l'autre : on écoute ses seules répliques, à la suite, et on choisit qui c'est. Les participants s'affichent sous le titre avec leur temps de parole ; un clic n'affiche que leurs répliques.
- **Coulisses reconnaît les voix d'une séance à l'autre.** Une voix pas encore nommée qui ressemble à celle d'une personne de l'espace est proposée : « C'est Marie ? ». Une coche confirme, une croix refuse (et s'annule par Cmd-Z) ; rien n'est jamais nommé sans vous. À activer dans les réglages de chaque espace (« Reconnaître les voix d'une séance à l'autre », désactivé par défaut). Les voix des séances traitées avant cette version ne comptent que si vous refaites leur séparation des voix.
- **Refaire le traitement**, depuis « ⋯ › Refaire le traitement… » : tout, le texte seul ou les voix seules. La version affichée reste lisible pendant ce temps, et vos corrections sont reportées sur la nouvelle.
- **Les chapitres apparaissent au fur et à mesure.** Pendant leur détection, Coulisses montre les premiers chapitres trouvés, sans attendre la fin. Ils peuvent encore évoluer et ne se modifient qu'une fois définitifs.
