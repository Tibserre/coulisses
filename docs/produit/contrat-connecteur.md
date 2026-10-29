# Contrat du connecteur (ADR 0065)

Les routes du service pour le connecteur des assistants : celles que lit le pont `coulisses-mcp`, et celles des Réglages et des espaces. Le service applique toutes les règles (connecteur ouvert, espaces accessibles, noms masqués) ; le pont ne filtre rien lui-même. Les noms de champs JSON sont en anglais, comme le reste de l'API ; les messages, en français.

## 1. Ce que lit le pont : `/api/connecteur/…`

Toutes en **GET**. Le pont n'envoie rien d'autre ; aucune route de ce préfixe n'accepte autre chose (405). Les identifiants suivent le glossaire (`phases` pour les chapitres, `timed_notes` pour les annotations, `note` pour la note d'après séance, `generations` pour les résumés) ; les outils du pont les présentent à l'assistant avec les mots de l'interface.

### Erreurs communes
| Cas | Code | `detail` |
|---|---|---|
| Requête venue d'une page web (en-tête `Origin`, ou `Sec-Fetch-Site` autre que `none`) | 403 | « Le connecteur ne se lit que par son pont. » |
| Connecteur coupé (Réglages) | 403 | « Le connecteur de Coulisses est coupé. Ouvrez-le dans Coulisses › Réglages › Connecteur. » |
| Séance inconnue, ou dans un espace fermé au connecteur | 404 | « Séance introuvable, ou dans un espace fermé au connecteur. » (les deux cas ne se distinguent pas) |
| Résumé inconnu de cette séance | 404 | « Résumé introuvable. » |
| Transcript pas encore prêt ; résumé échoué ou pas fini | 409 | la raison, en français |
| La séance a changé pendant une lecture par morceaux | 409 | « La séance a changé depuis le début de la lecture (corrections, version, chapitres) : reprenez au début. » |
| Les résultats ont changé entre deux pages d'une recherche | 409 | « La recherche a changé depuis la page précédente : relancez-la. » |
| Paramètre invalide | 422 | la raison, en français |

Le connecteur coupé est vérifié **avant tout autre contrôle** (404, 409, 422, types des paramètres compris) : coupé, tout répond 403. Aucune réponse ne nomme un espace fermé, ne compte ses séances ni ne cite son texte ; `more` et `next` ne tiennent compte que des espaces accessibles.

### Masquage des noms
Dans un espace dont l'option **Transmettre les noms** est fermée, chaque nom connu de l'espace devient « Personne A », « Personne B »… : présents, voix nommées, personnes de l'espace (membres et invités, archivés compris), noms propres de son glossaire et leurs variantes. Une lettre par personne (ou par terme), la même dans toute la séance ; l'ordre : première apparition dans le transcript, puis les autres dans leur ordre de création (jamais l'ordre alphabétique, qui dirait quelque chose des noms). Le masquage vaut **partout**, dans tout texte rendu : titre, nom de l'espace et du projet, présents, voix, chapitres, annotations, note, résumés, transcript, extraits de recherche. Il est fait au mieux (mots entiers, accents et casse ignorés) : un surnom, un diminutif ou une faute de transcription passe. Chaque réponse qui porte du texte d'une séance dit `names_shared` (vrai : rien n'est masqué).

### Provenance
Le transcript d'une séance porte la provenance de sa version affichée :
```json
{"engine_version": "1.13.2", "profile": "chaine-retenue", "models": {"transcribe": "…", "align": "…", "diarize": "…"}, "processed_at": "2026-10-12T19:31:10Z", "duration_s": 534.2, "corrections": 12}
```
Telle que la donne le moteur (`read_provenance`) : version, profil, modèles par étape, date de fin, durée totale des étapes ; `corrections` : le nombre de corrections de l'utilisateur appliquées. Un résumé porte la sienne (modèle de rédaction, date, version du transcript résumé, version du moteur).

### `GET /api/connecteur/seances` — outil `lister_seances`
Paramètres : `espace` (son nom tel que l'assistant le voit, masqué compris ; facultatif), `depuis`, `jusqu_a` (dates `AAAA-MM-JJ`, facultatives, sur la date d'enregistrement), `limite` (1 à 100, 30 par défaut), `apres` (le `next` d'une réponse précédente).
```json
{
  "sessions": [
    {
      "id": "20261012-201500-a1b2",
      "title": "Répétition du 12 octobre",
      "recorded_at": "2026-10-12T18:15:00Z",
      "duration_s": 5412.0,
      "space": "Troupe",
      "project": "Spectacle de juin",
      "names_shared": false,
      "transcript_ready": true,
      "generations": [{"id": 41, "action": "Résumé Impro", "created_at": "2026-10-12T19:40:02Z"}]
    }
  ],
  "next": "2026-10-05T18:10:00Z|20261005-201000-c3d4"
}
```
Du plus récent au plus ancien, seulement les espaces accessibles ; `espace` qui désigne un espace fermé ou inconnu donne une liste vide, sans le distinguer. `next` : opaque, à passer en `apres` pour la suite (les séances d'avant la dernière rendue, par date puis id : une séance supprimée n'interrompt pas la lecture et aucune n'est rendue deux fois ; une séance dont la date est corrigée pendant la lecture peut changer de place) ; `null` s'il n'y a plus rien. `title` : `null` pour une séance sans titre ; `project` : `null` hors projet. `generations` : la version affichée de chaque résumé ; un résumé échoué, pas fini ou illisible répond 409 à sa lecture, avec la raison.

### `GET /api/connecteur/recherche` — outil `chercher`
Paramètres : `q` (1 à 200 caractères), `espace`, `depuis`, `jusqu_a` (comme pour la liste), `limite` (1 à 30 séances, 10 par défaut), `apres` (le `next` d'une réponse précédente, avec les mêmes `q` et filtres). La recherche plein texte de Coulisses (§7.11), dans les seuls espaces accessibles, sur le texte **tel que l'assistant le verrait** : un nom masqué ne trouve rien dans cet espace, et les extraits sont masqués.
```json
{
  "query": "échauffement",
  "sessions": [
    {
      "id": "20261012-201500-a1b2",
      "title": "Répétition du 12 octobre",
      "recorded_at": "2026-10-12T18:15:00Z",
      "space": "Troupe",
      "names_shared": false,
      "hits": [
        {"kind": "turn", "ref": "57", "at_s": 312.4, "excerpt": "… on reprend l'«échauffement» avec Personne B …"}
      ],
      "more_hits": true
    }
  ],
  "next": "10.7c1e93a0",
  "problems": []
}
```
Les séances, de la plus pertinente à la moins pertinente ; `next` : opaque, à passer en `apres` pour les séances suivantes, `null` s'il n'y en a plus ; il fige le classement de la première page : si les résultats ont changé depuis (séance supprimée, corrigée, espace fermé), 409 « relancez-la », jamais une séance sautée ou rendue deux fois en silence. Dans une séance, 5 passages au plus ; `more_hits` : il y en a d'autres, à lire par `lire_transcript`. `kind` : `title`, `turn` (`ref` : l'indice de la réplique), `timed_note` (`ref` : l'id de l'annotation), `note` (la note d'après séance, `ref` vide), `generation` (`ref` : l'id du résumé). Les mots trouvés sont entre « et ». `problems` : les séances des espaces accessibles qui n'ont pas pu être lues pour la recherche (fichiers illisibles), dites, titres masqués comme le reste. `at_s` : le temps mesuré de la réplique ou de l'annotation (P2), `null` pour un titre, une note, un résumé ou une réplique sans temps mesuré.

### `GET /api/connecteur/seances/{id}` — outil `lire_seance`
```json
{
  "id": "20261012-201500-a1b2",
  "title": "Répétition du 12 octobre",
  "recorded_at": "2026-10-12T18:15:00Z",
  "duration_s": 5412.0,
  "space": "Troupe",
  "project": "Spectacle de juin",
  "names_shared": false,
  "attendees": ["Personne A", "Personne B", "Personne C"],
  "unnamed_attendees": 1,
  "speakers": [{"name": "Personne A", "seconds": 1820.5, "turns": 212}],
  "phases": [{"number": 1, "title": "Échauffement", "start_s": 0.0, "end_s": 610.2, "first_turn": 0, "last_turn": 48}],
  "timed_notes": [{"id": 3, "at_s": 1204.0, "text": "Revoir l'entrée de Personne C"}],
  "note": "…",
  "transcript": {"ready": true, "turns": 734, "words": 18245},
  "generations": [{"id": 41, "action": "Résumé Impro", "created_at": "2026-10-12T19:40:02Z"}],
  "provenance": {"engine_version": "1.13.2", "profile": "chaine-retenue", "models": {"…": "…"}, "processed_at": "…", "duration_s": 534.2, "corrections": 12}
}
```
`speakers` : les voix de la version affichée, nommées ou non (« Voix 3 »), avec leur nombre de répliques et leur temps de parole, somme des seules durées mesurées (P2). `phases` : vide si les chapitres ne sont pas faits. `timed_notes` : les annotations, `at_s` mesuré (P2) ; `note` : la note d'après séance, ou `null`. `provenance` : `null` si la séance n'est pas traitée.

### `GET /api/connecteur/seances/{id}/transcript` — outil `lire_transcript`
Le transcript corrigé (version affichée, corrections appliquées), par morceaux. Paramètres :
- `chapitre` (facultatif) : un numéro de chapitre (de 1) ; la lecture reste dans ce chapitre ;
- `depuis` (indice de réplique ; par défaut, le début de la séance ou du chapitre) et `nombre` (1 à 500, 200 par défaut) ;
- `vue` : la `view` du morceau précédent ; **obligatoire** dès que `depuis` dépasse le début de la séance ou du chapitre (sinon 422 « Passez la `view` du morceau précédent en `vue`. »).
```json
{
  "session_id": "20261012-201500-a1b2",
  "names_shared": false,
  "phase": null,
  "view": "r-20261012-a9f3.e12.p7",
  "turns": [
    {"index": 0, "speaker": "Personne A", "start_s": 1.2, "end_s": 6.8, "text": "Bon, on commence ?"}
  ],
  "total_turns": 734,
  "next": 200,
  "provenance": {"engine_version": "1.13.2", "profile": "chaine-retenue", "models": {"…": "…"}, "processed_at": "…", "duration_s": 534.2, "corrections": 12}
}
```
`next` : l'indice à passer en `depuis` (avec `vue`) pour la suite ; `null` s'il n'y a plus rien, dans la séance ou dans le chapitre demandé. Un morceau s'arrête entre deux répliques et ne dépasse jamais `nombre` : un long chapitre se lit en plusieurs. `view` désigne ce qui est lu (version affichée, corrections, chapitres) : si `vue` est donnée et ne correspond plus, 409 (« reprenez au début »), jamais une réplique sautée ou lue deux fois en silence. `phase` : le chapitre lu (`number`, `title`), ou `null`. `start_s` et `end_s` sont mesurés ou `null` (P2). `speaker` : `null` pour une réplique sans voix. Chapitre inconnu : 422.

### `GET /api/connecteur/seances/{id}/resumes/{resume}` — outil `lire_resume`
La version affichée d'un résumé (en Markdown, masqué si besoin), avec sa provenance.
```json
{
  "session_id": "20261012-201500-a1b2",
  "id": 41,
  "action": "Résumé Impro",
  "names_shared": false,
  "markdown": "## Ce qui a marché\n…",
  "provenance": {"model": "…", "created_at": "2026-10-12T19:40:02Z", "transcript_version": "…", "engine_version": "1.13.2"}
}
```
Un résumé dont la rédaction a échoué ou n'est pas finie : 409, avec la raison.

## 2. Réglages : `/api/reglages/connecteur`

Lus par la page de Coulisses, pas par le pont ; ils répondent que le connecteur soit ouvert ou coupé.

### `GET /api/reglages/connecteur`, `PUT /api/reglages/connecteur`
`PUT` prend `{"open": true}` ou `{"open": false}` ; les deux répondent :
```json
{
  "open": false,
  "launcher": "/Users/…/Coulisses/Connecteur/coulisses-mcp",
  "launcher_ready": true,
  "claude_code_command": "claude mcp add coulisses -- /Users/…/Coulisses/Connecteur/coulisses-mcp",
  "mcpb": "/Users/…/Coulisses/Connecteur/Coulisses.mcpb",
  "spaces": [{"id": 1, "name": "Troupe", "connector_access": true, "connector_names": false}]
}
```
Coupé par défaut (réglage `connector_open` de `app_setting`). `launcher` : le lanceur fixe (`coulisses-mcp`, ou `coulisses-mcp-dev` pour Coulisses (dév)), écrit par l'app du Dock ; `launcher_ready` : il existe et s'exécute. `mcpb` : l'extension pour Claude Desktop, `null` tant qu'elle n'existe pas. `spaces` : les espaces non archivés et leurs deux options, pour un résumé dans l'onglet. Le nom du serveur est `coulisses` (`coulisses-dev` pour Coulisses (dév)).

### `GET /api/reglages/connecteur/journal`
Paramètres : `limite` (1 à 200, 50 par défaut), `avant` (un `id` : les entrées plus anciennes).
```json
{
  "entries": [
    {"id": 812, "at": "2026-10-29T14:02:11Z", "tool": "lire_transcript", "session_id": "20261012-201500-a1b2", "session_title": "Répétition du 12 octobre", "session_deleted": false, "names_shared": false}
  ],
  "next": 790
}
```
Du plus récent au plus ancien, jamais purgé. Une entrée par lecture : `tool` vaut `chercher`, `lister_seances`, `lire_seance`, `lire_resume` ou `lire_transcript`. Une recherche ou une liste note une entrée par séance rendue, ou une seule entrée sans séance si elle n'en rend aucune. `names_shared` : `null` pour une entrée sans séance (rien n'a été transmis). `session_title` : le titre actuel, vrai (c'est l'utilisateur qui lit) ; `null` pour une séance supprimée depuis ou sans titre (`session_deleted` le dit). Le texte de la recherche n'est pas noté. Seules les réponses 200 sont notées : une lecture refusée (403, 404, 409, 422) n'a rien transmis.

## 3. Les deux options d'un espace

`Space` (`GET /api/espaces`, …) gagne `connector_access` et `connector_names` (faux par défaut). `PATCH /api/espaces/{id}` les accepte, comme les autres champs : `{"connector_access": true}`, `{"connector_names": true}`. Fermer l'accès vaut aussitôt pour la lecture suivante.

## 4. Le pont et l'app du Dock

- Le pont lit `GET /api/etat` pour savoir si le service répond. S'il ne répond pas, il ouvre l'app par son identifiant, en arrière-plan : `open -g -b local.coulisses.app --args --connecteur` (Coulisses (dév) : `local.coulisses.app.dev`, port 8766). L'app ouverte avec `--connecteur` n'ouvre aucune fenêtre (pas même celle des gestes demandés au lancement, ADR 0049). Le pont attend le service 60 s au plus, puis dit en français qu'il n'a pas pu l'ouvrir.
- Si, en cours de route, le service répond avec un autre `app_build` que celui du premier appel (une mise à jour par Sparkle), ou que l'app du pont a disparu, le pont s'arrête (code de sortie 0) : le client le relance.
