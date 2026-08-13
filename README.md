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
| `attack_taxonomy.py` | Validation contre le vrai référentiel MITRE ATT&CK (Step 2) |
| `generalizability.py` | Score de généralisabilité d'une mitigation (Step 4) |
| `knowledge_table.py` | Table de connaissance JSONL (métadonnées) + embeddings (Step 5) |
| `vector_store.py` | Stockage des embeddings en `.npz` (séparé du JSONL) + similarité cosinus vectorisée |
| `retrieval.py` | Retrieval Tier 1 (embeddings) / Tier 2 (recherche live) (Step 6) |
| `jsonl_utils.py` | Lecture/écriture JSONL partagées |
| `build_knowledge.py` | Orchestrateur CLI OFFLINE : PDF → Layer 1 → Layer 2 → table de connaissance |
| `query_knowledge.py` | Orchestrateur CLI de retrieval sur la table de connaissance |

## Pipeline méthodologie/mitigation (Layer 2)

Au-dessus de l'extraction d'entités (Layer 1, ci-dessus, **inchangée**), un
second pipeline construit une base de connaissance attaque → mitigation à
partir d'un corpus de papers, pour du retrieval ultérieur :

```
PDF → texte → chunks
   → Layer 1 : extraction d'entités (existant)
   → Layer 2 : résumé attaque/mitigation ancré sur le texte + les entités
     Layer 1 (jamais le texte brut seul)
   → catégorie MITRE ATT&CK validée contre le vrai référentiel (pas une
     taxonomie inventée par le LLM)
   → mitigation conservée UNIQUEMENT si attaque + catégorie confirmées
     (honest null sinon — jamais de mitigation inventée)
   → score de généralisabilité (mentions de produits/fournisseurs nommés)
   → knowledge_table.jsonl
```

### Installation supplémentaire

Layer 2 utilise Ollama aussi pour les embeddings (léger, cohérent avec
l'infrastructure Mistral déjà en place) :
```bash
ollama pull nomic-embed-text
```

### Construire la table de connaissance (un paper à la fois)
```bash
python build_knowledge.py --pdf backdoor.pdf
```
Sauvegarde les résumés bruts de Layer 2 dans `results/methodology_<pdf>.jsonl`
(**à inspecter à la main** avant de faire confiance à la table — recommandé en
particulier sur les 3 cas d'étude XZ Utils/SolarWinds/Log4Shell, pour lesquels
`ground_truth_backdoor.json` sert déjà de référence), et ajoute un
enregistrement par attaque confirmée à `results/knowledge_table.jsonl`
(texte + métadonnées uniquement) — les embeddings sont stockés à part dans
`results/knowledge_attack_vectors.npz` et `results/knowledge_mitigation_vectors.npz`
(voir `vector_store.py`), reliés au JSONL par un `record_id`.

Le référentiel MITRE ATT&CK (Step 2) est téléchargé une fois et mis en cache
dans `data/mitre_attack_techniques.json` (~700 techniques, ~30 Ko). Le choix
de catégorie est restreint à une short-list d'une quinzaine de techniques
pertinentes pour la chaîne d'approvisionnement (`attack_taxonomy.
SUPPLY_CHAIN_TECHNIQUE_IDS`) plutôt que les ~700 du référentiel complet —
laisser le modèle choisir librement produisait des ID réels mais hors-sujet
pour l'attaque décrite.

Pour un retrieval significatif, viser **15-30+ papers** couvrant plusieurs
catégories d'attaque — un seul paper ne suffit pas.

### Chercher dans la table de connaissance
```bash
python query_knowledge.py --attack-summary "Backdoor introduite via un mainteneur compromis" --category T1195
```
Tier 1 (embeddings) est toujours utilisé. Tier 2 (recherche live sur Semantic
Scholar/arXiv, ingestion à la volée) est **désactivé par défaut**
(`config.TIER2_ENABLED = False`) — l'activer en fait une ablation statique vs
augmenté contrôlable, pas une réécriture. Chaque déclenchement de Tier 2 est
journalisé dans `results/tier2_retrieval_log.jsonl`, y compris quand la
recherche ne ramène rien d'exploitable.

### Ce qui n'est PAS implémenté

La boucle Propose → Verify → Revise (Step 7 du plan complet) n'est
volontairement pas implémentée : elle dépend d'avoir d'abord une table de
connaissance non triviale (15-30+ papers) pour être évaluable. De même, le
score de généralisabilité noté par LLM avec auto-cohérence reste une version
future documentée dans `generalizability.py` — la version actuelle (comptage
d'entités Layer 1 nommées dans la mitigation) est la version "cheap,
reproducible" demandée en priorité.

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
