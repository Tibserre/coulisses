# Coulisses — spécification produit V1

> Nom provisoire. Document de référence du produit : **ce que** l'app fait et **pourquoi**.
> Le **comment** est dans `docs/decisions/` (ADR). Le vocabulaire est défini dans `glossaire-domaine.md`.
> Les points non tranchés sont dans `questions-ouvertes.md`.

## 1. En une phrase

Une app 100 % locale qui enregistre une séance (répétition d'impro ou réunion de travail) avec un micro (ou plusieurs appareils, plus tard), identifie au mieux qui parle, et produit en français des comptes rendus structurés.

## 2. Pourquoi

OpenWhispr, utilisé jusqu'ici, échoue sur ce cas d'usage :
- diarisation inexploitable en présentiel mono-micro : horodatages estimés au prorata des caractères, 82 % de la parole rattachée à un seul locuteur sur une séance de 81 min ;
- l'audio n'est jamais conservé, impossible de retraiter ;
- prompts de résumé en anglais, sans consigne de langue ;
- beaucoup de fonctions inutiles ici (sync, comptes, dictée, overlay).

Coulisses fait **une seule chose, bien** : le débrief d'une séance enregistrée. Le premier usage, et la référence de qualité, est la répétition d'impro ; le même outil sert aux réunions de travail (ADR 0020).

## 3. Utilisateur et contexte

- **Un seul utilisateur** : moi, sur mon Mac (Apple M5 Pro, 64 Go). Pas de distribution prévue ; seuls les comptes rendus sont partagés.
- **Des espaces** : une troupe d'impro (quelques comédiens et un coach, plus des invités ponctuels), des équipes ou des clients au travail. Chaque espace a ses membres ; les participants changent d'un espace à l'autre.
- **Une séance** : 1 h à 2 h, en salle, micro posé. En impro, alternance de **scènes jouées** et de **discussions** (retours, débrief, décisions sur le spectacle) ; au travail, une réunion découpée en chapitres.
- **Captation** : le Mac dans la salle (V1), ou un téléphone / enregistreur dont on importe le fichier (V1). Captation simultanée Mac + téléphones (plus tard, prévue dans le modèle dès la V1).

## 4. Objectifs

1. **Séance → compte rendu sans intervention.** J'enregistre, j'arrête, c'est prêt quand je reviens (au plus tard le lendemain matin).
2. **Savoir qui a dit quoi pendant les discussions.** C'est là que l'attribution doit être fiable. Pendant les scènes, « au mieux » suffit ; un personnage peut apparaître comme un locuteur distinct.
3. **Des comptes rendus en français**, dans le vocabulaire de l'impro, au moins aussi bons que ceux d'OpenWhispr avec le prompt « Résumé Impro » (`prompt-resume-impro.md`).
4. **Aucune donnée ne sort de la machine.** L'app fonctionne en mode avion.
5. **Rien ne disparaît sans décision explicite.** L'audio est gardé une durée choisie, puis supprimé ; le texte reste tant que je ne supprime pas la séance moi-même.
6. **Les modèles évoluent** : en changer est simple, et chaque changement se décide par une mesure sur mes propres séances.

## 5. Principes non négociables

Ces principes priment sur toute autre considération (performance, simplicité, délai). Un changement qui en viole un est refusé.

| # | Principe | Conséquence concrète |
|---|---|---|
| P1 | **Local d'abord, toujours.** | Aucun appel réseau à l'exécution. Les modèles sont téléchargés explicitement, une fois, par une commande dédiée ; ensuite tout tourne hors ligne. Pas de télémétrie, pas de CDN, pas de police web distante. |
| P2 | **Horodatages mesurés, jamais estimés.** | Chaque temps de mot vient de l'audio (moteur à horodatage mesuré ou alignement forcé), ou manque : un mot que l'aligneur ne sait pas placer reste sans temps (au moins 90 % de mots horodatés, sinon refus, ADR 0011). Jamais d'interpolation, jamais de répartition au prorata du texte. Un moteur déclare si ses horodatages sont mesurés. |
| P3 | **Mieux vaut trop de locuteurs que pas assez.** | Seuils orientés sur-segmentation. Le nombre de présents est un **minimum**, jamais un maximum. Aucun réglage de diarisation ne dépend de la durée de la séance. La métrique prioritaire est la pureté des locuteurs. |
| P4 | **Le français partout.** | Chaque génération reçoit une consigne de langue explicite, sans chemin d'exception. Prompts rédigés en français natif. |
| P5 | **Rejouable tant que l'audio est là, lisible pour toujours.** | Pendant la conservation, chaque étape peut être relancée. Après la purge, toutes les sorties textuelles restent. |
| P6 | **Aucun modèle gravé dans le produit.** | Chaque étape passe par un moteur interchangeable. Changer de modèle = changer une configuration. |
| P7 | **Transparence.** | On voit où en est le traitement, ce qui a échoué, et avec quel moteur, quelle version et quels réglages chaque résultat a été produit. |
| P8 | **Aucune perte silencieuse.** | Rien n'est tronqué, écrasé ou supprimé sans que l'app le dise. Une étape qui échoue n'efface pas les précédentes. Une correction qui ne peut pas être reportée est signalée. |

## 6. Parcours principal

1. **Préparer** : choisir l'espace et le projet, cocher les membres présents, ajouter d'éventuels invités.
2. **Enregistrer** : un gros bouton, niveau d'entrée visible, alerte si trop faible ou saturé. Un tap pose un marqueur (« scène », « discussion », « moment clé »). Je peux taper des notes horodatées.
   *Ou* importer un fichier enregistré ailleurs.
3. **Traiter** : automatiquement à l'arrêt, en arrière-plan, progression par étape visible. Un seul réglage : la chaîne retenue du moteur (≈ 10 min de calcul par heure d'audio).
4. **Relire** : transcript par locuteur, horodaté, découpé en phases. Cliquer une ligne rejoue l'audio à cet instant. Je renomme, fusionne, scinde des locuteurs, j'en marque un comme « personnage joué par Marie », je corrige un mot, je corrige une phase.
5. **Résumer** : les résumés automatiques de l'espace sont déjà là (le Résumé Impro pour une troupe). Je peux lancer d'autres actions, relancer, comparer deux versions côte à côte. Mes corrections (noms, texte, phases) sont prises en compte.
6. **Retrouver et partager** : bibliothèque par espace et par projet, recherche plein texte, export Markdown, copie dans le presse-papiers.

## 7. Fonctionnalités V1

### 7.1 Espaces, projets, présents (ADR 0020)

- **Des espaces** : une troupe, une équipe, un client. Chaque séance appartient à un espace. Un espace a ses membres, ses invités, son glossaire, ses projets et ses réglages. Les espaces sont étanches : une personne présente dans deux espaces y a deux fiches.
- **Membres** : un nom et un rôle libre (« coach », « comédienne », « cheffe de projet »).
- **Invités** : ajoutés à la volée sur une séance, réutilisables ensuite dans le même espace.
- **Projets** : groupent les séances d'un espace (un spectacle pour une troupe). Une séance appartient à un projet, ou à aucun.
- **Présents** : cochés à la préparation ou après coup, plus un nombre de personnes non nommées si besoin. Leur total alimente le minimum de locuteurs (P3).
- **Réglages d'un espace** : les résumés lancés automatiquement après le traitement, et la reconnaissance des voix d'une séance à l'autre (désactivée par défaut). À la création, un **modèle de départ** (« Troupe d'impro », « Réunions de travail », « Vide ») les remplit une fois ; tout reste modifiable. Il n'y a pas de type d'espace.

### 7.2 Enregistrement

- Choix du micro.
- **Captation brute** : pas de réduction de bruit, pas d'annulation d'écho, pas de gain automatique. WAV PCM 48 kHz, tel quel.
- Vumètre, alertes de niveau (trop faible, saturation), pause et reprise.
- **Écriture continue sur disque** : une séance survit à un crash de l'interface, du service ou du Mac. Au redémarrage, l'enregistrement interrompu est récupéré et signalé.
- **Pendant l'enregistrement, le Mac ne se met pas en veille.**
- **Marqueurs** horodatés : scène, discussion, moment clé.
- **Notes pendant la séance** : champ libre, chaque note horodatée.
- **Import** : fichiers audio (wav, m4a, mp3, flac, ogg…) et vidéo (la piste audio est extraite). L'original est conservé tel quel.

### 7.3 Sources multiples (préparées en V1, exploitées plus tard)

- Une séance a **une ou plusieurs sources audio**. En V1 : une seule, captée ou importée.
- Le modèle de données, le stockage et les étapes sont conçus pour N sources (ex. Mac + 2 téléphones), sans refonte ultérieure.
- *Plus tard* : synchronisation automatique des sources, choix ou mixage de la meilleure, et utilisation des différences de niveau entre appareils pour la diarisation.

### 7.4 Traitement

- **Étapes** : préparation audio, déréverbération (optionnelle), transcription, alignement, diarisation, attribution, détection des phases, titre, résumés. **Le moteur** (dépôt `coulisses-moteur`, ADR 0003 et 0014 de ce dépôt-là) fait la transcription, l'alignement, la diarisation et l'attribution ; **l'application** fait les phases, le titre et les résumés (via `prompting/`). La préparation audio et la déréverbération ne sont pas dans la chaîne retenue.
- **File d'attente** persistante : survit à un redémarrage.
- **Une étape qui échoue n'efface pas les précédentes.** L'erreur est lisible dans l'app.
- **Chaque étape se relance seule**, avec d'autres réglages ou un autre moteur. Exemple : refaire la diarisation sans retranscrire. Les étapes en aval sont alors marquées **périmées**, jamais supprimées.
- **Profil** : un seul en V1, la chaîne retenue du moteur (`chaine-retenue`), la plus juste mesurée au banc et déjà rapide (décidé le 2026-10-02). Un second profil ne viendra que si le banc trouve mieux en plus lent.
- **Nombre approximatif de présents** : utilisé comme minimum de locuteurs, jamais comme maximum.
- **Provenance** : chaque résultat porte le moteur, sa version, le modèle, les réglages, la durée, la mémoire max, la date.
- **Traitement de nuit** : le Mac ne dort pas pendant un traitement. Si le Mac est sur batterie, l'app prévient qu'un capot fermé peut interrompre la nuit.

### 7.5 Phases

- L'app **détecte automatiquement** les phases (scène, discussion, autre) à partir des marqueurs, du rythme des échanges et du contenu.
- Les **marqueurs posés à la main priment** sur la détection.
- Je corrige les phases en relecture (déplacer une frontière, changer un type).
- Les phases servent : à l'affichage, au transcript envoyé au modèle, à l'évaluation (attribution mesurée séparément sur les discussions), et plus tard éventuellement à des réglages de diarisation par phase.

### 7.6 Transcript et relecture

- Vue par **tours de parole** : une couleur par locuteur, horodatage, phases visibles, marqueurs et notes intercalés.
- **Lecture audio synchronisée** : clic sur une ligne → lecture à cet instant ; le mot courant est suivi. Vitesse de lecture réglable.
- **Locuteurs** : renommer (en choisissant un membre, un invité, ou un nom libre), fusionner, scinder, marquer « personnage joué par X ».
- **Édition du texte** : corriger un mot ou une phrase. Un mot corrigé garde son horodatage. Si la correction change le nombre de mots, la plage corrigée garde son début et sa fin mesurés ; les mots ajoutés n'ont pas de temps propre et sont marqués comme tels, jamais interpolés.
- **Mots peu sûrs** mis en évidence quand le moteur fournit une confiance.
- Longues séances fluides (2 h, plusieurs milliers de tours).
- **Corrections et retraitement** : relancer la transcription ou la diarisation produit une nouvelle version. L'app reporte automatiquement ce qu'elle peut (noms de locuteurs par recouvrement temporel, corrections de mots sur le même passage) et **liste ce qu'elle n'a pas pu reporter** (P8). L'ancienne version reste consultable.

### 7.7 Glossaire

- Un glossaire par espace : prénoms, jargon, formats, noms d'exercices, personnages récurrents, sigles.
- Utilisé à la **transcription** (dans la limite de ce que le moteur accepte) et au **résumé** (contexte).
- Une entrée peut avoir des variantes fautives connues (« Kathy » → « Cathy ») pour aider la relecture.

### 7.8 Notes manuelles

- Notes **pendant** la séance (horodatées) et **après** (libres, rattachées à la séance).
- Injectées dans le contexte de chaque génération, comme le prévoit le prompt « Résumé Impro ».

### 7.9 Résumés (« actions »)

- **Actions fournies** : Compte rendu de réunion (lancée automatiquement par le modèle « Réunions de travail », à écrire), Résumé Impro (lancée automatiquement par le modèle « Troupe d'impro » ; son prompt est réécrit pour Coulisses, le texte OpenWhispr servant de témoin), Retours de jeu par comédien, Idées de scènes et personnages, Prochaines étapes et logistique, Résumé court à envoyer à la troupe.
- **Résumé court à envoyer à la troupe** : destiné à WhatsApp. Environ 10 lignes, sans titres Markdown, quelques puces, au plus un emoji. Il se colle tel quel dans le groupe. L'utilisateur le range aussi dans Google Drive, à partir de l'export (voir Q7).
- **Actions modifiables et créables** dans l'app : nom, description, prompt. Les actions fournies peuvent être dupliquées ; l'original reste restaurable.
- **Assemblage du prompt**, toujours dans cet ordre :
  1. cadre système : rôle, Markdown strict, pas de préambule ni de titre, ne rien inventer ;
  2. prompt de l'action ;
  3. règle de repli : si rien de substantiel, une phrase factuelle, jamais une réponse vide ;
  4. consigne de langue explicite (français) ;
  5. contexte de séance : espace, projet, date, présents et rôles, glossaire, locuteurs avec leur nom et les personnages identifiés, notes manuelles ;
  6. transcript au format `[mm:ss] Nom : texte`, avec les marqueurs et les phases.
- **Pas de troncature silencieuse** : la taille du prompt est mesurée avant l'envoi. Si elle dépasse la fenêtre du modèle, l'app bascule sur un résumé par sections puis une consolidation, et l'indique. Chaque appel partiel et la consolidation passent par l'assemblage complet, consigne de langue comprise.
- **Historique des générations** par séance. Chaque génération conserve le prompt complet envoyé, le modèle et ses réglages (P7).
- **Comparaison côte à côte** de deux générations.
- **Choix du modèle local** par action ou par génération.
- **Titre de séance** généré automatiquement, modifiable.
- Le copier-coller fonctionne partout, clic droit compris.

### 7.10 Conservation de l'audio

- **Durée réglable**, 90 jours par défaut.
- À échéance, l'audio est supprimé : l'original **et** toutes ses versions dérivées (rééchantillonnée, déréverbérée…). Les sorties textuelles de chaque étape sont gardées, ainsi que les empreintes vocales que le moteur a écrites dans ses exécutions. Elles ne servent à reconnaître les voix que dans un espace qui l'a activé.
- **Aucune purge** d'une séance dont le traitement n'a pas abouti (transcription, alignement quand il est requis, diarisation et attribution réussis).
- **Épingler** une séance la soustrait à la purge (extrait annoté pour l'évaluation, séance charnière).
- **Avertissement à l'avance** (7 jours par défaut, réglable) des séances bientôt purgées, par un **bandeau dans l'app** et une **notification macOS**. Je peux prolonger.
- **Suppression manuelle immédiate**, après confirmation, au choix :
  - de l'**audio seul** : la séance devient une séance purgée ;
  - de la **séance entière**, texte compris (transcript, corrections, notes, résumés). C'est la seule façon de supprimer du texte. L'app rappelle ce qui sera perdu avant de confirmer.
- **Après purge** : plus de lecture audio ni de retraitement de la transcription, de l'alignement, de la diarisation ou des phases. Renommer les locuteurs, éditer le texte, relancer les résumés restent possibles. La séance l'indique clairement (« Audio supprimé le … »).

### 7.11 Bibliothèque

- Séances groupées par espace et par projet, triées par date.
- État visible de chaque séance : en traitement, prête, en erreur, audio bientôt purgé, audio purgé, épinglée.
- **Recherche plein texte** dans les transcripts, les notes et les résumés (insensible aux accents et à la casse).
- **Export Markdown** (résumé, transcript, ou les deux) et copie dans le presse-papiers.

### 7.12 Réglages et modèles

- **Lancement** : une icône dans le Dock ouvre une petite app lanceur, qui démarre le service et ouvre l'interface. Rien ne tourne quand l'app n'est pas utilisée. La permission micro de macOS est accordée à ce lanceur (ADR 0005).
- Durée de conservation, préavis de purge.
- **Modèles dans un dossier visible** : `~/Coulisses/Modèles`, un sous-dossier par modèle avec sa fiche (source, révision, taille, date). Je les vois, les déplace ou les supprime dans le Finder ou depuis l'app.
- Liste des moteurs et modèles installés, avec leur taille disque ; suppression d'un modèle après confirmation.
- Téléchargement d'un modèle : action explicite, seule exception au hors-ligne, jamais déclenchée automatiquement. Un modèle absent arrête le traitement avec un message qui dit comment le télécharger.

## 8. Hors périmètre V1

Dictée, raccourcis globaux, transcription en temps réel, capture audio système ou visio, comptes, sync, cloud, multi-utilisateur, diarisation vidéo, distribution de l'app.

## 9. Plus tard

- **Captation multi-appareils** : Mac + un ou plusieurs téléphones, synchronisation, meilleur son, et différences de niveau entre appareils comme indice de diarisation. *Prioritaire parmi les évolutions.*
- **Profils vocaux** : reconnaître Marie d'une séance à l'autre, seulement dans les espaces où la reconnaissance des voix est activée.
- **Questions sur tout l'historique** d'un projet (« qu'avait-on décidé pour la fin ? »).
- Micro multi-capsules : direction d'arrivée + empreinte vocale.
- Diarisation par la vidéo.
- Export PDF, partage avec les participants.
- Téléphone utilisé comme micro piloté par l'app.

## 10. Exigences non fonctionnelles

| Domaine | Exigence |
|---|---|
| Hors ligne | Tout le parcours fonctionne en mode avion. Vérifié par un test automatisé réseau coupé. |
| Vitesse | 80 min d'audio traitées en 15 min au plus par le moteur (≈ 10 min de calcul par heure d'audio mesurées), résumés en plus. |
| Mémoire | Tient dans 64 Go avec les autres applis ouvertes. Pas deux gros modèles chargés en même temps sans nécessité. |
| Robustesse | Crash pendant l'enregistrement : au plus quelques secondes perdues. Crash pendant le traitement : reprise à l'étape interrompue. |
| Données | Un seul dossier visible `~/Coulisses/` : `App/` et `Moteur/` (les deux dépôts git, ADR 0016), `Modèles/`, `Environnements/`, `Données/`. Jamais dans un dossier synchronisé (ADR 0010). |
| Longues séances | 2 h sans dérive d'horodatage ni dégradation de la diarisation. |

## 11. Critères de réussite V1

- Une vraie séance de 80 min enregistrée dans l'app donne un compte rendu sans intervention, avant le lendemain matin.
- Sur l'extrait annoté, les tours de parole des phases de discussion sont majoritairement bien attribués, et nettement mieux qu'avec OpenWhispr sur le même audio (protocole : `evaluation.md`).
- Je renomme un locuteur, je relance le résumé, et le bon nom apparaît.
- Passer d'un modèle à un autre, à n'importe quelle étape, ne demande qu'un changement de configuration.
- À échéance, la purge supprime l'audio et laisse intacts le transcript, les locuteurs et les résumés. Les séances épinglées ne sont pas touchées.
- L'app fonctionne entièrement hors ligne.
- Je juge le compte rendu au moins équivalent à celui d'OpenWhispr.

## 12. Méthode

1. **Moteur et banc d'essai, sans interface** : fichier audio en entrée → transcript diarisé et résumé en sortie. Validé sur un vrai enregistrement et sur l'extrait annoté.
2. **Interface** : relecture et renommage d'abord, enregistrement ensuite.
3. **Proposer, mesurer, décider** : chaque choix de modèle se tranche sur mes données, pas sur des benchmarks publics.
