# Journal des versions

Versions de l'application Coulisses, publiées automatiquement à chaque fusion dans `main`
à partir des messages de commit (`scripts/release.py`, convention dans `CLAUDE.md`).
Une section peut être réécrite ensuite pour les utilisateurs : la publication lit celle de `main`.

## v0.30.1 — 2026-10-19

### Corrections

- passe au moteur v1.8.2, qui rend à la transcription sa justesse (moteur)

## v0.30.0 — 2026-10-19

### Nouveautés

- passe au moteur v1.8.0, qui sort torch de l'app dans l'environnement « torch » (moteur)

## v0.29.0 — 2026-10-19

### Nouveautés

- garde les enregistrements en FLAC, sans perte, une fois finis (enregistrement)

## v0.28.1 — 2026-10-19

### Corrections

- passe au moteur v1.7.2, qui ne tire plus librosa (moteur)

## v0.28.0 — 2026-10-16

### Nouveautés

- Les chapitres suivent mieux la séance, impro comme réunion : environ un toutes les 6 à 10 minutes, en Jeu ou Discussion (« Autre » se choisit à la main), avec un type vérifié.
- Le titre proposé nomme le sujet principal et un détail qui distingue la séance, et reste court.

## v0.27.0 — 2026-10-14

### Nouveautés

- guide l'installation d'Ollama et conseille un modèle selon la mémoire (redaction)

## v0.26.3 — 2026-10-14

### Corrections

- distingue un accord donné pendant l'essai d'une connexion sans accord (construction)

## v0.26.2 — 2026-10-13

### Corrections

- ne signe plus le DMG, pour un seul « Ouvrir quand même » (publication)

## v0.26.1 — 2026-10-13

### Corrections

- n'accepte que la page de Coulisses et neutralise ce que le modèle écrit (securite)

## v0.26.0 — 2026-10-13

### Nouveautés

- prépare, envoie et confirme une version pour les amis (publication)

### Corrections

- ne touche aux préférences de l'app publiée que pour les remettre (publication)
- protège une préparation envoyée et éprouve mieux la version (publication)

## v0.25.1 — 2026-10-13

### Corrections

- ne reprend que les étapes de la version du moteur en place (traitement)

## v0.25.0 — 2026-10-13

### Nouveautés

- cherche les nouvelles versions par Sparkle, sur accord (mises-a-jour)

## v0.24.0 — 2026-10-13

### Nouveautés

- signe chaque binaire de Coulisses.app avec le certificat (construction)

### Corrections

- lit la signature entière dans l'essai du paquet (construction)

## v0.23.0 — 2026-10-13

### Nouveautés

- construit Coulisses.app autonome et l'essaie (construction)

## v0.22.1 — 2026-10-13

### Corrections

- passe au moteur v1.7.1, qui n'écrit plus de bytecode dans son paquet (moteur)

## v0.22.0 — 2026-10-13

### Nouveautés

- passe au moteur v1.7.0, qui range uv sous ses environnements (moteur)

## v0.21.0 — 2026-10-13

### Nouveautés

- trouve l'interface et ses outils dans Coulisses.app (service)

## v0.20.0 — 2026-10-13

### Nouveautés

- sépare Coulisses (dév) de l'app de tous les jours (lanceur)

## v0.19.0 — 2026-10-13

### Nouveautés

- choisit le modèle de langage du titre, des chapitres et des résumés (redaction)
- retrouve les répliques d'une voix, nommée ou non (relecture)
- nomme une voix en place, sous son nom, dans sa ligne (relecture)
- commence depuis l'accueil, édite l'espace en place et charge sans à-coups (interface)

### Corrections

- dit qu'un service trop ancien est à relancer au lieu de planter (redaction)
- ouvre la liste des noms par-dessus les lignes, sans rien pousser (relecture)

## v0.18.0 — 2026-10-12

### Nouveautés

- baisse le micro à l'écoute quand personne n'y parle (ecoute)

## v0.17.0 — 2026-10-12

### Nouveautés

- retire un environnement de calcul inutilisé, par le moteur v1.6.0 (reglages)
- ajoute la section Modèles par l'API de modèles du moteur v1.5.0 (reglages)

## v0.16.0 — 2026-10-09

### Nouveautés

- ajoute le rapatriement des séances vers un dossier de données vide (donnees)

## v0.15.0 — 2026-10-09

### Nouveautés

- ajoute l'app Coulisses dans le Dock, avec sa fenêtre, à la place de la PWA (app)

## v0.14.0 — 2026-10-09

### Nouveautés

- ajoute autant de micros que voulu et refait « Nouvelle séance » (enregistrement)
- enregistre le son de l'ordinateur avec le micro pour les réunions en ligne (enregistrement)

### Corrections

- démarre le son de l'ordinateur même quand rien ne joue (enregistrement)

## v0.13.0 — 2026-10-07

### Nouveautés

- enregistre avec deux micros à la fois, le Mac et l'iPhone (enregistrement)

### Corrections

- relit les micros avant d'ouvrir l'iPhone, qui change d'identité en se réveillant (enregistrement)

## v0.12.0 — 2026-10-07

### Nouveautés

- coquille d'application, projets, recherche et export vers un dossier (bibliotheque)

## v0.11.0 — 2026-10-07

### Nouveautés

- garde ou purge l'audio et supprime une séance pour de bon (conservation)

## v0.10.0 — 2026-10-07

### Nouveautés

- relance la transcription ou les voix et reporte les corrections (relance)

## v0.9.0 — 2026-10-06

### Nouveautés

- pose des marqueurs et des notes pendant la séance (enregistrement)
- enregistre une séance avec le micro du Mac (enregistrement)

### Corrections

- fait avancer la frise en direct sans à-coups (enregistrement)
- fait partir les ondes du centre au lieu de faire varier les anneaux (enregistrement)
- anime le niveau sans à-coups (enregistrement)

### Performances

- arrête l'animation du niveau quand il ne bouge plus (enregistrement)

## v0.8.0 — 2026-10-06

### Nouveautés

- propose le titre à la demande, à partir des chapitres (titre)
- ajoute les quatre actions, leur page et la note d'après séance (actions)

### Corrections

- fusionne deux voix nommées d'après la même personne (relecture)

## v0.7.0 — 2026-10-06

### Nouveautés

- découpe la séance en chapitres détectés puis corrigeables (chapitres)

### Corrections

- fait recharger la page après une nouvelle version (interface)
- garde le titre quand le modèle continue après sa première ligne (titre)

## v0.6.0 — 2026-10-06

### Nouveautés

- souligne les mots dont le modèle de transcription doutait (relecture)

## v0.5.0 — 2026-10-06

### Nouveautés

- ajoute au Résumé Impro l'organisation hors plateau (resumes)
- génère le titre et le Résumé Impro avec le LLM local (resumes)

### Corrections

- affiche la péremption du résumé dès qu'une correction change (resumes)

## v0.4.0 — 2026-10-06

### Nouveautés

- corrige le texte en place, comme dans un document (relecture)
- nomme les voix et corrige le transcript sans quitter l'écran (relecture)
- range les séances par espace et garde les corrections en journal (espaces)

### Corrections

- rétablit l'infobulle des mots dans les répliques modifiables (relecture)
- rétablit une scission annulée et refuse un double rétablissement (corrections)

## v0.3.0 — 2026-10-05

### Nouveautés

- explique chaque échec d'étape d'après le code d'erreur du moteur (erreurs)

## v0.2.0 — 2026-10-05

### Nouveautés

- range les détails techniques derrière un mode développeur (interface)

## v0.1.0 — 2026-10-05

### Nouveautés

- range les vraies séances dans le dossier de données réel par défaut (donnees)
- affiche l'avancement, la provenance et le transcript avec l'audio (relecture)
- importe un enregistrement et le traite en tâche de fond avec le moteur (socle)
