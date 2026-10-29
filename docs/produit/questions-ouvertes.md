# Questions ouvertes

> Ce qui n'est pas encore tranché. Quand une question est tranchée : la réponse va dans la spec ou dans un ADR, et la ligne est supprimée d'ici.

## À trancher par l'utilisateur
| # | Question | Quand | Piste |
|---|---|---|---|
| L1 | Les rédactions (chapitres, titre, résumés) d'une séance dans une autre langue que le français, avant toute mesure : les faire comme les autres, ou ne pas les lancer d'elles-mêmes tant que la langue n'est pas mesurée ? | Avec l'accord sur l'ADR 0072 | Proposé : les faire, sans en promettre la qualité, et mesurer sur la première vraie séance en anglais et en allemand |
| L2 | Dans un résumé en français d'une séance en anglais, une citation exacte reste-t-elle dans sa langue, ou est-elle traduite ? | Avec l'accord sur l'ADR 0072 | Rédaction propose : dans sa langue, entre guillemets |

## À trancher par la mesure (banc d'essai)
| # | Question |
|---|---|
| M1 | ~~Moteur de transcription pour Rapide et pour Qualité max.~~ Tranché : un seul profil, la chaîne retenue du moteur (2026-10-02). |
| M2 | L'alignement forcé améliore-t-il les horodatages d'un moteur qui en fournit déjà nativement ? |
| M3 | Moteur et seuil de diarisation qui maximisent la pureté en discussion sans exploser le nombre de locuteurs. |
| M4 | La déréverbération aide-t-elle la diarisation ? Et la transcription ? |
| M5 | Le glossaire améliore-t-il vraiment la transcription des prénoms et du jargon (selon le moteur) ? |
| M6 | Modèle de génération par défaut, `num_ctx` nécessaire, et seuil de bascule vers le résumé par sections. Tranché en partie (2026-10-16) : un modèle par rédaction (ADR 0039), `qwen3.5:4b-mlx` pour les chapitres et le titre, au choix de l'utilisateur après mesure contre des références. Reste ouvert : le modèle des résumés (après les avoir raccourcis, comparaison à l'aveugle), `num_ctx` et le seuil de bascule (lot 11g). |
| M7 | ~~Méthode de détection des phases.~~ Tranché : le LLM local (ADR 0024, 2026-10-06), lu par parties de 15 min depuis le 2026-10-14 (ADR 0044, 0045) ; à revoir si les corrections de chapitres sont nombreuses. |
| M8 | Faut-il des réglages de diarisation différents en scène et en discussion ? |

## Risques identifiés
- **Voix de personnages** : un comédien qui change de voix en scène peut être confondu avec un autre. Accepté pour les scènes (objectif 2) ; à surveiller en discussion.
- **Chevauchements fréquents** en discussion animée : dégradent diarisation et transcription.
- **Réverbération des salles de répétition** : la plus grosse inconnue sur la qualité.
- **Veille pendant la nuit** : Mac sur batterie, capot fermé → la nuit est perdue. L'app doit le signaler. L'app Coulisses doit rester ouverte pendant le traitement de nuit (la quitter l'interrompt ; il reprend au lancement suivant, ADR 0034).
- **Maturité d'Astryx** (bêta).
- **Dette de l'interface** : transcript non virtualisé (ne tiendra pas 2 h), pas encore de raccourcis clavier de relecture (`rules/web.md`). À traiter avant la relecture de vraies séances.
