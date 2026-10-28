# 0059 — Le flou, pour mettre une information au premier plan

Statut : Acceptée (2026-10-21, choix de l'utilisateur : « un flou peut vraiment donner du cachet s'il est bien maîtrisé, autorise pour mettre en valeur des infos en avant »). Précise l'ADR 0017 et la direction artistique, qui excluaient tout « effet de matière » et le verre dépoli.

## Contexte
La direction artistique (0017) interdit grain, verre dépoli, halo et dégradé de fond, après l'écart de la finition « Lumière », jugée trop chargée et trop « IA ». Pour la pause de l'enregistrement, l'utilisateur veut un état visible de loin par les personnes présentes, qui les mette en confiance : tout est coupé, et ce qui est derrière n'est plus actif. Il juge qu'un flou bien maîtrisé donne du cachet quand il sert à mettre en avant.

## Décision
- **Permis** : le flou du contenu qui est derrière une information mise au premier plan, et seulement là. Il dit que ce qui est dessous n'est plus actif : la pause, l'arrêt en cours, et plus tard un état de même nature.
- **Toujours interdits** : le verre dépoli décoratif sur des surfaces ordinaires (colonne, cartes, barres, menus), le halo, le grain, le dégradé de fond.
- **Mesure** : un flou modéré (8 px au plus), sous un voile neutre de la couleur du fond de page à environ 70 %. Le texte au premier plan reste dans les couleurs du thème, sans ombre portée. Entrée et sortie en 400 ms, sur la courbe de la direction artistique.
- **Repli** : si macOS réduit la transparence (`prefers-reduced-transparency`), le voile devient opaque. Si les animations sont réduites, il apparaît sans fondu.

## Conséquences
- La direction artistique dit l'exception, à « Forme, espace, matière » et à « Ce qu'on s'interdit ».
- Tout nouvel usage du flou doit mettre une information au premier plan. Sinon, il passe par un nouvel ADR.

## Alternatives écartées
- Un voile opaque seul : conforme, mais l'utilisateur préfère garder la séance visible, estompée.
- Le flou libre, comme effet de style : c'est ce qui avait fait écarter la finition « Lumière ».
