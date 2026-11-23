"""Assemble le mémoire complet en un seul fichier Markdown, pour le relire avant le Word.

Usage : python rapport/assembler_md.py
Sortie : rapport/Rapport_Memoire_CARL.md (page de garde résumée, table des
matières, listes, acronymes, puis chaque section de rapport/sections/ dans l'ordre).
"""
import glob
import os
import re

HERE = os.path.dirname(os.path.abspath(__file__))

GARDE = """**MÉMOIRE** présenté en vue de l'obtention du **Diplôme de Mastère de Recherche en Informatique**

Parcours : Smart Systems & IoT

**Sujet : Nexus Intel : De la Publication à la Protection — Synthèse Automatisée des Défenses contre les Menaces Émergentes sur les LLM**

Élaboré par : **Souhir AYARI** · Laboratoire LARIA · ENSI, Université de la Manouba

Encadrante : Dr Amal TARIFA, Maître Assistante · Année universitaire 2025/2026"""


def main():
    sections = []
    for path in sorted(glob.glob(os.path.join(HERE, "sections", "*.md"))):
        with open(path, encoding="utf-8") as f:
            sections.append(f.read().strip())

    toc = []
    for text in sections:
        for line in text.splitlines():
            m = re.match(r"^(#{1,3}) (.+)", line)
            if m:
                toc.append("  " * (len(m.group(1)) - 1) + "- " + m.group(2).strip())

    figures = [l for t in sections for l in t.splitlines() if l.startswith("*Figure ")]
    tableaux = [l for t in sections for l in t.splitlines() if l.startswith("*Tableau ")]

    with open(os.path.join(HERE, "acronymes.md"), encoding="utf-8") as f:
        rows = [l.split(":", 1) for l in f if ":" in l and not l.startswith("#")]
    rows.sort(key=lambda r: r[0].strip().lower())
    acro = ["| Sigle | Signification |", "|---|---|"]
    acro += [f"| **{s.strip()}** | {d.strip()} |" for s, d in rows]

    parts = [
        "# Page de garde", GARDE,
        "# Table des matières", "\n".join(toc) or "*(vide)*",
        "# Liste des figures", "\n".join("- " + f.strip("*") for f in figures) or "*(aucune figure pour l'instant)*",
        "# Liste des tableaux", "\n".join("- " + t.strip("*") for t in tableaux) or "*(aucun tableau pour l'instant)*",
        "# Liste des acronymes", "\n".join(acro),
    ] + sections
    out = os.path.join(HERE, "Rapport_Memoire_CARL.md")
    with open(out, "w", encoding="utf-8") as f:
        f.write("\n\n---\n\n".join(parts) + "\n")
    print("écrit :", out)


if __name__ == "__main__":
    main()
