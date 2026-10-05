# Décisions d'architecture (ADR)

Une fiche par décision structurante : contexte, décision, conséquences, alternatives écartées.
Une décision **acceptée** ne se remet pas en cause en passant : on écrit une nouvelle fiche qui la remplace (`Remplacée par 00XX`).
Une décision **proposée** attend la validation de l'utilisateur ; ne pas bâtir dessus de manière irréversible avant.

Nouvelle fiche : skill `/adr`.

| # | Décision | Statut |
|---|---|---|
| [0001](0001-local-et-emplacement-des-donnees.md) | 100 % local ; code et données séparés, hors de tout dossier synchronisé | Acceptée (emplacements : voir 0009, 0010) |
| [0002](0002-architecture-generale.md) | Service Python local + interface web servie en local ; étapes en sous-processus | Acceptée |
| [0005](0005-captation-par-le-service.md) | La captation audio est faite par le service Python, pas par le navigateur | Acceptée |
| [0006](0006-seance-multi-sources.md) | Une séance a N sources audio dès la V1 | Acceptée |
| [0007](0007-interface-react-astryx.md) | Interface React + Vite + TS, design system Astryx | Acceptée |
| [0008](0008-langues-du-projet.md) | Code en anglais, tout le reste en français | Acceptée |
| [0010](0010-dossier-unique-coulisses.md) | Un seul dossier visible `~/Coulisses` : `Code/` (git), `Modèles/`, `Données/` | Acceptée |
| [0016](0016-deux-depots-et-versions.md) | Deux dépôts (moteur avec son atelier, application seule), moteur installable et versionné, versions automatiques depuis les commits | Acceptée |
| [0017](0017-direction-artistique.md) | Direction artistique sobre et éditoriale : fonds neutres, accent brique, DM Sans et Figtree, relecture en deux colonnes | Acceptée |
| [0018](0018-schema-de-donnees.md) | Schéma de données : SQLite fait foi, les exécutions restent des fichiers, corrections en journal | Acceptée |

Les ADR techniques du moteur (0003, 0004, 0009, 0011 à 0015) sont dans le dépôt `coulisses-moteur` (`docs/decisions/`). Les numéros sont communs aux deux dépôts : un nouvel ADR prend le numéro libre suivant dans les deux.
