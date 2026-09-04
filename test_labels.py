"""
test_labels.py
----------------
Lance UNIQUEMENT Layer 1 (GLiNER) sur un PDF et montre ce que chaque label
attrape. Aucun appel à Ollama : quelques dizaines de secondes au lieu d'une
heure pour un run complet.

Pourquoi ce script existe : mesuré sur le corpus réel, la taxonomie LLM
construite sur les seuls axes du sujet ne ramenait que 8 entités sur 23
chunks (et 0 sur 14). Layer 1 vide, specificity.py et generalizability.py
n'ont plus rien à quoi s'accrocher et produisent des colonnes constantes —
un résultat faux, pas un résultat vide. La cause : GLiNER est un extracteur
d'ENTITÉS NOMMÉES, alors que "impact sur le modèle" ou "mécanisme de
contournement" sont des rôles analytiques, pas des types d'entités.

Régler ça demande d'essayer plusieurs formulations de labels. Le faire via
build_knowledge.py coûterait une heure par essai, presque entièrement passée
dans Layer 2 — qui n'a rien à voir avec la question. D'où ce raccourci.

Usage :
    python test_labels.py --pdf files/Prompt-injection.pdf
    python test_labels.py --pdf files/llm.pdf --domain supply_chain
    python test_labels.py --pdf files/llm.pdf --labels "nom de produit" "organisation"
"""

import argparse
from collections import Counter

from config import DEFAULT_DOMAIN, TOPIC_DOMAINS, topic_config
from generalizability import VENDOR_ENTITY_LABELS_BY_DOMAIN
from gliner_extractor import GLiNERExtractor
from pdf_extractor import chunk_text, extract_text_from_pdf
from specificity import SPECIFIC_ENTITY_LABELS_BY_DOMAIN


def check_label_coherence() -> bool:
    """
    Vérifie que tout label cité par specificity.py / generalizability.py
    existe RÉELLEMENT dans la taxonomie du domaine.

    Ce bug a déjà frappé trois fois : "nom de malware" et "acteur de menace
    (APT)" d'abord, puis les labels supply chain restés en place après le
    passage au domaine LLM, puis "nom de logiciel ou produit" et "système
    d'exploitation" dans generalizability. Un label absent de la taxonomie ne
    matche jamais rien : le filtre devient un no-op silencieux, aucune erreur
    n'est levée, et la colonne se remplit d'une valeur constante qui ressemble
    à un résultat. C'est le mode d'échec le plus coûteux du pipeline — il ne
    se voit qu'en relisant les données. D'où cette vérification statique,
    lancée avant même de charger GLiNER.
    """
    coherent = True
    for domain in sorted(TOPIC_DOMAINS):
        taxonomy = set(topic_config(domain)["labels"])
        for module_name, table in (
            ("specificity", SPECIFIC_ENTITY_LABELS_BY_DOMAIN),
            ("generalizability", VENDOR_ENTITY_LABELS_BY_DOMAIN),
        ):
            orphans = table.get(domain, frozenset()) - taxonomy
            if orphans:
                coherent = False
                print(
                    f"[!] {module_name}.py, domaine {domain!r} : "
                    f"{sorted(orphans)} n'existe(nt) pas dans la taxonomie "
                    f"Layer 1 de ce domaine — ce filtre ne matchera jamais rien."
                )
    print("Cohérence des labels :", "OK" if coherent else "PROBLÈME (voir ci-dessus)")
    return coherent


def main():
    parser = argparse.ArgumentParser(
        description="Teste les labels Layer 1 (GLiNER seul, sans Ollama)."
    )
    parser.add_argument("--pdf", required=True)
    parser.add_argument("--domain", default=DEFAULT_DOMAIN, choices=sorted(TOPIC_DOMAINS))
    parser.add_argument(
        "--labels",
        nargs="+",
        default=None,
        help="Labels à tester à la place de ceux du domaine — pour essayer une "
        "formulation avant de la graver dans config.py.",
    )
    parser.add_argument("--max-chunks", type=int, default=None)
    args = parser.parse_args()

    check_label_coherence()
    labels = args.labels or topic_config(args.domain)["labels"]

    text = extract_text_from_pdf(args.pdf)
    chunks = [c for _, c in chunk_text(text)]
    if args.max_chunks:
        chunks = chunks[: args.max_chunks]
    print(f"{args.pdf} -> {len(chunks)} chunk(s)\nLabels testés ({len(labels)}) :")
    for label in labels:
        print(f"  - {label}")

    gliner = GLiNERExtractor(labels=labels)
    entities = [e for chunk in chunks for e in gliner.extract(chunk)["entities"]]

    print(f"\n{'=' * 62}\n{len(entities)} entité(s) sur {len(chunks)} chunk(s) "
          f"({len(entities) / max(len(chunks), 1):.1f} par chunk)\n{'=' * 62}")

    par_label = Counter(e.get("label") for e in entities)
    identifiants = SPECIFIC_ENTITY_LABELS_BY_DOMAIN.get(args.domain, frozenset())
    for label in labels:
        n = par_label.get(label, 0)
        marque = " [identifiant -> marque un cas comme concret]" if label in identifiants else ""
        print(f"\n  {n:4}  {label}{marque}")
        exemples = Counter(
            e.get("text", "").strip() for e in entities if e.get("label") == label
        )
        for texte, k in exemples.most_common(6):
            print(f"          {k:3}x {texte[:70]}")
        if n == 0:
            print("          (rien — label probablement inadapté à GLiNER,")
            print("           ou absent de ce papier)")

    n_ident = sum(par_label.get(label, 0) for label in identifiants)
    print(f"\n{'-' * 62}")
    print(f"Entités IDENTIFIANTES (celles qui font basculer un cas en "
          f"'concrete') : {n_ident}")
    if n_ident == 0:
        print("[!] Aucune. specificity.py marquera TOUS les cas 'generic' et")
        print("    generalizability.py notera TOUT à 1.0 — des colonnes")
        print("    constantes qui ressemblent à un résultat mais n'en sont pas.")
        print("    Essayer d'autres formulations avec --labels avant de lancer")
        print("    un run complet.")


if __name__ == "__main__":
    main()
