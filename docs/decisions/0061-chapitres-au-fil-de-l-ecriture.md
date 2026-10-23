# 0061 — Les chapitres au fil de leur écriture : un avancement et un aperçu, jamais gardés comme résultat

Statut : Acceptée (2026-10-23). L'utilisateur a choisi, le 2026-10-22, de voir les chapitres arriver au fur et à mesure, quitte à les voir évoluer avant qu'ils soient définitifs (`docs/produit/animation-du-traitement.md`, étape 6). Il a aussi décidé qu'un chapitre provisoire ne se modifie pas. La façon de le faire revient à la conversation Rédaction et modèles. Précise les ADR 0024, 0044 et 0045.

## Contexte
Après le traitement, la détection lit la séance par parties de 15 minutes (ADR 0044), puis vérifie le type de chaque chapitre (ADR 0045). Une séance de 1 h 30 représente six parties et une dizaine de vérifications, soit une à plusieurs minutes avec `qwen3.5:4b`. Les chapitres n'étaient enregistrés qu'à la fin, d'un bloc (`output.json`), et rien ne disait où en était la détection. L'interface doit savoir trois choses : où en est la détection, quels chapitres sont déjà trouvés, et ce qui peut encore changer. Les contraintes : P2 (un chapitre commence à une réplique qui existe), P7 (résultat et provenance inchangés), P5 (aucune correction perdue), et les marqueurs posés pendant la séance priment.

## Décision
- **La détection tient un avancement dans son dossier d'exécution** (`runs/segment_phases-…/phases-progress.json`, modèle `PhasesProgress` : un autre nom que le `progress.json` du moteur, qui a son propre contrat). Il est remplacé à chaque étape, écrit à part puis mis en place d'un seul geste, pour n'être jamais lu à moitié écrit :
  - avant la lecture : `reading`, partie 0 sur N ;
  - après chaque partie : `reading`, partie k sur N, avec l'heure de la dernière réplique lue (`read_until`) et les chapitres trouvés jusque-là ;
  - pendant la vérification : `checking`, k sur M, les types déjà vérifiés corrigés ;
  - à la fin : `done`, avec les chapitres tels qu'ils sont enregistrés.
- **Les chapitres provisoires sont faits comme les définitifs.** Les parties lues passent par la même réunion des parties et le même placement sur les répliques (`join_parts`, puis `snap`) que le résultat final. Un chapitre provisoire commence donc toujours à une réplique qui existe (P2). Une réponse encore illisible ne donne pas d'aperçu à cette étape : c'est dit dans l'avancement (`problem`), et la fin échoue dessus comme avant (P8).
- **L'interface les reçoit par la route qu'elle lit déjà.** Pendant la détection, `GET /api/seances/{id}/chapitres` ajoute deux champs :
  - `progress` : l'étape, partie k sur N, vérification k sur M, jusqu'où le modèle a lu ;
  - `provisional` : les chapitres jusque-là, construits par la vue corrigée comme les définitifs. Les marqueurs posés pendant la séance priment, et les corrections de l'utilisateur s'appliquent par-dessus. Ils ne sont montrés que sur la version de « qui a dit quoi » sur laquelle la détection a été lancée : si la version affichée a changé entre-temps, leurs répliques seraient d'autres (P2), et l'avancement le dit. Un avancement illisible est dit à part (`progress_problem`) : la détection continue, ce n'est pas un échec.

  Les deux champs sont vides avant la détection et une fois qu'elle est finie (`done`) : les chapitres sont alors les vrais, dans la transcription comme avant.
- **Ce qui peut encore changer**, tant que l'état n'est pas `done` :
  - le dernier chapitre peut se prolonger dans la partie suivante (sa fin connue est `read_until`) ;
  - chaque type peut changer à la vérification.

  Les coupures déjà placées ne changent plus : la réunion d'une partie avec la précédente est décidée au moment où la partie est lue, avant qu'elle soit montrée. Les titres ne changent pas non plus.
- **Rien de l'aperçu n'est gardé comme résultat.** Le résultat reste `output.json`, écrit une fois à la fin, avec la même provenance (P7). `phases-progress.json` reste dans le dossier de l'exécution comme trace de son déroulé, et n'est jamais relu comme chapitres. Rien n'entre en base.
- **Un chapitre provisoire ne se modifie pas** : c'est à l'interface de ne pas l'autoriser, conformément à la décision de l'utilisateur. Le service garde le journal des corrections tel quel : une correction faite sur les chapitres précédents s'applique aux provisoires comme aux définitifs (P5).

## Conséquences
- Aucun appel au modèle en plus, et aucun changement dans la qualité des chapitres : l'aperçu reprend ce que la détection calculait déjà, un peu plus tôt.
- Chaque lecture de `GET /chapitres` pendant la détection reconstruit la vue corrigée : le même coût que la relecture d'une séance, à la fréquence où l'interface interroge (toutes les 4 s pour l'aperçu de la transcription, ADR 0058).
- Les premiers chapitres apparaissent après la première partie, soit 15 minutes de séance lues : environ 10 à 30 s avec `qwen3.5:4b`. Une séance de moins de 15 minutes est lue en une fois, et ses chapitres arrivent d'un coup, avant la vérification.
- La vérification change un type sans déplacer de coupure : l'interface peut ne changer que la couleur.

## Alternatives écartées
- Garder les chapitres de chaque partie en base au fil de l'eau : cela mélange un aperçu et le résultat, et une correction pourrait s'appuyer sur un chapitre qui va bouger.
- Montrer chaque partie sans la réunir à la précédente, puis recoudre : un en-tête apparaîtrait puis disparaîtrait à chaque limite de partie. Réunir avant de montrer coûte la même chose et ne fait jamais apparaître de fausse coupure.
- Un flux poussé par le service (SSE, websocket) : la page interroge déjà le service régulièrement (ADR 0043, 0058), et un avancement relu suffit au rythme d'une partie toutes les 10 à 30 s.
