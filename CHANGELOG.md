# Journal des versions

Versions de l'application Coulisses, publiées automatiquement à chaque fusion dans `main`
à partir des messages de commit (`scripts/release.py`, convention dans `CLAUDE.md`).

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
