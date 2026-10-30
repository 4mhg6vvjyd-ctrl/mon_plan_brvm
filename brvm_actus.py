import html as _html
import json
import os
import re
import sys
import time
import requests

H = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"}
SORTIE = "actualites.json"
CONSERVER_JOURS = 120
BASE = "https://www.sikafinance.com"
SOURCES_ARTICLES = [("Actualites du marche", BASE + "/marches/actualites_bourse_brvm"),
                    ("Actualites economiques", BASE + "/economie/")]
URL_COMMUNIQUES = BASE + "/marches/communiques_brvm"
URL_MATIERES = BASE + "/economie/commodities"
URL_DIVIDENDES = BASE + "/marches/dividendes"

# nom Sikafinance (en majuscules) -> code BRVM
NOM_VERS_CODE = {
    "AFRICA GLOBAL LOGISTICS": "SDSC", "BANK OF AFRICA BENIN": "BOAB", "BANK OF AFRICA BURKINA FASO": "BOABF",
    "BANK OF AFRICA CI": "BOAC", "BANK OF AFRICA MALI": "BOAM", "BANK OF AFRICA NIGER": "BOAN", "BANK OF AFRICA SENEGAL": "BOAS",
    "BANQUE INTERNATIONALE POUR LE COMMERCE DU BENIN": "BICB", "BERNABE": "BNBC", "BICICI": "BICC",
    "BRIDGE BANK GROUP COTE D'IVOIRE": "BBGC", "CFAO CI": "CFAC", "CIE CI": "CIEC", "CORIS BANK INTERNATIONAL BF": "CBIBF",
    "CROWN SIEM": "SEMC", "ECOBANK CI": "ECOC", "ETI TG": "ETIT", "FILTISAC CI": "FTSC", "LOTERIE NATIONALE DU BENIN": "LNBB",
    "NEI CEDA CI": "NEIC", "NESTLE CI": "NTLC", "NSIA BANQUE": "NSBC", "ONATEL BF": "ONTBF", "ORAGROUP TOGO": "ORGT",
    "ORANGE CI": "ORAC", "PALMCI": "PALC", "SAFCA CI": "SAFC", "SAPH CI": "SPHC", "SERVAIR ABIDJAN CI": "ABJC", "SETAO CI": "STAC",
    "SGBCI": "SGBC", "SICABLE CI": "CABC", "SICOR": "SICC", "SITAB": "STBC", "SMB CI": "SMBC",
    "SOCIETE IVOIRIENNE DE BANQUE CI": "SIBC", "SODECI": "SDCC", "SOGB": "SOGC", "SOLIBRA CI": "SLBC", "SONATEL": "SNTS",
    "SUCRIVOIRE": "SCRC", "TOTAL CI": "TTLC", "TOTAL SENEGAL": "TTLS", "TRACTAFRIC MOTORS CI": "PRSC", "UNILEVER CI": "UNLC",
    "UNIWAX CI": "UNXC", "VIVO ENERGY CI": "SHEC",
}
# expressions cherchees dans les titres -> code
ALIAS = {"sonatel": "SNTS", "orange ci": "ORAC", "orange côte d": "ORAC", "sgbci": "SGBC", "société générale côte d": "SGBC",
         "bernabé": "BNBC", "bernabe": "BNBC", "uniwax": "UNXC", "loterie nationale du bénin": "LNBB", "nsia banque": "NSBC",
         "ecobank côte d": "ECOC", "ecobank ci": "ECOC", "coris bank": "CBIBF", "onatel": "ONTBF", "palm ci": "PALC", "palmci": "PALC",
         "sapH": "SPHC", "saph": "SPHC", "sogb": "SOGC", "sucrivoire": "SCRC", "solibra": "SLBC", "sitab": "STBC", "total sénégal": "TTLS",
         "totalenergies marketing ci": "TTLC", "total ci": "TTLC", "vivo energy": "SHEC", "sicable": "CABC", "filtisac": "FTSC",
         "cie ci": "CIEC", "sodeci": "SDCC", "nestlé ci": "NTLC", "nestle ci": "NTLC", "unilever ci": "UNLC", "servair": "ABJC",
         "tractafric": "PRSC", "cfao": "CFAC", "bicici": "BICC", "bridge bank": "BBGC", "africa global logistics": "SDSC",
         "bank of africa bénin": "BOAB", "boa bénin": "BOAB", "bank of africa côte d": "BOAC", "boa côte d": "BOAC",
         "boa sénégal": "BOAS", "boa mali": "BOAM", "boa niger": "BOAN", "boa burkina": "BOABF", "oragroup": "ORGT",
         "setao": "STAC", "smb ci": "SMBC", "nei-ceda": "NEIC", "nei ceda": "NEIC", "safca": "SAFC"}
ALIAS = {k.lower(): v for k, v in ALIAS.items()}

CATEGORIES = [
    ("Resultats", 3, ["résultat net", "resultat net", "bénéfice", "benefice", "perte", "chiffre d'affaires", "rapport d'activit", "rapport dactivit", "résultats", "resultats", "trimestre", "semestre", "t3", "t2", "t1"]),
    ("Dividende", 3, ["dividende", "détachement", "detachement", "coupon"]),
    ("Operation sur titres", 3, ["fractionnement", "augmentation de capital", "offre publique", "opa ", "opv", "rachat d'actions", "introduction en bourse", "scission", "fusion", "cession", "acquisition", "rachat"]),
    ("Reglementaire", 3, ["suspension", "radiation", "sanction", "amf-umoa", "crepmf", "mise en demeure"]),
    ("Notation", 2, ["notation", "note financière", "agence de notation", "rating"]),
    ("Macro / monnaie", 2, ["bceao", "taux directeur", "inflation", "pib", "fmi", "banque mondiale", "uemoa", "eurobond", "emprunt obligataire", "dette", "croissance", "budget", "réserves"]),
    ("Financement", 2, ["mobilise", "financement", "levée de fonds", "levee de fonds", "émission", "emission", "prêt", "pret "]),
    ("Gouvernance", 1, ["assemblée générale", "assemblee generale", "convocation", "nomination", "démission", "demission", "directeur général", "annulation"]),
    ("Matieres premieres", 1, ["cacao", "café", "brent", "pétrole", "petrole", "caoutchouc", "huile de palme", "sucre", "coton"]),
]
BRUIT = ["anthropic", "openai", "intelligence artificielle", "paris sportifs", "jeux d'argent", "jeux et paris", "football", "distinction"]
ZONE_RE = re.compile(r"(?<!\w)(uemoa|umoa|bceao|brvm|c[oô]te d['’]ivoire|ivoir\w*|abidjan|s[ée]n[ée]gal\w*|dakar|mali\w*|bamako|burkina\w*|b[ée]nin\w*|togo\w*|nig[ée]r(?!ia)\w*|guin[ée]e-bissau|afrique de l['’]ouest|orange|sonatel|sgbci|nsia|boa|bank of africa|ecobank)(?!\w)", re.I)
HORS_RE = re.compile(r"(?<!\w)(cameroun\w*|gabon\w*|tchad\w*|congo\w*|nig[ée]ria\w*|guin[ée]e [ée]quatoriale|centrafri\w*|rdc|cemac|kenya\w*|ghana\w*|[ée]thiopi\w*|maroc\w*|alg[ée]ri\w*|[ée]gypt\w*|afrique du sud|rwanda\w*|ouganda\w*|tanzani\w*|zambi\w*|zimbabw\w*|angola\w*|mozambi\w*|namibi\w*|madagascar|maurice)(?!\w)", re.I)
POSITIF = ["bondit", "hausse", "progress", "retour aux profits", "record", "bénéfice", "benefice en", "croissance", "prolonge son ascension", "bons résultats", "rebond", "améliore", "amelior", "relèvement"]
NEGATIF = ["perte", "baisse", "chute", "déficit", "deficit", "recul", "décevant", "decevant", "suspension", "annulation", "dégrad", "degrad", "repli", "plonge", "sanction", "défaut", "retrait"]


def propre(s):
    return re.sub(r"\s+", " ", _html.unescape(re.sub(r"<[^>]+>", " ", s or ""))).strip()


def nombre(s):
    t = str(s).replace("\xa0", "").replace("\u202f", "").replace(" ", "").replace("%", "").replace("$", "")
    if "," in t and "." in t:
        t = t.replace(",", "")
    else:
        t = t.replace(",", ".")
    try:
        return float(t)
    except Exception:
        return None


def classer(titre, extrait=""):
    t = (titre + " " + extrait).lower()
    cat, score = "Autre", 0
    for nom, poids, mots in CATEGORIES:
        if any(m in t for m in mots) and poids > score:
            cat, score = nom, poids
    pos = sum(1 for m in POSITIF if m in t)
    neg = sum(1 for m in NEGATIF if m in t)
    sent = 1 if pos > neg else (-1 if neg > pos else 0)
    if "fractionnement" in t:
        sent = 0
    if any(b in t for b in BRUIT):
        cat, score, sent = "Autre", 0, 0
    elif HORS_RE.search(t) and not ZONE_RE.search(t):
        cat, score = "Hors zone UEMOA", 0
    return cat, score, sent


def codes_dans(titre, extrait=""):
    t = (titre + " " + extrait).lower()
    trouves = []
    for k, v in ALIAS.items():
        if v not in trouves and re.search(r"(?<!\w)" + re.escape(k) + r"(?!\w)", t):
            trouves.append(v)
    return trouves


def telecharger(url):
    for essai in range(2):
        try:
            r = requests.get(url, headers=H, timeout=30)
            if r.status_code == 200 and len(r.text) > 2000:
                return r.text
        except Exception as e:
            err = str(e)[:100]
        time.sleep(1)
    return None


ART = re.compile(r"""<a\b[^>]*?href=["'](?P<u>(?:https?://(?:www\.)?sikafinance\.com)?/(?:marches|economie)/[^"'#?]*?_(?P<id>\d{4,7}))(?:[?#][^"']*)?["'][^>]*>(?P<in>.*?)</a>""", re.S | re.I)
IMG = re.compile(r'/i/info/s/(?P<tk>[A-Z0-9]+)\.(?P<cc>[a-z]{2})_', re.I)
MOIS = {"janvier": 1, "fevrier": 2, "février": 2, "mars": 3, "avril": 4, "mai": 5, "juin": 6, "juillet": 7, "aout": 8, "août": 8, "septembre": 9, "octobre": 10, "novembre": 11, "decembre": 12, "décembre": 12}
DATE_FR = re.compile(r"(?<!\d)(\d{1,2})\s+(janvier|f[ée]vrier|mars|avril|mai|juin|juillet|ao[uû]t|septembre|octobre|novembre|d[ée]cembre)\s*(?:-|–|&ndash;|&#8211;)?\s*(?:<[^>]*>|\s)*(\d{2}):(\d{2})", re.I)
DATE_SEULE = re.compile(r"(\d{2})/(\d{2})/(\d{4})")
DATE = re.compile(r"(\d{2})/(\d{2})/(\d{4})(?:\s|&nbsp;|<[^>]*>)+(\d{2}):(\d{2})")


def date_fr(m):
    jour, mois = int(m.group(1)), MOIS[m.group(2).lower()]
    maintenant = time.localtime()
    annee = maintenant.tm_year
    try:
        if time.mktime((annee, mois, jour, 0, 0, 0, 0, 0, -1)) > time.time() + 2 * 86400:
            annee -= 1
    except Exception:
        pass
    return "%04d-%02d-%02d %s:%s" % (annee, mois, jour, m.group(3), m.group(4))


def lire_articles(page, source):
    occ = {}
    for m in ART.finditer(page):
        i = m.group("id")
        u = m.group("u")
        if u.startswith("/"):
            u = BASE + u
        a = occ.setdefault(i, {"url": u, "titre": "", "ticker": None, "debut": m.start(), "fin": m.end(), "source": source})
        im = IMG.search(m.group("in"))
        if im and not im.group("tk").upper().startswith("BRVM"):
            a["ticker"] = im.group("tk").upper()
        txt = propre(m.group("in"))
        if len(txt) > 12 and len(txt) > len(a["titre"]):
            a["titre"] = txt
        a["fin"] = max(a["fin"], m.end())
    liste = sorted(occ.values(), key=lambda a: a["debut"])
    sortie = []
    for k, a in enumerate(liste):
        if not a["titre"]:
            continue
        suivant = liste[k + 1]["debut"] if k + 1 < len(liste) else len(page)
        precedent = liste[k - 1]["fin"] if k > 0 else 0
        apres = page[a["fin"]:min(suivant, a["fin"] + 2500)]
        avant = page[max(precedent, a["debut"] - 700):a["debut"]]
        df = DATE_FR.search(apres)
        d = DATE.search(apres)
        extrait = ""
        if df and (not d or df.start() < d.start()):
            iso = date_fr(df)
            extrait = propre(apres[:df.start()])
            premium = "(P)" in extrait[:8]
            extrait = extrait.replace("(P)", "").strip()
            sortie.append({"id": a["url"].rsplit("_", 1)[-1], "source": a["source"], "date": iso, "titre": a["titre"], "extrait": extrait[:300], "url": a["url"], "ticker": a["ticker"], "premium": premium})
            continue
        if d:
            extrait = propre(apres[:d.start()])
        else:
            lst = list(DATE.finditer(avant))
            if lst:
                d = lst[-1]
            else:
                d1 = list(DATE_SEULE.finditer(avant)) or list(DATE_SEULE.finditer(apres))
                if not d1:
                    continue
                d = d1[-1] if d1[-1].re is DATE_SEULE else d1[0]
            extrait = propre(apres[:300])
        heure = d.group(4) + ":" + d.group(5) if d.re is DATE else "00:00"
        premium = "(P)" in extrait[:8]
        extrait = extrait.replace("(P)", "").strip()
        iso = "%s-%s-%s %s" % (d.group(3), d.group(2), d.group(1), heure)
        sortie.append({"id": a["url"].rsplit("_", 1)[-1], "source": a["source"], "date": iso, "titre": a["titre"], "extrait": extrait[:300], "url": a["url"], "ticker": a["ticker"], "premium": premium})
    return sortie


def lire_communiques(page):
    out = []
    for tr in re.findall(r"<tr\b.*?</tr>", page, re.S | re.I):
        cells = re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", tr, re.S | re.I)
        if len(cells) < 2:
            continue
        d = re.match(r"\s*(\d{2})/(\d{2})/(\d{4})", propre(cells[0]))
        lien = re.search(r'href="([^"]+)"', cells[1])
        if not d or not lien:
            continue
        txt = propre(cells[1])
        societe, _, titre = txt.partition(" : ")
        url = lien.group(1)
        if url.startswith("/"):
            url = BASE + url
        out.append({"date": "%s-%s-%s" % (d.group(3), d.group(2), d.group(1)), "societe": societe.strip(), "titre": titre.strip().replace("_", "-"), "url": url,
                    "ticker": NOM_VERS_CODE.get(societe.strip().upper().replace("’", "'"))})
    return out


def lire_matieres(page):
    out = []
    for tr in re.findall(r"<tr\b.*?</tr>", page, re.S | re.I):
        if "cotation_" not in tr:
            continue
        cells = [propre(c) for c in re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", tr, re.S | re.I)]
        if len(cells) >= 5:
            dernier, var = nombre(cells[3]), nombre(cells[4])
            if dernier is not None:
                out.append({"nom": cells[0], "dernier": dernier, "variation": var})
    return out


def lire_dividendes(page):
    out = []
    debut = page.find("<table")
    fin = page.find("</table>", debut)
    zone = page[debut:fin] if debut >= 0 and fin > debut else page
    for tr in re.findall(r"<tr\b.*?</tr>", zone, re.S | re.I):
        cells = re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", tr, re.S | re.I)
        lien = re.search(r"cotation_([A-Z0-9]+)\.([a-z]{2})", tr)
        if len(cells) >= 4 and lien:
            out.append({"date": propre(cells[0]), "ticker": lien.group(1), "nom": propre(cells[1]), "montant": nombre(propre(cells[2])), "rendement": nombre(propre(cells[3]))})
    return out


def main():
    debug = "--debug" in sys.argv
    ancien = {}
    if os.path.exists(SORTIE):
        try:
            ancien = json.load(open(SORTIE, encoding="utf-8"))
        except Exception:
            ancien = {}
    print("=== ACTUALITES ET ANNONCES ===")
    articles = {a["url"]: a for a in ancien.get("articles", [])}
    for nom, url in SOURCES_ARTICLES:
        page = telecharger(url)
        if not page:
            print("  %-24s : page inaccessible" % nom)
            continue
        lus = lire_articles(page, nom)
        print("  %-24s : %d article(s) lu(s)" % (nom, len(lus)))
        if not lus:
            liens = re.findall(r"""href=["']([^"']*/(?:marches|economie)/[^"']*)["']""", page)
            print("   (diagnostic) taille de la page : %d caracteres, %d lien(s) /marches/ ou /economie/" % (len(page), len(liens)))
            ids = [l for l in liens if re.search(r"_\d{3,8}", l)]
            print("   (diagnostic) %d lien(s) qui se terminent par un numero :" % len(ids))
            for l in ids[:6]:
                print("      lien :", l[:140])
            d0 = re.search(r"\d{2}/\d{2}/\d{4}", page)
            if d0:
                print("   (diagnostic) autour de la premiere date :", page[max(0, d0.start() - 400):d0.start() + 60].replace("\n", " ")[:460])
            try:
                open("page_%s.html" % re.sub(r"\W+", "_", nom), "w", encoding="utf-8").write(page)
                print("   (diagnostic) page enregistree dans page_%s.html" % re.sub(r"\W+", "_", nom))
            except Exception:
                pass
        for a in lus:
            cat, score, sent = classer(a["titre"], a["extrait"])
            a.update({"categorie": cat, "score": score, "sentiment": sent})
            tk = [a["ticker"]] if a["ticker"] else []
            for c in codes_dans(a["titre"], a["extrait"]):
                if c not in tk:
                    tk.append(c)
            a["tickers"] = tk
            if a["ticker"] and score == 0:
                a["score"] = 1
            articles[a["url"]] = a
    communiques = {c["url"]: c for c in ancien.get("communiques", [])}
    page = telecharger(URL_COMMUNIQUES)
    if page:
        lus = lire_communiques(page)
        print("  %-24s : %d communique(s) lu(s)" % ("Communiques societes", len(lus)))
        for c in lus:
            cat, score, sent = classer(c["titre"])
            if "attestation" in c["titre"].lower():
                cat, score = "Attestation", 1
            c.update({"categorie": cat, "score": score, "sentiment": sent, "tickers": [c["ticker"]] if c["ticker"] else []})
            communiques[c["url"]] = c
    else:
        print("  Communiques societes     : page inaccessible")
    matieres = ancien.get("matieres", [])
    page = telecharger(URL_MATIERES)
    if page:
        lus = lire_matieres(page)
        print("  %-24s : %d cotation(s) lue(s)" % ("Matieres premieres", len(lus)))
        if lus:
            matieres = lus
    else:
        print("  Matieres premieres       : page inaccessible")
    dividendes = ancien.get("dividendes_a_venir", [])
    page = telecharger(URL_DIVIDENDES)
    if page:
        lus = lire_dividendes(page)
        print("  %-24s : %d ligne(s) lue(s)" % ("Dividendes a venir", len(lus)))
        if lus or "A préciser" in page:
            dividendes = lus
    else:
        print("  Dividendes a venir       : page inaccessible")
    limite = time.strftime("%Y-%m-%d", time.localtime(time.time() - CONSERVER_JOURS * 86400))
    arts = sorted([a for a in articles.values() if a["date"][:10] >= limite], key=lambda a: a["date"], reverse=True)
    comms = sorted([c for c in communiques.values() if c["date"] >= limite], key=lambda c: c["date"], reverse=True)
    json.dump({"maj": time.strftime("%Y-%m-%d %H:%M"), "articles": arts, "communiques": comms, "matieres": matieres, "dividendes_a_venir": dividendes},
              open(SORTIE, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("\nEnregistre dans %s : %d article(s), %d communique(s), %d matiere(s) premiere(s), %d dividende(s) a venir" % (SORTIE, len(arts), len(comms), len(matieres), len(dividendes)))
    print("\nLes plus importants (score 2 ou 3) :")
    imp = [x for x in arts + comms if x.get("score", 0) >= 2][:12]
    for x in sorted(imp, key=lambda z: z["date"], reverse=True)[:12]:
        s = {1: "+", 0: " ", -1: "-"}[x.get("sentiment", 0)]
        print("  %s %s [%s] %s %s" % (x["date"][:10], s, x["categorie"], ("(" + ",".join(x["tickers"]) + ") ") if x["tickers"] else "", (x.get("titre") or "")[:90]))
    print("\nCeci n'est pas du conseil financier.")


if __name__ == "__main__":
    main()
