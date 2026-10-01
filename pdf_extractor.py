"""
pdf_extractor.py
----------------
Extraction du texte brut depuis un fichier PDF (rapport de threat intelligence,
CERT advisory, etc.), avec nettoyage léger et découpage en chunks si le texte
est trop long pour être envoyé en un seul appel au LLM.
"""

import re
import pdfplumber

# Aucun mot anglais ou français courant n'atteint cette longueur ; au-delà,
# c'est presque toujours plusieurs mots soudés par une extraction ratée.
LONGUEUR_MOT_MAX_PLAUSIBLE = 20

# pdfplumber n'insère un espace entre deux caractères que si l'écart
# horizontal dépasse x_tolerance (3 points par défaut). Sur un PDF au crénage
# serré, les espaces réels tombent sous ce seuil et disparaissent :
# "Bing Chat currently runs on the GPT-4 model" ressort en
# "BingChatcurrentlyrunsontheGPT-4model". Constaté sur Greshake et al., où
# GLiNER extrayait des entités comme "BingChatincentivizedustofollowthelink".
#
# Baisser le seuil aveuglément est risqué dans l'autre sens : trop bas, chaque
# crénage interne devient un espace et "attack" ressort en "att ack". D'où
# l'essai de plusieurs valeurs et la sélection de la MOINS mauvaise, mesurée
# sur le texte produit (_score_extraction) plutôt que devinée par PDF.
_TOLERANCES_A_ESSAYER = (None, 1.5, 1.0, 0.5)  # None = valeur par défaut de pdfplumber


# Mots courts LÉGITIMES (anglais et français). Sans cette liste, la détection
# de sur-découpe compterait "on", "of", "to", "le", "de" comme des fragments :
# un texte parfaitement extrait obtiendrait alors un mauvais score, et la
# comparaison entre réglages serait faussée dès le départ.
_MOTS_COURTS_LEGITIMES = frozenset(
    "a i o y an as at be by do go he if in is it me my no of on or so to up us "
    "we am id ai ml "
    "à y a au ce ces de du en et il je la le les ma me mes ne on ou où sa se "
    "si son ta te tu un une va vu".split()
)


def _mots_alphabetiques(text: str) -> list[str]:
    return re.findall(r"[A-Za-zÀ-ÿ]+", text)


def _score_extraction(text: str) -> float:
    """
    Note de MAUVAISE qualité d'une extraction (0 = parfait). Combine les deux
    façons de rater le placement des espaces, qui tirent en sens opposés :

      - mots soudés  : proportion de jetons plus longs qu'un mot plausible ;
      - sur-découpe  : proportion de jetons d'une ou deux lettres qui ne sont
        pas des mots courts réels, signe qu'on a inséré des espaces À
        L'INTÉRIEUR des mots.

    Sans le second terme, la recherche de la meilleure tolérance choisirait
    toujours la plus basse — qui supprime les mots soudés en fragmentant tout
    le reste.
    """
    mots = _mots_alphabetiques(text)
    if not mots:
        return 1.0
    soudes = sum(1 for m in mots if len(m) > LONGUEUR_MOT_MAX_PLAUSIBLE)
    fragments = sum(
        1
        for m in mots
        if len(m) <= 2 and m.lower() not in _MOTS_COURTS_LEGITIMES
    )
    # Les mots soudés pèsent plus lourd : un texte fragmenté reste lisible par
    # un LLM, un texte soudé rend les entités inexploitables.
    return 3 * (soudes / len(mots)) + (fragments / len(mots))


# En dessous de ce score, l'extraction est considérée comme propre : on cesse
# d'essayer d'autres réglages et on n'avertit pas. Non nul, parce qu'un
# papier scientifique contient toujours quelques jetons courts légitimes
# hors liste (sigles, symboles mathématiques, numéros de figure).
SCORE_ACCEPTABLE = 0.02


# Mise en page sur deux colonnes : pdfplumber lit chaque ligne de gauche à
# droite À TRAVERS les deux colonnes, et les phrases des deux colonnes se
# retrouvent entrelacées ("...won a free Amazon Gift / to the attack (e.g., via
# retrieval or email)... Card, which, to claim..."). Sur Prompt-Injection.pdf,
# GLiNER et Mistral recevaient ce texte brouillé, et des entités justes
# reconstituées par Mistral ("Amazon Gift Card", "markdown links") étaient
# comptées comme hallucinées faute d'exister d'un seul tenant dans la source.
# Une page est lue colonne par colonne quand une gouttière verticale proche du
# milieu n'est traversée par presque aucun mot.
_GOUTTIERE_ZONE = (0.40, 0.60)  # où chercher la gouttière, en fraction de largeur
_LIGNES_DEUX_COLONNES_MIN = 0.50  # part minimale de lignes que la gouttière ne traverse pas
_COLONNE_MIN_MOTS = 0.20  # chaque colonne doit porter au moins cette part des mots


def _mots_reels(page) -> list[dict]:
    # Seuls les vrais mots comptent : les figures en lettres éparpillées
    # (figure 1 de Prompt-Injection.pdf, une lettre par mot) traversent la
    # gouttière et masquaient la mise en page de la page entière.
    return [m for m in page.extract_words() if len(m["text"]) >= 3]


def _gouttiere(page) -> float | None:
    """
    Abscisse de la gouttière si la page est (au moins en partie) sur deux
    colonnes, sinon None. Les blocs pleine largeur (titre, figure large)
    traversent la gouttière sans empêcher la détection : on exige seulement
    qu'une majorité de LIGNES ne la traversent pas.
    """
    mots = _mots_reels(page)
    if len(mots) < 50:
        return None
    largeur = page.width
    candidats = [
        largeur * (_GOUTTIERE_ZONE[0] + (_GOUTTIERE_ZONE[1] - _GOUTTIERE_ZONE[0]) * i / 40)
        for i in range(41)
    ]
    x = min(candidats, key=lambda c: sum(1 for m in mots if m["x0"] < c < m["x1"]))
    lignes = _lignes(mots, x)
    libres = sum(1 for _, traverse in lignes if not traverse)
    gauche = sum(1 for m in mots if m["x1"] <= x)
    droite = sum(1 for m in mots if m["x0"] >= x)
    if (
        libres >= _LIGNES_DEUX_COLONNES_MIN * len(lignes)
        and gauche >= _COLONNE_MIN_MOTS * len(mots)
        and droite >= _COLONNE_MIN_MOTS * len(mots)
    ):
        return x
    return None


def _lignes(mots: list[dict], x: float) -> list[tuple[float, bool]]:
    """(ordonnée, traverse la gouttière ?) pour chaque ligne de mots, de haut en bas."""
    par_ligne: dict[int, bool] = {}
    for m in mots:
        cle = round(m["top"] / 3)  # mots d'une même ligne : même ordonnée à 3 pt près
        par_ligne[cle] = par_ligne.get(cle, False) or (m["x0"] < x < m["x1"])
    return [(cle * 3, traverse) for cle, traverse in sorted(par_ligne.items())]


def _texte_page(page, kwargs: dict) -> str:
    """
    Texte d'une page dans l'ordre de lecture. Sur deux colonnes, la page est
    découpée en bandes horizontales : une bande dont les lignes traversent la
    gouttière (titre, figure pleine largeur) est lue d'un bloc, une bande à
    deux colonnes est lue colonne gauche puis colonne droite.
    """
    x = _gouttiere(page)
    if x is None:
        return page.extract_text(**kwargs) or ""

    bandes = []  # (haut, bas, pleine_largeur)
    for y, traverse in _lignes(_mots_reels(page), x):
        if bandes and bandes[-1][2] == traverse:
            bandes[-1][1] = y
        else:
            bandes.append([y, y, traverse])
    morceaux = []
    for i, (haut, _, pleine_largeur) in enumerate(bandes):
        y0 = 0 if i == 0 else haut - 1
        y1 = page.height if i == len(bandes) - 1 else bandes[i + 1][0] - 1
        if y1 <= y0:
            continue
        zones = [(0, page.width)] if pleine_largeur else [(0, x), (x, page.width)]
        for x0, x1 in zones:
            morceaux.append(page.crop((x0, y0, x1, y1)).extract_text(**kwargs) or "")
    return "\n".join(m for m in morceaux if m)


def _recoller_cesures(text: str) -> str:
    """
    Recolle les mots coupés en fin de ligne : "informa-\ntion" -> "information",
    "jail-\nbreaking" -> "jailbreaking". Le tiret n'est retiré que si les deux
    côtés sont en minuscules (césure typographique) ; sinon c'est un vrai
    composé ("LLM-\nintegrated" -> "LLM-integrated", "Chat-\nGPT" ->
    "Chat-GPT") et seul le saut de ligne disparaît.
    """
    text = re.sub(r"(?<=[a-zà-ÿ])-[ \t]*\n[ \t]*(?=[a-zà-ÿ])", "", text)
    return re.sub(r"(?<=\w)-[ \t]*\n[ \t]*(?=\w)", "-", text)


def _extraire_pages(pdf, x_tolerance: float | None) -> str:
    kwargs = {} if x_tolerance is None else {"x_tolerance": x_tolerance}
    return _recoller_cesures("\n".join(_texte_page(page, kwargs) for page in pdf.pages))


def extract_text_from_pdf(pdf_path: str, verbose: bool = True) -> str:
    """
    Extrait tout le texte d'un PDF, en choisissant la tolérance d'espacement
    qui produit le texte le plus propre pour CE document (voir
    _TOLERANCES_A_ESSAYER). La valeur par défaut de pdfplumber est essayée en
    premier et gardée si elle suffit : la plupart des PDF n'ont pas le
    problème, et on ne repaie une extraction que quand il y a lieu.
    """
    with pdfplumber.open(pdf_path) as pdf:
        meilleur_texte = ""
        meilleur_score = float("inf")
        meilleure_tolerance = None
        for tolerance in _TOLERANCES_A_ESSAYER:
            texte = _extraire_pages(pdf, tolerance)
            score = _score_extraction(texte)
            if score < meilleur_score:
                meilleur_texte, meilleur_score, meilleure_tolerance = (
                    texte,
                    score,
                    tolerance,
                )
            if score <= SCORE_ACCEPTABLE:
                break  # extraction propre, inutile d'essayer d'autres réglages

    if verbose and meilleure_tolerance is not None:
        print(
            f"[pdf] espaces mal détectés avec les réglages par défaut — "
            f"x_tolerance={meilleure_tolerance} retenue "
            f"(qualité {meilleur_score:.4f}, 0 = parfait)"
        )
    if verbose and meilleur_score > SCORE_ACCEPTABLE:
        print(
            f"[⚠] Le texte extrait contient encore des mots soudés "
            f"(score {meilleur_score:.4f}). Les entités et les résumés en "
            f"pâtiront — vérifier le PDF avec : "
            f"python pdf_extractor.py {pdf_path}"
        )

    text = strip_front_matter(meilleur_texte)
    text = strip_references_section(text)
    return _clean_text(text)


def is_glued_token(text: str) -> bool:
    """
    Vrai si `text` ressemble à plusieurs mots soudés par une extraction PDF
    ratée ("BingChatincentivizedustofollowthelinkbysaying").

    Ces chaînes passent tous les filtres existants : elles sont bien présentes
    dans le texte source (donc pas des hallucinations) et ne comptent que pour
    UN mot (donc invisibles pour mistral_extractor._filter_by_length, qui
    plafonne un nombre de mots). Il faut donc un contrôle sur la longueur en
    CARACTÈRES, pas en mots.
    """
    if not text:
        return False
    return any(
        len(mot) > LONGUEUR_MOT_MAX_PLAUSIBLE for mot in _mots_alphabetiques(text)
    )


def strip_front_matter(text: str) -> str:
    """
    Coupe le texte avant le début du corps réel de l'article (marqueur
    "Abstract"), pour retirer le bloc titre/auteurs/affiliations/notice de
    preprint-copyright qui le précède. Constaté en conditions réelles : ce
    bloc, envoyé au LLM comme n'importe quel autre texte dans le premier
    chunk, produit des faux positifs typés (nom d'auteur catégorisé comme
    "organisation ayant analysé l'incident", notice de copyright catégorisée
    comme "année de l'incident", etc.) — du texte réel mal étiqueté plutôt
    que de l'hallucination, donc invisible pour compute_hallucination_rate.

    Heuristique papier académique : ne s'applique que si "Abstract" est
    trouvé tôt dans le document (recherche bornée aux 4000 premiers
    caractères pour éviter de couper sur une occurrence tardive et non
    pertinente) ; sinon le texte est renvoyé inchangé, sans effet sur les
    documents qui n'ont pas cette structure (rapports CERT, threat intel).
    """
    match = re.search(r"\babstract\b", text[:4000], re.IGNORECASE)
    return text[match.start():] if match else text


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
    if not match:
        # Mise en page sur deux colonnes : pdfplumber lit les lignes de gauche
        # à droite, et le titre se retrouve collé à la première référence de
        # l'autre colonne ("REFERENCES [34] Microsoft. 2023. ..."), ce que le
        # motif ci-dessus (titre seul sur sa ligne) ne voit pas. Constaté sur
        # Prompt-Injection.pdf : les deux derniers chunks, pure bibliographie,
        # partaient dans GLiNER/Mistral. Restreint au titre EN MAJUSCULES
        # suivi d'un numéro de référence, pour ne jamais couper sur un
        # "References" en début de phrase.
        match = re.search(
            r"\n[ \t]*(?:REFERENCES|BIBLIOGRAPHY|RÉFÉRENCES)[ \t]+\[\d+\]", text
        )
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
