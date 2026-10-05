# Questions ouvertes

> Ce qui n'est pas encore tranché. Quand une question est tranchée : la réponse va dans la spec ou dans un ADR, et la ligne est supprimée d'ici.

## À trancher par l'utilisateur
| # | Question | Quand | Piste |
|---|---|---|---|
| Q3 | Nom définitif de l'app | Avant la PWA | « Coulisses » provisoire |
| Q7 | Rangement des comptes rendus dans Google Drive : copie à la main depuis l'export, ou export automatique vers un dossier local synchronisé par Google Drive pour ordinateur ? L'app n'envoie jamais rien elle-même (P1). | Phase interface | Export Markdown vers un dossier choisi |

## À trancher par la mesure (banc d'essai)
| # | Question |
|---|---|
| M1 | ~~Moteur de transcription pour Rapide et pour Qualité max.~~ Tranché : un seul profil, la chaîne retenue du moteur (2026-10-02). |
| M2 | L'alignement forcé améliore-t-il les horodatages d'un moteur qui en fournit déjà nativement ? |
| M3 | Moteur et seuil de diarisation qui maximisent la pureté en discussion sans exploser le nombre de locuteurs. |
| M4 | La déréverbération aide-t-elle la diarisation ? Et la transcription ? |
| M5 | Le glossaire améliore-t-il vraiment la transcription des prénoms et du jargon (selon le moteur) ? |
| M6 | Modèle de génération par défaut, `num_ctx` nécessaire, et seuil de bascule vers le résumé par sections. |
| M7 | Méthode de détection des phases (règles sur le rythme des tours, classement par le LLM, mixte). |
| M8 | Faut-il des réglages de diarisation différents en scène et en discussion ? |

## Risques identifiés
- **Voix de personnages** : un comédien qui change de voix en scène peut être confondu avec un autre. Accepté pour les scènes (objectif 2) ; à surveiller en discussion.
- **Chevauchements fréquents** en discussion animée : dégradent diarisation et transcription.
- **Réverbération des salles de répétition** : la plus grosse inconnue sur la qualité.
- **Veille pendant la nuit** : Mac sur batterie, capot fermé → la nuit est perdue. L'app doit le signaler. Le lanceur du Dock doit rester ouvert pendant le traitement de nuit.
- **Maturité d'Astryx** (bêta).
- **Dette de l'interface** : transcript non virtualisé (ne tiendra pas 2 h), pas encore de raccourcis clavier de relecture (`rules/web.md`). À traiter avant la relecture de vraies séances.
