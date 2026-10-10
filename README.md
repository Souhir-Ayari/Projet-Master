# Expérience : GLiNER (NER pur) vs Mistral 7B (prompt-based) pour l'extraction d'entités en cybersécurité

## Objectif

Comparer deux approches d'extraction d'informations sur un même document PDF
de cybersécurité (rapport CERT, threat intel, advisory...) :

- **Cas 1 — NER pur (GLiNER)** : extraction zero-shot avec une liste de labels,
  sans prompt engineering.
- **Cas 2 — Prompt-based (Mistral 7B)** : extraction guidée par prompt, avec
  deux variantes (`naive` vs `engineered`) pour mesurer l'effet du prompt
  engineering.
- **Cas bonus — Hybride** : GLiNER détecte des candidats, Mistral les valide
  et en ajoute d'autres à partir du contexte. C'est souvent le meilleur
  compromis précision/rappel.

Chaque méthode produit un **JSON identique en structure**, ce qui permet une
évaluation automatisée et équitable via **Precision / Recall / F1-score** et
un **taux d'hallucination** (proportion d'entités extraites qui n'apparaissent
pas littéralement dans le texte source).

## Installation (VS Code)

```bash
python -m venv venv
source venv/bin/activate        # Windows : venv\Scripts\activate
pip install -r requirements.txt
```

### Backend Mistral 7B — deux options

**Option A (recommandée) : Ollama** — plus simple, tourne en local sans gros GPU dédié (quantifié) :
```bash
# installer Ollama : https://ollama.com/download
ollama pull mistral
ollama serve
```
C'est le backend par défaut (`config.MISTRAL_BACKEND = "ollama"`).

**Option B : HuggingFace transformers** — nécessite un GPU (~16 Go VRAM en fp16,
ou 4-bit avec bitsandbytes sur GPU plus modeste) :
```bash
python main.py --pdf rapport.pdf --backend transformers
```
Le modèle `mistralai/Mistral-7B-Instruct-v0.3` nécessite d'accepter les
conditions sur HuggingFace et d'être authentifié (`huggingface-cli login`).

## Utilisation

### 1. Extraction seule (sans évaluation)
```bash
python main.py --pdf rapport.pdf
```
Affiche dans le terminal le JSON du Cas 1 (GLiNER), puis du Cas 2 en variante
`naive` et `engineered`. Les fichiers sont aussi sauvegardés dans `results/`.

### 2. Avec le pipeline hybride en plus
```bash
python main.py --pdf rapport.pdf --hybrid
```

### Ground truth du corpus LLM (RQ1)

`ground_truth_prompt_injection.json` annote `Prompt-Injection.pdf` (Greshake
et al., AISec'23) avec la taxonomie `config.LLM_THREAT_ENTITY_LABELS` :
45 entités distinctes, chacune vérifiée présente dans le texte extrait par
`pdf_extractor.py` (bibliographie retirée). Statut `draft_to_validate` : la
liste doit être relue à la main avant d'être rapportée comme annotation
manuelle.

Une méthode par run (un run Mistral complet dure plusieurs heures sur CPU),
chaque run enregistrant ses scores dans `eval_<méthode>.json`, puis
assemblage de la Table I :

```bash
python main.py --pdf files/Prompt-Injection.pdf --ground-truth ground_truth_prompt_injection.json --only gliner --output-dir results/rq1_prompt_injection
python main.py --pdf files/Prompt-Injection.pdf --ground-truth ground_truth_prompt_injection.json --only topic --output-dir results/rq1_prompt_injection
# ... idem pour naive, engineered, custom (--user-need "...")
python rq1_table.py --dir results/rq1_prompt_injection
```

Audit manuel des faux positifs (la précision rapportée est une borne
inférieure si une partie des faux positifs sont des entités légitimes
absentes de l'annotation) : tirage reproductible de 30 faux positifs dans un
CSV à juger à la main (`valide` = o / n), puis calcul de la part valide
(intervalle de Wilson à 95 %) et de la précision corrigée estimée :

```bash
python audit_false_positives.py sample --pdf files/Prompt-Injection.pdf --ground-truth ground_truth_prompt_injection.json --case results/rq1_prompt_injection/case2_mistral_topic.json
# ... remplir la colonne "valide" de results/rq1_prompt_injection/audit_fp_topic.csv ...
python audit_false_positives.py score --audit results/rq1_prompt_injection/audit_fp_topic.csv
```

### 3. Avec évaluation F1 / hallucination

Copiez `ground_truth_template.json`, annotez-le à la main pour VOTRE PDF
(entités réellement présentes dans le document, copiées exactement) :

```bash
cp ground_truth_template.json ground_truth.json
# ... éditez ground_truth.json ...
python main.py --pdf rapport.pdf --ground-truth ground_truth.json --hybrid
```

Le terminal affichera, pour chaque méthode :
- `precision`, `recall`, `f1`
- `hallucination_rate` et la liste des entités hallucinées
- un **classement final** (`final_comparison.json`) désignant la meilleure méthode

## Structure du projet

| Fichier | Rôle |
|---|---|
| `config.py` | Labels d'entités cyber + templates de prompts |
| `pdf_extractor.py` | PDF → texte propre (+ découpage en chunks) |
| `gliner_extractor.py` | Cas 1 : NER zero-shot |
| `mistral_extractor.py` | Cas 2 : extraction prompt-based (naive/engineered) |
| `hybrid_extractor.py` | Cas bonus : GLiNER + validation Mistral |
| `evaluator.py` | Precision/Recall/F1 + taux d'hallucination |
| `main.py` | Orchestrateur CLI (Layer 1 : extraction d'entités) |
| `methodology_extractor.py` | Layer 2 : résumé attaque/mitigation ancré sur Layer 1 (Steps 1 et 3) |
| `attack_taxonomy.py` | Validation contre le vrai référentiel MITRE — ATLAS ou ATT&CK selon le domaine (Step 2) |
| `specificity.py` | Marque un cas comme concret ou générique selon les entités Layer 1 identifiantes |
| `deduplication.py` | Plafonne les cas par (papier, catégorie) — un papier reformule son sujet, ce ne sont pas des cas distincts |
| `test_labels.py` | Teste les labels Layer 1 (GLiNER seul, sans Ollama) + cohérence des filtres |
| `verifier_run.py` | Contrôle qualité hors ligne d'un run : catégories, spécificité, redondance, remplissage |
| `generalizability.py` | Score de généralisabilité d'une mitigation (Step 4) |
| `knowledge_table.py` | Table de connaissance JSONL (métadonnées) + embeddings (Step 5) |
| `vector_store.py` | Stockage des embeddings en `.npz` (séparé du JSONL) + similarité cosinus vectorisée |
| `retrieval.py` | Retrieval Tier 1 (embeddings) / Tier 2 (recherche live) (Step 6) |
| `jsonl_utils.py` | Lecture/écriture JSONL partagées |
| `build_knowledge.py` | Orchestrateur CLI OFFLINE : PDF → Layer 1 → Layer 2 → table de connaissance |
| `query_knowledge.py` | Orchestrateur CLI de retrieval sur la table de connaissance |
| `remediation.py` | Step 7 : boucle Propose -> Verify -> Revise minimale (N=1), vérification de traçabilité en code |
| `run_remediation.py` | Orchestrateur CLI du Step 7 : 3 modes (sans retrieval / retrieval / retrieval + boucle) -> Table IV |
| `calibrate_retrieval.py` | Calibre α (bonus / filtre de catégorie) et dérive θ sur les requêtes étiquetées de `data/eval_queries.json` |
| `ablation_filters.py` | Table II (RQ1) : ablation des filtres Layer 1 rejouée sur les réponses brutes enregistrées, sans relancer Mistral |
| `rq1_table.py` | Assemble la Table I (RQ1) à partir des `eval_<méthode>.json` écrits par `main.py --only` |
| `audit_false_positives.py` | Audit manuel RQ1 : tirage de faux positifs à juger, part d'entités valides absentes de l'annotation, précision corrigée |
| `review_cases.py` | Relecture manuelle de la knowledge table : justesse de la technique ATLAS, validité des mitigations, table corrigée |
| `reclassify_cases.py` | Reclasse la technique ATLAS des cas existants (noms seuls / avec définitions) et mesure la justesse contre la relecture |
| `test_retrieval.py` | Requêtes manuelles à famille ATLAS connue -> Hit@k du retrieval Tier 1 (+ contrôle hors ligne de Tier 2) |

## Pipeline méthodologie/mitigation (Layer 2)

Au-dessus de l'extraction d'entités (Layer 1, ci-dessus, **inchangée**), un
second pipeline construit une base de connaissance attaque → mitigation à
partir d'un corpus de papers, pour du retrieval ultérieur :

```
PDF → texte → chunks
   → Layer 1 : extraction d'entités (existant)
   → Layer 2 : résumé attaque/mitigation ancré sur le texte + les entités
     Layer 1 (jamais le texte brut seul)
   → catégorie MITRE validée contre le vrai référentiel du domaine (pas une
     taxonomie inventée par le LLM)
   → mitigation STRUCTURÉE (type + résumé) conservée dès que l'attaque est
     confirmée (honest null sinon — jamais de mitigation inventée)
   → score de généralisabilité (mentions de produits/fournisseurs nommés)
   → knowledge_table.jsonl
```

### Domaines d'analyse

Le pipeline traite deux sujets, chacun avec **sa** taxonomie de labels Layer 1,
**son** prompt spécialisé et **son** référentiel MITRE (`--domain`) :

| Domaine | Sujet | Référentiel | Labels Layer 1 |
|---|---|---|---|
| `llm` (défaut) | menaces émergentes sur les LLM : injection de prompt directe/indirecte, jailbreak, fuite du prompt système, empoisonnement RAG | **MITRE ATLAS** | `config.LLM_THREAT_ENTITY_LABELS` |
| `supply_chain` | compromissions de chaîne d'approvisionnement logicielle (XZ Utils, SolarWinds, Log4Shell) | MITRE ATT&CK | `config.SUPPLY_CHAIN_ENTITY_LABELS` |

MITRE ATT&CK Enterprise ne décrit **aucune** technique d'attaque sur les LLM
(pas d'ID `Txxxx` pour une injection de prompt) : le domaine `llm` s'ancre
donc sur MITRE ATLAS, le référentiel officiel des menaces sur les systèmes
d'IA, avec des identifiants de la forme `AML.Txxxx[.xxx]`. Le domaine
`supply_chain` est conservé à l'identique pour que les résultats déjà produits
sur ce premier corpus restent reproductibles.

### Déduplication par catégorie

Un papier de recherche reformule son sujet dans l'introduction, le related
work, la discussion et la conclusion. Layer 2 traite chaque reformulation
comme un cas distinct : sur Greshake et al., **23 chunks sur 23** marqués
« attaque confirmée », dont 18 partageant `AML.T0051.001` avec des résumés
paraphrasant les mêmes phrases. Ce ne sont pas 18 attaques, c'est une attaque
décrite 18 fois — et les mitigations se dupliquent mécaniquement avec elles.

`deduplication.py` plafonne donc les cas **par (papier, catégorie)**, en
gardant les plus spécifiques (cas concret d'abord, puis porteur d'une
mitigation, puis ancrage factuel). Le plafond est par papier, jamais global :
deux papiers décrivant la même technique apportent chacun leur point de vue,
c'est de la matière utile ; c'est la répétition interne qui est du bruit.

```bash
python build_knowledge.py --pdf paper.pdf --max-per-category 3   # défaut
python build_knowledge.py --pdf paper.pdf --max-per-category 0   # désactivé
```

Le filtrage intervient **avant** le calcul des embeddings : sur Greshake, 23
cas ramenés à 8 économisent 22 appels Ollama par run.

Niveau 2 (fusionner les résumés sémantiquement redondants par similarité
d'embeddings) volontairement non implémenté : il coûte un embedding par cas
avant même de savoir si on le garde. `verifier_run.py` signale la redondance
résiduelle par recouvrement de vocabulaire, ce qui permet de juger si ce
raffinement vaut la peine.

### Mitigation structurée

`mitigation_summary` n'est plus une phrase libre seule : chaque mitigation
porte un **type** fermé (`config.MITIGATION_TYPES`), proposé par le modèle puis
validé en code comme la catégorie MITRE —

| Type | Nature de la défense |
|---|---|
| `filtering_rule` | filtrage de l'entrée ou de la sortie du modèle |
| `secure_prompt_template` | structure de prompt durcie (délimiteurs, séparation instructions/données) |
| `detection_script` | détection automatisée a posteriori (classifieur, sonde, test) |

Un type hors de cette liste est mis à `null` **sans effacer le résumé** : une
défense réellement décrite dans le texte reste un signal exploitable même si
elle n'entre dans aucun des trois types (même découplage que pour la catégorie).

### Installation supplémentaire

Layer 2 utilise Ollama aussi pour les embeddings (léger, cohérent avec
l'infrastructure Mistral déjà en place) :
```bash
ollama pull nomic-embed-text
```

### Construire la table de connaissance (un paper à la fois)
```bash
python build_knowledge.py --pdf greshake_indirect_injection.pdf   # domaine llm par défaut
python build_knowledge.py --pdf backdoor.pdf --domain supply_chain
```
Sauvegarde les résumés bruts de Layer 2 dans `results/methodology_<pdf>.jsonl`
(**à inspecter à la main** avant de faire confiance à la table — recommandé en
particulier sur les 3 cas d'étude XZ Utils/SolarWinds/Log4Shell, pour lesquels
`ground_truth_backdoor.json` sert déjà de référence), et ajoute un
enregistrement par attaque confirmée à `results/knowledge_table.jsonl`
(texte + métadonnées uniquement) — les embeddings sont stockés à part dans
`results/knowledge_attack_vectors.npz` et `results/knowledge_mitigation_vectors.npz`
(voir `vector_store.py`), reliés au JSONL par un `record_id`.

Le référentiel MITRE du domaine (Step 2) est téléchargé une fois et mis en
cache dans `data/` : `mitre_atlas_techniques.json` (170 techniques ATLAS) ou
`mitre_attack_techniques.json` (~700 techniques ATT&CK). Le choix de catégorie
est restreint à une short-list d'une vingtaine de techniques pertinentes pour
le domaine (`attack_taxonomy.LLM_THREAT_TECHNIQUE_IDS` /
`SUPPLY_CHAIN_TECHNIQUE_IDS`) plutôt qu'au référentiel complet — laisser le
modèle choisir librement produisait des ID réels mais hors-sujet pour
l'attaque décrite.

Pour un retrieval significatif, viser **15-30+ papers** couvrant plusieurs
catégories d'attaque — un seul paper ne suffit pas.

Élargir le corpus en un lot : `fetch_corpus.py` télécharge depuis arXiv
12 papers sur l'injection, le jailbreak et l'empoisonnement, avec leurs
défenses. Le titre de chaque identifiant est vérifié avant téléchargement.
Aucun paper ne porte sur les attaques réservées aux requêtes hors corpus de
`data/eval_queries.json`. `build_knowledge.py` accepte ensuite plusieurs
PDF ou un dossier : les modèles ne sont chargés qu'une fois, un PDF en échec
n'arrête pas le lot, `--skip-existing` permet de reprendre un lot
interrompu, et un résumé de la table s'affiche à la fin (cas par technique
et par paper) :

```bash
python fetch_corpus.py
python build_knowledge.py --pdf files/corpus_llm --table results/knowledge_table_llm.jsonl --skip-existing
```

### Relire la table (justesse ATLAS + nettoyage)

`review_cases.py` exporte un cas par ligne dans un CSV à juger à la main :
technique ATLAS correcte ou non, vraie mitigation ou non, cas à garder ou
non. `score` mesure ensuite la justesse de classification et la validité des
mitigations sur la sortie **brute** du pipeline (pour le papier).
`apply` écrit la table corrigée : catégories corrigées, mitigations
invalides mises à null, cas retirés du JSONL et des deux `.npz`, avec une
sauvegarde `*.before_review`. Pas besoin d'Ollama. À faire avant la
calibration de θ/α, parce qu'un cas mal catégorisé change le statut
« couverte / hors corpus » des requêtes d'évaluation.

```bash
python review_cases.py export --table results/knowledge_table_llm.jsonl
# ... remplir results/review_knowledge_table_llm.csv ...
python review_cases.py score --review results/review_knowledge_table_llm.csv
python review_cases.py apply --review results/review_knowledge_table_llm.csv
python review_cases.py split --table results/knowledge_table_llm.jsonl
```

La relecture **mesure** la Layer 2 ; la table corrigée ne sert que de
borne supérieure. `split` écrit `knowledge_table_llm_raw.jsonl` (sortie du
pipeline, utilisée pour la calibration et la Table IV) et
`knowledge_table_llm_curated.jsonl` (après relecture).

### Reclasser les cas avec les définitions ATLAS

Le prompt de la Layer 2 donne maintenant, pour chaque technique de la
short-list, sa définition officielle ATLAS (`data/mitre_atlas_descriptions.json`)
et une règle pour distinguer jailbreak, injection de prompt et empoisonnement
(`config.TAXONOMY_PROMPT_DEFINITIONS`). `reclassify_cases.py` redemande
seulement la technique des cas existants, avec et sans définitions, et
mesure la justesse contre la relecture, sans refaire les résumés. Le script
reprend là où il s'est arrêté s'il est interrompu.

```bash
python reclassify_cases.py --table results/knowledge_table_llm_raw.jsonl --review results/review_knowledge_table_llm.csv --pdf-dir files --write-table
```

### Chercher dans la table de connaissance
```bash
python query_knowledge.py --attack-summary "Une page web récupérée par l'agent contient des instructions cachées" --category AML.T0051.001
python query_knowledge.py --attack-summary "Backdoor introduite via un mainteneur compromis" --category T1195
```
Chaque lancement enregistre son résultat JSON (UTF-8) dans `results/retrieval/`,
sous un nom horodaté qui ne s'écrase jamais (`query_AAAAMMJJ-HHMMSS_<début de
la requête>.json`) ; `--output` impose un nom précis. `test_retrieval.py` fait
de même (`test_top<k>_AAAAMMJJ-HHMMSS.json` : cas remontés, verdict par
requête, Hit@k), `--json` pour imposer le nom.

La catégorie suit le référentiel du corpus interrogé (`AML.Txxxx` pour `llm`,
`Txxxx` pour `supply_chain`) ; elle sert de bonus de similarité, jamais de
filtre.
Tier 1 (embeddings) est toujours utilisé. Tier 2 (recherche live sur Semantic
Scholar/arXiv, ingestion à la volée) est **désactivé par défaut**
(`config.TIER2_ENABLED = False`) — l'activer en fait une ablation statique vs
augmenté contrôlable, pas une réécriture. Chaque déclenchement de Tier 2 est
journalisé dans `results/tier2_retrieval_log.jsonl`, y compris quand la
recherche ne ramène rien d'exploitable.

### Calibrer α et θ

```bash
python calibrate_retrieval.py --table results/knowledge_table_llm.jsonl
```
Évalue sur `data/eval_queries.json` (18 requêtes étiquetées : 13 couvertes par
la table, 5 hors corpus) plusieurs bonus α, et le filtrage par catégorie
(`score_cases(category_filter=True)`), en Hit@1 / Hit@3 / MRR, puis dérive θ
du cosinus brut du meilleur cas (exactitude équilibrée couverte / hors corpus,
avec contrôle leave-one-out). Les embeddings ne sont calculés qu'une fois.

### Tester le retrieval sur des requêtes manuelles
```bash
python test_retrieval.py              # 4 requêtes, top-3, table par défaut
python test_retrieval.py --top-k 5
python test_retrieval.py --offline    # sans Ollama : attack_summary bien transmis à Tier 2
python test_retrieval.py --table results/knowledge_table_llm.jsonl --output results/retrieval_top3.txt
```
Chaque requête décrit une attaque sans reprendre le nom de la technique
(injection indirecte, fuite du prompt système, jailbreak, empoisonnement RAG)
et porte l'ensemble des techniques ATLAS attendues. Le script affiche le top-k
(score, catégorie, spécificité, papier source) et un Hit@k. Une requête dont
aucune catégorie attendue n'existe dans la table est comptée **hors corpus**,
pas comme un raté : c'est la taille du corpus qui est en cause, pas le
retrieval. Le critère par catégorie ne remplace pas la relecture des résumés
remontés.

Sans CVE, paquet ni ID MITRE (cas courant sur le domaine `llm`), Tier 2
construit sa requête live à partir des premiers mots de l'`attack_summary`
(`config.TIER2_SUMMARY_MAX_WORDS`) ; le résumé est aussi journalisé et renvoyé
dans le champ `query` du résultat.

**Limite à signaler dans le papier** : la table de connaissance de la première
soumission compte ~25 enregistrements. Les Hit@k mesurés dessus portent sur
peu de requêtes et sur une couverture partielle de la short-list ATLAS (d'où
le décompte « hors corpus ») ; ce sont des indications de fonctionnement, pas
des performances généralisables.

### Plan de remédiation : boucle Propose -> Verify -> Revise (Step 7)

Version minimale (`remediation.py`), lancée sur les requêtes du Bloc 1 :

- **Propose** : un appel Mistral, prompt contraint aux cas récupérés
  (numérotés C1, C2...). Chaque recommandation cite ses cas ; une liste vide
  est une réponse valide quand aucun cas ne s'applique.
- **Verify** : règle déterministe en code, sans LLM. Une recommandation est
  *traçable* si elle cite un cas existant, que ce cas porte une mitigation, et
  qu'au moins 60 % de ses mots porteurs de sens se retrouvent dans cette
  mitigation (`MIN_LEXICAL_SUPPORT`). Son type devient celui de la mitigation
  citée (déjà validé à Layer 2) ; les doublons sont retirés du plan final.
- **Seuil de similarité** : seuls les cas récupérés au-dessus de
  `RETRIEVAL_SIMILARITY_THRESHOLD` (0.6) sont montrés au modèle et citables.
  Sans aucun cas au-dessus (requête hors domaine), les modes `retrieval` et
  `retrieval_loop` s'abstiennent sans appel LLM.
- **JSON invalide** : les recommandations sont récupérées une par une et
  l'incident est compté (`n_parse_errors`) — jamais confondu avec une abstention.
- **Revise** : une seule itération (N=1), seulement si Verify rejette quelque
  chose. Ce qui reste non traçable après la révision est écarté du plan final
  (et conservé dans `dropped`).

```bash
python run_remediation.py --table results/knowledge_table_llm.jsonl --output-dir results/rq3
```

Produit un JSON par requête (cas récupérés, propositions, verdicts, révision,
plan final) et `table_iv_summary.json` : pour chacun des trois modes
(`no_retrieval`, `retrieval`, `retrieval_loop`), le nombre de recommandations,
le taux de traçabilité, les rejets avant révision, les recommandations
écartées et le nombre d'appels LLM. Verify est calculé dans les trois modes
contre les mêmes cas récupérés, pour que la traçabilité soit comparable.
L'empreinte SHA-256 de la table est enregistrée dans chaque résultat : la
table est figée, les chiffres ne sont comparables qu'à empreinte égale.

Traçable ne veut pas dire pertinent : une défense fidèlement recopiée d'un cas
récupéré peut ne pas s'appliquer à l'attaque (typiquement sur la requête hors
domaine). La pertinence relève de l'évaluation humaine (5 cas, Likert 1-5).

### Ce qui n'est PAS implémenté

- **Tier 2** (recherche live) : travail futur. Le champ `tier2_would_trigger`
  de la sortie du retrieval indique, requête par requête, quand il aurait été
  nécessaire (`best_score < threshold`) — `tier2_triggered` reste `false` tant
  que `TIER2_ENABLED=False`.
- **Ablation N=1/2/3** de la boucle : N fixé à 1.
- **Score de généralisabilité noté par LLM** avec auto-cohérence : version
  future documentée dans `generalizability.py` ; la version actuelle compte les
  entités Layer 1 nommées dans la mitigation.

## Notes méthodologiques

- **Pourquoi mesurer l'hallucination par présence littérale dans le texte ?**
  C'est le critère le plus objectif : GLiNER ne peut par construction
  extraire que des spans du texte, son taux d'hallucination sera donc
  quasi nul par design. Cela sert de baseline pour juger Mistral.
- **Pourquoi deux variantes de prompt ?** `naive` sert de référence basse pour
  isoler l'effet du prompt engineering (contraintes anti-hallucination,
  format JSON strict, exemple few-shot) sur le F1 et le taux d'hallucination.
- **Limite à noter dans votre rapport** : le fuzzy matching (`evaluator.py`,
  seuil 0.85) tolère de petites variations de tokenisation ; ajustez le
  seuil selon la sévérité d'évaluation souhaitée.
- Pour des résultats statistiquement solides, répétez l'expérience sur
  **plusieurs PDF** (au moins 5-10) et moyennez les F1-scores par méthode.
