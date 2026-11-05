"""Lecture des obligations cotées dans le Bulletin officiel de la cote (BOC) de la BRVM.

Usage : python brvm_obligations.py boc_AAAAMMJJ_2.pdf   (fichier local)
        python brvm_obligations.py --auto              (télécharge le BOC le plus récent)
Sortie : obligations.json
"""
import datetime as dt
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

ICI = Path(__file__).resolve().parent
SORTIE = ICI / "obligations.json"
PAYS = {"EOM": "Mali", "EOS": "Sénégal", "TPCI": "Côte d’Ivoire", "TPBF": "Burkina Faso", "TPNE": "Niger",
        "TPBJ": "Bénin", "TPTG": "Togo", "TPGB": "Guinée-Bissau"}
N = r"\d{1,3}(?: \d{3})*(?:[.,]\d+)?"
LIGNE = re.compile(
    r"^(?P<sym>[A-Z][A-Z0-9]*\.O\d+)\s+(?P<titre>.+?)\s{2,}(?P<nom>" + N + r")\s{2,}(?P<prec>" + N + r")\s{2,}"
    r"(?P<jour>NC|" + N + r")\s{2,}(?P<ref>" + N + r")\s{2,}(?:(?P<vol>" + N + r")\s{2,}(?P<val>" + N + r")\s{2,})?"
    r"(?P<couru>" + N + r")\s{2,}(?P<per>[AST])\s{2,}(?P<mnt>" + N + r")\s{2,}(?P<ech>\S+)\s{2,}(?P<am>[A-Z]+)\s*$")
EMETTEURS = {"EOM": "État du Mali", "EOS": "État du Sénégal", "TPCI": "Trésor public de Côte d’Ivoire",
             "TPBF": "Trésor public du Burkina Faso", "TPNE": "Trésor public du Niger", "TPBJ": "Trésor public du Bénin",
             "TPTG": "Trésor public du Togo"}


def nombre(s):
    if s is None:
        return None
    s = s.strip().replace(" ", "")
    if not s or s == "NC":
        return None
    if "," in s and "." not in s:
        s = s.replace(",", ".")
    elif "," in s and "." in s:
        s = s.replace(",", "")
    try:
        return float(s)
    except ValueError:
        return None


def secours(l):
    """Lignes atypiques (cotation suspendue « SP », colonnes vides) : lecture colonne par colonne."""
    m = re.match(r"^([A-Z][A-Z0-9]*\.O\d+)\s+(.*)$", l.rstrip())
    if not m:
        return None
    parts = re.split(r"\s{2,}", m.group(2).strip())
    titre = parts.pop(0)
    while parts and not re.fullmatch(N, parts[0]):
        titre += " " + parts.pop(0)
    if len(parts) < 6 or parts[-4] not in ("A", "S", "T"):
        return None
    couru, per, mnt, ech, am = parts[-5:]
    pre = parts[:-5]
    nums = [x for x in pre[1:] if re.fullmatch(N, x)]
    jour = next((x for x in pre[1:] if x in ("NC", "SP")), "NC")
    return {"sym": m.group(1), "titre": titre, "nom": pre[0] if pre else None, "prec": nums[0] if nums else None,
            "jour": jour, "ref": nums[1] if len(nums) > 1 else (nums[0] if nums else None), "vol": None, "val": None,
            "couru": couru, "per": per, "mnt": mnt, "ech": ech, "am": am}


def categorie(entete):
    e = entete.upper()
    if "SUKUK" in e:
        base = "Sukuk"
    elif "FCTC" in e or "TITRISATION" in e:
        base = "Titrisation"
    elif "CONVERTIBLE" in e:
        base = "Convertible"
    elif "SOUVERAINES" in e or "D’ÉTAT" in e or "D'ETAT" in e:
        base = "État"
    elif "INSTITUTIONS" in e:
        base = "Institution financière"
    elif "ENTREPRISES" in e:
        base = "Entreprise"
    else:
        base = None
    return base


def lire_boc(pdf):
    texte = subprocess.run(["pdftotext", "-layout", str(pdf), "-"], capture_output=True, text=True, check=True).stdout
    debut, fin = texte.find("1. OBLIGATIONS CLASSIQUES"), texte.find("TOTAL - MARCHE DES OBLIGATIONS")
    if debut < 0:
        raise ValueError("tableau des obligations introuvable dans le BOC")
    m = re.search(r"(lundi|mardi|mercredi|jeudi|vendredi)\s+(\d{1,2})\s+(\w+)\s+(20\d\d)", texte)
    date_boc = " ".join(m.groups()[1:]) if m else None
    lignes = texte[debut:fin if fin > 0 else None].splitlines()
    out, type_cour, gss = [], None, False
    for i, l in enumerate(lignes):
        s = l.strip()
        if re.match(r"^\d\.\s", s):
            gss = "GSS" in s or "VERTES" in s
            type_cour = categorie(s) or type_cour
        if re.match(r"^(OBLIGATIONS|FCTC|SUKUK)\b", s) and not re.search(r"\d", s):
            type_cour = categorie(s) or type_cour
            gss = gss or "GSS" in s
        mm = LIGNE.match(l.rstrip())
        if mm:
            d = mm.groupdict()
        else:
            d = secours(l)
            if not d:
                continue
        titre = re.sub(r"\s+", " ", d["titre"]).strip()
        suite = lignes[i + 1].strip() if i + 1 < len(lignes) else ""
        if re.fullmatch(r"\d{2,4}", suite):
            titre += suite if titre.endswith("-") else " " + suite
        taux = re.search(r"(\d+(?:[.,]\d+)?)\s*%", titre)
        ans = re.search(r"(20\d\d)\s*[-–]\s*(20\d\d)?", titre)
        nominal, ref = nombre(d["nom"]), nombre(d["ref"])
        prefixe = d["sym"].split(".")[0]
        out.append({
            "code": d["sym"], "nom": re.sub(r"^Etat", "État", titre.title()).replace(" Du ", " du ").replace(" De ", " de ").replace(" D’", " d’").replace("Tpci", "TPCI").replace("Tpbf", "TPBF").replace("Fctc", "FCTC").replace(" Sa ", " SA "),
            "emetteur": EMETTEURS.get(prefixe) or re.split(r"\s\d", titre)[0].strip().title(),
            "type": (type_cour or "Entreprise") + (" · durable" if gss else ""), "pays": PAYS.get(prefixe, "UEMOA"),
            "taux": nombre(taux.group(1)) if taux else None,
            "debut": int(ans.group(1)) if ans else None, "fin": int(ans.group(2)) if ans and ans.group(2) else None,
            "nominal": nominal, "cours": round(ref / nominal * 100, 2) if ref and nominal else None, "prix": ref,
            "periodicite": d["per"], "amort": d["am"], "coupon_net": nombre(d["mnt"]), "prochain_coupon": d["ech"],
            "coupon_couru": nombre(d["couru"]), "volume": nombre(d["vol"]), "valeur": nombre(d["val"]),
            "cote_du_jour": d["jour"] not in ("NC", "SP"), "suspendue": d["jour"] == "SP"})
    try:
        ind = lire_indices(texte, date_boc)
        if ind["principaux"]:
            (ICI / "indices.json").write_text(json.dumps(ind, ensure_ascii=False, indent=1), encoding="utf-8")
            print("Indices : %d principaux, %d par compartiment ou secteur" % (len(ind["principaux"]), len(ind["secteurs"])))
    except Exception as ex:
        print("Indices : lecture impossible (%s)" % ex)
    return {"source": "Bulletin officiel de la cote BRVM", "date": date_boc, "obligations": out}


def lire_indices(texte, date_boc):
    """Indices de la premiere page du BOC : Composite, BRVM 30, Prestige, compartiments et secteurs."""
    num = lambda x: float(x.replace(" ", "").replace(",", ".").replace("%", ""))
    out = {"date": date_boc, "principaux": [], "secteurs": []}
    l_val = re.search(r"BRVM COMPOSITE\s+([\d ,]+?)\s{2,}BRVM 30\s+([\d ,]+?)\s{2,}BRVM PRESTIGE\s+([\d ,]+)", texte)
    l_j = re.search(r"Variation Jour\s+(-?[\d,]+) %\s+Variation Jour\s+(-?[\d,]+) %\s+Variation Jour\s+(-?[\d,]+) %", texte)
    l_a = re.search(r"Variation annuelle\s+(-?[\d,]+) %\s+Variation annuelle\s+(-?[\d,]+) %\s+Variation annuelle\s+(-?[\d,]+) %", texte)
    if l_val:
        for i, nom in enumerate(["BRVM Composite", "BRVM 30", "BRVM Prestige"]):
            out["principaux"].append({"nom": nom, "valeur": num(l_val.group(i + 1)),
                                      "var_jour": num(l_j.group(i + 1)) if l_j else None, "var_an": num(l_a.group(i + 1)) if l_a else None})
    for m in re.finditer(r"^\s*(BRVM\s*[-–]\s*[A-Z][A-Z ’'ÉÈ-]+?)\s*(?:\(\*\*\))?\s{2,}(\d+)\s{2,}([\d ,]+?)\s{2,}(-?[\d,]+) %\s{2,}(-?[\d,]+) %\s{2,}[\d ]+?\s{2,}[\d ]+?\s{2,}([\d ,]+)\s*$", texte, re.M):
        nom = re.sub(r"\s+", " ", m.group(1)).replace("BRVM - ", "").replace("BRVM – ", "").replace("BRVM-", "").strip().title()
        out["secteurs"].append({"nom": nom, "societes": int(m.group(2)), "valeur": num(m.group(3)), "var_jour": num(m.group(4)),
                                "var_an": num(m.group(5)), "per": num(m.group(6))})
    m = re.search(r"Capitalisation boursi[èe]re \(FCFA\)\(Actions & Droits\)\s+([\d ]+?)\s{2,}", texte)
    if m:
        out["capitalisation_actions"] = int(m.group(1).replace(" ", ""))
    return out


def automatique():
    """Télécharge le BOC des 7 derniers jours ouvrés (le plus récent disponible)."""
    import requests
    j = dt.date.today()
    for _ in range(10):
        if j.weekday() < 5:
            for url in ("https://www.brvm.org/sites/default/files/boc_%s_2.pdf" % j.strftime("%Y%m%d"),
                        "https://www.brvm.org/sites/default/files/boc_%s.pdf" % j.strftime("%Y%m%d")):
                try:
                    r = requests.get(url, timeout=60, headers={"User-Agent": "Mozilla/5.0 (NAFA)"})
                    if r.ok and r.content[:4] == b"%PDF":
                        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
                            f.write(r.content)
                        return lire_boc(f.name)
                except Exception:
                    pass
        j -= dt.timedelta(days=1)
    raise RuntimeError("aucun BOC récent téléchargeable")


def main(args):
    try:
        res = automatique() if args[:1] == ["--auto"] else lire_boc(args[0])
    except Exception as ex:  # ne jamais bloquer la mise a jour : on garde l'ancienne liste
        print("Obligations : échec (%s), liste précédente conservée" % ex)
        return
    if len(res["obligations"]) < 20:
        print("Obligations : lecture incomplète (%d titres), liste précédente conservée" % len(res["obligations"]))
        return
    SORTIE.write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
    print("Obligations : %d titres lus (BOC du %s)" % (len(res["obligations"]), res["date"]))


if __name__ == "__main__":
    main(sys.argv[1:])
