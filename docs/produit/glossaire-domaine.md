# Glossaire du domaine

Vocabulaire unique du projet. **Interface, docs et prompts** utilisent le terme français ; **le code** utilise l'identifiant anglais, sans exception ni synonyme.

| Français | Code | Définition |
|---|---|---|
| Espace | `space` | Ce qui regroupe des séances et les gens qui y participent : une troupe d'impro, une équipe, un client (ADR 0020). Possède des membres, des invités, un glossaire, des projets, des réglages. Étanche : une personne n'appartient qu'à un espace. |
| Modèle de départ | `space_template` | Pré-remplissage des réglages d'un espace à sa création (« Troupe d'impro », « Réunions de travail », « Vide »). Pas un type : tout reste modifiable ensuite. |
| Reconnaissance des voix | `voice_recognition` | Réglage d'un espace : reconnaître une personne d'une séance à l'autre par sa voix. Désactivé par défaut. |
| Membre | `member` | Personne d'un espace, avec un rôle libre (« coach », « comédienne », « cheffe de projet »). |
| Invité | `guest` | Personne extérieure présente à une ou plusieurs séances d'un espace. |
| Personne | `person` | Membre ou invité. Ce à quoi un locuteur est rattaché. |
| Projet | `project` | Regroupe des séances d'un espace (un spectacle pour une troupe). Une séance appartient à un projet de son espace, ou à aucun ; un projet s'archive, ses séances y restent. |
| Dossier d'export | `export_folder` | Dossier du Mac choisi une fois, où « Exporter vers le dossier » écrit le compte rendu d'une séance (ADR 0030). |
| Index de recherche | `search_index` | Cache plein texte des transcriptions corrigées, notes, résumés et titres ; reconstruit à la demande, jamais une source de vérité. |
| Séance | `session` | Un enregistrement (répétition, atelier, réunion), de 1 h à 2 h. Unité de traitement. Appartient à un espace. |
| Présents | `attendees` | Personnes présentes à une séance. Leur nombre donne le minimum de locuteurs. |
| Source audio | `audio_source` | Un fichier audio original d'une séance (capté ou importé). 1 en V1, N plus tard. |
| Source de référence | `reference_source` | La source audio qui sert de base de temps quand une séance en a plusieurs. |
| Audio dérivé | `derived_audio` | Audio produit par une étape (rééchantillonné, déréverbéré, mixé). Purgé avec l'original. |
| Marqueur | `marker` | Repère horodaté posé à la main : `scene`, `discussion`, `key_moment`. |
| Note | `note` | Texte libre de l'utilisateur, horodaté (pendant) ou non (après). La note d'après séance est lue par chaque génération. |
| Phase | `phase` | Intervalle de la séance de type `scene`, `discussion` ou `other`. Détectée puis corrigeable. Dans l'interface : « chapitre », de type « Jeu », « Discussion » ou « Autre » (ADR 0024). |
| Étape | `stage` | Un maillon du traitement : `prepare`, `dereverb`, `transcribe`, `align`, `diarize`, `attribute`, `segment_phases`, `title`, `summarize`. |
| Exécution | `run` | Une exécution d'une étape sur une séance, avec ses entrées, sa sortie, sa provenance, son statut. Immuable une fois terminée. |
| Exécution active | `active_run` | Pour une séance et une étape, l'exécution affichée et utilisée en aval. Les exécutions d'une version deviennent actives ensemble. |
| Version (du traitement) | `version` | Une exécution « qui a dit quoi » réussie, avec les exécutions dont elle vient. Chaque version a ses propres corrections ; une seule est affichée. |
| Relance | `rerun` | Refaire une étape (la transcription ou la séparation des voix) depuis la version affichée, pour en faire une nouvelle. |
| Statut d'exécution | `run_status` | `queued`, `running`, `succeeded`, `failed`, `stale` (périmée : l'exécution affichée d'une étape qu'une relance refait ; état calculé, le statut enregistré d'une exécution finie ne change jamais). |
| Tâche | `job` | Travail mis en file pour une séance (une chaîne à lancer, une étape à relancer, une génération). Produit une ou plusieurs exécutions. La file survit à un redémarrage. |
| Capacité | `capability` | Ce qu'un moteur déclare savoir faire (ex. horodatage mesuré au mot, nombre minimal de locuteurs, glossaire). |
| Moteur | `engine` | Implémentation interchangeable d'une étape (ex. un modèle de transcription donné). |
| Référence de modèle | `model_ref` | Dépôt et révision épinglée d'un modèle, choisis par un profil, jamais par un moteur. |
| Profil | `profile` | Choix d'un moteur + réglages pour chaque étape. Un seul en V1 : `chaine-retenue`, défini par le moteur. |
| Provenance | `provenance` | Moteur, version, modèle, réglages, durée, mémoire max, date d'une exécution. |
| Locuteur | `speaker` | Voix distincte trouvée par la diarisation dans une séance (« Locuteur 3 »). Pas encore une personne. Dans l'interface, on dit « voix » pour le désigner (« Nommer cette voix », « Une nouvelle voix »). |
| Rattachement | `speaker_assignment` | Lien d'un locuteur vers une personne, ou vers un personnage joué par une personne. |
| Personnage | `character` | Rôle joué pendant une scène. Un locuteur peut être « personnage joué par Marie ». |
| Empreinte vocale | `speaker_embedding` | Vecteur caractérisant la voix d'un locuteur. Conservée après purge. |
| Transcription (sortie) | `transcript` | Sortie de `transcribe` ou `align` : les mots d'une séance, horodatés si mesurés. |
| Diarisation (sortie) | `diarization` | Sortie de `diarize` : les segments de locuteurs et la liste des locuteurs. |
| Mot | `word` | Unité du transcript : texte, début et fin (mesurés, ou absents avant alignement), confiance de la transcription (`asr_confidence`), locuteur. |
| Segment de locuteur | `speaker_segment` | Intervalle où un locuteur parle, produit par la diarisation. Les segments peuvent se chevaucher. |
| Tranche | `chunk` | Portion d'audio transcrite d'un seul tenant ; bornes = positions de coupe. À ne pas confondre avec un segment de locuteur. |
| Part horodatée | `timed_share` | Part des mots d'un transcript qui portent un temps mesuré (ADR 0011). |
| Locuteur principal | `speaker` (d'un mot attribué) | Locuteur qui couvre le plus longtemps un mot ; les autres locuteurs actifs sont gardés (`speakers`). |
| Mot incertain | `uncertain` | Mot rattaché à un locuteur par une règle, pas par le recouvrement de son temps avec la diarisation : mot dans un blanc rattaché au segment le plus proche (moins de 0,5 s), ou mot sans temps rattaché à ses voisins. Voir ADR 0011. |
| Tour bien attribué | `turns_correct` | Mesure du banc : tour de référence (≥ 1 s) dont la majorité des mots va à la bonne personne. |
| Tour de parole | `turn` | Suite de mots consécutifs du même locuteur. Unité d'affichage. |
| Référence de mesure | `annotation` | Ce qu'une personne a entendu sur une fenêtre d'une séance (texte et personne par tour, cochés « vérifié »), pour mesurer le moteur (`coulisses-banc juger`). Distincte des corrections : elle ne modifie aucun résultat et ne sert qu'à la mesure. |
| Correction | `edit` | Modification utilisateur (texte, locuteur, phase). Stockée à part des sorties de moteurs. Dans le code de l'interface : `EditRequest` (ce qu'on demande), `EditInfo` (l'historique). |
| Vue corrigée | `corrected_view` | Sortie de l'exécution active avec les corrections appliquées. Ce qu'affiche l'app et ce que lisent les résumés. |
| Report des corrections | `edit_carryover` | Réapplication des corrections de la version remplacée sur la nouvelle, par le temps mesuré (ADR 0028). Ce qui n'a pas pu être reporté est listé avec sa raison. |
| Glossaire | `glossary` | Termes d'un espace : prénoms, jargon, formats, exercices, personnages récurrents, sigles. |
| Action | `action` | Modèle de résumé : nom, description, prompt. Ex. « Résumé Impro ». Fournie (fichier de l'application, clé = nom du fichier) ou à soi (en base, clé `perso-<id>`). Une action fournie modifiée garde sa clé ; sa version modifiée est en base (`based_on`), l'original reste restaurable. |
| Assemblage | `prompt_assembly` | Construction du prompt complet dans l'ordre fixe de la spec §7.9. Seul chemin vers le LLM. |
| Génération | `generation` | Un résultat d'action sur une séance, avec le prompt complet envoyé et la provenance. |
| Conservation | `retention` | Politique de durée de vie de l'audio. |
| Purge | `purge` | Suppression de tout l'audio d'une séance à échéance. Le texte reste. |
| Suppression | `deletion` | Suppression manuelle et confirmée : de l'audio seul, ou de la séance entière, texte compris. Distincte de la purge. |
| Journal des suppressions | `deletion_log` | Trace de chaque purge et de chaque suppression : quand, quoi, quelle séance. |
| Audio gardé | `keep_audio` | Option d'une séance : son audio n'est jamais purgé (ADR 0029). Remplace « épinglée ». |
| Préavis | `notice` | Délai entre l'annonce d'une purge et la purge elle-même (7 jours par défaut). |
| Annonce de purge | `purge_announcement` | Avertissement (bandeau, notification macOS) qu'une purge aura lieu ; le préavis court à partir de lui. |
| Prolonger | `extend` | Garder l'audio d'une séance une durée de conservation entière à partir d'aujourd'hui. |
| Banc d'essai | `bench` | Outillage de mesure des moteurs sur mes données (`evaluation.md`). |
| Campagne | `campaign` | Une série de tests du banc : des systèmes × les fichiers d'un jeu de test, avec son rapport. |
| Système | `system` | Dans une campagne, une combinaison testée : moteur de transcription, modèle, réglages, et alignement si besoin. |
| Classement | `leaderboard` | Tous les systèmes mesurés sur un même jeu de test, du meilleur au moins bon (règles : `evaluation.md`). |
| Étape reprise | `reused run` | Étape identique déjà calculée, réutilisée au lieu d'être recalculée ; signalée par un fichier `.reprise.json`. |
| Corpus | `corpus` | Enregistrements publics téléchargés pour le banc (tri préalable), convertis en jeu de test. |
| Jeu de test | `dataset` | Fichiers audio et leurs références. Type : vérification (synthétique), public (tri préalable), personnel (vos séances). |
| Extrait annoté | `reference_excerpt` | 10–15 min annotées à la main (qui parle quand, phases). Vérité terrain du banc. |
