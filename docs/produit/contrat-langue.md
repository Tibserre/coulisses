# Contrat de l'API : la langue de transcription

> Ce que le service expose à l'interface pour la langue d'un espace et d'une séance (ADR 0072). Fixé avant le code : Interface peut construire d'après lui. Tout changement passe par ce document, dans le même commit que le code.

Les codes de langue sont ceux du moteur (ISO 639-1 : `fr`, `en`, `de`…). L'application n'en grave aucun, sauf « fr », la langue par défaut (P6). Les noms affichés viennent du moteur, déjà en français (`label`).

## Les langues : `GET /api/langues`

Les langues que la chaîne transcrit, le français d'abord, puis les autres dans l'ordre du moteur. Aucun réseau. La lecture vérifie les modèles sur le disque (moins d'une seconde).

```json
[
  {
    "language": "en",
    "label": "Anglais",
    "installed": false,
    "missing_models": ["wav2vec2-ctc-english"],
    "download_bytes": 1260000000,
    "models": ["qwen3-asr-1.7b-8bit", "wav2vec2-ctc-english"],
    "own_models": ["wav2vec2-ctc-english"],
    "downloads": [ { "kind": "model", "name": "wav2vec2-ctc-english", "state": "running", "done_bytes": 520000000, "total_bytes": 1260000000 } ],
    "used_by": {
      "spaces": [ { "id": 3, "name": "Réunions", "archived": false } ],
      "waiting_sessions": [ { "id": "20261029-101500-ab12", "title": null, "recorded_at": "2026-10-29T09:15:00Z" } ]
    }
  }
]
```

- Une langue que la chaîne ne transcrit ou n'aligne pas (`transcribed` ou `aligned` faux pour le moteur) n'est pas proposée : elle est traitée comme inconnue.
- `installed` : rien ne manque pour traiter une séance dans cette langue.
- `missing_models` et `download_bytes` : ce qu'il faut télécharger, et sa taille.
- `models` : tous les modèles dont la langue a besoin.
- `own_models` : ceux qui ne servent qu'à elle. Ce sont eux qu'on supprime pour « Supprimer » une langue ; le modèle de transcription, commun à toutes, n'y est jamais. Un modèle partagé par quelques langues, sans l'être par toutes, n'est le propre d'aucune ; sa suppression est refusée tant que l'une d'elles sert.
- `downloads` : les téléchargements de ses modèles, en cours ou juste finis, sous la forme de `GET /api/moteur/telechargements` (`ModelAction`, champs complets).
- `used_by` : les espaces qui ont cette langue par défaut (archivés compris) et les séances dont le traitement attend dans cette langue. Tant que l'un des deux n'est pas vide, la suppression de ses `own_models` est refusée.

**Télécharger une langue** : `POST /api/moteur/modeles/{cle}/telecharger` pour chaque modèle de `missing_models`, la route qui existe (ADR 0036), avec son avancement, son arrêt et sa reprise. Aucune route ne télécharge plusieurs modèles d'un coup.

**Supprimer une langue** : `DELETE /api/moteur/modeles/{cle}` pour chaque modèle de `own_models`. Si la langue sert encore, la réponse est **409**, avec un `detail` en français qui dit où, par exemple : « L'anglais sert encore : c'est la langue de l'espace « Réunions », et une séance attend ce modèle (« Répétition du 29 octobre »). Changez-les d'abord. » Rien n'est supprimé.

## Une langue inconnue
Tout code que le moteur ne propose pas est refusé avant d'être enregistré : **422**, `detail` : « Cette langue n'est pas prise en charge. Langues possibles : français, allemand, anglais, espagnol, italien, portugais. »

Un modèle qui manque ne fait jamais échouer une demande : la langue est enregistrée, et un traitement dans cette langue attend son modèle (voir plus bas).

## L'espace

- `Space` (réponses de `GET /api/espaces`, `POST`, `PATCH`) gagne **`language`** : le code de sa langue par défaut, « fr » pour les espaces existants.
- `POST /api/espaces` accepte `language` (par défaut « fr »).
- `PATCH /api/espaces/{id}` accepte `language`. Changer la langue d'un espace ne touche aucune de ses séances : elle ne sert qu'aux suivantes.
- Une langue retirée du moteur peut rester celle d'un espace. Elle n'est plus dans `GET /api/langues` : c'est ainsi que l'interface sait la dire « n'est plus prise en charge ».

## La séance

`Session` (liste, détail, réponses des actions sur une séance) gagne :
- **`language`** : la langue de la séance. Avant le premier traitement, celle choisie. Ensuite, celle de la version affichée : elle change quand une version dans une autre langue devient la version affichée, jamais avant.
- **`language_editable`** : `true` tant que la langue peut se changer par `PUT /api/seances/{id}/langue` (voir ci-dessous) ; `false` ensuite, où l'on passe par « Refaire le texte ».
- **`processing_waits_for`** : `null`, ou ce qu'attend son traitement en file :

```json
{
  "reason": "model_missing",
  "language": "en",
  "label": "Anglais",
  "missing_models": ["wav2vec2-ctc-english"],
  "download_bytes": 1260000000
}
```

  - `reason` : `model_missing`, un modèle de cette langue n'est pas sur ce Mac ; ou `language_unsupported`, le moteur ne prend plus cette langue (`label` à `null`, `missing_models` vide, `download_bytes` à 0). Dans ce cas, seule une autre langue débloque la séance.
  - L'avancement d'un téléchargement se lit dans `GET /api/langues` (`downloads`) ou `GET /api/moteur/telechargements`.
  - `job_state` reste `queued` : la séance n'est ni en échec ni en cours. Les autres séances passent devant elle.
  - Elle repart d'elle-même quand le dernier modèle manquant est installé (fin d'un téléchargement, ou au démarrage de l'app), ou quand sa langue change pour une langue installée.

### Choisir la langue d'une séance : `PUT /api/seances/{id}/langue`

Corps : `{ "langue": "en" }`. Réponse : la `Session`.

Possible tant que le texte de la séance n'est pas fait (`language_editable`) :
- pendant l'enregistrement ;
- tant que son premier traitement est en file : l'attente de « Qui était là ? » (ADR 0069), l'attente d'un modèle, ou simplement derrière d'autres séances. Le compte à rebours de « Qui était là ? » n'est pas relancé ;
- après un premier traitement arrêté ou en échec avant qu'aucune transcription n'ait réussi.

Sinon **409**, `detail` : « Le texte de cette séance est déjà fait. Pour une autre langue : « Refaire le texte ». » Une langue inconnue : 422.

Si la séance attendait un modèle et que la nouvelle langue est installée, elle repart. « Traiter en français » est ce même appel avec `fr`.

### La séance créée dans une langue
- `POST /api/seances` (l'import) accepte le champ de formulaire `langue`. Par défaut, la langue de l'espace où la séance est créée.
- `POST /api/enregistrement` accepte `langue`, avec la même valeur par défaut. Pendant l'enregistrement, elle se change par `PUT /api/seances/{id}/langue`. Le traitement part à l'arrêt dans la langue du moment.
- Déplacer une séance dans un autre espace (`PUT /api/seances/{id}/espace`) ne change pas sa langue.

### Refaire le texte dans une autre langue : `POST /api/seances/{id}/relancer`

`RerunRequest` gagne **`langue`** (facultatif) :
- `etape: "transcribe"` (« Refaire le texte ») ou `"all"` (« Tout refaire ») : la langue de la nouvelle version. Par défaut, celle de la version affichée.
- `etape: "diarize"` : refusé avec une langue différente de celle de la version affichée (422) ; refaire les voix garde le texte, donc sa langue.

La langue de la séance ne change que lorsque la nouvelle version devient la version affichée. Si un modèle manque, la relance attend comme un premier traitement (`processing_waits_for`). Une relance arrêtée ou en échec ne change rien.

Les corrections suivent la règle du report (ADR 0028) : les noms des voix suivent ; une correction de texte qui ne se reporte pas est comptée dans `GET /api/seances/{id}/versions` (`not_carried`), comme aujourd'hui.

### Les versions : `GET /api/seances/{id}/versions`

Chaque `Version` gagne **`language`** : la langue de sa transcription, lue dans la provenance du moteur (P7). Une transcription d'un moteur antérieur à la v1.14.0 est en français. `null` si la provenance ne le dit pas alors qu'elle le devrait : l'interface dit « langue inconnue », jamais « français ».

Afficher une autre version (`POST …/versions/{run_id}/afficher`) donne à la séance la langue de cette version. Si la provenance de cette version ne dit pas sa langue (`language` à `null`), la séance garde la sienne : `Session.language` peut alors différer de la version affichée, et c'est `Version.language` qui fait foi.

## Un échec sur la langue
Si le moteur refuse quand même (`model_missing` après la vérification, `language_unsupported`), le traitement échoue avec un `job_error` en français qui dit quoi télécharger, ou quelles langues sont possibles. « Reprendre » vérifie d'abord les modèles : il remet la tâche en attente du modèle plutôt que de la relancer pour échouer de la même façon.
