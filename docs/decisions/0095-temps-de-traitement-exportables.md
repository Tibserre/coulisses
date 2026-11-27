# 0095 — Les temps de traitement, exportables avec la description du Mac

Statut : Acceptée (2026-11-27, demande de l'utilisateur transmise par Pilotage : savoir combien de temps prend le traitement d'une heure d'audio sur un M5 Pro, un M4, un M2… ; chaque testeur exporte le fichier et le lui envoie ; l'export dans les réglages « Avancé », sans gros bouton ailleurs).

## Contexte
Chaque étape lancée par le moteur a sa propre exécution, réussie ou en échec, jamais réécrite ni purgée (P5), et sa provenance dit ce qu'elle a coûté : durée, mémoire maximale, moteur, modèle et révision, réglages, versions (P7). Une reprise ne réécrit pas une exécution : elle en crée une nouvelle. Tout ce qu'il faut est donc déjà gardé. Mais la provenance porte aussi ce que l'étape a entendu : les chemins des fichiers et le glossaire de l'espace.

## Décision
- **Rien de nouveau n'est enregistré** : l'export relit les exécutions du moteur de chaque séance et leur provenance. Aucun changement de schéma.
- **Par séance** : un numéro, dans l'ordre où elle est entrée dans l'app, et la durée de son audio de référence. **Par exécution** : le traitement dont elle vient (son rang dans la séance, et l'étape refaite s'il s'agit d'une relance), l'étape, son état, la durée et la mémoire maximale mesurées par le moteur, le code de sortie, le type et le code d'erreur, la langue et le minimum de voix demandés, le moteur, le modèle et sa révision, les réglages, les versions, la version du moteur, la plateforme. Une exécution dont la provenance manque ou est illisible est dite comme telle (`provenance` : `lue`, `absente` ou `illisible`), jamais retirée (P8).
- **Le Mac** : la puce, les cœurs (performance et efficacité), la mémoire, la version de macOS (lues par `sysctl` et Python ; ce qui ne se lit pas vaut `null`, jamais deviné), et les versions de l'app et du moteur.
- **Rien d'une séance ne sort** : ni identifiant, ni titre, ni nom, ni texte, ni date d'enregistrement, ni chemin, ni message d'erreur (il peut citer un fichier). Des entrées de la provenance, seules la langue et le minimum de voix sortent. Des réglages, seuls sortent les nombres, les booléens et les noms (un seul mot, sans espace ni virgule : un modèle, un appareil) : ce qui est connu pour sûr, pas ce qui est reconnu comme dangereux. Des versions, les listes et les textes de plus de 80 caractères sont retirés.
- **Un fichier JSON que l'utilisateur enregistre** (`GET /api/temps-de-traitement`, `coulisses-temps-de-traitement-<date>.json`), depuis Réglages › Avancé ; il l'envoie lui-même. Rien ne part tout seul (P1).

## Conséquences
- Les essais ratés comptent : une diarisation refusée puis reprise donne deux lignes.
- Une séance supprimée emporte ses exécutions : ses temps ne sont plus dans l'export. Une séance purgée garde les siennes.
- Les étapes de l'application (les chapitres, par le LLM) n'y sont pas : seulement celles du moteur.
- Le format porte un numéro (`format`) : une évolution le change.
- Une étape en cours ou en attente au moment de l'export n'y est pas encore : seules les exécutions closes y sont.
- À chaque montée de version du moteur, relire ce que ses provenances mettent dans les réglages et les versions avant de garder ce filtre.

## Alternatives écartées
- Une table des temps, remplie à chaque étape : un double de la provenance, qui peut diverger d'elle.
- Garder `started_at`/`finished_at` du traitement à chaque reprise : ils mesurent l'attente et la reprise, pas le travail ; la provenance de chaque exécution le mesure déjà.
- Un CSV : une ligne par exécution perd la machine et les réglages imbriqués ; le JSON se lit aussi dans un tableur par un script.
- Un envoi automatique : contraire à P1.
