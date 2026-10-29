# 0069 — Importer en un geste : plus de fenêtre « Nouvelle note »

Statut : Acceptée (2026-10-29, par l'utilisateur : « glisser un fichier sur la fenêtre » et « Importer un fichier… » dans le menu d'un espace, puis, la fenêtre d'import revue à l'essai : « c'est vraiment pas bon celle-là, elle jure avec le reste »). Précise l'ADR 0056, qui gardait l'import et le choix détaillé dans la fenêtre « Nouvelle note ».

## Contexte
Depuis l'ADR 0056, enregistrer se fait en un geste. Importer passait encore par une grande fenêtre (comment, espace, projet, présents, invités, non-nommés, lieu, micros, puis le fichier), seulement atteinte depuis l'accueil. L'utilisateur ne la trouvait pas, et elle jure avec le reste. Les présents se cochent déjà sur la séance, après coup (spec §7.1) ; les micros s'ajoutent pendant l'enregistrement (ADR 0067). P3 : les présents ne sont qu'un minimum. P8 : un refus se dit.

## Décision
- **Un geste** : glisser un fichier audio ou vidéo n'importe où sur la fenêtre, « Importer un fichier… » dans le menu « … » d'un espace (« Importer un fichier dans ce projet… » pour un projet), ⌘O, ou « ou importer un fichier » sur l'accueil. Les trois derniers ouvrent la fenêtre du Finder ; le fichier choisi ou déposé est envoyé aussitôt.
- **Où il va** : là où il a été demandé (l'espace et le projet du menu, sinon l'espace sélectionné, comme pour enregistrer, ADR 0056). Un espace archivé n'en reçoit pas : il va alors là où l'accueil enregistrerait, sans projet. Pendant qu'on glisse le fichier, la fenêtre dit où il ira.
- **Pendant l'envoi** : une barre « Envoi de « fichier » » en haut de la page ; puis la séance s'ouvre, sur l'écran de traitement. L'espace, le projet et les présents s'y changent dans le fil au-dessus du titre.
- **Refusés, et dit** : plusieurs fichiers déposés ensemble, un fichier qui n'est ni audio ni vidéo, un second envoi pendant le premier. Rien n'est envoyé.
- **La fenêtre « Nouvelle note » est supprimée**, et avec elle l'enregistrement « en choisissant tout d'avance » (lieu, micros) : le geste démarre en hybride, le son de l'ordinateur se coupe et les micros s'ajoutent sur l'écran d'enregistrement (ADR 0056, 0067).

## Conséquences
- Un import démarre sans présents : le moteur cherche seul le nombre de voix. Cochés avant que le premier traitement commence, les présents en deviennent le minimum ; après, la séparation des voix a commencé avec le traitement, et rien ne change (spec §7.1, « Présents » ; fait par le Service, `feat/presents-avant-diarisation`, 2026-10-29). La liste des présents le dit alors, avec « Refaire les voix… », qui ouvre « Refaire le traitement » sur « Les voix ».
- Le micro principal ne se choisit plus dans Coulisses : c'est le micro par défaut de macOS au départ. Le choisir sur l'écran d'enregistrement serait une suite à décider.
- La spec (§7.2, §7.11) est mise à jour.

## Alternatives écartées
- Garder la fenêtre et y mener les nouveaux chemins (fait d'abord, puis écarté à l'essai) : un geste de plus, et une fenêtre qui ne ressemble pas au reste.
- Une petite fenêtre « espace, projet, présents » avant l'envoi : ce sont des choix qui se font déjà sur la séance.
