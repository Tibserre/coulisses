# 0043 — Seule la page de Coulisses parle au service ; la fenêtre n'affiche que lui

Statut : Acceptée (2026-10-13, revue de sécurité avant la publication, corrections approuvées par l'utilisateur). Précise les ADR 0002 et 0034.

## Contexte
Le service n'écoute que sur 127.0.0.1 (ADR 0001). La revue de sécurité du 2026-10-13 a pourtant montré qu'une page web ouverte dans un navigateur pouvait l'atteindre, de deux façons :
- **en nommant un hôte à elle qui pointe vers 127.0.0.1** (DNS rebinding). Elle pouvait alors lire les transcriptions et l'audio, et même lancer un enregistrement ;
- **en envoyant, depuis son propre site, les requêtes qu'un navigateur laisse passer sans rien demander** (formulaire, envoi de fichier, POST sans corps). Elle pouvait alors mettre en pause ou arrêter un enregistrement en cours, importer un fichier ou déclencher un téléchargement de modèle.

La fenêtre de l'app du Dock affichait de plus toute adresse de 127.0.0.1, quel que soit le port, ainsi que `data:` et `blob:`. L'inspecteur web y était actif, et le lanceur transmettait au service les variables `DYLD_*` et `PYTHON*` dont il héritait.

## Décision
- **Le service** (`local_only.py`, appliqué à toutes les routes) :
  - refuse tout hôte autre que `127.0.0.1` ou `localhost` ;
  - refuse toute requête qui modifie quelque chose (autre que GET et HEAD) si elle vient d'une autre origine que sa propre page, ou d'un autre site d'après `Sec-Fetch-Site`. Une requête sans `Origin` (curl, le lanceur, les scripts) reste acceptée ;
  - ne sert jamais d'en-têtes CORS, ni la description de son API ;
  - envoie avec chaque réponse une politique de sécurité du contenu : rien que ses propres ressources, et ne pas être affiché dans le cadre d'un autre site.
- **La fenêtre** n'affiche que le service et les pages du lanceur. Toute autre adresse web s'ouvre dans le navigateur, et tout le reste est refusé. L'inspecteur web n'est actif que dans « Coulisses (dév) ». Le lanceur retire les variables `DYLD_*` et `PYTHON*` qu'il hérite avant de lancer le service, dans les deux modes.
- **Ce que le modèle de langage écrit** (titre, résumé, titres de chapitres ; pas la transcription ni ce que l'utilisateur tape) est neutralisé à l'export Markdown et à la copie, comme à l'affichage : une image, sous toutes ses formes, ne garde que sa description, un lien que son texte, et le HTML brut reste du texte (`<` suivi d'une lettre devient `&lt;`, ce qui se voit tel quel dans une copie collée en texte brut, cas rare accepté).
- **Un refus** est journalisé par le service avec son motif, et dit en français à l'interface.

## Conséquences
- Les tests parlent au service comme sa page (`local_client`, hôte 127.0.0.1). Une nouvelle route en écriture est protégée sans rien ajouter.
- Une future intégration qui voudrait appeler le service depuis une autre origine (un autre outil local, une extension) demandera un nouvel ADR.
- Le serveur de développement de l'interface (Vite) reste utilisable : il garde l'hôte du navigateur, et la page a la même origine que lui.
- Reste à décider plus tard par un ADR : signer avec le « hardened runtime » de macOS, qui empêcherait aussi l'injection d'une bibliothèque dans l'app elle-même (ADR 0040).

## Alternatives écartées
- **Un jeton secret demandé à chaque requête :** plus lourd (le lanceur doit le donner à la page), pour une protection que le contrôle de l'hôte et de l'origine donne déjà face à un site web.
- **Autoriser l'hôte de test `testserver` :** un réseau d'entreprise pourrait résoudre ce nom ; les tests se présentent plutôt comme 127.0.0.1.
