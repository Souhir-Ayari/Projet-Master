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

import os
import time
import xml.etree.ElementTree as ET

import requests

from config import (
    ARXIV_API_URL,
    KNOWLEDGE_ATTACK_VECTORS_PATH,
    RETRIEVAL_CATEGORY_BONUS,
    RETRIEVAL_SIMILARITY_THRESHOLD,
    SEMANTIC_SCHOLAR_API_URL,
    TIER2_ENABLED,
    TIER2_LOG_PATH,
    TIER2_MAX_RESULTS,
    TIER2_SUMMARY_MAX_WORDS,
)
from jsonl_utils import append_jsonl
from knowledge_table import embed_text, load_table
from vector_store import cosine_similarities, load_vectors


class VectorStoreError(Exception):
    """Levée quand la table et son store vectoriel ne permettent aucun retrieval."""


def check_vector_store(table: list[dict], attack_vectors_path: str) -> dict:
    """
    Vérifie que la table et son store vectoriel d'attaque sont utilisables
    ENSEMBLE, et lève VectorStoreError avec un diagnostic sinon.

    Sans ce contrôle, tier1_retrieve renvoyait silencieusement [] dans deux
    cas indiscernables en sortie (best_score=0.0, aucun cas) : le fichier .npz
    est absent — le plus souvent parce que la table a été construite sous un
    autre nom, et ses vecteurs avec elle —, ou bien il existe mais aucun de ses
    record_id n'est dans la table (table reconstruite ou remplacée sans ses
    vecteurs). En aval, la boucle Propose-Verify-Revise tournait alors sur zéro
    cas et rejetait tout, ce qui ressemblait à un échec de la boucle.
    """
    table_ids = {r["record_id"] for r in table}
    if not os.path.exists(attack_vectors_path):
        raise VectorStoreError(
            f"Store vectoriel introuvable : {attack_vectors_path}\n"
            "    Les vecteurs d'une table portent le nom de la table "
            "(<table>_attack_vectors.npz), sauf pour la table par défaut "
            "(knowledge_attack_vectors.npz). Vérifier les .npz présents dans "
            "results/ : renommer le bon fichier, ou reconstruire la table."
        )
    ids, matrix = load_vectors(attack_vectors_path)
    matched = sum(1 for i in ids if i in table_ids)
    report = {
        "vectors_path": attack_vectors_path,
        "n_vectors": int(len(ids)),
        "n_records": len(table),
        "n_matched": matched,
    }
    if matrix.size == 0 or matched == 0:
        raise VectorStoreError(
            f"Aucun des {len(ids)} vecteurs de {attack_vectors_path} ne "
            f"correspond aux {len(table)} record_id de la table : la table et "
            "ses vecteurs sont désynchronisés (table reconstruite ou copiée "
            "sans ses vecteurs). Reprendre le .npz produit en même temps que "
            "cette table, ou reconstruire la table."
        )
    if matched < len(table_ids):
        print(
            f"[⚠] {len(table_ids) - matched} enregistrement(s) de la table sans "
            f"vecteur dans {attack_vectors_path} : ils ne pourront jamais remonter."
        )
    return report


def score_cases(
    similarities,
    ids,
    record_by_id: dict,
    query_category: str = None,
    category_bonus: float = RETRIEVAL_CATEGORY_BONUS,
    category_filter: bool = False,
    top_k: int = 3,
) -> list[dict]:
    """
    Classe les cas à partir des similarités cosinus déjà calculées.

    Séparé de tier1_retrieve pour que la calibration (calibrate_retrieval.py)
    puisse comparer plusieurs réglages de α et du filtre sur les MÊMES
    embeddings, sans rappeler Ollama pour chaque réglage.

    category_bonus : α, ajouté au cosinus quand la catégorie du cas est
        exactement query_category (score plafonné à 1).
    category_filter : si vrai et query_category connue, ne garde que les cas
        de cette catégorie — avec repli sur tous les cas si la table n'en
        contient aucun, pour ne pas confondre "catégorie absente du corpus"
        et "aucun cas proche".
    Chaque résultat porte similarity_score (avec bonus, utilisé pour le
    classement et le seuil) ET cosine_score (brut), pour pouvoir dériver θ
    de l'historique sans l'effet du bonus.
    """
    scored = []
    for record_id, cosine in zip(ids, similarities):
        record = record_by_id.get(record_id)
        if record is None:
            continue  # vecteur orphelin (rare : table_path et vectors_path désynchronisés)
        cosine = float(cosine)
        score = cosine
        if query_category and record.get("category") == query_category:
            score = min(1.0, cosine + category_bonus)
        scored.append((score, cosine, record))

    if category_filter and query_category:
        same = [t for t in scored if t[2].get("category") == query_category]
        scored = same or scored

    scored.sort(key=lambda t: t[0], reverse=True)
    return [
        {**record, "similarity_score": round(score, 4), "cosine_score": round(cosine, 4)}
        for score, cosine, record in scored[:top_k]
    ]


def tier1_retrieve(
    query_attack_summary: str,
    query_category: str = None,
    table: list[dict] = None,
    attack_vectors_path: str = KNOWLEDGE_ATTACK_VECTORS_PATH,
    top_k: int = 3,
    category_bonus: float = RETRIEVAL_CATEGORY_BONUS,
    category_filter: bool = False,
) -> list[dict]:
    """
    Similarité cosinus, calculée vectoriellement (vector_store.
    cosine_similarities) en une seule opération numpy plutôt qu'une boucle
    Python par enregistrement, entre l'embedding de query_attack_summary et
    TOUS les attack_embedding stockés dans attack_vectors_path (voir
    knowledge_table.py : les embeddings ne sont plus inline dans le JSONL).
    La catégorie de la requête, si connue, intervient via score_cases
    (bonus α ou filtre) — la similarité sémantique seule peut confondre deux
    attaques de la même famille conceptuelle mais de catégorie différente.
    """
    table = table if table is not None else load_table()
    if not table:
        return []

    record_by_id = {record["record_id"]: record for record in table}
    ids, matrix = load_vectors(attack_vectors_path)
    if matrix.size == 0:
        return []

    query_embedding = embed_text(query_attack_summary)
    similarities = cosine_similarities(query_embedding, matrix)
    return score_cases(
        similarities, ids, record_by_id, query_category,
        category_bonus=category_bonus, category_filter=category_filter, top_k=top_k,
    )


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


def _build_tier2_query(
    cve: str = None,
    package: str = None,
    mitre_id: str = None,
    attack_summary: str = None,
    max_summary_words: int = TIER2_SUMMARY_MAX_WORDS,
) -> str:
    """
    Construit une requête textuelle à partir des identifiants disponibles de
    l'attaque, et à défaut de son résumé.

    Les identifiants (CVE, paquet, ID MITRE) restent prioritaires : ils sont
    précis et courts, exactement ce qu'attend une recherche par mots-clés.
    Mais sur le domaine "llm", une nouvelle attaque n'a presque jamais de CVE
    ni de paquet, et l'ID MITRE est souvent inconnu au moment de la requête :
    sans repli sur attack_summary, Tier 2 levait une ValueError alors que la
    description de l'attaque était bien disponible (elle n'était simplement
    pas transmise depuis retrieve()). Le résumé est tronqué : une phrase
    entière noie les termes discriminants dans la recherche Semantic
    Scholar/arXiv.
    """
    parts = [p for p in (cve, package, mitre_id) if p]
    if parts:
        return " ".join(parts)
    if attack_summary and attack_summary.strip():
        return " ".join(attack_summary.split()[:max_summary_words])
    raise ValueError(
        "Au moins un identifiant (cve, package ou mitre_id) ou un résumé "
        "d'attaque est requis pour Tier 2."
    )


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
    attack_summary: str = None,
    max_results: int = TIER2_MAX_RESULTS,
) -> list[dict]:
    """
    Construit une requête à partir des identifiants disponibles de l'attaque
    (ou de son résumé à défaut, voir _build_tier2_query), cherche sur Semantic Scholar puis arXiv en repli. Journalise
    systématiquement le déclenchement (voir _log_tier2_trigger), y compris en
    cas d'échec réseau des deux sources.
    """
    query = _build_tier2_query(cve, package, mitre_id, attack_summary)
    results = _search_semantic_scholar(query, max_results)
    source = "semantic_scholar"
    if not results:
        results = _search_arxiv(query, max_results)
        source = "arxiv"

    outcome = f"{len(results)} résultat(s) via {source}" if results else "aucun résultat exploitable"
    _log_tier2_trigger(
        query={
            "attack_summary": attack_summary,
            "cve": cve,
            "package": package,
            "mitre_id": mitre_id,
            "text": query,
        },
        outcome=outcome,
    )
    return results


def retrieve(
    query_attack_summary: str,
    query_category: str = None,
    cve: str = None,
    package: str = None,
    table: list[dict] = None,
    attack_vectors_path: str = KNOWLEDGE_ATTACK_VECTORS_PATH,
    threshold: float = RETRIEVAL_SIMILARITY_THRESHOLD,
) -> dict:
    """
    Point d'entrée Step 6 : Tier 1 d'abord, Tier 2 seulement si le meilleur
    score de Tier 1 est sous `threshold` ET config.TIER2_ENABLED est vrai.
    Tier 2 ne fait ICI que la recherche + journalisation (tier2_search) :
    l'ingestion réelle (téléchargement + Layer1->Layer2 + append à la table)
    reste à la charge du script orchestrateur.
    """
    tier1_results = tier1_retrieve(
        query_attack_summary, query_category, table, attack_vectors_path
    )
    best_score = tier1_results[0]["similarity_score"] if tier1_results else 0.0

    result = {
        # Requête renvoyée avec le résultat : sans elle, une sortie de
        # query_knowledge.py sauvegardée pour l'évaluation ne dit plus à
        # quelle attaque ses cas répondent.
        "query": {
            "attack_summary": query_attack_summary,
            "category": query_category,
            "cve": cve,
            "package": package,
        },
        "tier1_results": tier1_results,
        "best_score": best_score,
        "threshold": threshold,
        # tier2_triggered vaut toujours False tant que TIER2_ENABLED=False :
        # seul, il confond "score suffisant, Tier 2 inutile" et "score
        # insuffisant, Tier 2 nécessaire mais désactivé". tier2_would_trigger
        # expose ce second cas dans le JSON lui-même (et plus seulement dans
        # tier2_retrieval_log.jsonl), pour pouvoir le citer comme preuve dans
        # la section limitations du papier.
        "tier2_would_trigger": best_score < threshold,
        "tier2_enabled": TIER2_ENABLED,
        "tier2_triggered": False,
        "tier2_search_results": [],
    }

    if result["tier2_would_trigger"]:
        if TIER2_ENABLED:
            result["tier2_triggered"] = True
            result["tier2_search_results"] = tier2_search(
                cve=cve,
                package=package,
                mitre_id=query_category,
                attack_summary=query_attack_summary,
            )
        else:
            _log_tier2_trigger(
                query={
                    "attack_summary": query_attack_summary,
                    "cve": cve,
                    "package": package,
                    "mitre_id": query_category,
                },
                outcome=(
                    f"Tier 2 aurait été déclenché (best_score={best_score:.3f} "
                    f"< {threshold}) mais TIER2_ENABLED=False"
                ),
            )

    return result
