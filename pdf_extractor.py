"""
pdf_extractor.py
----------------
Extraction du texte brut depuis un fichier PDF (rapport de threat intelligence,
CERT advisory, etc.), avec nettoyage léger et découpage en chunks si le texte
est trop long pour être envoyé en un seul appel au LLM.
"""

import re
import pdfplumber


def extract_text_from_pdf(pdf_path: str) -> str:
    """Extrait tout le texte d'un PDF, page par page."""
    full_text = []
    with pdfplumber.open(pdf_path) as pdf:
        for i, page in enumerate(pdf.pages):
            page_text = page.extract_text() or ""
            full_text.append(page_text)
    text = "\n".join(full_text)
    text = strip_references_section(text)
    return _clean_text(text)


def strip_references_section(text: str) -> str:
    """
    Coupe le texte à partir de la section références/bibliographie (heuristique
    sur le titre de section). Sans ça, les chunks qui tombent dans la
    bibliographie sont envoyés au LLM comme n'importe quel autre texte, qui en
    extrait alors des fragments de citations cassées ("[35] M. Giannelis..."),
    gonflant artificiellement les faux positifs.

    Regex élargie par rapport à la v1 (qui ne matchait que "References" seul
    sur sa ligne) : accepte un préfixe de numérotation de section
    ("5. References", "VI. Bibliography"), l'accent français ("Références"),
    et les intitulés alternatifs ("Works Cited", "Reference List", "Sources")
    — la version stricte ratait la plupart des papiers académiques, dont le
    titre de section de bibliographie est presque toujours numéroté.
    """
    pattern = re.compile(
        r"\n[ \t]*(?:(?:[ivxlcdm]{1,6}|\d{1,2})[.\)][ \t]*)?"
        r"(references|références|bibliographie|bibliography|works cited|reference list|sources)"
        r"[ \t]*:?[ \t]*\n",
        re.IGNORECASE,
    )
    match = pattern.search(text)
    return text[: match.start()] if match else text


def _clean_text(text: str) -> str:
    """Nettoyage léger : espaces multiples, sauts de ligne parasites."""
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def chunk_text(
    text: str, max_chars: int = 3000, overlap: int = 200
) -> list[tuple[int, str]]:
    """
    Découpe le texte en chunks avec chevauchement, pour respecter la fenêtre
    de contexte du LLM et éviter de couper une entité entre deux chunks.

    Renvoie une liste de tuples (start_idx, chunk_text) — la position de
    départ RÉELLE de chaque chunk dans le texte original. C'est nécessaire
    pour recaler correctement les offsets d'entités GLiNER sur le document
    entier (voir gliner_extractor.extract_from_chunks) : recalculer l'offset
    cumulé via len(chunk) serait faux à cause du chevauchement (overlap) entre
    chunks consécutifs, alors que start_idx est exact par construction.
    """
    if len(text) <= max_chars:
        return [(0, text)]

    chunks = []
    start = 0
    while start < len(text):
        end = start + max_chars
        chunks.append((start, text[start:end]))
        start = end - overlap
    return chunks


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Usage: python pdf_extractor.py <chemin_vers_pdf>")
        sys.exit(1)

    txt = extract_text_from_pdf(sys.argv[1])
    print(f"Longueur du texte extrait : {len(txt)} caractères")
    print(txt[:1000])
