# 0068 — Un micro qui ne tourne pas à 48 kHz est converti avec le son de l'ordinateur

Statut : Proposée (2026-10-29, correction d'un bug signalé par l'utilisateur ; à accepter après l'essai avec de vrais AirPods). Précise l'ADR 0032.

## Contexte
Des AirPods dont le micro est actif passent en mode « mains libres », à 16 ou 24 kHz, et refusent 48 kHz. Le programme du son de l'ordinateur (ADR 0032) donne au micro l'horloge de l'agrégat et lui demande 48 kHz : il s'arrêtait sur l'erreur `frequence` (« 24000.0 Hz » au journal). Or « Nouvelle note » démarre avec le son de l'ordinateur (ADR 0056) : avec des AirPods, l'enregistrement ne démarrait pas. Sans le son de l'ordinateur, PortAudio convertit déjà à la fréquence demandée.

## Décision
- Le programme demande toujours 48 kHz. Si le micro ne peut pas, l'agrégat garde la fréquence du micro, et **les deux pistes sont converties ensemble** vers 48 kHz (AVAudioConverter, qualité maximale), dans le même bloc : elles restent sur la même horloge (P2).
- Les images perdues sont comptées à 48 kHz. À l'arrêt, ce que le convertisseur retient encore est écrit, et une perte restée sans bloc part seule.
- Si la conversion échoue en cours d'enregistrement, ou si aucun convertisseur ne vient de la nouvelle fréquence du micro, chaque bloc devient du silence de sa durée, compté perdu : jamais de bloc envoyé à une autre fréquence que 48 kHz (P2), jamais de perte tue (P8). L'enregistrement continue, et les pertes se voient à l'écran.
- Si le micro change de fréquence pendant l'enregistrement, le programme écrit ce que le convertisseur retient, puis convertit depuis la nouvelle fréquence et le dit (`{"event":"rate"}`).
- `ready` donne `rate` (celle des blocs) et `device_rate` (celle du micro). Le service refuse un programme dont les blocs ne sont pas à 48 kHz. Il note au journal un micro converti.
- Les fichiers restent en WAV 48 kHz, 24 bits : rien ne change pour la suite (mix, moteur, schéma).

## Conséquences
- Avec des AirPods en mains libres, le son de l'ordinateur passe lui aussi par la fréquence du micro : sa bande est limitée à la moitié de cette fréquence (12 kHz à 24 kHz). C'est assez pour la voix.
- Un bloc capté à la nouvelle fréquence avant que le programme apprenne le changement serait converti à l'ancien rapport. Le système arrête l'entrée du micro pour en changer la fréquence : aucun n'est attendu, mais rien ne le prouve. Le changement de fréquence et l'échec de conversion ne sont vérifiés qu'à la main.
- Un test sur le vrai matériel (`uv run pytest -m materiel`) demande une fréquence qu'aucun micro du Mac ne fait (32 kHz) ; il ne tourne pas avec les autres tests.

## Alternatives écartées
- Enregistrer à la fréquence du micro : chaque temps, chaque mix et chaque piste supposent 48 kHz ; tout aurait changé pour un seul cas.
- Rééchantillonner en Python : le programme a déjà un convertisseur d'Apple, avec son état d'un bloc à l'autre.
