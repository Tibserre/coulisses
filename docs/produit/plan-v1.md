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
| 7 | Relancer une étape | Relance de la transcription ou de la séparation des voix depuis la version affichée, nouvelle version activée seulement entière, étapes refaites périmées, report des corrections par le temps mesuré et liste de ce qui n'a pas pu l'être, anciennes versions réaffichables (ADR 0028) | Livrée (v0.10.0) |
| 8 | Bibliothèque | Coquille d'application (colonne des espaces, projets et séances ; ⌘K, ⌘N, ⌘\\), projets, états des séances, recherche plein texte, export vers un dossier (Q7) (ADR 0030) | Livrée (v0.12.0) |
| 9 | Conservation et purge | Durée, « Garder l'audio », préavis (bandeau et notification), prolonger, suppression de l'audio ou de la séance (totale, sauvegardes comprises), journal des suppressions, page Réglages (ADR 0029) | Livrée (v0.11.0) |
| 10 | App au quotidien | Lanceur du Dock, PWA, réglages et modèles, test du parcours complet réseau coupé (nom définitif, Q3) | |

Tranché à l'étape 7 (ADR 0028) : en V1, on relance la transcription (glossaire enrichi, moteur mis à jour) ou la séparation des voix (autre nombre de présents) ; « un autre moteur » viendra avec les profils du moteur.
