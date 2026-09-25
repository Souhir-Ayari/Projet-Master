"""
test_retrieval.py
-------------------
Teste le retrieval Step 6 (Tier 1) sur quelques requêtes MANUELLES, dont on
connaît à l'avance la famille d'attaque attendue, et vérifie que les bons cas
remontent dans le top-k de la table de connaissance.

Pourquoi ce script existe : query_knowledge.py affiche un JSON brut, un cas à
la fois. Pour juger si le retrieval fonctionne, il faut voir côte à côte, pour
chaque requête, ce qui remonte, de quel papier, avec quelle catégorie ATLAS —
et distinguer un vrai raté d'une requête dont la catégorie n'existe tout
simplement pas dans le corpus (25 enregistrements ne couvrent pas les 23
techniques de la short-list : un "raté" hors corpus n'est pas un bug du
retrieval, c'est la limite de taille du corpus).

Le critère "bon cas" est volontairement simple et reproductible : la
catégorie du cas remonté appartient à l'ensemble des techniques ATLAS
attendues pour la requête. Ne remplace PAS la relecture des résumés remontés
— un cas de la bonne catégorie peut rester hors-sujet, et inversement.

Mode --offline : vérifie sans Ollama ni table réelle (embeddings simulés) que
attack_summary est bien transmis de retrieve() à Tier 2 — requête live
construite à partir du résumé quand l'attaque n'a ni CVE, ni paquet, ni ID
MITRE, et résumé présent dans le journal Tier 2.

Usage :
    python test_retrieval.py                       # table par défaut, top-3
    python test_retrieval.py --table results/knowledge_table.jsonl --top-k 5
    python test_retrieval.py --offline             # contrôle du fix, sans Ollama
    python test_retrieval.py --table results/knowledge_table_llm.jsonl --output files/retrieval_top3.txt
"""

import argparse
import os
import sys
import tempfile
from collections import Counter

import retrieval
from config import KNOWLEDGE_TABLE_PATH, RETRIEVAL_SIMILARITY_THRESHOLD
from jsonl_utils import read_jsonl
from knowledge_table import load_table, vector_paths_for
from vector_store import add_vectors


# Requêtes rédigées à la main, en anglais comme les attack_summary de la table
# (nomic-embed-text est entraîné surtout sur de l'anglais : une requête en
# français contre des résumés en anglais mesure la traduction, pas le
# retrieval). Chacune décrit une attaque SANS reprendre le nom de la
# technique, pour ne pas tester un simple recouvrement de mots-clés.
QUERIES = [
    {
        "name": "injection indirecte via page web",
        "attack_summary": (
            "A web page retrieved by the assistant contains hidden instructions "
            "that make it send the user's conversation to an attacker-controlled URL."
        ),
        "expected_categories": {"AML.T0051.001", "AML.T0051", "AML.T0093", "AML.T0086"},
    },
    {
        "name": "fuite du prompt système",
        "attack_summary": (
            "The user asks the chatbot to repeat everything above this message, "
            "and the model reveals its hidden configuration instructions."
        ),
        "expected_categories": {"AML.T0056", "AML.T0069", "AML.T0069.002", "AML.T0057"},
    },
    {
        "name": "jailbreak par jeu de rôle",
        "attack_summary": (
            "The attacker asks the model to role-play a fictional character without "
            "rules, which makes it produce content its safety training should refuse."
        ),
        "expected_categories": {"AML.T0054", "AML.T0065", "AML.T0068", "AML.T0015"},
    },
    {
        "name": "empoisonnement de la base RAG",
        "attack_summary": (
            "The attacker plants a crafted document in the knowledge base so that "
            "the retrieval step feeds it to the model and changes its answers."
        ),
        "expected_categories": {"AML.T0070", "AML.T0071", "AML.T0080", "AML.T0020"},
    },
]


def run_queries(table_path: str, top_k: int) -> None:
    table = load_table(table_path)
    if not table:
        print(f"[✗] Table vide ou absente : {table_path} — lancer build_knowledge.py d'abord.")
        return
    attack_vectors_path, _ = vector_paths_for(table_path)

    categories_in_table = Counter(r.get("category") for r in table)
    papers = sorted({r.get("source_paper") for r in table if r.get("source_paper")})
    print(f"Table : {table_path} — {len(table)} enregistrements, {len(papers)} papier(s)")
    print("Catégories présentes :", dict(categories_in_table.most_common()))

    hits, evaluable = 0, 0
    for query in QUERIES:
        expected = query["expected_categories"]
        in_corpus = sum(categories_in_table.get(c, 0) for c in expected)

        results = retrieval.tier1_retrieve(
            query["attack_summary"],
            table=table,
            attack_vectors_path=attack_vectors_path,
            top_k=top_k,
        )
        n_good = sum(1 for r in results if r.get("category") in expected)

        print(f"\n=== {query['name']}")
        print(f"    requête : {query['attack_summary']}")
        print(f"    attendu : {sorted(expected)} — {in_corpus} cas dans la table")
        for rank, r in enumerate(results, 1):
            mark = "✓" if r.get("category") in expected else "·"
            print(
                f"    {mark} #{rank} [{r['similarity_score']:.3f}] "
                f"[{r.get('category') or 'non validée'}] [{r.get('specificity')}] "
                f"({r.get('source_paper')})"
            )
            print(f"          {(r.get('attack_summary') or '')[:110]}")
        if results and results[0]["similarity_score"] < RETRIEVAL_SIMILARITY_THRESHOLD:
            print(
                f"    [!] meilleur score {results[0]['similarity_score']:.3f} < seuil "
                f"{RETRIEVAL_SIMILARITY_THRESHOLD} : Tier 2 serait déclenché"
            )

        if in_corpus == 0:
            print("    -> HORS CORPUS : aucun cas de cette famille dans la table, "
                  "raté attendu (limite de taille du corpus, pas du retrieval)")
            continue
        evaluable += 1
        if n_good:
            hits += 1
            print(f"    -> OK : {n_good}/{len(results)} cas de la bonne famille dans le top-{top_k}")
        else:
            print(f"    -> RATÉ : aucun cas de la bonne famille dans le top-{top_k}")

    print(f"\nHit@{top_k} : {hits}/{evaluable} requêtes évaluables "
          f"({len(QUERIES) - evaluable} hors corpus)")


def check_attack_summary_forwarding() -> bool:
    """
    Contrôle hors ligne du fix : sans CVE, paquet ni catégorie (cas typique du
    domaine "llm"), Tier 2 doit chercher à partir de attack_summary au lieu de
    lever une ValueError, et le journal Tier 2 doit contenir le résumé.
    """
    fake_vectors = {
        "injection": [1.0, 0.0, 0.0],
        "leak": [0.0, 1.0, 0.0],
        "query": [0.2, 0.2, 0.9],  # loin de tout : force best_score < seuil
    }
    table = [
        {"record_id": "a", "attack_summary": "injection", "category": "AML.T0051.001"},
        {"record_id": "b", "attack_summary": "leak", "category": "AML.T0056"},
    ]
    summary = "query"
    captured = {}

    def fake_search(query, max_results, timeout=20):
        captured["query"] = query
        return [{"title": "stub"}]

    saved = (
        retrieval.embed_text,
        retrieval.TIER2_ENABLED,
        retrieval.TIER2_LOG_PATH,
        retrieval._search_semantic_scholar,
    )
    ok = True
    with tempfile.TemporaryDirectory() as tmp:
        vectors_path = os.path.join(tmp, "attack.npz")
        add_vectors(vectors_path, ["a", "b"], [fake_vectors["injection"], fake_vectors["leak"]])
        log_path = os.path.join(tmp, "tier2_log.jsonl")
        retrieval.embed_text = lambda text: fake_vectors[text]
        retrieval.TIER2_LOG_PATH = log_path
        retrieval._search_semantic_scholar = fake_search
        try:
            for enabled in (True, False):
                retrieval.TIER2_ENABLED = enabled
                result = retrieval.retrieve(
                    summary, table=table, attack_vectors_path=vectors_path
                )
                if result["query"]["attack_summary"] != summary:
                    print(f"[✗] TIER2_ENABLED={enabled} : résumé absent de result['query']")
                    ok = False
                if enabled and captured.get("query") != summary:
                    print(f"[✗] requête Tier 2 = {captured.get('query')!r}, attendu {summary!r}")
                    ok = False
        except ValueError as e:
            print(f"[✗] Tier 2 lève encore une ValueError sans identifiant : {e}")
            ok = False
        finally:
            (
                retrieval.embed_text,
                retrieval.TIER2_ENABLED,
                retrieval.TIER2_LOG_PATH,
                retrieval._search_semantic_scholar,
            ) = saved

        log = read_jsonl(log_path)
        if len(log) != 2 or any(e["query"].get("attack_summary") != summary for e in log):
            print(f"[✗] journal Tier 2 sans attack_summary : {log}")
            ok = False

    print("[✓] attack_summary transmis à Tier 2 et journalisé" if ok else "[✗] contrôle échoué")
    return ok


class _Tee:
    """
    Écrit la sortie à la fois dans le terminal et dans un fichier UTF-8.

    Une redirection PowerShell (`> fichier.txt`) écrit en UTF-16 et, sous
    Windows, fait planter print() sur les caractères hors cp1252 (✓, «, ✗)
    dès que la sortie n'est plus une console : --output évite les deux.
    """

    def __init__(self, path: str):
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        self.file = open(path, "w", encoding="utf-8")
        self.console = sys.stdout

    def write(self, text: str) -> None:
        self.file.write(text)
        try:
            self.console.write(text)
        except UnicodeEncodeError:
            self.console.write(text.encode("ascii", "replace").decode("ascii"))

    def flush(self) -> None:
        self.file.flush()
        self.console.flush()


def main():
    parser = argparse.ArgumentParser(
        description="Teste le retrieval Tier 1 sur des requêtes manuelles (Step 6)."
    )
    parser.add_argument("--table", default=KNOWLEDGE_TABLE_PATH)
    parser.add_argument("--top-k", type=int, default=3)
    parser.add_argument(
        "--offline",
        action="store_true",
        help="Contrôle seulement la transmission de attack_summary à Tier 2 "
        "(embeddings simulés, sans Ollama ni table réelle).",
    )
    parser.add_argument(
        "--output",
        default=None,
        help="Enregistre aussi la sortie dans ce fichier texte UTF-8 "
        "(ex: files/retrieval_top3.txt), dossier créé si besoin.",
    )
    args = parser.parse_args()

    if args.output:
        sys.stdout = _Tee(args.output)
        print(f"# python test_retrieval.py {' '.join(sys.argv[1:])}\n")

    if args.offline:
        raise SystemExit(0 if check_attack_summary_forwarding() else 1)
    run_queries(args.table, args.top_k)


if __name__ == "__main__":
    main()
