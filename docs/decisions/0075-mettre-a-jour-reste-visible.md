# 0075 — « Mettre à jour » reste dans la colonne tant qu'une version attend

Statut : Acceptée (2026-11-09, demande de l'utilisateur : « J'aimerai que le bouton en bas dans la sidebar, de mise à jour, reste visible tant qu'il y a une maj disponible », puis « Oui, transmets » à la proposition de l'Interface, relayée à Distribution). Remplace, dans l'ADR 0051, la règle « `ready` repasse à faux une fois la fenêtre de Sparkle vue ».

## Contexte
- L'ADR 0051 retire « Mettre à jour » de la colonne dès que la fenêtre de Sparkle est vue, quel que soit le choix : installer, ignorer ou « Plus tard ».
- Après « Plus tard », la version attend encore, mais plus rien ne le dit. Sparkle la rappelle seulement à sa prochaine recherche automatique.

## Décision
- L'app du Dock suit le choix fait dans la fenêtre de Sparkle (`updater(_:userDidMake:forUpdate:state:)`) :
  - **« Plus tard »** : `updates.ready` reste vrai (ou le devient, si la fenêtre s'était ouverte d'elle-même) ; « Mettre à jour » reste dans la colonne, et son clic rouvre la fenêtre de Sparkle sur cette version ;
  - **installer** ou **« Ignorer cette version »** : `ready` passe à faux ; le bouton disparaît.
- Une recherche qui ne trouve plus de nouvelle version (`updaterDidNotFindUpdate`) remet `ready` à faux. Une installation interrompue (`didAbortWithError` après « Installer ») le remet à vrai.
- Le reste de l'ADR 0051 ne change pas : la page montre le bouton tant que `ready` est vrai ; pendant un enregistrement, ni bouton ni point ; un clic pendant un traitement est refusé, en français. Le contrat de la page ne change pas.

## Conséquences
- `ready` ne survit pas à un redémarrage de l'app : après « Plus tard » puis une relance, le bouton revient à la prochaine recherche automatique de Sparkle, ou sur « Rechercher les mises à jour… ».
- Si la page retire son rappel (page du lanceur, page tombée), une version laissée pour plus tard ne rouvre pas d'elle-même la fenêtre de Sparkle : ce serait une recherche que l'utilisateur n'a pas demandée (0040). Elle a déjà été montrée, et le bouton revient au prochain montage de la page. Une version trouvée par la recherche automatique et jamais montrée ouvre toujours la fenêtre, comme avant (0051).
- Une installation choisie puis interrompue (téléchargement en échec ou annulé) laisse la version en attente : le bouton revient.

## Vérification
- App publiée, avec une version plus récente dans l'appcast : « Plus tard » laisse « Mettre à jour » dans la colonne ; son clic rouvre la fenêtre sur la même version.
- « Ignorer cette version » retire le bouton.
- Une installation retire le bouton (l'app relancée est à jour).
