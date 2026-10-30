# 0072 — Transcrire une séance dans une autre langue que le français

Statut : Acceptée (2026-10-29, par l'utilisateur, qui a retenu chaque proposition ; voir « Réponses de l'utilisateur »). Proposée le même jour (phase 1 du multilingue, demande de l'utilisateur : « l'utilisateur veut pouvoir transcrire une séance dans une autre langue que le français », relayée par Interface ; « Lance les phases pour le multilingue »). S'appuie sur le moteur v1.14.0 (ADR 0071 du moteur). Précise 0020, 0028, 0036, 0049, 0056, 0066 et 0069.

## Contexte
- **Le moteur v1.14.0** transcrit et aligne six langues avec la chaîne retenue : français, anglais, allemand, espagnol, italien et portugais. La langue est une entrée de la chaîne : `ChainInput(language=…)`, un code ISO 639-1, « fr » par défaut. Elle est écrite dans la provenance de la transcription (`inputs.language`) et dans la transcription elle-même (`Transcript.language`).
- **Pour chaque langue**, `languages(profil)` donne son nom, ses modèles, ceux qui manquent et la taille à télécharger. `readiness(profil, language=…)` dit ce qui manque pour une séance dans cette langue. Chaque langue autre que le français demande un aligneur de 1,26 Go, téléchargé sur demande seulement (`download`). Erreurs : `language_unsupported` pour une langue hors de ces six ; `model_missing` (avec la clé du modèle) pour un aligneur absent.
- **La diarisation ne dépend pas de la langue.** La transcription, l'alignement et l'attribution, si.
- **Aujourd'hui**, l'application ne passe pas de langue : tout est transcrit en français. Le français reste identique, octet pour octet.
- **Les rédactions** (titre, chapitres, résumés) passent par l'assemblage unique de `prompting/`, qui impose la consigne de langue française (P4).

## Décision

### La langue d'un espace et celle d'une séance
- **Chaque espace a une langue par défaut** : `space.language`, code ISO 639-1, « fr » par défaut. Elle se règle dans les paramètres de l'espace. Une réunion de travail en anglais aura ainsi son espace en anglais.
- **Chaque séance a sa langue** : `session.language`. Elle est prise de l'espace à la création (import, enregistrement), et l'utilisateur peut la changer tant que le premier traitement n'a pas commencé. Ensuite, elle suit la version affichée : elle change quand une version dans une autre langue devient la version affichée (voir « Refaire le texte »), jamais avant.
  - Déplacer une séance dans un autre espace ne change jamais sa langue : elle est fixée à la création, ou par l'utilisateur.
  - Les séances qui existent déjà sont en français (migration), ce qu'elles sont.
- **La langue d'une version vient de la provenance du moteur** (`inputs.language` de sa transcription), pas de la séance (P7) ; c'est elle que l'interface montre pour une version. Une transcription faite par un moteur antérieur à la v1.14.0 (version lue dans la même provenance) n'a pas de langue : elle est en français, seule langue de ces versions. Une provenance de v1.14.0 ou plus récente sans langue est une erreur dite, jamais un français supposé. Tant qu'une version en anglais n'est pas complète, la version affichée garde sa langue (ADR 0028).
- La liste des langues proposées est celle de `languages()` : l'application n'en grave aucune (P6), ni nom, ni nombre, ni taille ; l'interface lit `label` (déjà en français) et `download_bytes` dans `GET /api/langues`. Une langue que le moteur ne connaît pas est refusée avant d'être enregistrée.
- **Une langue retirée du moteur** plus tard peut rester celle d'un espace ou d'une séance. L'espace le dit dans ses paramètres (« n'est plus prise en charge ») ; une séance créée dedans garde cette langue, et son traitement ne part pas : il attend, comme pour un modèle manquant, en disant que la langue n'est plus prise en charge et en proposant d'en choisir une autre. Jamais de repli muet vers le français, ni d'échec tardif.

### Passer la langue au moteur
- **À la création de la tâche**, la langue de la séance est copiée dans ses paramètres (`ChainParams.language`, dans le JSON de la tâche : pas de nouvelle colonne). L'application la passe à `run_chain` par `ChainInput(language=…)`. « Reprendre » une tâche reprend sa langue, jamais une autre.
- **La file ne bloque pas** : une tâche qui attend son modèle est sautée par `claim_next`, comme une tâche qui attend ses présents (ADR 0069). Les autres séances ne l'attendent pas. La docstring de `ChainParams` (qui ne cite que `take_attendees`) le dira : `language` et `waits_for_models` changent aussi tant que la tâche est en file.
- **Changer la langue d'une séance dont le premier traitement attend encore** (l'import en un geste, qui attend « Qui était là ? » deux minutes au plus, ADR 0069) change aussi la langue de cette tâche en file, sous le même verrou que les présents (`take_attendees`). Une fois la tâche commencée, la langue ne se change plus que par « Refaire le texte ».
- **Avant de lancer une tâche**, le service vérifie `readiness(profil, language=…)`. **Si un modèle de cette langue manque, la tâche attend au lieu d'échouer** : elle reste en file, marquée dans ses paramètres (`ChainParams.waits_for_models`, la langue et les clés manquantes ; pas de nouvel état de tâche, donc pas de changement du CHECK de `job.state`), et n'est pas reprise tant que ces modèles manquent. La séance le dit (`Session.processing_waits_for` : la langue, son nom, les modèles, leur taille, et le téléchargement en cours avec son avancement). Elle repart d'elle-même quand le dernier modèle est installé (fin d'un téléchargement, ou au démarrage de l'app), ou dans une autre langue si l'utilisateur la change (« Traiter en français »). Rien ne se télécharge de lui-même (P1).
- **Si le moteur échoue quand même** sur la langue (`model_missing` après la vérification, `language_unsupported`), la tâche échoue avec un message en français qui dit quoi télécharger, ou quelles langues sont possibles. « Reprendre » vérifie d'abord la même chose : il remet la tâche en attente du modèle plutôt que de la relancer pour échouer de la même façon.

### Refaire le texte dans une autre langue
- **« Refaire le texte » prend une langue**, par défaut celle de la version affichée. C'est la relance `transcribe` de l'ADR 0028. Sont refaits la transcription, l'alignement et l'attribution. La séparation des voix est gardée : elle ne dépend pas de la langue. « Tout refaire » (ADR 0066) prend aussi une langue.
- **Les corrections suivent la règle du report** (ADR 0028), sans exception pour la langue :
  - le nom d'une voix va à la nouvelle voix qui reprend au moins la moitié de son temps de parole : les noms suivent presque tous ;
  - une correction de texte ne va qu'à une réplique de texte d'origine identique, au même moment. Dans une autre langue, elle ne se reporte presque jamais : elle est listée avec sa raison et reste sur l'ancienne version, avec son texte, pour être reprise à la main (P5, P8) ;
  - les coupures de chapitre suivent leur réplique, à deux secondes près.
- **Ce qui ne dépend pas de la transcription est gardé** : les annotations et les marques datées de l'enregistrement, la note d'après séance, les présents, l'audio.
- **Les rédactions ne sont pas refaites d'elles-mêmes.** Les chapitres sont détectés à nouveau, comme après toute nouvelle version (ADR 0028). Les résumés faits sur l'ancienne version se signalent comme faits sur une autre version.
- La langue choisie est dans les paramètres de la relance. Elle devient celle de la séance (`session.language`) quand la nouvelle version devient la version affichée, dans la même transaction que le report (ADR 0028). Une relance qui échoue ou est arrêtée (ADR 0070) ne change donc rien : la séance garde la langue de la version affichée. L'ancienne version reste affichable, dans sa langue.

### L'import et l'enregistrement en un geste
- **La langue par défaut est celle de l'espace où la séance est créée** : l'espace sélectionné (ADR 0056, 0069).
- **On peut la changer avant que le traitement parte** :
  - pour un import, pendant l'attente de « Qui était là ? » (deux minutes au plus, ou jusqu'à « Lancer ») ;
  - pour un enregistrement, pendant l'enregistrement, comme le contexte de la séance (espace, projet, présents, ADR 0056). Son traitement part à l'arrêt, dans la langue du moment.

### Le parcours dans l'interface
Proposé par Interface (2026-10-29), à valider par l'utilisateur sur maquette :
- **Un espace** : ses paramètres gagnent une section « Langue des séances », une liste des six langues, « Français » par défaut. Une langue pas encore installée y est marquée « à télécharger · 1,3 Go ». Le texte dit que changer la langue de l'espace ne touche pas ses séances existantes.
- **Une séance** : la langue se montre dans le fil au-dessus du titre (espace · projet · présents), dans une liste flottante, seulement si elle a quelque chose à dire : une autre langue est installée, ou la séance n'est pas en français. Un usage tout en français ne voit rien de nouveau.
- **Après le traitement**, changer la langue ne change rien en silence : le choix ouvre « Refaire le texte » dans cette langue (« Refaire le texte en anglais : la transcription est refaite, les voix sont gardées. »). La tuile « Le texte » de « Refaire le traitement… » gagne le choix de la langue. Tant que la relance n'est pas finie, la langue affichée est celle de la version affichée.
- **Enregistrement** : la langue se change dans le fil en tête de l'écran, pendant l'enregistrement, comme l'espace, le projet et les présents.
- **Import** : le bloc « Qui était là ? » gagne une ligne « En français · Changer », la langue de l'espace. Changer la langue enregistre aussitôt et ne relance pas le compte à rebours de deux minutes.
- **Un modèle qui manque, au moment de choisir** : la langue se présente « Anglais · à télécharger, 1,3 Go » ; la choisir demande « L'anglais n'est pas encore sur ce Mac. Le télécharger (1,3 Go) ? », et oui lance le téléchargement, comme dans les Réglages.
- **Au moment de lancer**, si le modèle manque encore : la séance dit « En attente du modèle anglais (téléchargement : 40 %) » ou « Le modèle anglais n'est pas sur ce Mac », avec « Télécharger » et « Traiter en français ».
- **Réglages › Transcription** : une section « Langues », au-dessus des modèles. Le français est « Installé » ; les cinq autres ont « Ajouter · 1,3 Go », puis leur barre d'avancement, puis « Installé » et « Supprimer ». Hors mode développeur, les aligneurs des autres langues ne sont plus listés parmi les modèles : cette section les montre.

### L'API
- `GET /api/langues` : les langues de la chaîne, d'après `languages()` et `readiness(language=…)`, le français d'abord, puis les autres dans l'ordre du moteur. Pour chacune : `language`, `label`, `installed` (rien ne manque), `missing_models`, `download_bytes`, et le téléchargement en cours avec son avancement (comme `actions` aujourd'hui).
- **Le téléchargement passe par la route qui existe** : `POST /api/moteur/modeles/{cle}/telecharger`, pour chaque modèle manquant, avec sa progression, son arrêt et sa reprise (ADR 0036). Aucune route ne télécharge plusieurs modèles d'un coup sans que chacun se voie.
- `PATCH /api/espaces/{id}` accepte `language`. `PUT /api/seances/{id}/langue` change la langue d'une séance tant que son premier traitement n'a pas commencé : pendant l'enregistrement, l'attente des présents ou l'attente d'un modèle (409 ensuite : « Refaire le texte »).
- **Supprimer une langue** passe par la suppression de ses modèles (`DELETE /api/moteur/modeles/{cle}`, ADR 0036). Elle est refusée, avec la raison, tant qu'un espace a cette langue par défaut ou qu'une séance attend dans cette langue. `POST /api/seances/{id}/relancer` accepte `langue` pour « Refaire le texte » et « Tout refaire ». `Session` gagne `language`, et chaque version (`/versions`, la séance) donne la sienne, lue dans sa provenance.
- **Une langue inconnue** donne 422, avec la liste des langues possibles. **Un modèle qui manque** ne fait jamais échouer la demande : la tâche est créée et attend son modèle, ce que la séance dit.
- **Les modèles des autres langues ne sont exigés que pour leur langue.** L'onglet Transcription ne montre pas comme manquant l'aligneur d'une langue qu'aucune séance n'utilise. Cela dépend du correctif d'Interface `fix/aligneurs-par-langue` (a7dd2c3), qui n'est pas encore dans `main` : il doit y entrer avec `build/moteur-1-14-0`, avant toute publication.

### Le schéma
- **Migration** : `space.language` et `session.language`, `TEXT NOT NULL DEFAULT 'fr'`, sans liste gravée dans le schéma (P6 : les langues sont celles du moteur). Les espaces et les séances existants reçoivent « fr ».
- **Numéro** : `main` s'arrête à 0010, et deux branches qui n'y sont pas encore ont chacune une migration 0011 : `feat/resumes-par-objectif` (Rédaction) et `feat/connecteur-mcp` (Service). Celle-ci serait donc la troisième. La numérotation doit rester continue (`migrations()` refuse les trous et les doublons) : chaque branche prend, juste avant d'entrer dans `main`, le numéro qui suit la dernière migration de `main`, et ajuste la doc du schéma. Une base de développement migrée avec un autre numéro se refait.
- Aucun autre changement : la langue d'une tâche est dans ses paramètres (JSON), celle d'une version dans la provenance du moteur.

### Les rédactions restent en français
Avis de Rédaction (2026-10-29), repris ici :
- Titres, chapitres et résumés sont rédigés **en français** quelle que soit la langue de la séance, par l'assemblage unique de `prompting/` (P4). La consigne de langue prévoit déjà une transcription en partie dans une autre langue, et elle est ajoutée à chaque appel.
- **La langue de la séance est dite au modèle** : une ligne du bloc de contexte (par exemple « Langue de la séance : anglais (la réponse reste en français) »), lue dans la provenance de la version résumée, jamais devinée. L'assemblage est fait par Rédaction, dans `prompting/`.
- **Risque connu** : avec un long transcript dans une autre langue, un modèle tend à basculer dans cette langue, le petit modèle des chapitres et du titre plus que le gros. **Aucune langue n'est dite prise en charge pour les rédactions avant une mesure** sur au moins une vraie séance en anglais et une en allemand (`scripts/mesurer-modeles.py` : chapitres, titre, un résumé). Critères : toute la sortie en français, titres de chapitres compris ; noms et vocabulaire gardés ; aucune traduction inventée. Le rapport caractères par token (1,8, mesuré en français) est revérifié sur ces langues, pour qu'aucun prompt ne dépasse `num_ctx`. Il n'y a pas encore de vraie séance étrangère : la mesure attend la première. Jusque-là, la transcription d'une autre langue est disponible, et ses rédactions sont faites, mais l'interface ne promet pas leur qualité.
- La recherche et le connecteur ne changent pas : ils lisent le texte tel qu'il est.

## Réponses de l'utilisateur
Le 2026-10-29, par la session Pilotage, l'utilisateur a retenu chaque proposition :
0. **Le schéma** : oui, deux colonnes, `space.language` et `session.language`, « fr » par défaut.
1. **Une langue par défaut par espace** : oui. La séance prend la langue de son espace à sa création, puis ne la suit plus.
2. **Les rédactions d'une séance dans une autre langue** : elles se font comme les autres, sans en promettre la qualité. La mesure se fera sur la première vraie séance en anglais et en allemand.
3. **Les citations exactes** dans un résumé en français restent dans leur langue, entre guillemets. C'est à Rédaction de le dire dans `prompting/`.
4. **Supprimer une langue** est refusé tant qu'un espace l'a par défaut ou qu'une séance attend dans cette langue, et le message dit où.
5. **Le parcours** : Interface en fait une maquette, que l'utilisateur voit avant que l'écran soit codé.

## Conséquences
- Une langue ajoutée coûte 1,26 Go, téléchargé sur demande, une fois.
- Une séance mal choisie se rattrape par « Refaire le texte » : la séparation des voix et les noms sont gardés, les corrections de texte sont listées.
- Le glossaire de l'espace est passé tel quel, quelle que soit la langue : à l'utilisateur d'y mettre les noms propres de sa séance.
- Les langues proposées suivent le moteur. Une langue ajoutée au moteur apparaît sans changement de l'application ; une langue retirée laisse les séances déjà transcrites lisibles ; un nouveau traitement dans cette langue attend, en le disant, qu'on en choisisse une autre (`processing_waits_for` dit alors sa raison : langue plus prise en charge, et non modèle manquant).
- La spec gagne la langue d'un espace et d'une séance (§7.1, §7.4, §7.6, §7.12) dans les commits qui la construisent.

## Alternatives écartées
- **La langue d'une séance seulement dans la tâche** (pas de colonne `session.language`) : un enregistrement n'a pas de tâche avant son arrêt, et l'utilisateur veut pouvoir choisir pendant qu'il enregistre.
- **Une liste de langues fixée dans le schéma (CHECK)** : chaque langue ajoutée au moteur demanderait une migration (P6).
- **Détecter la langue automatiquement** : Qwen3 le fait parfois, mais le moteur ne le mesure ni ne le propose ; une séance mêlée (deux langues) serait tranchée sans le dire. L'utilisateur choisit, l'espace propose.
- **Télécharger le modèle d'une langue de lui-même au moment de traiter** : un téléchargement est toujours explicite et confirmé (P1, spec §7.12).
- **Garder une langue de version dans la base** : la provenance du moteur la donne déjà (P7) ; deux sources finiraient par diverger.
