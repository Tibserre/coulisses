# 0024 — Les chapitres : détectés par le LLM local, placés sur une réplique, corrigés dans le journal

Statut : Acceptée (2026-10-06 : l'utilisateur retient la détection par le LLM, aucune migration du schéma, et le mot « chapitre » dans l'interface). Les résumés ne suivent plus la détection d'eux-mêmes : ils se lancent à la demande (ADR 0025).

## Contexte
La spec (§7.5) demande de découper la séance en phases (scène, discussion, autre), de les corriger en relecture, et de s'en servir à l'affichage et dans le transcript envoyé au modèle. L'ADR 0020 veut un découpage valable pour toute réunion. La méthode de détection était une question ouverte (M7). Un essai le 2026-10-06, sur une vraie séance de 1 h 32 avec `qwen3.6`, a donné 14 chapitres plausibles en un appel de 40 s.

## Décision
- **Méthode (M7) : le LLM local, en un appel**, par l'assemblage unique (P4). Le prompt est `prompting/textes/chapitres.md`, et la réponse est imposée en JSON (`format` d'Ollama) : pour chaque chapitre, l'heure de sa première réplique telle qu'écrite dans la transcription, son type (`scene`, `discussion`, `autre`) et un titre court. Une séance trop longue est découpée en parties, et les chapitres des parties sont mis bout à bout, sans appel de fusion.
- **Une coupure tombe toujours sur une réplique existante (P2).** Une heure qui n'est celle d'aucune réplique est ramenée sur la plus proche. Un chapitre dont l'heure est illisible, ou qui tombe sur la même réplique qu'un autre, est écarté. Le premier chapitre commence à la première réplique. Chaque ajustement est écrit dans la sortie de la détection et visible en mode développeur (P8).
- **Une détection est une exécution de l'application** (ADR 0018), dans `runs/segment_phases-…/`, avec le prompt mot pour mot, `output.json` et la provenance de l'ADR 0022. La détection active est celle de `active_run`, et elle ne vaut que pour l'exécution « qui a dit quoi » sur laquelle elle a été faite (`run_upstream`).
- **Les corrections vont dans le journal existant** (`edit`), avec deux nouvelles sortes :
  - `set_phase` : un chapitre commence à cette réplique, ou son type ou son titre change ;
  - `remove_phase` : la coupure disparaît, et les répliques rejoignent le chapitre précédent.

  Chaque coupure est repérée par le numéro de sa réplique. Les corrections se rejouent par-dessus la détection, si bien qu'une nouvelle détection ne les efface pas. Annuler et rétablir passent par le journal, comme pour le reste. **Aucune migration du schéma.**
- **Dans les résumés**, les chapitres apparaissent dans le transcript envoyé (`[mm:ss] ── Chapitre « titre » (jeu) ──`). Une séance trop longue y est découpée entre les chapitres quand ils tiennent dans la fenêtre. La provenance d'un résumé donne la détection lue (`phases_run_id`). Le résumé est périmé quand la détection ou une correction de chapitre change.
- **Dans l'interface, on dit « chapitre »** pour tous les espaces. Le type s'y lit « Jeu », « Discussion » ou « Autre », dans les trois poids de la direction artistique.
- La file détecte les chapitres juste après la chaîne, avant le titre et les résumés automatiques. Si la détection échoue, les résumés se font sans chapitres, et l'échec s'affiche à côté du transcript avec « Relancer ».

## Conséquences
- Il faut Ollama pour détecter. Sans lui, l'utilisateur peut quand même couper des chapitres à la main.
- La justesse se mesure aux corrections de l'utilisateur : coupures déplacées ou retirées, types changés. Si elles sont nombreuses, une méthode mixte (règles sur le rythme des tours, puis le LLM pour nommer) fera l'objet d'un nouvel ADR.
- Les marqueurs posés à la main (étape 6) devront primer sur la détection (spec §7.5). Ils seront donnés au modèle et appliqués après lui.
- Les heures sont recopiées par le modèle : un format d'heure qui change (`h:mm:ss` passé une heure) doit lui être décrit. L'essai du 2026-10-06 a montré qu'il réécrit sinon `1:03:05` en `103:05`.

## Alternatives écartées
- Des règles sur le rythme des échanges, seules : elles ne savent ni nommer un sujet de réunion ni distinguer une fiction d'une vraie discussion.
- Numéroter les répliques dans le transcript envoyé : cela change le format fixé par la spec (§7.9) pour un seul usage, alors que l'heure suffit une fois ramenée sur une réplique.
- Une table `phase` : elle figerait une forme que le journal porte déjà, et elle doublerait le mécanisme d'annulation.
