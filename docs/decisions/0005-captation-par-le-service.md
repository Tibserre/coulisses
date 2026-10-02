# 0005 — Captation audio par le service Python

Statut : Acceptée (2026-09-24)

## Contexte
Le brief suggère une captation dans le navigateur (getUserMedia, sans echoCancellation, noiseSuppression ni autoGainControl). Exigences : WAV 48 kHz brut, écriture continue sur disque, survie à un crash, Mac qui ne dort pas pendant 2 h.

## Décision
Le **service Python** capte le micro (PortAudio via `sounddevice`) et écrit le WAV en continu sur disque. L'interface ne fait que piloter (démarrer, pause, marqueur, note) et affiche le vumètre reçu par WebSocket.

Pourquoi :
- **Robustesse** : fermer l'onglet, recharger la page ou un plantage du navigateur n'interrompt pas l'enregistrement. Le navigateur ralentit parfois les onglets en arrière-plan.
- **Brut garanti** : pas de traitement de voix du navigateur, même partiel. Accès direct au format natif du périphérique (48 kHz, 24 bits si disponible).
- **Écriture disque** : directe, en-tête WAV réparé au redémarrage, sans aller-retour réseau local.
- **Anti-veille** : le service maintient une assertion d'activité macOS (`caffeinate`) pendant la captation et les traitements.

Coûts :
- La permission micro de macOS est accordée au processus qui lance le service (Terminal pendant le développement, l'app lanceur du Dock ensuite, voir spec §7.12).
- La future captation depuis un téléphone passera par le navigateur du téléphone : ce sera un second chemin de captation, prévu par le modèle multi-sources (0006).

## Alternative écartée
Captation navigateur (AudioWorklet → PCM → WebSocket → disque) : un seul chemin, réutilisable sur téléphone, mais plus fragile pour une séance de 2 h sur le Mac.
