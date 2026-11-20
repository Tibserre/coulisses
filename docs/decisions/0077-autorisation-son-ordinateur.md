# 0077 — Demander l'autorisation du son de l'ordinateur dès le début

Statut : Acceptée (2026-11-10, par l'utilisateur : « une alerte d'autorisation de son de l'ordinateur au début, voire à l'onboarding », relayé par Interface ; puis, entre les deux façons de savoir si c'est autorisé : « api privée, et si il y a une maj MACOS on fait un check de si ça a cassé ou non »). Précise 0032 et 0056.

## Contexte
- Le son de l'ordinateur est capté par un « process tap » de macOS (ADR 0032, macOS 14.4). Le premier enregistrement hybride déclenche la question de macOS. Un refus ne donne aucune erreur : le tap rend du silence. On ne le découvre qu'après coup, par l'avertissement « macOS ne l'a sans doute pas donné ».
- macOS n'a **aucune API publique** pour savoir si cette capture est autorisée ni pour la demander. Seuls les appels privés de TCC, `TCCAccessPreflight` et `TCCAccessRequest` avec le service `kTCCServiceAudioCapture`, le font. C'est la voie de l'exemple AudioCap, connue des développeurs. Une mise à jour de macOS peut les retirer ou les changer sans prévenir.
- La question de macOS est posée pour l'app du Dock, qui est le processus responsable du service et de son outil de capture.

## Décision
- **L'app du Dock lit l'autorisation** par `TCCAccessPreflight`, chargé à l'exécution (`dlopen`, `dlsym`), jamais lié. Elle la dit à la page : `coulissesApp.systemAudio`, `"allowed"`, `"denied"` ou `"unknown"`, sur le modèle de `notifications`. L'état est relu au lancement et à chaque retour au premier plan (changé dans Réglages Système entre-temps), et l'évènement `coulisses:mises-a-jour` le signale.
- **La page demande** par le message `demander-son-ordinateur`. Tant que c'est `"unknown"`, l'app pose la question de macOS (`TCCAccessRequest`), puis relit l'état. Une fois refusé, macOS ne la repose plus : l'app ouvre alors la page « Enregistrement de l'écran et de l'audio du système » des Réglages Système (`Privacy_ScreenCapture`).
- **Si les appels privés manquent ou répondent autre chose** (0 autorisé, 1 refusé, 2 pas décidé), l'état reste `"unknown"`, jamais un refus supposé. « Autoriser » ouvre alors les Réglages Système, et l'avertissement d'après enregistrement reste le filet. Le journal de l'app le dit une fois par version de macOS (P8).
- **Après chaque mise à jour de macOS**, on vérifie que ça n'a pas cassé :
  - l'app le fait d'elle-même : au premier lancement sous une nouvelle version de macOS, elle inscrit au journal si les appels répondent encore ;
  - `swift scripts/verifier-son-ordinateur.swift` le vérifie à la main ;
  - `scripts/essai-paquet.sh` le passe avant chaque publication et échoue si ça a cassé.
- Où la page le montre (la fenêtre de bienvenue, la barre d'enregistrement) relève de l'Interface.

## Conséquences
- La question de macOS peut être posée dès la bienvenue, avant tout enregistrement, et un refus se voit avant la réunion.
- Coulisses dépend d'un appel privé de macOS pour cet état seulement. La capture elle-même n'en dépend pas.
- L'app de développement le fait aussi, pour elle-même : ses permissions sont les siennes (ADR 0040).

## Alternatives écartées
- **L'API publique seule** : démarrer un tap une seconde pour déclencher la question. L'app ne saurait jamais dire « refusé » avec certitude. L'utilisateur a préféré un état fiable, vérifié à chaque mise à jour de macOS.
