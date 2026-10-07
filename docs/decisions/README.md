# Décisions d'architecture (ADR)

Une fiche par décision structurante : contexte, décision, conséquences, alternatives écartées.
Une décision **acceptée** ne se remet pas en cause en passant : on écrit une nouvelle fiche qui la remplace (`Remplacée par 00XX`).
Une décision **proposée** attend la validation de l'utilisateur ; ne pas bâtir dessus de manière irréversible avant.

Nouvelle fiche : skill `/adr`.

| # | Décision | Statut |
|---|---|---|
| [0001](0001-local-et-emplacement-des-donnees.md) | 100 % local ; code et données séparés, hors de tout dossier synchronisé | Acceptée (emplacements : voir 0009, 0010) |
| [0002](0002-architecture-generale.md) | Service Python local + interface web servie en local ; étapes en sous-processus | Acceptée |
| [0005](0005-captation-par-le-service.md) | La captation audio est faite par le service Python, pas par le navigateur | Acceptée (niveaux : précisé par 0027) |
| [0006](0006-seance-multi-sources.md) | Une séance a N sources audio dès la V1 | Acceptée |
| [0007](0007-interface-react-astryx.md) | Interface React + Vite + TS, design system Astryx | Acceptée |
| [0008](0008-langues-du-projet.md) | Code en anglais, tout le reste en français | Acceptée |
| [0010](0010-dossier-unique-coulisses.md) | Un seul dossier visible `~/Coulisses` : `Code/` (git), `Modèles/`, `Données/` | Acceptée |
| [0016](0016-deux-depots-et-versions.md) | Deux dépôts (moteur avec son atelier, application seule), moteur installable et versionné, versions automatiques depuis les commits | Acceptée |
| [0017](0017-direction-artistique.md) | Direction artistique sobre et éditoriale : fonds neutres, accent brique, DM Sans et Figtree, relecture en deux colonnes | Acceptée |
| [0018](0018-schema-de-donnees.md) | Schéma de données : SQLite fait foi, les exécutions restent des fichiers, corrections en journal | Acceptée (sauvegardes et séance supprimée : remplacé par 0029) |
| [0020](0020-espaces.md) | Des espaces (troupe, équipe, client) plutôt qu'une troupe ; pas de type, des modèles de départ ; reconnaissance des voix sur option | Acceptée |
| [0022](0022-generation-des-resumes.md) | Générer les résumés : une exécution de l'application, tokens estimés puis vérifiés, modèle en configuration | Acceptée |
| [0024](0024-chapitres.md) | Les chapitres : détectés par le LLM local, placés sur une réplique, corrigés dans le journal | Acceptée |
| [0025](0025-resumes-a-la-demande.md) | Des résumés à la demande, avec le modèle choisi dans une liste ; seuls les chapitres et le titre restent automatiques | Acceptée (titre : remplacé par 0026) |
| [0026](0026-titre-a-la-demande.md) | Le titre à la demande, fait à partir des chapitres ; seuls les chapitres restent automatiques | Acceptée |
| [0027](0027-captation-en-pratique.md) | La captation en pratique : WAV 24 bits tenu à jour, niveaux en flux (SSE), anti-veille, pas de traitement automatique sur batterie | Acceptée |
| [0028](0028-relance-et-report-des-corrections.md) | Relancer la transcription ou les voix : une nouvelle version complète ou rien, corrections reportées par le temps mesuré, anciennes versions affichables | Acceptée |
| [0029](0029-conservation-et-suppression.md) | Garder l'audio (option de séance), purge annoncée avant d'avoir lieu, suppression totale d'une séance, sauvegardes comprises | Acceptée |

Les ADR techniques du moteur (0003, 0004, 0009, 0011 à 0015, 0019, 0021, 0023) sont dans le dépôt `coulisses-moteur` (`docs/decisions/`). Les numéros sont communs aux deux dépôts : un nouvel ADR prend le numéro libre suivant dans les deux.
