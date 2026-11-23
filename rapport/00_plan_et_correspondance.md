# Rapport de mémoire — plan, correspondance avec la présentation, répartition des pages

Sources : l'article ICAART (`icaart_final_7.tex`), la présentation de soutenance (22 diapositives), les remarques de l'encadrante (`souha_state_of.docx`), le code du dépôt et les fichiers de résultats. Aucun chiffre n'est ajouté s'il ne figure pas dans ces sources.

Le rapport complet est assemblé dans `rapport/Rapport_Memoire_CARL.docx` par `python rapport/build_rapport.py <page_de_garde.docx> rapport/Rapport_Memoire_CARL.docx`, à partir des sections validées de `rapport/sections/`.

## 1. Correspondance diapositives → parties du rapport

| Diapositive(s) | Partie du rapport |
|---|---|
| 1 · Couverture | Page de garde |
| 2 · Sommaire | Table des matières |
| — | Liste des figures (s'il y en a) |
| — | Liste des tableaux |
| 5 · Mots clés | Liste des acronymes |
| 3 · Introduction (LLM, menaces, besoin) | Introduction générale |
| 4 · Problématique | 1. Problématique |
| 6–7 · État de l'art (6 approches) | 2. État de l'art |
| 8 · Synthèse critique · 9 · Positionnement et contributions | 3. Synthèse critique, positionnement et contributions |
| 10 · Objectifs | 4. Objectifs |
| 11 · Pipeline global | 5. Méthodologie : le pipeline CARL |
| 12 · Architecture | 6. Architecture et mise en œuvre de CARL |
| 13 · Données · 14 · Protocole · 15–17 · RQ1–RQ3 · 18 · Évaluation humaine | 7. Évaluations |
| 19 · Discussion et limites | 8. Discussion et limites |
| 20 · Conclusion | Conclusion générale et perspectives |
| — (rédigé à la fin) | Résumé / Abstract |
| 21 · Références | Références bibliographiques |

## 2. Plan détaillé et répartition des pages (corps : 66 pages)

| Partie | Pages |
|---|---|
| Introduction générale | 2 |
| 1. Problématique | 5 |
| 2. État de l'art | 12 |
| 3. Synthèse critique, positionnement et contributions | 6 |
| 4. Objectifs | 2 |
| 5. Méthodologie : le pipeline CARL | 6 |
| 6. Architecture et mise en œuvre de CARL | 9 |
| 7. Évaluations | 16 |
| 7.1 Données d'évaluation | 1 |
| 7.2 Corpus et base de cas | 2 |
| 7.3 Protocole expérimental | 2 |
| 7.4 Méthodes d'extraction (GLiNER vs Mistral, filtres) | 2 |
| 7.5 Classification : validité et exactitude (RQ1) | 2 |
| 7.6 Recherche de cas : similarité et couverture (RQ2) | 2 |
| 7.7 Adaptation et recommandations : traçabilité et solidité (RQ3) | 3 |
| 7.8 Évaluation humaine | 1 |
| 7.9 Synthèse des résultats et des métriques | 1 |
| 8. Discussion et limites | 5 |
| Conclusion générale et perspectives | 3 |
| Résumé / Abstract | 1 |
| Références bibliographiques | 3 |
| **Total** | **70** |

Pages liminaires non comptées : page de garde, table des matières, liste des figures, liste des tableaux, liste des acronymes (`rapport/acronymes.md`, complétée au fil des chapitres).

Ordre de rédaction : introduction générale → chapitres 1 à 8 → conclusion → références → résumé et abstract en dernier.
