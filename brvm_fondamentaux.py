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
        "ca": ["chiffre d'affaires", "sous total chiffre d'affaires", "total chiffre d'affaires", "sous-total chiffre d'affaires"],
        "res_exploitation": ["resultat d'exploitation"],
        "res_financier": ["resultat financier"],
        "produits_financiers": ["produits financiers", "total produits financiers"],
        "res_ordinaire": ["resultat des activites ordinaires"],
        "res_hao": ["resultat h.a.o", "resultat hao"],
        "impot": ["impots sur le resultat", "impot sur le resultat", "impots sur les benefices"],
        "res_net": ["resultat net", "benefice net"],
        "capitaux_propres": ["situation nette", "total capitaux propres", "capitaux propres"],
        "capital": ["capital social", "capital"],
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
        "res_net": ["resultat net", "benefice net", "resultat de l'exercice"],
        "capitaux_propres": ["capitaux propres et ressources assimilees", "total capitaux propres", "capitaux propres"],
        "capital": ["capital souscrit", "capital social"],
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
        "capitaux_propres": ["capitaux propres attribuables aux proprietaires de la societe mere", "total capitaux propres"],
        "tresorerie": ["disponibilites et quasi-disponibilites a la cloture"],
        "dette_fin_nc": ["passifs financiers non courants"],
        "dette_fin_c": ["passifs financiers courants"],
        "investissements": ["acquisitions d'immobilisations corporelles et incorporelles"],
    },
}
PAR_ACTION = {"bpa"}
CODES = {"XB": "ca", "XE": "res_exploitation", "XF": "res_financier", "XG": "res_ordinaire", "XH": "res_hao", "XI": "res_net", "CP": "capitaux_propres"}
# Libelles qui peuvent se trouver dans la colonne de droite d'un tableau cote a cote
PARTOUT = {"capitaux_propres", "tresorerie_actif", "dettes_financieres", "dividendes_verses", "investissements_corporels"}  # valeurs deja par action : pas de conversion d'unite


def sans_accents(s):
    s = s.replace("\u2019", "'").replace("\u2018", "'").replace("\u00a0", " ")
    s = "".join(c if ord(c) < 128 else (unicodedata.normalize("NFKD", c).encode("ascii", "ignore").decode() or "?") for c in s)
    return s.lower()


NUM = re.compile(r"^\(?-?\d+(?:[.,]\d{1,2})?\)?$")


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
            ent = [re.split(r"[.,]", x)[0] for x in brut]
            if any(len(x) != 3 for x in ent[1:]) or (len(g) > 1 and len(ent[0]) > 3):
                vals = None
                break
            if len(brut[0]) > 1 and brut[0].startswith("0"):
                vals = None
                break
            if any(re.search(r"[.,]", x) for x in brut[:-1]):
                vals = None
                break
            v = float("".join(brut).replace(",", ".")) if re.search(r"[.,]", brut[-1]) else int("".join(brut))
            vals.append(-v if neg else v)
        if vals is not None:
            res.append(vals)
    return res


def normaliser_nombres(s):
    """1,234,567 ou 1.234.567 -> 1234567 ; les milliers separes par des espaces sont geres ensuite."""
    s = re.sub(r"(?<![\d,.])(\d{1,3}(?:,\d{3}){2,})(?![\d,])", lambda m: m.group(1).replace(",", ""), s)
    s = re.sub(r"(?<![\d,.])(\d{1,3}(?:\.\d{3}){2,})(?![\d.])", lambda m: m.group(1).replace(".", ""), s)
    s = s.replace("\u202f", " ").replace("\u00a0", " ")
    return s


def lire_valeurs(apres, attendu=2):
    """Lit les nombres qui suivent un libelle, jusqu'au prochain mot (cas des tableaux cote a cote)."""
    jetons = []
    apres = normaliser_nombres(re.sub(r"^\s*\([^)]*[A-Za-z][^)]*\)", "", apres))
    mots = apres.split()
    while mots and re.match(r"^\d{1,2}\.\d{1,2}$", mots[0]) and len(mots) > 2:  # renvoi a une note (ex. 4.1)
        mots = mots[1:]
    for t in mots:
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
    if re.search(r"en milliards|\(milliards", t):
        return 1_000_000_000
    if re.search(r"en millions|\(millions|millions de f", t):
        return 1_000_000
    if re.search(r"en milliers|\(milliers|milliers de f|en kfcfa|en k ?fcfa", t):
        return 1_000
    if re.search(r"en (?:francs? )?f\.? ?cfa|\(f\.? ?cfa\)|en xof|\(en francs", t):
        return 1
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


NOM_FICHIER = re.compile(r"^([A-Z]{3,6})_?(20\d\d)(S\d|T\d)?\.pdf$", re.I)


def lire_pages(pdf_path, max_pages=60):
    """Texte de chaque page ; si le PDF est une image scannee, reconnaissance de caracteres (tesseract)."""
    with pdfplumber.open(pdf_path) as pdf:
        pages = [(p.extract_text() or "", p.extract_text_lines()) for p in pdf.pages[:max_pages]]
    if sum(len(t.strip()) for t, _ in pages) >= 300 * max(1, len(pages)):
        return pages, False
    import shutil, subprocess, tempfile
    if not shutil.which("tesseract"):
        return pages, False
    langs = subprocess.run(["tesseract", "--list-langs"], capture_output=True, text=True).stdout
    lang = "fra" if "\nfra" in langs else "eng"
    out = []
    with tempfile.TemporaryDirectory() as d:
        subprocess.run(["pdftoppm", "-r", "200", "-l", str(max_pages), "-gray", "-png", str(pdf_path), d + "/p"], check=True)
        for img in sorted(Path(d).glob("p*.png")):
            t = subprocess.run(["tesseract", str(img), "-", "-l", lang, "--psm", "6"], capture_output=True, text=True).stdout
            out.append((t, [{"text": x} for x in t.splitlines() if x.strip()]))
    return out, True


def deduire_unite(texte, n):
    m = re.search(r"capital (?:social )?de ([\d .,]{5,}) ?(?:f\.? ?cfa|fcfa|francs)", sans_accents(texte))
    cap = n.get("capital")
    if m and cap:
        try:
            vrai = int(re.sub(r"\D", "", m.group(1)))
            r = vrai / cap
            for f in (1, 1_000, 1_000_000):
                if 0.9 < r / f < 1.1:
                    return f
        except Exception:
            pass
    ref = max(abs(n.get(k) or 0) for k in ("ca", "pnb", "res_net", "capitaux_propres"))
    return 1 if ref >= 1e9 else 1_000


def extraire(pdf_path, ticker=None, historique_div=None):
    nom = Path(pdf_path).name
    pages, ocr = lire_pages(pdf_path)
    tout = "\n".join(t for t, _ in pages)
    norme = detecter_norme(tout)
    m_nom = NOM_FICHIER.match(nom)
    annee = int(m_nom.group(2)) if m_nom else exercice_du_document(tout, nom)
    libs = LIBELLES[norme]
    n, n1, notes = {}, {}, []
    unite_doc = unite_de(tout)
    # une seule unite dans tout le document : on l'applique partout ; plusieurs : page par page
    for texte_page, lignes in pages:
        unite = unite_de(texte_page) or unite_doc or 1
        sans_unite = not (unite_de(texte_page) or unite_doc)
        devant = ordre_colonnes(texte_page, annee)
        for l in lignes:
            brut = l["text"]
            s = sans_accents(brut)
            mc = re.match(r"^([A-Z]{1,2}\d?) (?=\S)", brut)  # code SYSCOHADA (XB, XE...) ou lettre parasite
            off = mc.end() if mc else 0
            code = CODES.get(mc.group(1)) if mc and norme == "syscohada" else None
            if code and code not in n:
                vals = lire_valeurs(re.sub(r"^[^\d(\-]*", "", re.sub(r"\([^)]*[A-Za-z][^)]*\)", "", brut[off:])))
                if vals and len(vals) == 2:
                    cur, prev = (vals[0], vals[1]) if devant else (vals[1], vals[0])
                    n[code], n1[code] = cur * unite, prev * unite
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
    # Unite non indiquee : on la deduit du capital social ecrit en toutes lettres dans l'en-tete
    if not unite_doc and n:
        f = deduire_unite(tout, n)
        if f != 1:
            for d in (n, n1):
                for k in list(d):
                    if k not in PAR_ACTION:
                        d[k] = d[k] * f
            notes.append("Unité non indiquée : déduite du capital social (x%d)." % f)
    if ocr:
        notes.append("Rapport scanné, lu par reconnaissance de caractères : chiffres à contrôler.")
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
        brut = n["res_net_part_groupe"] / n["bpa"]
        nb_actions = int(round(brut, -int(math.log10(brut)) + 2))  # le BPA publie est arrondi
        notes.append("Nombre d’actions déduit du bénéfice par action publié (valeur approchée).")
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
    if ca is not None and rn is not None and ca > 0 and rn < -0.5 and (n1.get("res_net") or 0) > 0:
        out.append(f"Titre trompeur possible : l’activité progresse ({ca:+.0%}) mais le bénéfice chute ({rn:+.0%}). Regardez d’où vient la baisse avant de conclure.")
    if n.get("res_exploitation") is not None and n["res_exploitation"] < 0 < (n.get("res_net") or 0):
        out.append("Le bénéfice ne vient pas de l’activité propre (résultat d’exploitation négatif) : il vient des produits financiers, souvent les dividendes des filiales.")
    if n.get("produits_financiers") and n1.get("produits_financiers") and n["produits_financiers"] < 0.5 * n1["produits_financiers"]:
        out.append(f"Les produits financiers ont fortement baissé ({var('produits_financiers'):+.0%}).")
    if n.get("res_net") and e.get("dividende_total"):
        taux = e["dividende_total"] / n["res_net"]
        out.append(f"Dividende proposé : {taux:.0%} du bénéfice de l’exercice.")
    inv = n.get("investissements_corporels") or n.get("investissements")
    inv1 = n1.get("investissements_corporels") or n1.get("investissements")
    if inv and inv1 and abs(inv) > 1.6 * abs(inv1):
        out.append(f"Les investissements ont fortement augmenté ({abs(inv) / abs(inv1) - 1:+.0%}).")
    return out


UA = {"User-Agent": "Mozilla/5.0 (mon_plan_brvm ; lecture des etats financiers publics)"}


def est_annuel(titre):
    t = sans_accents(titre)
    return "etats financiers" in t and not re.search(r"semestre|semestriel|trimestre|trimestriel|s1 |t1 |t2 |t3 ", t)


def automatique(base):
    """Lit les communiques collectes par brvm_actus.py et traite les nouveaux etats financiers annuels."""
    import tempfile
    import requests
    actus = ICI / "actualites.json"
    if not actus.exists():
        print("actualites.json absent : rien a faire.")
        return
    comms = json.loads(actus.read_text(encoding="utf-8")).get("communiques", [])
    traites = base.setdefault("_traites", {})
    nouveaux = 0
    for c in comms:
        url, t = c.get("url", ""), c.get("ticker") or (c.get("tickers") or [None])[0]
        if not url.lower().endswith(".pdf") or not t or not est_annuel(c.get("titre", "")):
            continue
        etat = traites.get(url, {})
        if etat.get("ok") or etat.get("essais", 0) >= 3:
            continue
        try:
            r = requests.get(url, headers=UA, timeout=60)
            r.raise_for_status()
            with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
                f.write(r.content)
                chemin = f.name
            e = enregistrer(base, chemin, t, Path(url).name, url)
            e["date_publication"] = c.get("date")
            traites[url] = {"ok": True, "ticker": t, "exercice": e["exercice"], "date": c.get("date")}
            nouveaux += 1
        except Exception as ex:  # un rapport illisible ne doit jamais bloquer la mise a jour
            traites[url] = {"ok": False, "essais": etat.get("essais", 0) + 1, "erreur": str(ex)[:150]}
            print(f"{t} : echec ({str(ex)[:80]})")
    print(f"Fondamentaux : {nouveaux} nouveau(x) rapport(s) traite(s).")
    # Operations sur titres : fractionnements (divisions du nominal)
    ops = base.setdefault("_operations", {})
    for c in comms:
        url, t = c.get("url", ""), c.get("ticker") or (c.get("tickers") or [None])[0]
        titre = sans_accents(c.get("titre", ""))
        if not t or not re.search(r"fractionnement|division du nominal|split", titre):
            continue
        deja = [o for o in ops.get(t, []) if o.get("url") == url]
        if deja and (deja[0].get("facteur") or deja[0].get("essais", 0) >= 3):
            continue
        op = deja[0] if deja else {"type": "fractionnement", "date": c.get("date"), "url": url, "titre": c.get("titre")}
        if not deja:
            ops.setdefault(t, []).append(op)
        if url.lower().endswith(".pdf"):
            try:
                r = requests.get(url, headers=UA, timeout=60)
                r.raise_for_status()
                with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
                    f.write(r.content)
                with pdfplumber.open(f.name) as pdf:
                    texte = "\n".join(p.extract_text() or "" for p in pdf.pages)
                op["facteur"] = facteur_fractionnement(texte)
            except Exception as ex:
                op["erreur"] = str(ex)[:150]
            op["essais"] = op.get("essais", 0) + 1
        print(f"{t} : fractionnement du {op['date']}, facteur {op.get('facteur') or 'non lu'}")


def facteur_fractionnement(texte):
    """Lit la parite d'un fractionnement dans un communique (ex. 10 actions nouvelles pour 1 ancienne)."""
    t = re.sub(r"\s+", " ", sans_accents(texte))
    t = re.sub(r"(?<=\d) (?=\d{3}\b)", "", t)  # 1 000 000 -> 1000000
    motifs = [
        r"(\d+) actions? nouvelles? (?:pour|contre) (?:une|1) actions? anciennes?",
        r"(?:une|1) actions? anciennes? (?:donne(?:ra)? droit a|pour|contre|=) (\d+) actions? nouvelles?",
        r"parite (?:de )?(?:une|1) (?:pour|contre|/|:) ?(\d+)",
        r"parite (?:de )?(\d+) (?:pour|contre|/|:) ?(?:une|1)\b",
        r"divis(?:ee|e|ion)? (?:de la valeur nominale )?par (\d+)",
        r"fractionnement (?:de (?:l'? ?)?actions? |des actions )?par (\d+)",
        r"(?:valeur|cours) (?:theorique|ajuste)[^.]{0,80}?/ ?(\d+)\b",
    ]
    for m in motifs:
        x = re.search(m, t)
        if x and 1 < int(x.group(1)) <= 1000:
            return int(x.group(1))
    # valeur nominale qui passe de A a B, ou nombre d'actions qui passe de A a B
    for m in [r"valeur nominale[^.]{0,80}?de (\d+) ?f? ?cfa a (\d+) ?f? ?cfa", r"de (\d{6,}) actions a (\d{6,}) actions"]:
        x = re.search(m, t)
        if x:
            a, b = int(x.group(1)), int(x.group(2))
            r = a / b if "nominale" in m else b / a
            if r > 1 and abs(r - round(r)) < 0.01:
                return int(round(r))
    return None


def enregistrer(base, chemin, ticker, nom=None, url=None):
    e = extraire(chemin, ticker)
    if nom:
        e["source"] = nom
        m = re.match(r"(20\d\d)(\d\d)(\d\d)", nom)
        if m and not e.get("date_publication"):
            e["date_publication"] = "-".join(m.groups())
    if url:
        e["url"] = url
    e["signaux"] = signaux(e)
    if e["exercice"] is None:
        raise ValueError("exercice introuvable")
    base.setdefault(ticker, {})[str(e["exercice"])] = e
    etat = "A VERIFIER" if e["a_verifier"] else "ok"
    print(f"{ticker} {e['exercice']} ({e['norme']}) : {len(e['valeurs'].get(str(e['exercice']), {}))} chiffres, {etat}")
    return e


def fusionner_saisies(base):
    """Ajoute les chiffres releves a la main (rapports scannes) : ils priment sur la lecture automatique."""
    f = ICI / "saisies_manuelles.json"
    if not f.exists():
        return
    for t, par_an in json.loads(f.read_text(encoding="utf-8")).items():
        if t.startswith("_"):
            continue
        for a, x in par_an.items():
            e = {"ticker": t, "source": x.get("source"), "norme": x["norme"], "exercice": int(a),
                 "valeurs": {a: x["n"], str(int(a) - 1): x.get("n1", {})}, "dividende_brut_par_action": x.get("dpa"),
                 "dividende_total": x.get("dividende_total"), "nombre_actions": x.get("nombre_actions"),
                 "notes": x.get("notes", []) + ["Chiffres relevés à la main sur le rapport scanné."], "saisie_manuelle": True}
            e["controles"] = controler(e["norme"], x["n"], x.get("n1", {}))
            e["signaux"] = signaux(e)
            e["a_verifier"] = any(not c["ok"] for c in e["controles"])
            base.setdefault(t, {})[a] = e


def main(args):
    base = json.loads(SORTIE.read_text(encoding="utf-8")) if SORTIE.exists() else {}
    if args and args[0] == "--auto":
        automatique(base)
    else:  # mode manuel : python brvm_fondamentaux.py rapport.pdf TICKER [autre.pdf TICKER ...]
        i = 0
        while i < len(args):
            f = args[i]; t = None
            if i + 1 < len(args) and not args[i + 1].lower().endswith(".pdf"):
                t = args[i + 1]; i += 1
            i += 1
            enregistrer(base, f, t or Path(f).stem, Path(f).name)
    fusionner_saisies(base)
    SORTIE.write_text(json.dumps(base, ensure_ascii=False, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main(sys.argv[1:])
