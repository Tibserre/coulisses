# Plan de construction de la V1

Étapes livrées une par une, chacune utilisable et testable par l'utilisateur, chacune close par un jalon (`/jalon`). Ordre tiré de la spec (§12) : relecture et renommage d'abord, enregistrement ensuite.

| # | Étape | Ce que l'utilisateur peut faire à la fin | État |
|---|---|---|---|
| 1 | Socle : importer, traiter, lire | Importer un fichier, suivre le traitement en tâche de fond (reprise après un arrêt), lire le transcript par tours et réécouter (vitesse, espace et flèches), voir la provenance | Livrée (v0.1.0) |
| 2 | Troupe et relecture corrigée | Membres, invités, présents, glossaire ; nommer, fusionner, scinder les locuteurs, « personnage joué par X », corriger un mot ; raccourcis de relecture (renommer…) | |
| 3 | Résumé Impro | Titre et Résumé Impro prêts à la fin du traitement, avec les bons noms ; copie, export Markdown | |
| 4 | Phases | Détection, correction, phases dans le transcript et dans le prompt | |
| 5 | Les autres actions | Les quatre autres actions, actions modifiables, historique, comparaison, choix du modèle, notes d'après séance | |
| 6 | Enregistrement | Captation par le service (vumètre, alertes, pause, marqueurs, notes, reprise après un crash, anti-veille), traitement à l'arrêt | |
| 7 | Relancer une étape | Relance d'une étape seule, étapes en aval périmées, report des corrections et liste de ce qui n'a pas pu l'être | |
| 8 | Bibliothèque | Spectacles, états des séances, recherche plein texte, export vers un dossier (Q7) | |
| 9 | Conservation et purge | Durée, épinglage, préavis, suppression de l'audio ou de la séance, journal des suppressions | |
| 10 | App au quotidien | Lanceur du Dock, PWA, réglages et modèles, test du parcours complet réseau coupé (nom définitif, Q3) | |

À trancher avant l'étape 7 : la spec parle de relancer une étape « avec un autre moteur » (§7.4, §11), alors que la V1 n'a qu'un profil, défini par le moteur. En pratique, une relance changera le nombre de présents ou la version du moteur.
