# 0092 — L'onde de la séance : mesurée sur le son d'écoute, gardée après la purge

Statut : Acceptée (2026-11-19, choix de l'utilisateur : « Oui, fais-le » pour une onde mesurée, « On la garde » après la purge). Remplace la section « L'onde » de l'ADR 0090 (l'onde tirée des temps des répliques, « en attendant le Service ») ; précise l'ADR 0029 (l'audio n'est plus le seul contenu tiré du son : son onde survit à la purge).

## Contexte
« Qui parle ? » (0090) dessine l'onde de la séance. Faute de données, elle était faite des temps des répliques : une forme, pas une mesure. Le son d'écoute est déjà sur le disque (0037, 0074) et ffmpeg le décode vite (2 h 20 en 1,5 s, 100 Mo de mémoire). Une fois l'audio purgé (0029), plus rien ne permet de la refaire.

## Décision
- **Mesurée, jamais déduite** (P2) : ffmpeg décode le son d'écoute (`lossless.heard_path`) en mono à 48 kHz ; chaque tranche de 50 ms donne sa crête en dBFS, −120 dB au moins pour le silence.
- **Gardée hors de `sources/`**, dans `sessions/<id>/onde.json`, avec la version du fichier mesuré (`heard_version` : nom, date, taille). Écrite d'un bloc, jamais à moitié.
- **Refaite quand le son d'écoute change** (mix d'écoute fait, piste mise en MP4), en tâche de fond, à la demande de la page. Une mesure dont le son a changé entre-temps n'est pas écrite.
- **Mesurée avant la purge** si elle ne l'est pas encore ou plus, puis gardée : la purge ne l'efface pas. La suppression de la séance l'emporte avec elle.
- `GET /api/seances/{id}/onde?barres=N` donne N niveaux, chacun la plus haute crête de ses tranches (jamais plus de niveaux que de tranches). Précisé pour 0094 : `debut` et `fin` (secondes, facultatifs) ne donnent que les tranches entières que touche ce passage (jusqu'à 50 ms de plus de chaque côté, coupé à la fin du son) ; `fin` ≤ `debut` ou un passage hors du son donnent 422. 409 pendant la mesure ou l'enregistrement : la page garde alors son dessin des répliques (depuis 0094, elle ne dessine rien en attendant). 404 avec un message quand il n'y a rien à mesurer, quand l'audio a été supprimé sans onde, ou quand la mesure a échoué (le détail dans le journal ; pas de nouvel essai avant que le son change).

## Conséquences
- Après la purge, la page montre toujours l'onde de la séance, avec le texte ; elle ne joue plus rien (0029).
- Une mesure qui échoue juste avant la purge ne la retient pas : l'onde manque alors, et la page dessine celle des répliques.
- La suppression d'une séance attend la fin d'une mesure en cours (« réessayez dans un instant »).
- Taille : environ 1 Mo de JSON pour 2 h 20.

## Alternatives écartées
- L'onde tirée des répliques, à demeure : une forme qui ne dit ni les silences ni les éclats.
- Une mesure à la volée à chaque demande, sans fichier : impossible après la purge.
- La ranger dans `sources/` avec le son : la purge l'emporterait.
