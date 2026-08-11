"""
retrieval.py
-------------
Step 6 du pipeline méthodologie/mitigation, en DEUX niveaux :

  Tier 1 : similarité d'embedding (+ bonus catégorie MITRE) contre la table
           de connaissance existante (knowledge_table.jsonl). Rapide, hors
           ligne, c'est le chemin par défaut.
  Tier 2 : seulement si le meilleur score de Tier 1 est sous
           RETRIEVAL_SIMILARITY_THRESHOLD ET config.TIER2_ENABLED est vrai —
           recherche live (Semantic Scholar, puis arXiv en repli) à partir
           des identifiants de l'attaque (CVE, paquet, ID MITRE). Journalisé
           SYSTÉMATIQUEMENT (requête + résultat), y compris quand rien
           d'exploitable ne revient — ce journal devient la preuve que la
           couverture du corpus grandit dans le temps.

Le flag TIER2_ENABLED (config.py, False par défaut) fait de "statique vs
augmenté" une ablation contrôlable dès le départ, pas une réécriture
ultérieure.

Ce module ne fait QUE chercher et journaliser Tier 2 — l'ingestion réelle
(télécharger le PDF trouvé, le faire passer par Layer1->Layer2, l'ajouter à
la table) reste à la charge du script orchestrateur, qui a accès au pipeline
PDF complet. Ce découpage évite de coupler ce module de recherche au reste
du pipeline d'extraction.
"""

import math
import time
import xml.etree.ElementTree as ET

import requests

from config import (
    ARXIV_API_URL,
    RETRIEVAL_SIMILARITY_THRESHOLD,
    SEMANTIC_SCHOLAR_API_URL,
    TIER2_ENABLED,
    TIER2_LOG_PATH,
    TIER2_MAX_RESULTS,
)
from jsonl_utils import append_jsonl
from knowledge_table import embed_text, load_table


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


def tier1_retrieve(
    query_attack_summary: str,
    query_category: str = None,
    table: list[dict] = None,
    top_k: int = 3,
) -> list[dict]:
    """
    Similarité cosinus entre l'embedding de query_attack_summary et
    attack_embedding de chaque enregistrement de la table. Un léger bonus est
    ajouté si query_category correspond exactement (même ID MITRE validé) —
    la similarité sémantique seule peut confondre deux attaques de la même
    famille conceptuelle mais de catégorie MITRE différente.
    """
    table = table if table is not None else load_table()
    if not table:
        return []

    query_embedding = embed_text(query_attack_summary)
    scored = []
    for record in table:
        record_embedding = record.get("attack_embedding")
        if not record_embedding:
            continue
        similarity = _cosine_similarity(query_embedding, record_embedding)
        if query_category and record.get("category") == query_category:
            similarity = min(1.0, similarity + 0.05)
        scored.append((similarity, record))

    scored.sort(key=lambda pair: pair[0], reverse=True)
    return [
        {**record, "similarity_score": round(score, 4)}
        for score, record in scored[:top_k]
    ]


def _log_tier2_trigger(query: dict, outcome: str, n_ingested: int = 0) -> None:
    """
    Journalise CHAQUE déclenchement de Tier 2, succès ou échec — la preuve
    que la couverture du corpus grandit dans le temps, même (surtout) quand
    une recherche ne ramène rien d'exploitable.
    """
    append_jsonl(
        TIER2_LOG_PATH,
        {
            "timestamp": time.time(),
            "query": query,
            "outcome": outcome,
            "n_ingested": n_ingested,
        },
    )


def _build_tier2_query(cve: str = None, package: str = None, mitre_id: str = None) -> str:
    """Construit une requête textuelle à partir des identifiants disponibles de l'attaque."""
    parts = [p for p in (cve, package, mitre_id) if p]
    if not parts:
        raise ValueError(
            "Au moins un identifiant (cve, package ou mitre_id) est requis pour Tier 2."
        )
    return " ".join(parts)


def _search_semantic_scholar(query: str, max_results: int, timeout: int = 20) -> list[dict]:
    try:
        response = requests.get(
            SEMANTIC_SCHOLAR_API_URL,
            params={
                "query": query,
                "limit": max_results,
                "fields": "title,abstract,url,externalIds",
            },
            timeout=timeout,
        )
        response.raise_for_status()
        return response.json().get("data", [])
    except requests.exceptions.RequestException as e:
        print(f"[⚠] Semantic Scholar indisponible ({e}) — bascule sur arXiv.")
        return []


def _parse_arxiv_atom(atom_xml: str) -> list[dict]:
    """Parsing minimal du flux Atom d'arXiv : titre + lien PDF, suffisant pour Tier 2."""
    ns = {"atom": "http://www.w3.org/2005/Atom"}
    root = ET.fromstring(atom_xml)
    results = []
    for entry in root.findall("atom:entry", ns):
        title_el = entry.find("atom:title", ns)
        title = title_el.text.strip() if title_el is not None and title_el.text else ""
        pdf_url = None
        for link in entry.findall("atom:link", ns):
            if link.get("title") == "pdf" or link.get("type") == "application/pdf":
                pdf_url = link.get("href")
        results.append({"title": title, "pdf_url": pdf_url})
    return results


def _search_arxiv(query: str, max_results: int, timeout: int = 20) -> list[dict]:
    try:
        response = requests.get(
            ARXIV_API_URL,
            params={"search_query": f"all:{query}", "max_results": max_results},
            timeout=timeout,
        )
        response.raise_for_status()
        return _parse_arxiv_atom(response.text)
    except (requests.exceptions.RequestException, ET.ParseError) as e:
        print(f"[⚠] arXiv indisponible ({e}).")
        return []


def tier2_search(
    cve: str = None,
    package: str = None,
    mitre_id: str = None,
    max_results: int = TIER2_MAX_RESULTS,
) -> list[dict]:
    """
    Construit une requête à partir des identifiants disponibles de l'attaque,
    cherche sur Semantic Scholar puis arXiv en repli. Journalise
    systématiquement le déclenchement (voir _log_tier2_trigger), y compris en
    cas d'échec réseau des deux sources.
    """
    query = _build_tier2_query(cve, package, mitre_id)
    results = _search_semantic_scholar(query, max_results)
    source = "semantic_scholar"
    if not results:
        results = _search_arxiv(query, max_results)
        source = "arxiv"

    outcome = f"{len(results)} résultat(s) via {source}" if results else "aucun résultat exploitable"
    _log_tier2_trigger(
        query={"cve": cve, "package": package, "mitre_id": mitre_id, "text": query},
        outcome=outcome,
    )
    return results


def retrieve(
    query_attack_summary: str,
    query_category: str = None,
    cve: str = None,
    package: str = None,
    table: list[dict] = None,
    threshold: float = RETRIEVAL_SIMILARITY_THRESHOLD,
) -> dict:
    """
    Point d'entrée Step 6 : Tier 1 d'abord, Tier 2 seulement si le meilleur
    score de Tier 1 est sous `threshold` ET config.TIER2_ENABLED est vrai.
    Tier 2 ne fait ICI que la recherche + journalisation (tier2_search) :
    l'ingestion réelle (téléchargement + Layer1->Layer2 + append à la table)
    reste à la charge du script orchestrateur.
    """
    tier1_results = tier1_retrieve(query_attack_summary, query_category, table)
    best_score = tier1_results[0]["similarity_score"] if tier1_results else 0.0

    result = {
        "tier1_results": tier1_results,
        "best_score": best_score,
        "tier2_triggered": False,
        "tier2_search_results": [],
    }

    if best_score < threshold:
        if TIER2_ENABLED:
            result["tier2_triggered"] = True
            result["tier2_search_results"] = tier2_search(
                cve=cve, package=package, mitre_id=query_category
            )
        else:
            _log_tier2_trigger(
                query={"cve": cve, "package": package, "mitre_id": query_category},
                outcome=(
                    f"Tier 2 aurait été déclenché (best_score={best_score:.3f} "
                    f"< {threshold}) mais TIER2_ENABLED=False"
                ),
            )

    return result
