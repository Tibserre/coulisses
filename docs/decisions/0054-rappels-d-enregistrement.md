# 0054 — Rappeler qu'un enregistrement tourne : barre des menus, silence long, durée, jamais d'arrêt automatique

Statut : Acceptée (2026-10-21). Choix de l'utilisateur, pour le parcours « je lance l'enregistrement en réunion… jusqu'à l'arrêt » (étape 13c) : notification après un silence long, sans arrêt automatique ; rond toujours visible dans la barre des menus ; rappel après une durée réglable. Choix de mise en œuvre, à ajuster à l'usage : le seuil de voix, les valeurs par défaut (5 min, 1 h 30), l'ordre des alertes, rien pendant une pause. Partie app du Dock : conversation Distribution (branche `feat/barre-des-menus`). Le numéro 0053 est laissé au moteur (transcription en direct, empreintes vocales).

## Contexte
L'utilisateur oublie souvent d'arrêter l'enregistrement après une réunion. Rien ne le lui rappelle : la page peut être fermée (l'enregistrement continue, spec §7.2), et les notifications du service (`osascript`, purges : ADR 0029) n'ont pas d'actions. Principes : P8 (rien ne s'arrête ni ne se perd sans décision visible), P1 (aucun réseau).

## Décision
- **Le service décide des alertes, l'app du Dock les montre** (la page d'enregistrement pourra les reprendre). `GET /api/enregistrement` donne `silent_for_s` (temps enregistré depuis la dernière voix, pauses exclues) et `alert` : rien, ou `{ key, title, text }`, en français, prêt à afficher. `key` reste la même pour une même alerte : `error-<seconde>`, `silence-<seconde où le silence a commencé>-<multiple de durée atteint>`, `duration-<secondes atteintes>`.
- **Erreur du micro principal** (débranché, fichier plein) : elle passe avant tout, car elle fige le temps de l'enregistrement, et plus rien d'autre ne préviendrait.
- **Silence long** : personne n'est entendu, au micro principal comme dans le son de l'ordinateur, depuis 5 min (par défaut). Une voix, c'est un son d'au moins −45 dBFS (RMS, `SPEECH_DB`) pendant au moins 0,5 s (`SPEECH_MIN_S`) : une toux, une porte ou le son d'une notification ne l'interrompent pas. Une alerte par épisode de silence, reposée à chaque multiple de la durée : une notification manquée n'arrête pas les rappels.
- **Durée** : un rappel à chaque multiple de la durée choisie (1 h 30 par défaut).
- Le silence passe avant la durée. Rien pendant une pause.
- **Jamais d'arrêt automatique** : une alerte ne fait que demander (« Arrêter » ou « Continuer »).
- Les deux seuils se règlent dans Réglages, onglet Séances, « Pendant un enregistrement », par « − » et « + » sur des valeurs usuelles (silence : 2 à 30 min ; durée : 30 min à 4 h). Ils sont gardés dans `app_setting` (`rappels_enregistrement`), sans changer le schéma. Un enregistrement en cours suit tout de suite un nouveau réglage.
- **App du Dock** (Distribution) :
  - elle interroge `GET /api/enregistrement` (2 s au repos, 1 s pendant un enregistrement) ;
  - la barre des menus montre « ● 12:34 », ou « ◯ 12:34 en pause », avec Pause/Reprendre, Arrêter et Ouvrir Coulisses ;
  - chaque alerte devient une notification de macOS, une fois par (séance, `key`), avec les actions Arrêter et Continuer ;
  - l'alerte en cours est aussi en tête du menu de la barre des menus, grisée : on la voit même si les notifications sont refusées ;
  - « Arrêter » d'une notification n'agit que si la séance de l'alerte enregistre encore (sinon « Cet enregistrement est déjà terminé. », rien n'est arrêté) ; les notifications d'une séance finie sont retirées ;
  - une réponse illisible du service n'efface jamais la barre des menus (le journal le dit) ; sans réponse depuis plus de 8 s pendant un enregistrement, elle dit « Coulisses ne répond pas », sans rien arrêter ; l'échec d'une action se dit en français ;
  - dans « Coulisses (dév) », la barre des menus commence par « dév » ;
  - l'autorisation est demandée au premier enregistrement. Si elle est refusée, la barre des menus reste, et la page le dit. L'autorisation est relue à chaque retour dans l'app. L'app donne `window.coulissesApp.notifications` : `allowed`, `denied`, ou `unknown` tant que macOS n'a rien demandé ; elle envoie l'évènement `coulisses:mises-a-jour` à chaque changement. Une autre valeur n'affiche rien.

## Conséquences
- Un silence dans une salle bruyante (au-dessus de −45 dBFS) n'est pas vu comme un silence : seul le rappel de durée alerte alors. À ajuster après usage, sans changer le contrat.
- Les alertes ne dépendent pas de la page : elles marchent fenêtre fermée.
- Glossaire : « Alerte d'enregistrement » (`recording_alert`), « Rappel d'enregistrement » (`reminders`).
- Des valeurs de rappel illisibles n'empêchent jamais d'enregistrer : les valeurs usuelles sont suivies, le journal le dit, et les Réglages l'affichent.

## Alternatives écartées
- Arrêt automatique après un long silence : écarté par l'utilisateur, qui veut garder la main.
- Fin d'appel détectée (le son de l'ordinateur se tait) : non retenue pour l'instant.
- Événement poussé du service vers l'app du Dock : une interrogation régulière marche aussi quand la page n'est pas chargée, et reste testable côté Python.
