# 0067 — Les micros pendant l'enregistrement : couper, ajouter, reprendre ceux de la dernière fois

Statut : Proposée (2026-10-28, parcours d'Interface validé par l'utilisateur sur maquettes, planches « B · 1 à 8 »). Précise les ADR 0031, 0033 et 0056.

## Contexte
Depuis l'ADR 0056 (un geste), « Nouvelle note » démarre avec le micro par défaut du Mac : on ne choisit plus ni n'ajoute de micro au départ. L'utilisateur veut pouvoir couper un micro, les couper tous, en ajouter un en cours, et retrouver ceux de la dernière fois. P2 : les temps restent mesurés, chaque fichier sur l'horloge de la référence. P8 : rien n'est perdu ni tu.

## Décision
- **Couper** une piste (le micro principal, un micro ajouté, le son de l'ordinateur), ou **tous les micros d'un coup** (le son de l'ordinateur garde son propre bouton) : du silence est écrit à sa place, décidé au moment où le son est entendu, comme la pause. Chaque fichier garde la longueur de l'enregistrement.
- L'état de l'enregistrement dit, pour chaque piste, si elle est coupée et ses coupures (`cuts` : de, à, en temps enregistré, pauses retirées). Elles ne sont gardées que pendant l'enregistrement : rien dans le schéma.
- **Ajouter un micro en cours** : il prend la source suivante (`micN`, jamais une source déjà prise, même par un essai qui n'a pas abouti). Son fichier commence par du silence jusqu'au temps de la référence à son premier bloc entendu (mesuré, à un bloc près), puis ce qu'il entend. Ce silence est **écrit dans le fichier**, pas noté comme un décalage : `offset_s` reste à 0 (ADR 0031), le fichier est déjà sur l'horloge de la référence. Un micro ajouté puis muet jusqu'à l'arrêt garde ce silence. S'il ne s'ouvre pas, l'enregistrement continue et l'erreur est dite.
- **Reprendre les micros de la dernière fois**, quand l'interface le demande (« Nouvelle note ») : ceux ajoutés à la dernière séance enregistrée dans l'app, au départ ou en cours. **La dernière séance fait foi** : aucun réglage n'est gardé. Un micro absent, ou qui ne s'ouvre pas, n'empêche pas de démarrer : l'état le dit (`last_time.missing`).

## Conséquences
- Une séance sans micro ajouté fait que la suivante n'en reprend aucun.
- Les coupures ne sont pas visibles après l'enregistrement. Les garder (dans le déroulé de la relecture) demanderait un changement de schéma.
- Le traitement ne lit toujours que le micro principal : coupé, c'est du silence qu'il entend.

## Alternatives écartées
- Retirer un micro en cours : couper suffit, et le fichier reste entier.
- Un réglage « micros habituels » gardé par le service : un état de plus à tenir à jour ; la dernière séance dit déjà ce qui a servi.
- Noter l'avance d'un micro ajouté en `offset_s` : ce champ attend la synchronisation du moteur (ADR 0006) ; un fichier qui commence à zéro avec la référence reste lisible par tout outil.
