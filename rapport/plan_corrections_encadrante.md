# Plan des corrections demandées par l'encadrante (mails du 28/11/2026)

Source : trois mails de Dr Amal Tarifa en réponse à la version du rapport (25/11).
Principe : une étape à la fois ; chaque étape est validée avant de passer à la suivante.
Statut : ☐ à faire · ◐ en cours · ☑ validé

## Étape 0 — Décision préalable : Word ou LaTeX ☐
L'encadrante écrit « LaTeX est beaucoup meilleur ! ». À trancher avant tout le reste, car cela change la gestion des références (BibTeX), des figures et de la table des matières.
- Option A : rester en Word (script actuel).
- Option B : passer en LaTeX (Overleaf), à partir des sections Markdown déjà validées.

## Étape 1 — Restructuration des chapitres 2 et 3 ☐ (bloquant : change la numérotation)
- Chapitre 2 = état de l'art **+ synthèse critique** à la fin (tableau 3.1, limites L1–L5).
- Nouvelle §2.8 substantielle (1 à 1,5 p.) : ce que les six approches couvrent ensemble, ce qu'aucune ne couvre, transition vers le chapitre 3.
- Tableau **approche × difficulté** (● traité, ◐ partiel, ○ non traité) reliant les 6 approches aux 4 difficultés du chapitre 1.
- Tableau 3.1 : limiter les « n.r. » et les définir clairement dans la légende.
- Chapitre 3 autonome = **positionnement et contributions**.

## Étape 2 — Chapitre 2 : compléments ☐
- Phrase de sélection : pourquoi ces six approches et pas d'autres.
- Expliquer pourquoi LADDER (et d'autres) restent sur ATT&CK alors que le domaine a besoin d'ATLAS (lien avec la limite L2).
- Justifier explicitement le lien entre Self-Refine et CARL (mécanisme que CARL refuse d'utiliser seul).
- Rompre la monotonie de la grille en quatre sous-parties (transitions, phrases de liaison).

## Étape 3 — Chapitre 1 (Problématique) ☐
- §1.2.4 : définition de l'**hallucination** (factuelle vs non-fidélité à la source).
- Préciser en une phrase ce qu'est Niu et al. (2024).
- Une illustration concrète par difficulté ; nouvelle §1.2.5 « propagation des erreurs ».
- Scénario concret à la fin de §1.1 (un analyste face à une attaque).
- §1.3 **Questions de recherche** : question principale (mentionnant les attaques visant les LLM) + RQ1, RQ2, RQ3.
- Nouvelle §1.4 **Périmètre et niveau d'ambition** (attaques, source des connaissances, prototype de recherche).
- Enjeux / publics visés (2–3 phrases).
- Hypothèses H1–H3 : seulement si elles sont testées au chapitre 5 (à décider).

## Étape 4 — Introduction générale ☐
- Utiliser et introduire le mot « hallucination ».
- Clarifier **Nexus Intel vs CARL** (une phrase).
- Annoncer les contributions.
- Paragraphe « Organisation du mémoire » (une phrase par chapitre, renvoi aux RQ).

## Étape 5 — Chapitre 5 ☐
- §5.3 renommée « Évaluation préliminaire : extraction des entités » (ou fondue dans le protocole).
- Raccourcir le titre de §5.6 (problème d'affichage dans la table des matières).
- Renvois RQ1–RQ3 cohérents avec le nouveau §1.3.

## Étape 6 — Figures (de 2 à environ 10) ☐
Priorité 1 :
1. Propagation des erreurs (diagramme en cascade ou Sankey) — chapitre 5 ou 6.
2. Résultats de classification (matrice de confusion si les données le permettent, sinon barres validité/exactitude).
3. Récupération (barres Hit@1 base automatique vs base de référence, par configuration).
4. Architecture d'au moins une approche du chapitre 2 (CTINexus), redessinée avec attribution.
Priorité 2 :
5. Fossé publication → protection (chapitre 1).
6. Positionnement de CARL par rapport aux six approches (chapitre 3).
7. Exemple de bout en bout (cas réel, par exemple le *jailbreak* en Base64).
8. Architectures de LADDER et FALCON.
Priorité 3 : comparaison des extracteurs (barres).

## Étape 7 — Pages liminaires et références ☐
- Résumé et Abstract **au début**, avant l'introduction.
- Références : format de citation cohérent entre le texte et la liste (numéros [n] dans le texte si la liste est numérotée).
- Acronymes : ajouter RQ, LARIA, Nexus Intel ; vérifier OS.

## Étape 8 — Mise en page finale ☐
- Numérotation des pages des références et du résumé (continue ou en chiffres romains).
- Table des matières : vérifier les titres longs.
- Page de garde : noms et rôles du jury (à compléter par l'étudiante).
- « Texte corrompu p. 10 » : à vérifier dans le fichier envoyé (début de l'introduction).
