"""
fetch_corpus.py
-----------------
Télécharge depuis arXiv les papers proposés pour élargir la knowledge table
LLM (25 cas sur 3 papers -> objectif ~100+ cas), à traiter ensuite en un lot :

    python fetch_corpus.py                      # -> files/corpus_llm/*.pdf
    python build_knowledge.py --pdf files/corpus_llm --table results/knowledge_table_llm.jsonl --skip-existing

Choix des papers :
  - les techniques déjà présentes dans la table (injection directe/indirecte/
    déclenchée, jailbreak, empoisonnement), pour avoir plusieurs cas par
    technique venant de papers DIFFÉRENTS — c'est ce qui donne au retrieval
    de vrais choix à faire ;
  - des papers de DÉFENSE (StruQ, BIPIA, SmoothLLM, défenses de base), parce
    qu'un cas sans mitigation n'aide pas la remédiation ;
  - volontairement AUCUN paper sur l'inférence d'appartenance, l'extraction
    de modèle, l'extraction de prompt système ou de données d'entraînement,
    ni les images adverses : ces attaques servent de requêtes HORS CORPUS
    dans data/eval_queries.json pour calibrer θ. Les ajouter supprimerait
    les exemples négatifs de la calibration.

Avant de télécharger, le script vérifie via l'API arXiv que le titre de
chaque identifiant correspond au titre attendu. En cas de différence, il
saute le paper au lieu de télécharger le mauvais.
Un PDF déjà présent n'est pas re-téléchargé.
"""

import argparse
import os
import re
import time
import urllib.request
import xml.etree.ElementTree as ET

# (arXiv id, nom de fichier, titre attendu)
PAPERS = [
    ("2211.09527", "perez_ignore_previous_prompt", "Ignore Previous Prompt: Attack Techniques For Language Models"),
    ("2306.05499", "liu_houyi_prompt_injection", "Prompt Injection attack against LLM-integrated Applications"),
    ("2312.14197", "yi_bipia_indirect_injection", "Benchmarking and Defending Against Indirect Prompt Injection Attacks on Large Language Models"),
    ("2402.06363", "chen_struq", "StruQ: Defending Against Prompt Injection with Structured Queries"),
    ("2403.02691", "zhan_injecagent", "InjecAgent: Benchmarking Indirect Prompt Injections in Tool-Integrated Large Language Model Agents"),
    ("2307.02483", "wei_jailbroken", "Jailbroken: How Does LLM Safety Training Fail?"),
    ("2307.15043", "zou_universal_adversarial_attacks", "Universal and Transferable Adversarial Attacks on Aligned Language Models"),
    ("2308.03825", "shen_do_anything_now", "Do Anything Now: Characterizing and Evaluating In-The-Wild Jailbreak Prompts on Large Language Models"),
    ("2310.08419", "chao_pair_jailbreak", "Jailbreaking Black Box Large Language Models in Twenty Queries"),
    ("2310.03684", "robey_smoothllm", "SmoothLLM: Defending Large Language Models Against Jailbreaking Attacks"),
    ("2309.00614", "jain_baseline_defenses", "Baseline Defenses for Adversarial Attacks Against Aligned Language Models"),
    ("2305.00944", "wan_instruction_tuning_poisoning", "Poisoning Language Models During Instruction Tuning"),
]

API = "https://export.arxiv.org/api/query?id_list={ids}&max_results={n}"
PDF = "https://arxiv.org/pdf/{id}"
ATOM = "{http://www.w3.org/2005/Atom}"
HEADERS = {"User-Agent": "projet-master-corpus/1.0 (academic use)"}


def _words(title: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", title.lower())


def same_title(expected: str, actual: str) -> bool:
    """Tolère casse, ponctuation et guillemets ; exige les mêmes mots."""
    return _words(expected) == _words(actual)


def arxiv_titles(ids: list[str]) -> dict[str, str]:
    req = urllib.request.Request(API.format(ids=",".join(ids), n=len(ids)), headers=HEADERS)
    with urllib.request.urlopen(req, timeout=60) as r:
        root = ET.fromstring(r.read())
    titles = {}
    for entry in root.findall(f"{ATOM}entry"):
        arxiv_id = entry.findtext(f"{ATOM}id", "").rsplit("/", 1)[-1]
        arxiv_id = re.sub(r"v\d+$", "", arxiv_id)
        titles[arxiv_id] = " ".join(entry.findtext(f"{ATOM}title", "").split())
    return titles


def main():
    parser = argparse.ArgumentParser(description="Télécharge les papers du corpus LLM depuis arXiv.")
    parser.add_argument("--out-dir", default="files/corpus_llm")
    args = parser.parse_args()
    os.makedirs(args.out_dir, exist_ok=True)

    titles = arxiv_titles([p[0] for p in PAPERS])
    ok, skipped = [], []
    for arxiv_id, name, expected in PAPERS:
        path = os.path.join(args.out_dir, f"{name}.pdf")
        actual = titles.get(arxiv_id, "")
        if not same_title(expected, actual):
            print(f"[✗] {arxiv_id} : titre arXiv « {actual or 'introuvable'} » ≠ attendu « {expected} » — sauté")
            skipped.append(arxiv_id)
            continue
        if os.path.exists(path):
            print(f"[=] {name}.pdf déjà présent")
            ok.append(path)
            continue
        req = urllib.request.Request(PDF.format(id=arxiv_id), headers=HEADERS)
        with urllib.request.urlopen(req, timeout=120) as r:
            data = r.read()
        if not data.startswith(b"%PDF"):
            print(f"[✗] {arxiv_id} : la réponse n'est pas un PDF — sauté")
            skipped.append(arxiv_id)
            continue
        with open(path, "wb") as f:
            f.write(data)
        print(f"[✓] {name}.pdf ({len(data) // 1024} Ko) — {actual}")
        ok.append(path)
        time.sleep(3)  # politesse envers arXiv (pas plus d'une requête toutes les 3 s)

    print(f"\n{len(ok)} PDF dans {args.out_dir}" + (f", {len(skipped)} sauté(s) : {', '.join(skipped)}" if skipped else ""))
    print(f"Ensuite : python build_knowledge.py --pdf {args.out_dir} "
          "--table results/knowledge_table_llm.jsonl --skip-existing")


if __name__ == "__main__":
    main()
