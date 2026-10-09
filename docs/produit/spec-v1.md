# Coulisses — spécification produit V1

> Document de référence du produit : **ce que** l'app fait et **pourquoi**.
> Le **comment** est dans `docs/decisions/` (ADR). Le vocabulaire est défini dans `glossaire-domaine.md`.
> Les points non tranchés sont dans `questions-ouvertes.md`.

## 1. En une phrase

Une app 100 % locale qui enregistre une séance (répétition d'impro ou réunion de travail, sur place ou en ligne) avec un micro (avec le son de l'ordinateur pour une réunion en ligne, et plusieurs appareils), identifie au mieux qui parle, et produit en français des comptes rendus structurés.

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
5. **Résumer** : à la demande. Les chapitres sont déjà là ; le titre se propose d'un clic ; je lance le résumé proposé par l'espace (le Résumé Impro pour une troupe) ou un autre, avec le modèle choisi dans la liste. Je peux relancer, comparer deux versions côte à côte (ADR 0025). Mes corrections (noms, texte, phases) sont prises en compte.
6. **Retrouver et partager** : bibliothèque par espace et par projet, recherche plein texte, export Markdown, copie dans le presse-papiers.

## 7. Fonctionnalités V1

### 7.1 Espaces, projets, présents (ADR 0020)

- **Des espaces** : une troupe, une équipe, un client. Chaque séance appartient à un espace. Un espace a ses membres, ses invités, son glossaire, ses projets et ses réglages. Les espaces sont étanches : une personne présente dans deux espaces y a deux fiches.
- **Membres** : un nom et un rôle libre (« coach », « comédienne », « cheffe de projet »).
- **Invités** : ajoutés à la volée sur une séance, réutilisables ensuite dans le même espace.
- **Projets** : groupent les séances d'un espace (un spectacle pour une troupe). Une séance appartient à un projet, ou à aucun.
- **Présents** : cochés à la préparation ou après coup, plus un nombre de personnes non nommées si besoin. Leur total alimente le minimum de locuteurs (P3).
- **Réglages d'un espace** : le résumé proposé en premier (aucun résumé ne se lance seul, ADR 0025), et la reconnaissance des voix d'une séance à l'autre (désactivée par défaut). À la création, un **modèle de départ** (« Troupe d'impro », « Réunions de travail », « Vide ») les remplit une fois ; tout reste modifiable. Il n'y a pas de type d'espace.

### 7.2 Enregistrement

- **Où se passe la séance** : « Sur place » (le micro) ou « En ligne ou hybride » : le micro **et le son de l'ordinateur** (tout ce qu'il joue : Zoom, Teams, Meet…), enregistrés ensemble sur la même horloge, chacun dans son fichier, avec son vumètre (ADR 0032). Pour le traitement et l'écoute, les deux sont réunis en une piste ; les personnes à distance sont entendues même avec un casque. macOS demande la permission « Enregistrement audio du système » ; sans elle, ce son arrive muet, et l'écran d'enregistrement le rappelle.
- Choix du **micro principal**, et d'**autant de micros ajoutés** que voulu (« Ajouter un micro ») enregistrant en même temps : souvent un iPhone, que Continuité fait apparaître comme un micro du Mac (ADR 0031, 0033). Chacun a son fichier, son vumètre et ses alertes ; la pause les coupe ensemble ; un micro ajouté qui lâche n'arrête pas l'enregistrement. Pour l'instant, seul le micro principal est traité ; les autres sont gardés (« 3 micros » sous le titre de la séance).
- **Captation brute** : pas de réduction de bruit, pas d'annulation d'écho, pas de gain automatique. WAV PCM 48 kHz, tel quel.
- Vumètre, alertes de niveau (trop faible, saturation, micro qui ne donne plus de son), pause et reprise. La pause coupe le son à l'instant où on la demande : le fichier ne contient que ce qui a été enregistré. Fermer la page n'arrête pas l'enregistrement ; la bibliothèque montre qu'il est en cours.
- **Écriture continue sur disque** : une séance survit à un crash de l'interface, du service ou du Mac. Au redémarrage, l'enregistrement interrompu est récupéré et signalé.
- **Pendant l'enregistrement, le Mac ne se met pas en veille**, ni pendant le traitement.
- **À l'arrêt**, le traitement démarre si le Mac est branché. Sur batterie, il attend : la séance propose « Traiter maintenant », avec la durée estimée (ADR 0027).
- **Marqueurs** horodatés, au temps de l'enregistrement (pauses exclues) : une **bascule** Jeu ⇄ Discussion qui montre le mode en cours (« Jeu depuis 3:40 ») et passe à l'autre d'un geste (touches J et D), et **★ Moment** pour un moment clé (M). Au départ, aucun mode : ce qui n'est pas marqué est laissé à la détection. Une frise se construit en direct, comme celle des chapitres en relecture.
- **Notes pendant la séance** : une ligne sans cadre (touche N) ; la note prend l'heure de sa **première lettre**, pas celle de l'envoi. Un marqueur ou une note posés par erreur se retirent de la liste, pendant l'enregistrement.
- **Import** : fichiers audio (wav, m4a, mp3, flac, ogg…) et vidéo (la piste audio est extraite). L'original est conservé tel quel.

### 7.3 Sources multiples (préparées en V1, exploitées plus tard)

- Une séance a **une ou plusieurs sources audio**. En V1 : une seule, captée ou importée.
- Le modèle de données, le stockage et les étapes sont conçus pour N sources (ex. Mac + 2 téléphones), sans refonte ultérieure.
- *Plus tard* : synchronisation automatique des sources, choix ou mixage de la meilleure, et utilisation des différences de niveau entre appareils pour la diarisation.

### 7.4 Traitement

- **Étapes** : préparation audio, déréverbération (optionnelle), transcription, alignement, diarisation, attribution, détection des phases, titre, résumés. **Le moteur** (dépôt `coulisses-moteur`, ADR 0003 et 0014 de ce dépôt-là) fait la transcription, l'alignement, la diarisation et l'attribution ; **l'application** fait les phases, le titre et les résumés (via `prompting/`). La préparation audio et la déréverbération ne sont pas dans la chaîne retenue.
- **File d'attente** persistante : survit à un redémarrage.
- **Une étape qui échoue n'efface pas les précédentes.** L'erreur est lisible dans l'app, en français, avec ce qu'il faut faire (modèle à installer, mémoire, fichier illisible…) d'après le code d'erreur du moteur. Reprendre ne relance que ce qui n'a pas réussi. Si la diarisation a trouvé moins de voix que de présents, je reprends en indiquant moins de présents : le moteur ne fusionne jamais des voix pour atteindre le compte.
- **Chaque étape se relance seule**, depuis la version affichée (« Relancer… » dans la vue d'ensemble, ADR 0028) : la **transcription**, avec le glossaire de l'espace tel qu'il est et la version installée du moteur, en gardant la séparation des voix ; ou la **séparation des voix**, avec un autre nombre de présents, en gardant la transcription. Le dialogue dit ce que la relance apporte (termes ajoutés au glossaire, moteur mis à jour) et combien de temps elle a pris la dernière fois. « Un autre moteur » viendra quand le moteur proposera plusieurs profils.
- Une relance produit une **nouvelle version**, qui remplace la version affichée **seulement une fois complète**. D'ici là, je continue à relire et corriger ; les étapes refaites sont marquées **périmées**, jamais supprimées. Une relance qui s'arrête en route ne change rien à la version affichée, et « Reprendre » repart de ce qui a réussi.
- **Profil** : un seul en V1, la chaîne retenue du moteur (`chaine-retenue`), la plus juste mesurée au banc et déjà rapide (décidé le 2026-10-02). Un second profil ne viendra que si le banc trouve mieux en plus lent.
- **Nombre approximatif de présents** : utilisé comme minimum de locuteurs, jamais comme maximum.
- **Provenance** : chaque résultat porte le moteur, sa version, le modèle, les réglages, la durée, la mémoire max, la date.
- **Mode développeur** : un interrupteur, désactivé par défaut, affiche les détails techniques (provenance de chaque étape, durée de calcul, mémoire, versions, dossier des données, empreinte du fichier, erreur brute du moteur). Sans lui, l'interface ne montre que l'état de chaque étape et une erreur en français simple : rien n'est caché d'une erreur, seulement son détail technique.
- **Traitement de nuit** : le Mac ne dort pas pendant un traitement. Si le Mac est sur batterie, l'app prévient qu'un capot fermé peut interrompre la nuit.

### 7.5 Phases (« chapitres » dans l'interface)

- L'app **détecte automatiquement** les phases après le traitement ; c'est le seul appel automatique au LLM (titre et résumés à la demande, ADR 0025 et 0026) : le LLM local lit la transcription et propose des chapitres, chacun de type jeu (`scene`), discussion ou autre, avec un titre court (ADR 0024). Une séance de travail est découpée par sujet. Chaque chapitre commence à une réplique existante, jamais à une heure inventée.
- Les **marqueurs posés à la main priment** sur la détection : une bascule Jeu ou Discussion coupe un chapitre sur la réplique qui la suit, avec ce type ; une coupure détectée à moins d'une minute est remplacée par elle, en gardant son titre ; le chapitre d'ouverture reste. Ces chapitres portent un petit drapeau « posé pendant la séance ». Les moments clés et les notes s'intercalent dans la transcription et sont envoyés au modèle à leur place ; les moments clés sont aussi sur la frise.
- Je corrige les chapitres en relecture : renommer en tapant directement dans le titre, changer le type, retirer une coupure (les répliques rejoignent le chapitre précédent), commencer un chapitre à une réplique (bouton ou touche C). Déplacer une frontière, c'est retirer la coupure puis recouper ailleurs. Cmd-Z et Maj-Cmd-Z annulent et rétablissent, comme les autres corrections. Une nouvelle détection garde mes corrections.
- Sous le titre de la séance, une frise montre les chapitres, proportionnels à leur durée, avec le chapitre en cours et la tête de lecture ; un clic y amène la lecture. Dans le transcript, un chapitre se replie ; celui qu'on écoute reste ouvert.
- Si la détection échoue (Ollama absent, réponse illisible), l'échec s'affiche avec « Relancer » et les résumés se font sans chapitres.
- Les phases servent : à l'affichage, au transcript envoyé au modèle, à l'évaluation (attribution mesurée séparément sur les discussions), et plus tard éventuellement à des réglages de diarisation par phase.

### 7.6 Transcript et relecture

- Vue par **tours de parole** : une couleur par locuteur, horodatage, phases visibles, marqueurs et notes intercalés.
- **Lecture audio synchronisée** : clic sur une ligne → lecture à cet instant ; le mot courant est suivi. Vitesse de lecture réglable.
- **Locuteurs** : renommer (en choisissant un membre, un invité, ou un nom libre), fusionner, scinder, marquer « personnage joué par X ». Nommer une voix d'après une personne qui a déjà une voix dans la séance les fusionne (le moteur avait coupé une personne en deux, P3) ; un personnage joué reste une voix à part. Deux voix déjà rattachées à la même personne de l'espace se voient dans les participants, avec « Fusionner » ; le service le signale au moment où un nommage devient une fusion.
- **Édition du texte** : corriger un mot ou une phrase. Un mot corrigé garde son horodatage. Si la correction change le nombre de mots, la plage corrigée garde son début et sa fin mesurés ; les mots ajoutés n'ont pas de temps propre et sont marqués comme tels, jamais interpolés.
- **Édition directe**, comme dans un document : je clique dans une réplique et je tape ; la correction s'enregistre quand je quitte la réplique ou appuie sur Entrée, Échap annule ma saisie. Un texte refusé reste à l'écran pour être corrigé. Cmd-Z et Maj-Cmd-Z annulent et rétablissent la dernière correction (texte, nom, fusion, scission, chapitre) ; une réplique corrigée peut revenir à son texte d'origine. Rien n'est effacé : chaque annulation s'ajoute au journal.
- **Glossaire en relecture** : une graphie fautive connue est signalée ; un clic applique les bonnes graphies du glossaire à toute la réplique.
- **Mots peu sûrs** soulignés quand le modèle de transcription doutait (`asr_confidence` du moteur sous 0,3, depuis sa v1.4.0) et présentés comme « le modèle doutait » : ce score ne trouve qu'une partie des fautes, un mot non souligné n'est donc pas garanti juste. Le score d'alignement n'est jamais montré comme un doute.
- Longues séances fluides (2 h, plusieurs milliers de tours).
- **Corrections et retraitement** : relancer la transcription ou la diarisation produit une nouvelle version. L'app reporte automatiquement ce qu'elle peut, par le temps mesuré (ADR 0028) : le nom d'une voix à la nouvelle voix qui reprend au moins la moitié de son temps de parole, les fusions et les répliques données à une autre voix, les corrections de texte sur une réplique au texte d'origine identique, les coupures de chapitre à deux secondes près. Dans le doute, rien n'est reporté : l'app **liste ce qu'elle n'a pas pu reporter** (P8), avec la raison, l'heure du passage et le texte corrigé à reprendre à la main. Un bandeau le dit à l'arrivée de la nouvelle version. Une correction reportée s'annule comme les autres. Une correction faite pour la version qui vient d'être remplacée n'est jamais écrite ailleurs : l'app le dit, se met à jour et rend le texte tapé.
- **Versions du traitement** : la vue d'ensemble liste les versions (premier traitement, transcription refaite, voix séparées à nouveau), avec ce qui a été reporté. Une ancienne version s'affiche de nouveau d'un clic, avec ses propres corrections et ses chapitres ; passer d'une version à l'autre ne reporte rien.

### 7.7 Glossaire

- Un glossaire par espace : prénoms, jargon, formats, noms d'exercices, personnages récurrents, sigles.
- Utilisé à la **transcription** (dans la limite de ce que le moteur accepte) et au **résumé** (contexte).
- Une entrée peut avoir des variantes fautives connues (« Kathy » → « Cathy ») pour aider la relecture.

### 7.8 Notes manuelles

- Notes **pendant** la séance (horodatées, avec l'enregistrement) et **après** (libres, rattachées à la séance).
- La note d'après séance s'écrit dans la Vue d'ensemble, directement, sans cadre, comme le reste ; elle s'enregistre quand on la quitte.
- Injectées dans le contexte de chaque génération (« Notes prises après la séance »). Un résumé fait avant une modification de la note est signalé comme périmé.

### 7.9 Résumés (« actions »)

- **Actions fournies** : Compte rendu de réunion (proposé par le modèle « Réunions de travail »), Résumé Impro (proposé par le modèle « Troupe d'impro » ; son prompt est réécrit pour Coulisses, le texte OpenWhispr servant de témoin), Retours de jeu par comédien, Idées de scènes et personnages, Prochaines étapes et logistique, Résumé court à envoyer à la troupe.
- **Résumé court à envoyer à la troupe** : destiné à WhatsApp. Environ 10 lignes, sans titres Markdown, quelques puces, au plus un emoji. Il se colle tel quel dans le groupe. L'utilisateur le range aussi dans Google Drive, à partir de l'export (voir Q7).
- **Actions modifiables et créables** dans l'app (page « Actions ») : nom, description, prompt. Modifier une action fournie crée sa version modifiée, utilisée partout à sa place ; « Restaurer l'original » la met de côté sans l'effacer. Toute action se duplique. Une action à soi se retire (archivée, avec confirmation) : elle disparaît des listes et n'est plus proposée. Les actions sont communes à tous les espaces. Un résumé déjà fait garde le prompt exact qui l'a produit.
- **Assemblage du prompt**, toujours dans cet ordre :
  1. cadre système : rôle, Markdown strict, pas de préambule ni de titre, ne rien inventer ;
  2. prompt de l'action ;
  3. règle de repli : si rien de substantiel, une phrase factuelle, jamais une réponse vide ;
  4. consigne de langue explicite (français) ;
  5. contexte de séance : espace, projet, date, présents et rôles, glossaire, locuteurs avec leur nom et les personnages identifiés, notes manuelles ;
  6. transcript au format `[mm:ss] Nom : texte`, avec les marqueurs et les phases (pour le titre : les chapitres, sinon le dernier résumé, ADR 0026).
- **Pas de troncature silencieuse** : la taille du prompt est mesurée avant l'envoi. Si elle dépasse la fenêtre du modèle, l'app bascule sur un résumé par sections puis une consolidation, et l'indique. Chaque appel partiel et la consolidation passent par l'assemblage complet, consigne de langue comprise.
- **Historique des générations** par séance. Chaque génération conserve le prompt complet envoyé, le modèle et ses réglages (P7).
- **Comparaison côte à côte** de deux générations : on coche deux résumés de l'historique, puis « Comparer les deux ».
- **Choix du modèle local** au moment de générer, dans la liste des modèles d'Ollama ; le dernier choisi devient le défaut (ADR 0025).
- **Titre de séance** : proposé à la demande (« Proposer un titre », sous le titre), à partir des titres des chapitres, sinon du dernier résumé, sinon de la transcription ; modifiable ; un titre écrit à la main n'est jamais remplacé (ADR 0026).
- Le copier-coller fonctionne partout, clic droit compris.

### 7.10 Conservation de l'audio

- **Durée réglable**, 90 jours par défaut, comptés depuis l'entrée de la séance dans l'app (import ou enregistrement), jamais depuis la date du fichier (ADR 0029).
- À échéance, l'audio est supprimé : l'original **et** toutes ses versions dérivées (rééchantillonnée, déréverbérée…). Les sorties textuelles de chaque étape sont gardées, ainsi que les empreintes vocales que le moteur a écrites dans ses exécutions. Elles ne servent à reconnaître les voix que dans un espace qui l'a activé.
- **Aucune purge** d'une séance dont le traitement n'a pas abouti (transcription, alignement quand il est requis, diarisation et attribution réussis).
- **« Garder l'audio »**, option de chaque séance, la soustrait à la purge (extrait annoté pour l'évaluation, séance charnière).
- **Avertissement à l'avance** (7 jours par défaut, réglable) des séances bientôt purgées, par un **bandeau dans l'app** et une **notification macOS**. Je peux prolonger ou garder l'audio. La purge n'a lieu qu'une fois le préavis écoulé depuis l'avertissement : rien ne disparaît sans avoir été annoncé, même si je n'ouvre pas l'app pendant des mois.
- **Suppression manuelle immédiate et définitive**, après confirmation, depuis le menu « … » de la séance, au choix :
  - de l'**audio seul** : la séance devient une séance purgée ;
  - de la **séance entière**, traitée ou non, texte compris (transcript, corrections, notes, chapitres, résumés), y compris dans les sauvegardes de la base. C'est la seule façon de supprimer du texte. L'app rappelle ce qui sera perdu avant de confirmer.
- **Après purge** : plus de lecture audio ni de retraitement de la transcription, de l'alignement ou de la diarisation. Renommer les locuteurs, éditer le texte, redétecter les chapitres (ils ne lisent que le texte) et relancer les résumés restent possibles. La séance l'indique clairement (« audio supprimé le … »).
- **Journal des suppressions**, dans les réglages : chaque purge et chaque suppression, avec sa date, ses fichiers et leur taille ; aucun texte d'une séance supprimée.

### 7.11 Bibliothèque

- **Une coquille d'application** (ADR 0030) : une colonne latérale toujours là, avec les espaces, leurs projets et leurs séances, la plus récente d'abord ; un clic ouvre une séance à côté, sans quitter l'écran. Sur un espace, « + » commence une séance à cet endroit et « … » ouvre un menu (nouveau projet, paramètres de l'espace, archiver). Une séance se range dans un projet en la glissant dessus, ou depuis le fil « espace · projet » au-dessus de son titre. La colonne se masque (`⌘\`).
- « Nouvelle séance » (⌘N) : d'abord enregistrer maintenant ou importer un fichier, puis espace, projet, présents ; pour enregistrer, où se passe la séance et ce qui est enregistré (micro principal, micros ajoutés, son de l'ordinateur). Les boutons restent visibles en bas (ADR 0033).
- État visible de chaque séance : en traitement, prête, en erreur, audio bientôt purgé, audio purgé, audio gardé (un point dans la colonne, des étiquettes dans la liste des dernières séances).
- **Recherche plein texte** (⌘K) dans les transcriptions corrigées, les notes, les résumés et les titres, insensible aux accents et à la casse, chaque mot cherché comme début de mot ; un résultat ouvre la séance au passage.
- **Export Markdown** (résumé, transcript, ou les deux), copie dans le presse-papiers, et **export vers un dossier** choisi une fois dans les Réglages (par exemple un dossier synchronisé par Google Drive) : Coulisses n'y écrit qu'un fichier, ne remplace jamais un fichier existant sans le demander, et n'envoie rien lui-même.

### 7.12 Réglages et modèles

- **Lancement** : l'app **Coulisses** dans le Dock démarre le service et montre l'interface dans sa propre fenêtre. Quitter (⌘Q) arrête le service ; pendant un enregistrement ou un traitement, l'app demande d'abord. Rien ne tourne quand l'app est fermée. Les permissions de macOS (micro, son de l'ordinateur) vont à Coulisses (ADR 0005, 0034).
- **Dossiers** : depuis les Réglages, ouvrir dans le Finder le dossier des données, celui des modèles et le journal du service.
- Durée de conservation, préavis de purge.
- **Modèles dans un dossier visible** : `~/Coulisses/Modèles`, un sous-dossier par modèle avec sa fiche (source, révision, taille, date). Je les vois, les déplace ou les supprime dans le Finder ou depuis l'app.
- Liste des moteurs et modèles installés, avec leur taille disque ; suppression d'un modèle après confirmation.
- Téléchargement d'un modèle : action explicite, seule exception au hors-ligne, jamais déclenchée automatiquement. Un modèle absent arrête le traitement avec un message qui dit comment le télécharger.

## 8. Hors périmètre V1

Dictée, raccourcis globaux, transcription en temps réel, capture vidéo de la visio, comptes, sync, cloud, multi-utilisateur, diarisation vidéo, distribution de l'app.

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

- Une vraie séance de 80 min enregistrée dans l'app est traitée sans intervention (chapitres compris) avant le lendemain matin ; son compte rendu s'obtient ensuite en un clic (ADR 0025).
- Sur l'extrait annoté, les tours de parole des phases de discussion sont majoritairement bien attribués, et nettement mieux qu'avec OpenWhispr sur le même audio (protocole : `evaluation.md`).
- Je renomme un locuteur, je relance le résumé, et le bon nom apparaît.
- Passer d'un modèle à un autre, à n'importe quelle étape, ne demande qu'un changement de configuration.
- À échéance, la purge supprime l'audio et laisse intacts le transcript, les locuteurs et les résumés. Les séances dont l'audio est gardé ne sont pas touchées.
- L'app fonctionne entièrement hors ligne.
- Je juge le compte rendu au moins équivalent à celui d'OpenWhispr.

## 12. Méthode

1. **Moteur et banc d'essai, sans interface** : fichier audio en entrée → transcript diarisé et résumé en sortie. Validé sur un vrai enregistrement et sur l'extrait annoté.
2. **Interface** : relecture et renommage d'abord, enregistrement ensuite.
3. **Proposer, mesurer, décider** : chaque choix de modèle se tranche sur mes données, pas sur des benchmarks publics.
