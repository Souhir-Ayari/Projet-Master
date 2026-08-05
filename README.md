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
| `main.py` | Orchestrateur CLI |

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
