# Plan de construction de la V1

Étapes livrées une par une, chacune utilisable et testable par l'utilisateur, chacune close par un jalon (`/jalon`). Ordre tiré de la spec (§12) : relecture et renommage d'abord, enregistrement ensuite.

| # | Étape | Ce que l'utilisateur peut faire à la fin | État |
|---|---|---|---|
| 1 | Socle : importer, traiter, lire | Importer un fichier, suivre le traitement en tâche de fond (reprise après un arrêt), lire le transcript par tours et réécouter (vitesse, espace et flèches), voir la provenance | Livrée (v0.1.0) |
| 2 | Espaces et relecture corrigée | Espaces (membres, invités, glossaire), présents cochés à l'import ; nommer une voix, personnage joué par, fusionner, scinder en donnant des répliques à une nouvelle voix, corriger le texte en place (Cmd-Z, retour à l'origine), suggestions du glossaire, annuler et rétablir ; raccourcis N et E | Livrée (v0.4.0) |
| 3 | Résumé Impro | Titre et Résumé Impro prêts à la fin du traitement, avec les bons noms ; copie, export Markdown ; compte rendu de réunion ; choix du modèle parmi ceux d'Ollama ; résumé signalé périmé après une correction | Livrée (v0.5.0) |
| 4 | Chapitres (phases) | Chapitres détectés par le LLM local après le traitement ; frise sous le titre ; titres de chapitre dans le transcript, repliables ; renommer, changer le type, couper (C), retirer une coupure, Cmd-Z ; chapitres dans le transcript envoyé aux résumés et découpage des longues séances par chapitre | Livrée (v0.7.0) |
| 5 | Les autres actions | Les quatre autres actions (retours de jeu, idées de scènes, prochaines étapes, résumé court) ; page « Actions » : modifier, restaurer l'original, créer, dupliquer, retirer ; résumés et titre à la demande, le titre fait à partir des chapitres, seuls les chapitres automatiques (ADR 0025, 0026) ; historique et comparaison côte à côte ; note d'après séance lue par les résumés | Livrée (v0.8.0) |
| 6 | Enregistrement | 6a : captation par le service (choix du micro, vumètre, alertes, pause, reprise après un crash, anti-veille), traitement à l'arrêt sauf sur batterie (ADR 0027). 6b : marqueurs et notes pendant la séance, marqueurs prioritaires sur les chapitres | Livrée (v0.9.0) |
| 7 | Relancer une étape | Relance d'une étape seule, étapes en aval périmées, report des corrections et liste de ce qui n'a pas pu l'être | |
| 8 | Bibliothèque | Spectacles, états des séances, recherche plein texte, export vers un dossier (Q7) | |
| 9 | Conservation et purge | Durée, épinglage, préavis, suppression de l'audio ou de la séance, journal des suppressions | |
| 10 | App au quotidien | Lanceur du Dock, PWA, réglages et modèles, test du parcours complet réseau coupé (nom définitif, Q3) | |

À trancher avant l'étape 7 : la spec parle de relancer une étape « avec un autre moteur » (§7.4, §11), alors que la V1 n'a qu'un profil, défini par le moteur. En pratique, une relance changera le nombre de présents ou la version du moteur.
