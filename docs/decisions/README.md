# Décisions d'architecture (ADR)

Une fiche par décision structurante : contexte, décision, conséquences, alternatives écartées.
Une décision **acceptée** ne se remet pas en cause en passant : on écrit une nouvelle fiche qui la remplace (`Remplacée par 00XX`).
Une décision **proposée** attend la validation de l'utilisateur ; ne pas bâtir dessus de manière irréversible avant.

Nouvelle fiche : skill `/adr`.

| # | Décision | Statut |
|---|---|---|
| [0001](0001-local-et-emplacement-des-donnees.md) | 100 % local ; code et données séparés, hors de tout dossier synchronisé | Acceptée (emplacements : voir 0009, 0010 ; hors ligne : exception des mises à jour, 0040) |
| [0002](0002-architecture-generale.md) | Service Python local + interface web servie en local ; étapes en sous-processus | Acceptée (PWA remplacée par 0034) |
| [0005](0005-captation-par-le-service.md) | La captation audio est faite par le service Python, pas par le navigateur | Acceptée (niveaux : précisé par 0027) |
| [0006](0006-seance-multi-sources.md) | Une séance a N sources audio dès la V1 | Acceptée |
| [0007](0007-interface-react-astryx.md) | Interface React + Vite + TS, design system Astryx | Acceptée (PWA remplacée par 0034) |
| [0008](0008-langues-du-projet.md) | Code en anglais, tout le reste en français | Acceptée |
| [0010](0010-dossier-unique-coulisses.md) | Un seul dossier visible `~/Coulisses` : `Code/` (git), `Modèles/`, `Données/` | Acceptée |
| [0016](0016-deux-depots-et-versions.md) | Deux dépôts (moteur avec son atelier, application seule), moteur installable et versionné, versions automatiques depuis les commits | Acceptée (dossiers : précisé par 0040) |
| [0017](0017-direction-artistique.md) | Direction artistique sobre et éditoriale : fonds neutres, accent brique, DM Sans et Figtree, relecture en deux colonnes | Acceptée (échelle typographique : remplacée par 0038) |
| [0018](0018-schema-de-donnees.md) | Schéma de données : SQLite fait foi, les exécutions restent des fichiers, corrections en journal | Acceptée (sauvegardes et séance supprimée : remplacé par 0029 ; reprise et version du moteur : précisé par 0040) |
| [0020](0020-espaces.md) | Des espaces (troupe, équipe, client) plutôt qu'une troupe ; pas de type, des modèles de départ ; reconnaissance des voix sur option | Acceptée |
| [0022](0022-generation-des-resumes.md) | Générer les résumés : une exécution de l'application, tokens estimés puis vérifiés, modèle en configuration | Acceptée |
| [0024](0024-chapitres.md) | Les chapitres : détectés par le LLM local, placés sur une réplique, corrigés dans le journal | Acceptée |
| [0025](0025-resumes-a-la-demande.md) | Des résumés à la demande, avec le modèle choisi dans une liste ; seuls les chapitres et le titre restent automatiques | Acceptée (titre : remplacé par 0026) |
| [0026](0026-titre-a-la-demande.md) | Le titre à la demande, fait à partir des chapitres ; seuls les chapitres restent automatiques | Acceptée |
| [0027](0027-captation-en-pratique.md) | La captation en pratique : WAV 24 bits tenu à jour, niveaux en flux (SSE), anti-veille, pas de traitement automatique sur batterie | Acceptée (format gardé : précisé par 0046) |
| [0028](0028-relance-et-report-des-corrections.md) | Relancer la transcription ou les voix : une nouvelle version complète ou rien, corrections reportées par le temps mesuré, anciennes versions affichables | Acceptée |
| [0029](0029-conservation-et-suppression.md) | Garder l'audio (option de séance), purge annoncée avant d'avoir lieu, suppression totale d'une séance, sauvegardes comprises | Acceptée |
| [0030](0030-coquille-et-bibliotheque.md) | Coquille d'application : colonne des espaces, projets et séances, recherche plein texte (cache FTS5), export vers un dossier choisi (Q7) | Acceptée |
| [0031](0031-deux-micros.md) | Enregistrer avec deux micros à la fois (le Mac et l'iPhone par Continuité) : deux fichiers, la référence seule traitée pour l'instant | Acceptée |
| [0032](0032-son-de-l-ordinateur.md) | Enregistrer le son de l'ordinateur avec le micro (réunions en ligne ou hybrides) : un programme Swift, deux fichiers sur une horloge, réunis pour le traitement | Acceptée |
| [0033](0033-autant-de-micros.md) | Autant de micros que l'on veut (« Ajouter un micro ») ; « Nouvelle séance » commence par enregistrer ou importer | Acceptée |
| [0034](0034-app-du-dock.md) | Coulisses, une app dans le Dock avec sa propre fenêtre : démarre et arrête le service, reçoit les permissions ; la PWA est abandonnée ; le nom reste Coulisses (Q3) | Acceptée (lancement, signature, app sans réseau, empaquetage : remplacés par 0040) |
| [0036](0036-page-modeles.md) | La section « Modèles » des Réglages, par l'API de modèles du moteur (v1.5.0, puis v1.6.0 pour les environnements) : état, téléchargement confirmé et suivi, suppression confirmée, `stop_downloads` à l'arrêt | Acceptée (mention du réseau : 0040 ; gestes demandés au lancement : 0049) |
| [0037](0037-mix-d-ecoute.md) | Un mix d'écoute qui baisse le micro quand personne n'y parle (le clavier, la pièce) ; le moteur garde la somme simple | Acceptée |
| [0038](0038-echelle-typographique.md) | Une échelle typographique pour une interface : rien sous 12 px, texte d'appoint 13 px, titres 18 à 34 px (remplace le rapport 1,333 de 0017) | Acceptée |
| [0039](0039-un-modele-par-redaction.md) | Un modèle de langage par rédaction (titre, chapitres, résumés), choisi dans Réglages, onglet « Rédaction » ; le choix fait dans l'onglet Résumé ne change que celui des résumés (précise 0022) | Acceptée |
| [0040](0040-distribuer-a-quelques-amis.md) | Distribuer Coulisses à quelques amis : app autonome (Python embarqué), certificat auto-signé, mises à jour par Sparkle avec vérification automatique sur accord (P1 amendé), dépôt de l'app public (MIT), deux apps sur ce Mac (publiée et dév), passage de l'une à l'autre par tests, essai du paquet et pré-version | Acceptée (ffmpeg : précisé par 0041) |
| [0041](0041-ffmpeg-embarque.md) | ffmpeg et ffprobe embarqués dans Coulisses.app, compilés sur ce Mac depuis l'archive officielle (empreinte vérifiée) : statiques, audio seul, LGPL, sans réseau | Acceptée (protocoles et formats : précisés par 0042) |
| [0042](0042-ffmpeg-tubes-et-formats.md) | Le ffmpeg embarqué lit aussi par un tube (la transcription en a besoin), et lit Matroska (WebM, MKV) et W64 ; toujours sans réseau | Acceptée |
| [0043](0043-seule-sa-page-parle-au-service.md) | Seule la page de Coulisses parle au service (hôte 127.0.0.1 ou localhost, origine contrôlée pour toute modification, CSP) ; la fenêtre n'affiche que lui ; ce que le modèle écrit est neutralisé à l'export et à la copie (revue de sécurité du 2026-10-13) | Acceptée |
| [0044](0044-chapitres-par-parties.md) | Les chapitres lus par parties de durée réglée (15 min au plus, ADR 0045), chacune avec le dernier chapitre de la précédente et un ordre de grandeur ; prompt des chapitres généraliste, sans titre d'exemple (précise 0024) | Acceptée |
| [0045](0045-chapitres-moins-nombreux-et-mieux-types.md) | Chapitres : « autre » posé à la main seulement, vérification du type de chaque chapitre, 6 à 10 min par chapitre visées (regroupement mesuré puis écarté) ; précise 0024 et 0044 | Acceptée (parties de 15 min, rappel de 3 min, 6 à 10 min par chapitre, vérification du type) |
| [0046](0046-enregistrements-en-flac.md) | Les enregistrements gardés en FLAC sans perte une fois finis (pistes et mixes), le WAV supprimé seulement après preuve d'identité des échantillons ; empreinte des échantillons (schéma), encodeur FLAC dans le ffmpeg embarqué ; imports et anciennes séances inchangés (lot 12e) | Acceptée |
| [0049](0049-gestes-demandes-au-lancement.md) | Une fenêtre au lancement pour les mises à jour qui attendent une action (modèle remplacé, ce qui manque au traitement, ancien environnement), déduites de l'état du moteur ; une à la fois : nature, gains chiffrés, deux sorties en boutons, la recommandée d'abord ; choisir vaut confirmer ; un point sur « Réglages » (précise 0036) | Acceptée |

Les ADR techniques du moteur (0003, 0004, 0009, 0011 à 0015, 0019, 0021, 0023) sont dans le dépôt `coulisses-moteur` (`docs/decisions/`). Les numéros sont communs aux deux dépôts : un nouvel ADR prend le numéro libre suivant dans les deux.
