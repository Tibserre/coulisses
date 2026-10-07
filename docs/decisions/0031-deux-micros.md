# 0031 — Enregistrer avec deux micros à la fois, le Mac et l'iPhone par Continuité

Statut : Acceptée (2026-10-07, demande de l'utilisateur). Met en œuvre, pour la captation, l'ADR 0006 (une séance a N sources).

## Contexte
L'utilisateur veut enregistrer une séance avec le Mac et son téléphone en même temps, pour un meilleur son et, plus tard, des indices sur qui parle (ADR 0006). Le traitement des deux pistes viendra plus tard. Depuis macOS Ventura, Continuité fait de l'iPhone proche un micro du Mac : il apparaît comme une entrée audio ordinaire (« Micro de « iPhone de … » »), sans rien installer sur le téléphone et sans réseau à ouvrir.

## Décision
- Dans « Nouvelle séance », un **deuxième micro, facultatif**, choisi parmi les entrées du Mac (autre que le premier). Le service ouvre les deux flux et écrit **deux fichiers** : `ref.wav` (la source de référence) et `mic2.wav` (source `mic2`, origine captée), chacun avec son fil d'écriture, ses niveaux et ses alertes.
- La pause coupe les deux au même instant (le drapeau est lu avec chaque bloc, comme pour un seul micro). Les marqueurs et les notes sont au temps de la référence.
- **Un deuxième micro qui lâche** (iPhone éloigné, débranché, disque) n'arrête jamais l'enregistrement principal : l'alerte le dit, ce qu'il a enregistré est gardé et décrit à l'arrêt. Un deuxième micro qui refuse de démarrer empêche le départ, sans rien laisser derrière.
- Après un plantage, les deux fichiers sont réparés et signalés au démarrage suivant.
- **Le traitement ne lit que la référence**, comme avant. La seconde piste est gardée, comptée (« 2 micros » sous le titre), purgée et supprimée avec l'audio de la séance.
- Aucun décalage ni dérive n'est estimé ici : `offset_s` et `drift_ppm` restent à 0 jusqu'à l'étape de synchronisation du moteur (ADR 0006). Les deux flux démarrent à quelques millisecondes d'écart et ont chacun leur horloge ; rien n'est inventé à leur place (P2).

## Conséquences
- Rien de nouveau dans le schéma : la table `audio_source` tenait déjà N sources.
- L'iPhone doit être près du Mac, Continuité active (même identifiant Apple, Bluetooth et Wi-Fi). Le Mac garde l'accès au micro ; le téléphone n'a rien à autoriser.
- Une demande au moteur suivra (synchronisation, puis usage des deux pistes), comme prévu par l'ADR 0006.

## Alternatives écartées
- Enregistrer avec l'application Dictaphone du téléphone, puis ajouter le fichier : deux départs à la main, et un fichier à transférer.
- Une page de Coulisses ouverte sur le téléphone par le Wi-Fi : il faudrait ouvrir le service au réseau local avec un certificat (le micro de Safari l'exige).
- Un « appareil agrégé » de Configuration audio et MIDI : réglage à faire dans macOS, et une seule piste à deux canaux au lieu de deux sources.
