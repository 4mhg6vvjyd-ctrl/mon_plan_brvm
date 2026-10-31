"""Extraction automatique des chiffres cles des etats financiers publies sur la BRVM.

Usage :  python brvm_fondamentaux.py fichier.pdf [TICKER]  (plusieurs fichiers possibles)
Resultat : fondamentaux.json (une entree par societe et par exercice).

Trois formats reconnus :
  - SYSCOHADA (societes commerciales et industrielles, ex. AGL CI)
  - PCB revise (banques, ex. SGBCI)
  - IFRS (groupes consolides, ex. Sonatel)
Chaque extraction passe des controles de coherence ; en cas de doute, la ligne est marquee "a_verifier".
"""
import json
import math
import re
import sys
import unicodedata
from itertools import combinations
from pathlib import Path

import pdfplumber

ICI = Path(__file__).resolve().parent
SORTIE = ICI / "fondamentaux.json"

# Libelles recherches (debut de ligne, sans accents, en minuscules), par norme
LIBELLES = {
    "syscohada": {
        "ca": ["chiffre d'affaires"],
        "res_exploitation": ["resultat d'exploitation"],
        "res_financier": ["resultat financier"],
        "produits_financiers": ["produits financiers"],
        "res_ordinaire": ["resultat des activites ordinaires"],
        "res_hao": ["resultat h.a.o", "resultat hao"],
        "impot": ["impots sur le resultat"],
        "res_net": ["resultat net"],
        "capitaux_propres": ["situation nette", "capitaux propres"],
        "tresorerie_actif": ["tresorerie - actif", "tresorerie actif"],
        "dettes_financieres": ["dettes financieres"],
        "dividendes_verses": ["dividendes verses"],
        "investissements_corporels": ["decaissements liees aux acquisitions d'immobilisations corporelles",
                                      "decaissements lies aux acquisitions d'immobilisations corporelles"],
    },
    "banque": {
        "pnb": ["produit net bancaire"],
        "frais_generaux": ["frais generaux"],
        "res_brut_exploitation": ["resultat brut d'exploitation"],
        "cout_risque": ["cout net du risque"],
        "res_exploitation": ["resultat d'exploitation"],
        "gains_immobilises": ["gains ou pertes nets sur actifs immobilises"],
        "impot": ["impots sur les benefices"],
        "res_net": ["resultat net"],
        "capitaux_propres": ["capitaux propres et ressources assimilees"],
        "credits_clientele": ["creances sur la clientele"],
        "depots_clientele": ["dettes a l'egard de la clientele"],
    },
    "ifrs": {
        "ca": ["chiffre d'affaires"],
        "res_exploitation": ["resultat d'exploitation"],
        "res_financier": ["resultat financier"],
        "impot": ["impot sur les societes"],
        "res_net": ["resultat net de l'ensemble consolide"],
        "res_net_part_groupe": ["resultat net attribuable aux proprietaires de la maison mere",
                                "resultat net part du groupe"],
        "bpa": ["- de base", "de base"],
        "capitaux_propres": ["total capitaux propres"],
        "tresorerie": ["disponibilites et quasi-disponibilites a la cloture"],
        "dette_fin_nc": ["passifs financiers non courants"],
        "dette_fin_c": ["passifs financiers courants"],
        "investissements": ["acquisitions d'immobilisations corporelles et incorporelles"],
    },
}
PAR_ACTION = {"bpa"}
# Libelles qui peuvent se trouver dans la colonne de droite d'un tableau cote a cote
PARTOUT = {"capitaux_propres", "tresorerie_actif", "dettes_financieres", "dividendes_verses", "investissements_corporels"}  # valeurs deja par action : pas de conversion d'unite


def sans_accents(s):
    s = s.replace("\u2019", "'").replace("\u2018", "'").replace("\u00a0", " ")
    s = "".join(c if ord(c) < 128 else (unicodedata.normalize("NFKD", c).encode("ascii", "ignore").decode() or "?") for c in s)
    return s.lower()


NUM = re.compile(r"^\(?-?\d+\)?$")


def nombres_possibles(jetons, k):
    """Toutes les facons de regrouper les jetons numeriques en k nombres.
    Un nombre = un premier groupe de chiffres, puis des groupes d'exactement 3 chiffres."""
    n = len(jetons)
    res = []
    for coupes in combinations(range(1, n), k - 1):
        bornes = (0,) + coupes + (n,)
        vals = []
        for a, b in zip(bornes, bornes[1:]):
            g = jetons[a:b]
            if any(t.startswith(("-", "(")) for t in g[1:]) or any(t.endswith(")") for t in g[:-1]):
                vals = None
                break
            brut = [t.strip("()") for t in g]
            neg = g[0].startswith("(") or g[0].startswith("-") or g[-1].endswith(")")
            brut[0] = brut[0].lstrip("-")
            if any(len(x) != 3 for x in brut[1:]) or (len(g) > 1 and len(brut[0]) > 3):
                vals = None
                break
            if len(brut[0]) > 1 and brut[0].startswith("0"):
                vals = None
                break
            v = int("".join(brut))
            vals.append(-v if neg else v)
        if vals is not None:
            res.append(vals)
    return res


def lire_valeurs(apres, attendu=2):
    """Lit les nombres qui suivent un libelle, jusqu'au prochain mot (cas des tableaux cote a cote)."""
    jetons = []
    for t in apres.split():
        if NUM.match(t):
            jetons.append(t)
        elif t in ("-", "–") and not jetons:
            continue
        else:
            break
    if not jetons:
        return None
    if attendu == 1:
        o = nombres_possibles(jetons, 1)
        return o[0] if o else None

    def ecart(v):  # deux exercices successifs ont en general un ordre de grandeur proche
        a, b = abs(v[0]) or 1, abs(v[1]) or 1
        return abs(math.log(a / b))
    deux = nombres_possibles(jetons, 2)
    if deux and min(map(ecart, deux)) <= math.log(50):
        return min(deux, key=ecart)
    options = []
    for k in range(3, min(len(jetons), 5) + 1):  # colonnes en plus (variation...) ignorees
        options += [v[:2] for v in nombres_possibles(jetons, k)]
    options += deux
    if options:
        return min(options, key=ecart)
    o = nombres_possibles(jetons, 1)
    return o[0] if o else None


def detecter_norme(texte):
    t = sans_accents(texte)
    if "produit net bancaire" in t:
        return "banque"
    if "ifrs" in t or "ensemble consolide" in t:
        return "ifrs"
    return "syscohada"


def unite_de(texte_page):
    t = sans_accents(texte_page)
    if "en milliers" in t:
        return 1_000
    if "en millions" in t:
        return 1_000_000
    return None


def ordre_colonnes(texte_page, annee):
    """True si la colonne de l'exercice est la premiere (ex. '2025 2024'), False si 'Dec.-24 Dec.-25'."""
    t = sans_accents(texte_page)
    a, b = str(annee), str(annee - 1)
    m = re.search(r"(20\d\d|dec\.?-?\s?\d\d)\s+(20\d\d|dec\.?-?\s?\d\d)", t)
    if not m:
        return True
    premier = m.group(1)
    return premier.endswith(a) or premier.endswith(a[-2:])


def exercice_du_document(texte, nom):
    for src in (nom, texte):
        m = re.search(r"exercice[ _-]*(20\d\d)|au 31[/ ]12[/ ](20\d\d)|31 decembre (20\d\d)|fy ?(20\d\d)", sans_accents(src))
        if m:
            return int(next(g for g in m.groups() if g))
    ans = [int(x) for x in re.findall(r"\b(20[2-3]\d)\b", texte)]
    return max(set(ans), key=ans.count) if ans else None


def extraire(pdf_path, ticker=None, historique_div=None):
    nom = Path(pdf_path).name
    with pdfplumber.open(pdf_path) as pdf:
        pages = [(p.extract_text() or "", p.extract_text_lines()) for p in pdf.pages]
    tout = "\n".join(t for t, _ in pages)
    norme = detecter_norme(tout)
    annee = exercice_du_document(tout, nom)
    libs = LIBELLES[norme]
    n, n1, notes = {}, {}, []
    unite_doc = unite_de(tout)
    for texte_page, lignes in pages:
        unite = unite_de(texte_page) or unite_doc
        if unite is None:
            continue
        devant = ordre_colonnes(texte_page, annee)
        for l in lignes:
            brut = l["text"]
            s = sans_accents(brut)
            off = 2 if re.match(r"^[a-z] (?=[a-z])", s) else 0  # lettre parasite d'un titre vertical
            for cle, variantes in libs.items():
                if cle in n:
                    continue
                for v in variantes:
                    i = s.find(v, off)
                    if i == -1 or (i - off > 3 and cle not in PARTOUT):
                        continue
                    if i - off > 3 and not re.search(r"\d\s*$", s[:i]):
                        continue
                    reste = brut[i + len(v):] if len(brut) == len(s) else s[i + len(v):]
                    vals = lire_valeurs(reste.lstrip(" :."))
                    if not vals:
                        continue
                    mult = 1 if cle in PAR_ACTION else unite
                    if len(vals) == 2:
                        cur, prev = (vals[0], vals[1]) if devant else (vals[1], vals[0])
                        n[cle], n1[cle] = cur * mult, prev * mult
                    else:
                        n[cle] = vals[0] * mult
                    break
    # Dividende et nombre d'actions
    t = sans_accents(tout)
    dpa = None
    m = re.search(r"fixer a ([\d .]+) fcfa le dividende brut", t)
    if m:
        dpa = int(re.sub(r"\D", "", m.group(1)))
    m = re.search(r"dividende brut par action[^\d]*([\d ]+)", t)
    if m and dpa is None:
        dpa = int(m.group(1).split()[0])
    m = re.search(r"nombre d'actions\s*([\d ]{6,})", t)
    nb_actions = int(m.group(1).replace(" ", "")) if m else None
    m = re.search(r"dividendes bruts aux actionnaires\s*([\d ]+)", t)
    div_total = int(m.group(1).replace(" ", "")) if m else None
    if div_total is None:
        for texte_page, lignes in pages:
            for l in lignes:
                s = sans_accents(l["text"])
                if s.startswith("- dividendes"):
                    v = lire_valeurs(l["text"].split("ividendes", 1)[1], 1)
                    if v:
                        div_total = v[0] * (unite_de(texte_page) or unite_doc or 1)
    if nb_actions is None and n.get("res_net_part_groupe") and n.get("bpa"):
        nb_actions = round(n["res_net_part_groupe"] / n["bpa"])
        notes.append("Nombre d'actions deduit du benefice par action publie.")
    if dpa is None and div_total and nb_actions:
        dpa = round(div_total / nb_actions, 2)

    controles = controler(norme, n, n1)
    if historique_div and dpa:
        dernier = historique_div
        r = dpa / dernier if dernier else None
        if r and (r > 4 or r < 0.25):
            controles.append({"ok": False, "texte": f"Dividende par action ({dpa}) tres different du dernier connu ({dernier}) : division du nominal ou dividende exceptionnel ?"})
    return {
        "ticker": ticker, "source": nom, "norme": norme, "exercice": annee,
        "valeurs": {str(annee): n, str(annee - 1): n1} if annee else {"?": n},
        "dividende_brut_par_action": dpa, "dividende_total": div_total, "nombre_actions": nb_actions,
        "controles": controles, "notes": notes,
        "a_verifier": any(not c["ok"] for c in controles) or len(n) < 4,
    }


def proche(a, b, tol=0.01):
    return a is not None and b is not None and abs(a - b) <= max(abs(b) * tol, 2_000_000)


def controler(norme, n, n1):
    c = []

    def chk(nom, calcule, publie):
        if calcule is None or publie is None:
            return
        c.append({"ok": proche(calcule, publie), "texte": f"{nom} : calcule {calcule:,.0f} / publie {publie:,.0f}".replace(",", " ")})
    g = n.get
    if norme == "syscohada":
        if g("res_exploitation") is not None and g("res_financier") is not None:
            chk("Activites ordinaires = exploitation + financier", g("res_exploitation") + g("res_financier"), g("res_ordinaire"))
        if None not in (g("res_ordinaire"), g("res_hao"), g("impot")):
            chk("Resultat net = ordinaire + HAO - impot", g("res_ordinaire") + g("res_hao") - g("impot"), g("res_net"))
    elif norme == "banque":
        if None not in (g("pnb"), g("frais_generaux")):
            chk("RBE = PNB + frais generaux", g("pnb") + g("frais_generaux"), g("res_brut_exploitation"))
        if None not in (g("res_exploitation"), g("gains_immobilises"), g("impot")):
            chk("Resultat net = exploitation + gains - impot", g("res_exploitation") + g("gains_immobilises") + g("impot"), g("res_net"))
    else:
        if None not in (g("res_exploitation"), g("res_financier"), g("impot")):
            chk("Resultat net = exploitation + financier - impot", g("res_exploitation") + g("res_financier") + g("impot"), g("res_net"))
    return c


def signaux(e):
    """Faits saillants calcules automatiquement, en langage simple."""
    a = str(e["exercice"]); p = str(e["exercice"] - 1)
    n, n1 = e["valeurs"].get(a, {}), e["valeurs"].get(p, {})
    out = []

    def var(k):
        if n.get(k) is None or not n1.get(k):
            return None
        return n[k] / n1[k] - 1
    ca = var("ca") if "ca" in n else var("pnb")
    rn = var("res_net")
    if ca is not None and rn is not None and ca > 0 and rn < -0.5:
        out.append(f"Titre trompeur possible : l'activite progresse ({ca:+.0%}) mais le benefice chute ({rn:+.0%}). Regarder d'ou vient la baisse.")
    if n.get("res_exploitation") is not None and n["res_exploitation"] < 0 < (n.get("res_net") or 0):
        out.append("Le benefice ne vient pas de l'activite propre (resultat d'exploitation negatif) : il vient des produits financiers, souvent les dividendes des filiales.")
    if n.get("produits_financiers") and n1.get("produits_financiers") and n["produits_financiers"] < 0.5 * n1["produits_financiers"]:
        out.append(f"Les produits financiers ont fortement baisse ({var('produits_financiers'):+.0%}).")
    if n.get("res_net") and e.get("dividende_total"):
        taux = e["dividende_total"] / n["res_net"]
        out.append(f"Taux de distribution propose : {taux:.0%} du benefice.")
    inv = n.get("investissements_corporels") or n.get("investissements")
    inv1 = n1.get("investissements_corporels") or n1.get("investissements")
    if inv and inv1 and abs(inv) > 1.6 * abs(inv1):
        out.append(f"Les investissements ont fortement augmente ({abs(inv) / abs(inv1) - 1:+.0%}).")
    return out


def main(args):
    base = json.loads(SORTIE.read_text(encoding="utf-8")) if SORTIE.exists() else {}
    i = 0
    while i < len(args):
        f = args[i]; t = None
        if i + 1 < len(args) and not args[i + 1].lower().endswith(".pdf"):
            t = args[i + 1]; i += 1
        i += 1
        e = extraire(f, t)
        e["signaux"] = signaux(e)
        cle = t or Path(f).stem
        base.setdefault(cle, {})[str(e["exercice"])] = e
        etat = "A VERIFIER" if e["a_verifier"] else "ok"
        print(f"{cle} {e['exercice']} ({e['norme']}) : {len(e['valeurs'].get(str(e['exercice']), {}))} chiffres, {etat}")
    SORTIE.write_text(json.dumps(base, ensure_ascii=False, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main(sys.argv[1:])
