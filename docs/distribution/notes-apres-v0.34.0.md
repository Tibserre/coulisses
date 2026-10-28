# Notes de version prêtes : de v0.34.0 (dernière publiée) à v0.35.0

À recopier, juste après `publier.py --numeroter` (ADR 0064), dans la section de la version de `CHANGELOG.md`
(titre « Nouveautés depuis la 0.34.0 », comme pour v0.33.1) : `scripts/publier.py` lit
ces notes dans `CHANGELOG.md`, pas ici. Ce fichier disparaît une fois la version publiée.

À ajuster avant de publier :
- **Chapitres** : `main` n'a que la partie service ; l'écran qui les montre est
  sur la branche Interface (`feat/vue-resume-objectifs`). Sans sa fusion, retirer ce point.
- Ajouter ce qu'apporteront les branches Interface et Rédaction si elles sont fusionnées.

---

### Nouveautés depuis la 0.34.0

- **Un enregistrement oublié ne passe plus inaperçu.** Pendant un enregistrement, la barre des menus montre « ● » et sa durée, avec Pause, Arrêter et Ouvrir Coulisses, même fenêtre fermée. Après un long silence (5 minutes par défaut) ou une longue durée (1 h 30 par défaut), une notification demande s'il faut arrêter : « Arrêter » ou « Continuer ». Coulisses n'arrête jamais un enregistrement de lui-même. Les deux délais se règlent dans Réglages > Séances, « Pendant un enregistrement ». macOS demande l'autorisation des notifications au premier enregistrement ; si vous la refusez, le rappel reste visible dans la barre des menus.
- **Coulisses reconnaît les voix d'une séance à l'autre.** Une voix pas encore nommée qui ressemble à celle d'une personne de l'espace est proposée : « C'est Marie ? ». Une coche confirme, une croix refuse (et s'annule par Cmd-Z) ; rien n'est jamais nommé sans vous. À activer dans les réglages de chaque espace (« Reconnaître les voix d'une séance à l'autre », désactivé par défaut). Les voix déjà nommées servent tout de suite, sauf celles des séances traitées avant cette version : pour qu'elles comptent, refaites leur séparation des voix.
- **Les chapitres apparaissent au fur et à mesure.** Pendant leur détection, Coulisses montre où il en est et les premiers chapitres trouvés, sans attendre la fin. Ils peuvent encore évoluer (le dernier s'allonger, un type changer) et ne se modifient qu'une fois définitifs.
