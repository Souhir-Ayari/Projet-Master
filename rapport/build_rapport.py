"""Assemble le mémoire en un seul fichier Word.

Usage : python rapport/build_rapport.py <page_de_garde.docx> <sortie.docx> [--remplir]

La page de garde ENSI est reprise telle quelle (l'étudiante la complète
elle-même) ; avec --remplir, les champs connus sont remplis. Chaque section
(fichiers rapport/sections/NN_*.md, dans l'ordre des noms) est ajoutée à la suite.
Syntaxe reconnue dans les fichiers .md : '# ' titre de chapitre, '## ' et
'### ' sous-titres, paragraphes séparés par une ligne vide, *italique*,
**gras**, `code`, listes '- ' et '1. ', citations '> ', tableaux Markdown,
images ![...](chemin) et légendes '*Tableau …*' / '*Figure …*'.
"""
import copy
import glob
import os
import re
import sys

import docx
from docx.enum.section import WD_SECTION
from docx.enum.style import WD_STYLE_TYPE
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_BREAK
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor

HERE = os.path.dirname(os.path.abspath(__file__))

GARDE = {
    "parcours": "Smart Systems & IoT",
    "sujet": "Nexus Intel : De la Publication à la Protection — Synthèse Automatisée "
             "des Défenses contre les Menaces Émergentes sur les LLM",
    "auteur": "Souhir AYARI",
    "sigle": "LARIA",
    "encadrant": "Dr Amal TARIFA, Maître Assistante",
}

FONT = "Times New Roman"
NAVY = RGBColor(0x14, 0x21, 0x3D)


def set_text(paragraph, text, bold=None, size=None):
    """Remplace le texte d'un paragraphe en gardant le format du premier run."""
    runs = paragraph.runs
    if runs:
        runs[0].text = text
        for r in runs[1:]:
            r.text = ""
        run = runs[0]
    else:
        run = paragraph.add_run(text)
    if bold is not None:
        run.bold = bold
    if size is not None:
        run.font.size = Pt(size)


def fill_cover(doc):
    p = doc.paragraphs
    set_text(p[4], "Parcours : " + GARDE["parcours"])
    set_text(p[7], GARDE["sujet"], bold=True, size=16)
    p[7].alignment = WD_ALIGN_PARAGRAPH.CENTER
    set_text(p[9], GARDE["auteur"])
    set_text(p[12], GARDE["sigle"])
    table = doc.tables[0]
    table.rows[2].cells[2].text = GARDE["encadrant"]
    # Deux paragraphes vides avant « Année universitaire » font déborder la
    # page de garde sur une seconde page : on les retire.
    for para in doc.paragraphs:
        if para.style.name == "Footer" and not para.text.strip():
            para._p.getparent().remove(para._p)
    # Une des deux lignes vides avant « Soutenu le » est retirée pour la même raison.
    paras = doc.paragraphs
    idx = next(i for i, q in enumerate(paras) if q.text.startswith("Soutenu le"))
    if not paras[idx - 1].text.strip():
        paras[idx - 1]._p.getparent().remove(paras[idx - 1]._p)


def heading_style(doc, name, size, level, before, after, color=NAVY):
    styles = doc.styles
    try:
        st = styles[name]
    except KeyError:
        st = styles.add_style(name, WD_STYLE_TYPE.PARAGRAPH)
    st.base_style = styles["Normal"]
    st.font.name = FONT
    st.font.size = Pt(size)
    st.font.bold = True
    st.font.color.rgb = color
    pf = st.paragraph_format
    pf.space_before = Pt(before)
    pf.space_after = Pt(after)
    pf.keep_with_next = True
    pf.alignment = WD_ALIGN_PARAGRAPH.LEFT
    ppr = st.element.get_or_add_pPr()
    for old in ppr.findall(qn("w:outlineLvl")):
        ppr.remove(old)
    lvl = OxmlElement("w:outlineLvl")
    lvl.set(qn("w:val"), str(level))
    ppr.append(lvl)
    return st


def get_style(doc, name):
    try:
        return doc.styles[name]
    except KeyError:
        return doc.styles.add_style(name, WD_STYLE_TYPE.PARAGRAPH)


def caption_style(doc, name):
    st = get_style(doc, name)
    st.base_style = doc.styles["Normal"]
    st.font.name = FONT
    st.font.size = Pt(11)
    st.font.italic = True
    st.font.bold = False
    st.font.color.rgb = NAVY
    pf = st.paragraph_format
    pf.alignment = WD_ALIGN_PARAGRAPH.CENTER
    pf.space_before = Pt(6)
    pf.space_after = Pt(10)
    return st


def body_style(doc):
    st = get_style(doc, "Corps memoire")
    st.base_style = doc.styles["Normal"]
    st.font.name = FONT
    st.font.size = Pt(12)
    pf = st.paragraph_format
    pf.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
    pf.line_spacing = 1.5
    pf.space_after = Pt(8)
    pf.first_line_indent = Cm(0.75)
    return st


def add_field(paragraph, instr):
    """Insère un champ Word (numéro de page, table des matières...)."""
    run = paragraph.add_run()
    for tag, attr in (("w:fldChar", "begin"), ("w:instrText", None), ("w:fldChar", "separate")):
        el = OxmlElement(tag)
        if attr:
            el.set(qn("w:fldCharType"), attr)
        else:
            el.set(qn("xml:space"), "preserve")
            el.text = instr
        run._r.append(el)
    run2 = paragraph.add_run("Clic droit puis « Mettre à jour le champ »" if "TOC" in instr else "1")
    end = OxmlElement("w:fldChar")
    end.set(qn("w:fldCharType"), "end")
    run2._r.append(end)


def new_report_section(doc):
    """Ouvre la section du rapport sans créer de page vide après la page de garde.

    Les propriétés de la page de garde (en-tête avec logos, pied avec l'année)
    sont rattachées à son dernier paragraphe ; la section finale du document
    reçoit un en-tête vide et la numérotation des pages.
    """
    body = doc.element.body
    final = body.sectPr
    cover = copy.deepcopy(final)
    last_p = [el for el in body.iterchildren() if el.tag == qn("w:p")][-1]
    last_p.get_or_add_pPr().append(cover)
    for ref in final.findall(qn("w:headerReference")) + final.findall(qn("w:footerReference")):
        final.remove(ref)
    sec = doc.sections[-1]
    sec.start_type = WD_SECTION.NEW_PAGE
    for m in ("left_margin", "right_margin"):
        setattr(sec, m, Cm(2.5))
    sec.top_margin = Cm(2.5)
    sec.bottom_margin = Cm(2.5)
    sec.header.is_linked_to_previous = False
    sec.footer.is_linked_to_previous = False
    for part in (sec.header, sec.footer):
        for para in part.paragraphs:
            for r in para.runs:
                r.text = ""
        for tbl in list(part.tables):
            tbl._element.getparent().remove(tbl._element)
    fp = sec.footer.paragraphs[0] if sec.footer.paragraphs else sec.footer.add_paragraph()
    fp.alignment = WD_ALIGN_PARAGRAPH.CENTER
    add_field(fp, "PAGE")
    return sec


INLINE = re.compile(r"(\*\*[^*]+\*\*|\*[^*]+\*|`[^`]+`)")


def add_inline(paragraph, text, italic=False, size=None):
    for piece in INLINE.split(text):
        if not piece:
            continue
        if piece.startswith("**") and piece.endswith("**") and len(piece) > 4:
            run = paragraph.add_run(piece[2:-2])
            run.bold = True
            run.italic = italic or None
        elif piece.startswith("*") and piece.endswith("*") and len(piece) > 2:
            run = paragraph.add_run(piece[1:-1])
            run.italic = not italic
        elif piece.startswith("`") and piece.endswith("`"):
            run = paragraph.add_run(piece[1:-1])
            run.font.name = "Courier New"
            run.font.size = Pt(size - 1 if size else 11)
            run.italic = italic or None
        else:
            run = paragraph.add_run(piece)
            run.italic = italic or None
        if size and not piece.startswith("`"):
            run.font.size = Pt(size)


def strip_outer_italic(text):
    """« *texte avec **gras*** » → (« texte avec **gras** », True)."""
    if text.startswith("*") and not text.startswith("**") and text.endswith("*"):
        inner = text[1:-1]
        if inner.endswith("**") and inner.count("**") % 2 == 1:
            inner = inner + "*"
        return inner, True
    return text, False


def set_cell_shading(cell, hex_color):
    tcpr = cell._tc.get_or_add_tcPr()
    shd = OxmlElement("w:shd")
    shd.set(qn("w:val"), "clear")
    shd.set(qn("w:color"), "auto")
    shd.set(qn("w:fill"), hex_color)
    tcpr.append(shd)


def add_table(doc, block):
    rows = [r.strip() for r in block.splitlines() if r.strip().startswith("|")]
    rows = [r for r in rows if not re.match(r"^\|[\s:|-]+\|$", r)]
    cells = [[c.strip() for c in r.strip("|").split("|")] for r in rows]
    ncol = max(len(r) for r in cells)
    size = 10 if ncol <= 4 else 9 if ncol <= 6 else 8
    table = doc.add_table(rows=0, cols=ncol)
    table.style = doc.styles["Table Grid"]
    table.alignment = 1
    for i, row in enumerate(cells):
        tr = table.add_row().cells
        for j in range(ncol):
            text = row[j] if j < len(row) else ""
            para = tr[j].paragraphs[0]
            para.paragraph_format.space_after = Pt(0)
            para.paragraph_format.first_line_indent = Cm(0)
            if i == 0:
                run = para.add_run(text.replace("**", ""))
                run.bold = True
                run.font.size = Pt(size)
                run.font.name = FONT
                set_cell_shading(tr[j], "DCE6F0")
            else:
                add_inline(para, text, size=size)
                for run in para.runs:
                    if run.font.name != "Courier New":
                        run.font.name = FONT
    doc.add_paragraph().paragraph_format.space_after = Pt(2)


def add_markdown(doc, path, body, first):
    with open(path, encoding="utf-8") as f:
        blocks = [b.strip() for b in f.read().split("\n\n") if b.strip()]
    base = os.path.dirname(path)
    for block in blocks:
        if block.startswith("# "):
            if not first:
                doc.add_paragraph().add_run().add_break(WD_BREAK.PAGE)
            first = False
            doc.add_paragraph(block[2:].strip(), style="Heading 1")
        elif block.startswith("### "):
            doc.add_paragraph(block[4:].strip(), style="Heading 3")
        elif block.startswith("## "):
            doc.add_paragraph(block[3:].strip(), style="Heading 2")
        elif block.startswith("!["):
            m = re.match(r"!\[[^\]]*\]\(([^)]+)\)", block)
            img = os.path.normpath(os.path.join(base, m.group(1)))
            p = doc.add_paragraph()
            p.alignment = WD_ALIGN_PARAGRAPH.CENTER
            p.add_run().add_picture(img, width=Cm(15.5))
        elif re.match(r"^\*(Tableau|Figure) \d", block):
            style = "Legende tableau" if block.startswith("*Tableau") else "Legende figure"
            p = doc.add_paragraph(style=style)
            add_inline(p, block.strip("*"), italic=True)
        elif block.startswith("|"):
            add_table(doc, block)
        elif block.startswith("> "):
            p = doc.add_paragraph(style=body)
            p.paragraph_format.first_line_indent = Cm(0)
            p.paragraph_format.left_indent = Cm(1.25)
            p.paragraph_format.right_indent = Cm(1.25)
            add_inline(p, " ".join(l[2:].strip() for l in block.splitlines()), italic=True)
        elif all(line.startswith("- ") for line in block.splitlines()):
            for line in block.splitlines():
                p = doc.add_paragraph(style=body)
                p.paragraph_format.first_line_indent = Cm(-0.5)
                p.paragraph_format.left_indent = Cm(1.25)
                p.paragraph_format.space_after = Pt(4)
                add_inline(p, "•  " + line[2:].strip())
        elif all(re.match(r"^\d+\. ", line) for line in block.splitlines()):
            for line in block.splitlines():
                p = doc.add_paragraph(style=body)
                p.paragraph_format.first_line_indent = Cm(-0.6)
                p.paragraph_format.left_indent = Cm(1.25)
                p.paragraph_format.space_after = Pt(4)
                add_inline(p, line.strip())
        elif re.match(r"^\[\d+\] ", block):
            p = doc.add_paragraph(style=body)
            p.alignment = WD_ALIGN_PARAGRAPH.LEFT
            p.paragraph_format.first_line_indent = Cm(-1)
            p.paragraph_format.left_indent = Cm(1)
            p.paragraph_format.line_spacing = 1.15
            add_inline(p, " ".join(block.splitlines()))
        else:
            # un paragraphe peut contenir une liste qui suit une phrase d'introduction
            lines = block.splitlines()
            if len(lines) > 1 and all(l.startswith("- ") for l in lines[1:]):
                p = doc.add_paragraph(style=body)
                add_inline(p, lines[0])
                for line in lines[1:]:
                    q = doc.add_paragraph(style=body)
                    q.paragraph_format.first_line_indent = Cm(-0.5)
                    q.paragraph_format.left_indent = Cm(1.25)
                    q.paragraph_format.space_after = Pt(4)
                    add_inline(q, "•  " + line[2:].strip())
                continue
            text, italic = strip_outer_italic(" ".join(lines))
            p = doc.add_paragraph(style=body)
            if italic:
                p.paragraph_format.first_line_indent = Cm(0)
                add_inline(p, text, italic=True, size=10)
            else:
                add_inline(p, text)
    return first


def liminaire(doc, body, titre, champ):
    """Page liminaire générée par Word (table des matières, des figures, des tableaux)."""
    p = doc.add_paragraph(titre, style="Unnumbered heading")
    add_field(doc.add_paragraph(style=body), champ)
    doc.add_paragraph().add_run().add_break(WD_BREAK.PAGE)
    return p


def acronymes(doc, body):
    """Liste des acronymes, lue dans rapport/acronymes.md (lignes « SIGLE : définition »)."""
    doc.add_paragraph("Liste des acronymes", style="Unnumbered heading")
    path = os.path.join(HERE, "acronymes.md")
    with open(path, encoding="utf-8") as f:
        rows = [line.split(":", 1) for line in f if ":" in line and not line.startswith("#")]
    rows.sort(key=lambda r: r[0].strip().lower())
    table = doc.add_table(rows=0, cols=2)
    for sigle, definition in rows:
        cells = table.add_row().cells
        cells[0].width, cells[1].width = Cm(3.5), Cm(12.5)
        r = cells[0].paragraphs[0].add_run(sigle.strip())
        r.bold = True
        add_inline(cells[1].paragraphs[0], definition.strip())
        for c in cells:
            for run in c.paragraphs[0].runs:
                run.font.name, run.font.size = FONT, Pt(12)
    doc.add_paragraph().add_run().add_break(WD_BREAK.PAGE)


def main(garde, out, remplir=False):
    doc = docx.Document(garde)
    if remplir:
        fill_cover(doc)
    heading_style(doc, "Heading 1", 18, 0, 0, 18)
    heading_style(doc, "Heading 2", 14, 1, 14, 8)
    heading_style(doc, "Heading 3", 12, 2, 10, 6)
    unnumbered = heading_style(doc, "Unnumbered heading", 18, 9, 0, 18)
    unnumbered.paragraph_format.alignment = WD_ALIGN_PARAGRAPH.CENTER
    caption_style(doc, "Legende tableau")
    caption_style(doc, "Legende figure")
    body = body_style(doc)

    new_report_section(doc)
    liminaire(doc, body, "Table des matières", 'TOC \\o "1-3" \\h \\z \\u')
    liminaire(doc, body, "Liste des figures", 'TOC \\h \\z \\t "Legende figure,1"')
    liminaire(doc, body, "Liste des tableaux", 'TOC \\h \\z \\t "Legende tableau,1"')
    acronymes(doc, body)

    first = True
    for path in sorted(glob.glob(os.path.join(HERE, "sections", "*.md"))):
        first = add_markdown(doc, path, body, first)
    settings = doc.settings.element
    upd = OxmlElement("w:updateFields")
    upd.set(qn("w:val"), "true")
    settings.append(upd)
    doc.save(out)
    print("écrit :", out)


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2], remplir="--remplir" in sys.argv[3:])
