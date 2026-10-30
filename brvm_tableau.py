import glob
import html
import json
import os
import sys
import time
import webbrowser
import numpy as np
import pandas as pd
import brvm_regles as REGLES

DONNEES = "brvm_donnees"
DIVS = "brvm_dividendes"
ACTUS = "actualites.json"
EVENTS = "evenements.csv"
SORTIE = "brvm_tableau.html"
CANDIDATS = "candidats.json"
N_LIGNES_DEFAUT = 8
FENETRE = 120
HISTORIQUE_MIN = 250
RETARD_MAX = 10
SEUIL_ETUDIER = 75      # score minimal pour etre classe 'a etudier' (sans point de vigilance grave)
SEUIL_SURVEILLER = 60   # score minimal pour etre classe 'a surveiller'

NOMS = {
    "SNTS": ("Sonatel", "Telecoms"), "ORAC": ("Orange CI", "Telecoms"), "ONTBF": ("Onatel BF", "Telecoms"),
    "SGBC": ("SGBCI", "Finance"), "SIBC": ("SIB CI", "Finance"), "BICC": ("BICICI", "Finance"), "BOAC": ("BOA Cote d'Ivoire", "Finance"),
    "BOAB": ("BOA Benin", "Finance"), "BOABF": ("BOA Burkina Faso", "Finance"), "BOAM": ("BOA Mali", "Finance"), "BOAN": ("BOA Niger", "Finance"),
    "BOAS": ("BOA Senegal", "Finance"), "ETIT": ("ETI (Ecobank Transnational)", "Finance"), "ECOC": ("Ecobank CI", "Finance"),
    "CBIBF": ("Coris Bank International", "Finance"), "NSBC": ("NSIA Banque CI", "Finance"), "ORGT": ("Oragroup Togo", "Finance"),
    "SAFC": ("Safca CI", "Finance"), "BBGC": ("Bridge Bank Group CI", "Finance"), "BICB": ("Banque Intl pour le Commerce du Benin", "Finance"),
    "PALC": ("PalmCI", "Agro-industrie"), "SOGC": ("SOGB", "Agro-industrie"), "SPHC": ("SAPH CI", "Agro-industrie"), "SCRC": ("Sucrivoire", "Agro-industrie"),
    "NTLC": ("Nestle CI", "Conso. de base"), "SLBC": ("Solibra CI", "Conso. de base"), "UNLC": ("Unilever CI", "Conso. de base"), "STBC": ("Sitab", "Conso. de base"),
    "CFAC": ("CFAO CI", "Distribution"), "PRSC": ("Tractafric Motors CI", "Distribution"), "BNBC": ("Bernabe CI", "Distribution"),
    "TTLC": ("Total CI", "Energie"), "TTLS": ("Total Senegal", "Energie"), "SHEC": ("Vivo Energy CI", "Energie"), "SMBC": ("SMB CI", "Energie"),
    "CABC": ("Sicable CI", "Industrie"), "FTSC": ("Filtisac CI", "Industrie"), "SEMC": ("Crown Siem", "Industrie"), "SIVC": ("SIVC (nom a verifier)", "Industrie"),
    "STAC": ("Setao CI", "Industrie"), "SICC": ("Sicor", "Industrie"), "NEIC": ("NEI-CEDA CI", "Industrie"), "UNXC": ("Uniwax CI", "Industrie"),
    "CIEC": ("CIE CI", "Services publics"), "SDCC": ("SODECI", "Services publics"),
    "SDSC": ("Africa Global Logistics", "Transport / services"), "ABJC": ("Servair Abidjan CI", "Transport / services"), "LNBB": ("Loterie Nationale du Benin", "Transport / services"),
}
GROUPES = {"BOA": {"BOAB", "BOABF", "BOAC", "BOAM", "BOAN", "BOAS"}, "Total": {"TTLC", "TTLS"}, "Orange": {"SNTS", "ORAC"}}
PAYS = {"ci": "Cote d'Ivoire", "sn": "Senegal", "bf": "Burkina Faso", "tg": "Togo", "bj": "Benin", "ml": "Mali", "ne": "Niger"}
IMPACT = [("CACAO", "Premier produit d'exportation de la Cote d'Ivoire : revenus agricoles, recettes publiques et consommation (effet indirect sur banques et distribution).", []),
          ("CAOUTCHOUC", "Prix du caoutchouc : chiffre d'affaires de SAPH, SOGB et PalmCI.", ["SPHC", "SOGC", "PALC"]),
          ("PALM", "Huile de palme : chiffre d'affaires de PalmCI et SOGB.", ["PALC", "SOGC"]),
          ("SUCRE", "Prix du sucre : Sucrivoire.", ["SCRC"]),
          ("BRENT", "Petrole : marges des distributeurs d'hydrocarbures, inflation et pouvoir d'achat dans l'UEMOA.", ["TTLC", "TTLS", "SHEC", "SMBC"]),
          ("WTI", "Petrole : marges des distributeurs d'hydrocarbures, inflation et pouvoir d'achat.", ["TTLC", "TTLS", "SHEC", "SMBC"]),
          ("COTON", "Matiere premiere du textile (impression sur tissus) : Uniwax.", ["UNXC"]),
          ("CAFE", "Cafe : effet indirect sur l'economie ivoirienne.", []),
          ("OR ", "Or : valeur refuge, reserves de la BCEAO.", [])]


def h(x):
    return html.escape(str(x), quote=True)


def fmt(x, d=0):
    if x is None or (isinstance(x, float) and np.isnan(x)):
        return "-"
    return ("{:,.%df}" % d).format(x).replace(",", " ")


def pct(x, d=1, signe=True):
    if x is None or (isinstance(x, float) and np.isnan(x)):
        return "-"
    if abs(x * 100) < 0.5 * 10 ** (-d):
        x = 0.0
    return ("{:+.%df} %%" % d if signe and x != 0 else "{:.%df} %%" % d).format(x * 100).replace(".", ",")


def cls(x):
    if x is None or (isinstance(x, float) and np.isnan(x)) or abs(x) < 0.0005:
        return ""
    return "pos" if x > 0 else "neg"


def spark(vals, w=92, hh=26, color="#2a6fdb"):
    v = np.asarray([x for x in vals if not np.isnan(x)], dtype=float)
    if len(v) < 5:
        return ""
    lo, hi = v.min(), v.max()
    rng = (hi - lo) or 1.0
    pts = " ".join("%.1f,%.1f" % (i * (w - 2) / (len(v) - 1) + 1, hh - 2 - (x - lo) / rng * (hh - 4)) for i, x in enumerate(v))
    return '<svg width="%d" height="%d" viewBox="0 0 %d %d"><polyline fill="none" stroke="%s" stroke-width="1.5" points="%s"/></svg>' % (w, hh, w, hh, color, pts)


def courbe(series, w=900, hh=250, sma=None):
    dates, vals = series.index, series.values.astype(float)
    pad_l, pad_b = 52, 22
    lo, hi = np.nanmin(vals), np.nanmax(vals)
    rng = (hi - lo) or 1.0
    X = lambda i: pad_l + i * (w - pad_l - 8) / (len(vals) - 1)
    Y = lambda x: 8 + (hh - pad_b - 8) * (1 - (x - lo) / rng)
    pts = " ".join("%.1f,%.1f" % (X(i), Y(x)) for i, x in enumerate(vals))
    out = ['<svg width="100%%" viewBox="0 0 %d %d" xmlns="http://www.w3.org/2000/svg">' % (w, hh)]
    for k in range(5):
        y = 8 + (hh - pad_b - 8) * k / 4
        val = hi - rng * k / 4
        out.append('<line x1="%d" y1="%.1f" x2="%d" y2="%.1f" stroke="#e5e5e5"/><text x="4" y="%.1f" font-size="11" fill="#777">%s</text>' % (pad_l, y, w - 8, y, y + 4, fmt(val)))
    last_year = None
    for i, d in enumerate(dates):
        if d.year != last_year and d.month in (1, 2) :
            last_year = d.year
            out.append('<text x="%.1f" y="%d" font-size="11" fill="#777">%d</text>' % (X(i), hh - 6, d.year))
    if sma is not None:
        sp = " ".join("%.1f,%.1f" % (X(i), Y(x)) for i, x in enumerate(sma.values.astype(float)) if not np.isnan(x))
        if sp:
            out.append('<polyline fill="none" stroke="#d9822b" stroke-width="1.2" stroke-dasharray="4 3" points="%s"/>' % sp)
    out.append('<polyline fill="none" stroke="#1b7f3b" stroke-width="2" points="%s"/></svg>' % pts)
    return "".join(out)


def charger():
    mapping = json.load(open(os.path.join(DONNEES, "mapping.json"))) if os.path.exists(os.path.join(DONNEES, "mapping.json")) else {}
    px = {}
    for f in sorted(glob.glob(os.path.join(DONNEES, "*.csv"))):
        t = os.path.splitext(os.path.basename(f))[0]
        df = pd.read_csv(f, index_col=0, parse_dates=True)
        px[t] = df[df["Close"] > 0]
    divs = {}
    for f in glob.glob(os.path.join(DIVS, "*.csv")):
        t = os.path.splitext(os.path.basename(f))[0]
        divs[t] = pd.read_csv(f).dropna(subset=["Montant"]).set_index("Annee")["Montant"]
    actus = json.load(open(ACTUS, encoding="utf-8")) if os.path.exists(ACTUS) else {}
    return mapping, px, divs, actus


def perf(c, n):
    return float(c.iloc[-1] / c.iloc[-1 - n] - 1) if len(c) > n else float("nan")


def analyser(t, df, divs, news):
    nom, secteur = NOMS.get(t, (t, "Autres"))
    r = {"t": t, "nom": nom, "secteur": secteur, "flags": [], "raisons": []}
    c = df["Close"]
    r["prix"] = float(c.iloc[-1])
    r["fin"] = df.index[-1]
    r["retard"] = (pd.Timestamp.now().normalize() - df.index[-1]).days
    r["n"] = len(df)
    for k, n in (("p1j", 1), ("p1s", 5), ("p1m", 21), ("p3m", 63), ("p6m", 126), ("p1a", 252)):
        r[k] = perf(c, n)
    prec = c[c.index.year < df.index[-1].year]
    r["ytd"] = float(c.iloc[-1] / prec.iloc[-1] - 1) if len(prec) else float("nan")
    ret = c.pct_change().clip(-0.10, 0.10)
    r["vol"] = float(ret.tail(252).std() * np.sqrt(252)) if len(c) > 60 else float("nan")
    h1 = c.tail(252)
    r["dd"] = float(c.iloc[-1] / h1.max() - 1)
    r["sma50"] = float(c.rolling(50).mean().iloc[-1]) if len(c) >= 50 else float("nan")
    r["sma200"] = float(c.rolling(200).mean().iloc[-1]) if len(c) >= 200 else float("nan")
    r["d200"] = r["prix"] / r["sma200"] - 1 if r["sma200"] == r["sma200"] else float("nan")
    r["d50"] = r["prix"] / r["sma50"] - 1 if r["sma50"] == r["sma50"] else float("nan")
    fen = df.tail(FENETRE)
    r["med"] = float((fen["Close"] * fen["Volume"]).median())
    r["spark"] = c.tail(120).values
    # dividendes
    d = divs.get(t)
    r["div"] = d
    r["rend_der"] = r["rend_moy"] = float("nan")
    r["serie"] = 0
    r["croiss"] = float("nan")
    r["croiss3"] = float("nan")
    suspect = coupe = False
    if d is not None and len(d) > 0:
        der = int(d.index.max())
        r["der"] = der
        v = {int(a): float(m) for a, m in d.items()}
        k = der
        while k in v and v[k] > 0:
            r["serie"] += 1
            k -= 1
        last3 = [v[a] for a in (der - 2, der - 1, der) if a in v and v[a] > 0]
        if (der - 3) in v and v[der - 3] > 0 and v.get(der, 0) > 0:
            r["croiss3"] = (v[der] / v[der - 3]) ** (1 / 3) - 1
        elif (der - 2) in v and v[der - 2] > 0 and v.get(der, 0) > 0:
            r["croiss3"] = (v[der] / v[der - 2]) ** 0.5 - 1
        r["rend_der"] = v[der] / r["prix"] if v.get(der, 0) > 0 else float("nan")
        r["rend_moy"] = float(np.mean(last3)) / r["prix"] if last3 else float("nan")
        if (der - 1) in v and v[der - 1] > 0 and v.get(der, 0) > 0:
            r["croiss"] = v[der] / v[der - 1] - 1
        prev = [v[a] for a in (der - 2, der - 1) if a in v and v[a] > 0]
        suspect = bool((r["rend_der"] == r["rend_der"] and r["rend_der"] > 0.15) or (prev and v.get(der, 0) > 3 * np.mean(prev)))
        coupe = bool(r["croiss"] == r["croiss"] and r["croiss"] < -0.30)
    # actualites
    recent = [x for x in news.get(t, []) if x["jours"] <= 30]
    r["news"] = recent
    neg = [x for x in recent if x.get("sentiment", 0) < 0 and x.get("score", 0) >= 2]
    pos = [x for x in recent if x.get("sentiment", 0) > 0 and x.get("score", 0) >= 2]
    # score
    s_liq = 20 if r["med"] >= 100e6 else 17 if r["med"] >= 50e6 else 14 if r["med"] >= 20e6 else 10 if r["med"] >= 10e6 else 5 if r["med"] >= 3e6 else 0
    s_tr = 0
    if r["d200"] == r["d200"] and r["d200"] > 0:
        s_tr += 10
    if r["sma50"] == r["sma50"] and r["sma200"] == r["sma200"] and r["sma50"] > r["sma200"]:
        s_tr += 8
    if r["p6m"] == r["p6m"]:
        s_tr += 7 if 0 <= r["p6m"] <= 0.60 else 3 if r["p6m"] > 0.60 else 0
    s_div = 0
    if "der" in r and r["der"] >= 2025 and r["rend_der"] == r["rend_der"]:
        s_div += 10
    s_div += 10 if r["serie"] >= 3 else 5 if r["serie"] == 2 else 0
    if r["rend_moy"] == r["rend_moy"] and not suspect:
        s_div += 10 if 0.06 <= r["rend_moy"] <= 0.12 else 7 if 0.03 <= r["rend_moy"] < 0.06 else 7 if 0.12 < r["rend_moy"] <= 0.15 else 3
    if r["croiss"] == r["croiss"] and r["croiss"] >= 0:
        s_div += 5
    s_risk = 0
    if r["vol"] == r["vol"]:
        s_risk += 10 if r["vol"] < 0.20 else 7 if r["vol"] < 0.30 else 4 if r["vol"] < 0.40 else 0
    s_risk += 10 if r["dd"] > -0.15 else 7 if r["dd"] > -0.25 else 3 if r["dd"] > -0.40 else 0
    s_ct = 0
    if r["p1m"] == r["p1m"]:
        s_ct = -8 if r["p1m"] <= -0.15 else -5 if r["p1m"] <= -0.10 else -2 if r["p1m"] <= -0.05 else 0
    r["score"] = max(0, min(100, s_liq + s_tr + s_div + s_risk + s_ct))
    r["detail"] = (s_liq, s_tr, s_div, s_risk, s_ct)
    # raisons et signaux
    if s_liq >= 14:
        r["raisons"].append("liquidite correcte (%s M FCFA echanges par jour, valeur mediane)" % fmt(r["med"] / 1e6))
    if r["d200"] == r["d200"] and r["d200"] > 0:
        r["raisons"].append("cours au-dessus de sa moyenne de 200 jours (%s)" % pct(r["d200"]))
    if r["serie"] >= 3:
        r["raisons"].append("dividende verse %d exercices de suite" % r["serie"])
    if r["rend_moy"] == r["rend_moy"] and 0.03 <= r["rend_moy"] <= 0.15 and not suspect:
        r["raisons"].append("rendement moyen du dividende de %s sur le cours actuel" % pct(r["rend_moy"], 1, False))
    if r["croiss"] == r["croiss"] and r["croiss"] > 0.05:
        r["raisons"].append("dividende en hausse de %s" % pct(r["croiss"], 0))
    if r["vol"] == r["vol"] and r["vol"] < 0.25:
        r["raisons"].append("volatilite moderee (%s)" % pct(r["vol"], 0, False))
    if pos:
        r["raisons"].append("annonce recente favorable : " + pos[0]["titre"][:70])
    if r["p1m"] == r["p1m"] and r["p1m"] <= -0.10:
        r["flags"].append("repli de %s en 1 mois" % pct(r["p1m"], 0))
    if r["retard"] > RETARD_MAX:
        r["flags"].append("inactive depuis %d jours" % r["retard"])
    if r["med"] < 3e6:
        r["flags"].append("liquidite tres faible")
    elif r["med"] < 10e6:
        r["flags"].append("liquidite limitee")
    if suspect:
        r["flags"].append("dividende suspect ou exceptionnel")
    if coupe:
        r["flags"].append("dividende reduit de plus de 30 %")
    if r["p6m"] == r["p6m"] and r["p6m"] > 0.60:
        r["flags"].append("surchauffe possible (%s en 6 mois)" % pct(r["p6m"], 0))
    if r["d200"] == r["d200"] and r["d200"] < 0:
        r["flags"].append("sous sa moyenne de 200 jours")
    if r["vol"] == r["vol"] and r["vol"] > 0.40:
        r["flags"].append("volatilite elevee (%s)" % pct(r["vol"], 0, False))
    if r["dd"] < -0.30:
        r["flags"].append("a %s de son plus haut sur 1 an" % pct(r["dd"], 0))
    if "der" not in r:
        r["flags"].append("pas de donnees de dividendes")
    elif r["der"] < 2025:
        r["flags"].append("dividende de l'exercice 2025 absent")
    if neg:
        r["flags"].append("annonce recente defavorable : " + neg[0]["titre"][:70])
    grave = any(f.startswith(("inactive", "liquidite tres faible")) for f in r["flags"])
    vigilance = any(f.startswith(("surchauffe", "dividende suspect", "dividende reduit", "repli de", "annonce recente defavorable", "volatilite elevee", "a -")) for f in r["flags"])
    vigilance = vigilance or (r["dd"] <= -0.25)
    r["vigilance"] = vigilance
    r["suspect"], r["coupe"], r["grave"] = bool(suspect), bool(coupe), bool(grave)
    if r["retard"] > RETARD_MAX:
        r["etat"] = "Inactive"
    elif r["score"] >= SEUIL_ETUDIER and not grave and not suspect and not vigilance:
        r["etat"] = "A etudier"
    elif r["score"] >= SEUIL_SURVEILLER and not grave:
        r["etat"] = "A surveiller"
    elif r["score"] >= 40:
        r["etat"] = "Neutre"
    else:
        r["etat"] = "Prudence"
    return r


def index_equipondere(px, annees=3):
    fin = max(df.index[-1] for df in px.values())
    debut = fin - pd.DateOffset(years=annees)
    cols = {}
    for t, df in px.items():
        if len(df) >= HISTORIQUE_MIN and (fin - df.index[-1]).days <= RETARD_MAX:
            cols[t] = df["Close"].loc[debut:]
    allc = pd.concat(cols, axis=1).sort_index().ffill()
    ret = allc.pct_change().clip(-0.10, 0.10).mean(axis=1).fillna(0)
    ind = 100 * (1 + ret).cumprod()
    return ind


def preparer_news(actus, aujourdhui):
    par = {}
    toutes = []
    for a in actus.get("articles", []):
        a = dict(a)
        a["type"] = "Article"
        toutes.append(a)
    for c in actus.get("communiques", []):
        c = dict(c)
        c["type"] = "Communique"
        c["date"] = c["date"] + " 00:00"
        toutes.append(c)
    vus, uniques = set(), []
    for x in toutes:
        cle = (x.get("titre", "")[:60].lower(), x["date"][:10])
        if cle not in vus:
            vus.add(cle)
            uniques.append(x)
    toutes = uniques
    for x in toutes:
        try:
            x["jours"] = (aujourdhui - pd.Timestamp(x["date"][:10])).days
        except Exception:
            x["jours"] = 999
        for t in x.get("tickers", []):
            par.setdefault(t, []).append(x)
    for t in par:
        par[t].sort(key=lambda z: z["date"], reverse=True)
    return par, sorted(toutes, key=lambda z: z["date"], reverse=True)


def candidats_json(res, mapping):
    out = []
    for r in res:
        out.append({"t": r["t"], "secteur": r["secteur"], "pays": REGLES.PAYS.get(mapping.get(r["t"], ""), "?"), "score": r["score"], "etat": r["etat"],
                    "vigilance": bool(r.get("vigilance", False)), "suspect": bool(r.get("suspect", False)), "coupe": bool(r.get("coupe", False)), "grave": bool(r.get("grave", False)),
                    "rend_moy": None if r["rend_moy"] != r["rend_moy"] else float(r["rend_moy"]), "d200": None if r["d200"] != r["d200"] else float(r["d200"]),
                    "p6m": None if r["p6m"] != r["p6m"] else float(r["p6m"]), "med": float(r["med"]),
                    "p1a": None if r["p1a"] != r["p1a"] else float(r["p1a"]), "serie": int(r["serie"]),
                    "croiss3": None if r["croiss3"] != r["croiss3"] else float(r["croiss3"])})
    return out


def stats_profil(ret, par):
    if not ret:
        return None
    n = len(ret)
    moy = lambda cle: float(np.nanmean([par[c["t"]][cle] for c in ret]))
    secteurs, pays, groupes = {}, {}, {}
    for c in ret:
        secteurs[c["secteur"]] = secteurs.get(c["secteur"], 0) + 1
        pays[c["pays"]] = pays.get(c["pays"], 0) + 1
        g = REGLES.groupe_de(c["t"])
        if g:
            groupes[g] = groupes.get(g, 0) + 1
    top = lambda d: max(d.items(), key=lambda x: x[1]) if d else ("-", 0)
    cr = [par[c["t"]]["croiss3"] for c in ret if par[c["t"]]["croiss3"] == par[c["t"]]["croiss3"]]
    return {"croiss": float(np.median(cr)) if cr else float("nan"), "n": n, "rend": moy("rend_moy"), "vol": moy("vol"), "dd": moy("dd"), "p6m": moy("p6m"), "p1m": moy("p1m"),
            "sect": top(secteurs), "pays": top(pays), "groupe": top(groupes), "ordre_min": min(par[c["t"]]["med"] for c in ret) * 0.10 / 1e6}


def liste_diversifiee(res, mapping, n, completer, profil, part_div=0.5):
    P = REGLES.PROFILS.get(profil, REGLES.PROFILS["prudent"])
    n = n or P["n"]
    cands = candidats_json(res, mapping)
    retenues, ecartees = REGLES.selection(cands, n, completer, profil, part_div)
    par = {r["t"]: r for r in res}
    pg, ps, pp = REGLES.limites(profil, n)
    regle = ("<div class=\"note\"><b>Profil \"%s\" - liste diversifiee de %d lignes :</b> %s. Limites : au plus %d valeur(s) d'un meme groupe (BOA, Total, Orange), %d d'un meme secteur et %d d'un meme pays de cotation. "
             "Autre profil : <code>py brvm_tableau.py --profil composition</code> (prudent, equilibre, composition, rendement, dynamique ; pour le profil composition, <code>--part-dividende 0.7</code> donne 70 %% au dividende et 30 %% a la croissance) ; autre nombre de lignes : <code>--lignes 6</code>. "
             "Les limites sont modifiables dans <code>brvm_regles.py</code>.</div>") % (h(P["nom"]), n, h(P["texte"] + (" ; part du rendement du dividende dans le classement : %d %%, part de la croissance : %d %%" % (round(100 * part_div), round(100 * (1 - part_div))) if profil == "composition" else "")), pg, ps, pp)
    if not retenues:
        return regle + "<p>Aucune valeur ne remplit les criteres.</p>", cands, retenues
    lignes = "".join("<tr><td>%d</td><td class='l'><b>%s</b> <span class='muted'>%s</span></td><td class='l'>%s</td><td class='l'>%s</td><td>%d</td><td>%s</td><td class='l'>%s</td></tr>" % (
        i + 1, h(c["t"]), h(par[c["t"]]["nom"]), h(c["secteur"]), h(c["pays"]), c["score"], pct(par[c["t"]]["rend_moy"], 1, False), h(c["etat"])) for i, c in enumerate(retenues))
    ec = "".join("<tr><td class='l'><b>%s</b> <span class='muted'>%s</span></td><td>%d</td><td class='l'>%s</td></tr>" % (h(t), h(par[t]["nom"]), par[t]["score"], h(why)) for t, why in ecartees if t in par)
    manque = ""
    if len(retenues) < n:
        manque = "<p class='muted'>Seulement %d valeur(s) respectent a la fois les criteres et les limites de diversification (sur %d demandees).</p>" % (len(retenues), n)
    # comparaison des profils
    lcomp = []
    for cle, Pc in REGLES.PROFILS.items():
        rr, _ = REGLES.selection(cands, None, False, cle, part_div)
        st = stats_profil(rr, par)
        if not st:
            continue
        lcomp.append("<tr%s><td class='l'><b>%s</b></td><td>%d</td><td class='l'>%s</td><td>%s</td><td>%s</td><td>%s</td><td>%s</td><td class='l'>%s (%d)</td><td class='l'>%s (%d)</td><td>%s M</td></tr>" % (
            " style='background:#eef6ff'" if cle == profil else "", h(Pc["nom"]), st["n"], h(", ".join(c["t"] for c in rr)), pct(st["rend"], 1, False), pct(st["vol"], 0, False), pct(st["dd"], 0),
            pct(st["p6m"], 0), h(st["sect"][0]), st["sect"][1], h(st["pays"][0]), st["pays"][1], fmt(st["ordre_min"], 1)))
    comp = ("<h2>Comparer les profils (memes donnees, nombre de lignes par defaut de chaque profil)</h2><div style='overflow-x:auto'><table><thead><tr><th class='l'>Profil</th><th>Lignes</th><th class='l'>Valeurs</th>"
            "<th>Rend. dividendes</th><th>Croissance dividende (mediane/an)</th><th>Volatilite moy.</th><th>Baisse 1 an moy.</th><th>Hausse 6 mois (passe)</th><th class='l'>Secteur dominant</th><th class='l'>Pays dominant</th><th>Ordre max mini</th></tr></thead><tbody>%s</tbody></table></div>"
            "<p class='muted'>Rend. dividendes = moyenne des 3 derniers dividendes / cours actuel, avant impots et frais. Volatilite et baisse sont des moyennes par valeur, pas celles du portefeuille. La hausse des 6 derniers mois est une information sur le passe, pas une prevision.</p>") % "".join(lcomp)
    html_ = (regle + "<h2>Liste diversifiee (%d valeurs retenues)</h2><table style='max-width:860px'><thead><tr><th>Rang</th><th class='l'>Valeur</th><th class='l'>Secteur</th><th class='l'>Pays</th><th>Score</th><th>Rend. 3 ans</th><th class='l'>Etat</th></tr></thead><tbody>%s</tbody></table>%s" % (len(retenues), lignes, manque)
             + composition([par[c["t"]] for c in retenues], mapping).replace("Composition de cette liste", "Composition de la liste diversifiee")
             + comp + '<div class="grid">' + "".join(carte(par[c["t"]]) for c in retenues) + "</div>"
             + ("<h2>Valeurs ecartees par les limites ou le profil</h2><table style='max-width:760px'><thead><tr><th class='l'>Valeur</th><th>Score</th><th class='l'>Raison</th></tr></thead><tbody>%s</tbody></table>" % ec if ec else ""))
    return html_, cands, retenues


def composition(lst, mapping):
    n = len(lst)
    if n == 0:
        return ""
    sec, grp, pays = {}, {}, {}
    for r in lst:
        sec[r["secteur"]] = sec.get(r["secteur"], 0) + 1
        for g, ens in GROUPES.items():
            if r["t"] in ens:
                grp[g] = grp.get(g, 0) + 1
        p = PAYS.get(mapping.get(r["t"], ""), "?")
        pays[p] = pays.get(p, 0) + 1
    tri = lambda d: ", ".join("%s %d" % (k, v) for k, v in sorted(d.items(), key=lambda x: -x[1]))
    alertes = []
    for k, v in sec.items():
        if v / n > 0.5:
            alertes.append("%s = %d %% de la liste" % (k, round(100 * v / n)))
    for k, v in grp.items():
        if v >= 3:
            alertes.append("%d valeurs du groupe %s" % (v, k))
    for k, v in pays.items():
        if v / n > 0.6:
            alertes.append("%s = %d %% de la liste" % (k, round(100 * v / n)))
    return ('<div class="note"><b>Composition de cette liste (%d valeurs) :</b> secteurs : %s. Groupes : %s. Pays : %s.%s</div>' % (
        n, h(tri(sec)), h(tri(grp) or "aucun"), h(tri(pays)),
        (" <b>Concentration a surveiller :</b> " + h("; ".join(alertes)) + ". Un portefeuille ne devrait pas empiler ces valeurs : plusieurs titres d'un meme groupe ou d'un meme secteur bougent souvent ensemble.") if alertes else ""))


def carte(r, vigilance=False):
    f = "".join('<li class="warn">%s</li>' % h(x) for x in r["flags"][:5])
    ra = "".join('<li class="ok">%s</li>' % h(x) for x in r["raisons"][:5])
    nw = "".join('<li class="news">%s <span class="muted">(%s)</span></li>' % (h(x["titre"][:90]), h(x["date"][:10])) for x in r["news"][:2])
    liq = r["med"] * 0.10
    return ('<div class="card"><div class="ch"><b>%s</b> <span class="muted">%s &middot; %s</span><span class="badge b-%s">%d/100</span></div>'
            '<div class="kv"><span>Cours <b>%s</b></span><span>Rend. moyen <b>%s</b></span><span>6 mois <b class="%s">%s</b></span><span>Vol. <b>%s</b></span><span>Ordre max conseille <b>%s M</b></span></div>'
            '<ul>%s%s%s</ul></div>') % (h(r["t"]), h(r["nom"]), h(r["secteur"]), ("w" if vigilance and r["etat"] in ("A etudier", "A surveiller") else {"A etudier": "g", "A surveiller": "b", "Neutre": "n", "Prudence": "r", "Inactive": "r"}[r["etat"]]), r["score"],
                                          fmt(r["prix"]), pct(r["rend_moy"], 1, False), cls(r["p6m"]), pct(r["p6m"], 0), pct(r["vol"], 0, False), fmt(liq / 1e6, 1), ra, f, nw)


CSS = """
body{font-family:Segoe UI,Arial,sans-serif;margin:0;background:#f6f7f9;color:#1d2330}
header{background:#14213d;color:#fff;padding:14px 22px}header h1{margin:0;font-size:20px}header .sub{font-size:12px;opacity:.8;margin-top:3px}
.tabs{display:flex;gap:4px;background:#e9ecf2;padding:6px 14px;flex-wrap:wrap}.tab{padding:8px 14px;border-radius:6px;cursor:pointer;font-size:14px}.tab.on{background:#fff;font-weight:600;box-shadow:0 1px 3px #0002}
.page{display:none;padding:16px 22px}.page.on{display:block}
.cards{display:flex;flex-wrap:wrap;gap:10px;margin-bottom:14px}.kpi{background:#fff;border-radius:8px;padding:10px 14px;min-width:150px;box-shadow:0 1px 3px #0001}.kpi b{display:block;font-size:20px}.kpi span{font-size:12px;color:#667}
table{border-collapse:collapse;background:#fff;font-size:12.5px;width:100%}th,td{padding:5px 7px;border-bottom:1px solid #eceef2;text-align:right;white-space:nowrap}th{background:#eef1f6;cursor:pointer;position:sticky;top:0}td:first-child,th:first-child,td.l,th.l{text-align:left}
.pos{color:#1b7f3b}.neg{color:#c0392b}.muted{color:#778;font-size:12px}h2{font-size:16px;margin:18px 0 8px}
.grid{display:flex;flex-wrap:wrap;gap:12px}.card{background:#fff;border-radius:8px;padding:10px 14px;width:430px;box-shadow:0 1px 3px #0001}.ch{display:flex;align-items:baseline;gap:8px}.ch .badge{margin-left:auto}
.badge{padding:2px 8px;border-radius:10px;font-size:12px;font-weight:600;color:#fff}.b-g{background:#1b7f3b}.b-b{background:#2a6fdb}.b-n{background:#8a93a3}.b-r{background:#c0392b}.b-w{background:#d9822b}td[colspan]{white-space:normal;text-align:left}
.kv{display:flex;flex-wrap:wrap;gap:4px 14px;font-size:12px;color:#556;margin:6px 0}ul{margin:6px 0 0 0;padding-left:18px;font-size:12.5px}li.ok::marker{content:"✓ ";color:#1b7f3b}li.warn::marker{content:"⚠ ";color:#d9822b}li.news::marker{content:"📰 "}
.note{background:#fff8e1;border-left:4px solid #d9822b;padding:8px 12px;font-size:12.5px;margin:10px 0}.two{display:flex;gap:18px;flex-wrap:wrap}.two>div{flex:1;min-width:360px}
input.f{padding:6px 10px;border:1px solid #ccd;border-radius:6px;margin-bottom:8px;width:260px}.s-1{color:#1b7f3b}.s--1{color:#c0392b}
"""
JS = """
function tab(n){document.querySelectorAll('.page').forEach(function(e){e.classList.remove('on')});document.querySelectorAll('.tab').forEach(function(e){e.classList.remove('on')});document.getElementById('p'+n).classList.add('on');document.getElementById('t'+n).classList.add('on');}
function tri(th){var t=th.closest('table'),i=Array.prototype.indexOf.call(th.parentNode.children,th),b=t.tBodies[0],rows=Array.prototype.slice.call(b.rows),asc=th.dataset.asc!=='1';th.dataset.asc=asc?'1':'0';
rows.sort(function(a,c){var x=a.cells[i].dataset.v,y=c.cells[i].dataset.v;var nx=parseFloat(x),ny=parseFloat(y);if(!isNaN(nx)&&!isNaN(ny))return asc?nx-ny:ny-nx;return asc?String(x).localeCompare(y):String(y).localeCompare(x);});rows.forEach(function(r){b.appendChild(r)});}
function filtre(inp){var q=inp.value.toLowerCase();document.querySelectorAll('#tab_actions tbody tr').forEach(function(r){r.style.display=r.innerText.toLowerCase().indexOf(q)>=0?'':'none'});}
"""


def td(val, aff, c=""):
    v = "" if val is None or (isinstance(val, float) and np.isnan(val)) else val
    return '<td class="%s" data-v="%s">%s</td>' % (c, h(v), aff)


def main():
    ouvrir = "--sans-ouverture" not in sys.argv
    completer = "--completer" in sys.argv
    n_lignes = None
    profil = "prudent"
    if "--profil" in sys.argv:
        try:
            profil = sys.argv[sys.argv.index("--profil") + 1].lower().replace("é", "e")
        except Exception:
            pass
    part_div = 0.5
    if "--part-dividende" in sys.argv:
        try:
            part_div = min(1.0, max(0.0, float(sys.argv[sys.argv.index("--part-dividende") + 1].replace(",", "."))))
        except Exception:
            pass
    if profil not in REGLES.PROFILS:
        print("Profil inconnu : %s (choix : %s)" % (profil, ", ".join(REGLES.PROFILS)))
        return
    if "--lignes" in sys.argv:
        try:
            n_lignes = max(1, int(sys.argv[sys.argv.index("--lignes") + 1]))
        except Exception:
            pass
    mapping, px, divs, actus = charger()
    if not px:
        print("Aucune donnee : lance d'abord brvm_data.py")
        return
    aujourdhui = pd.Timestamp.now().normalize()
    news, toutes = preparer_news(actus, aujourdhui)
    res = [analyser(t, df, divs, news) for t, df in px.items() if len(df) >= 60]
    res.sort(key=lambda r: -r["score"])
    actifs = [r for r in res if r["retard"] <= RETARD_MAX]
    fin = max(r["fin"] for r in res)

    # ---- Marche
    ind = index_equipondere(px, 3)
    sma = ind.rolling(200).mean()
    hausse = sum(1 for r in actifs if r["p1j"] == r["p1j"] and r["p1j"] > 0)
    baisse = sum(1 for r in actifs if r["p1j"] == r["p1j"] and r["p1j"] < 0)
    s200 = sum(1 for r in actifs if r["d200"] == r["d200"] and r["d200"] > 0)
    s50 = sum(1 for r in actifs if r["sma50"] == r["sma50"] and r["prix"] > r["sma50"])
    vals = pd.concat({t: (df["Close"] * df["Volume"]).loc[df.index >= fin - pd.Timedelta(days=45)] for t, df in px.items()}, axis=1).sort_index().sum(axis=1)
    val_jour = float(vals.iloc[-1]) if len(vals) else float("nan")
    val_20 = float(vals.tail(20).mean()) if len(vals) else float("nan")
    ind_1m, ind_1a = perf(ind, 21), perf(ind, 252)
    kpis = [("Valeurs actives", "%d / %d" % (len(actifs), len(res)), ""), ("Hausses / baisses (derniere seance)", "%d / %d" % (hausse, baisse), ""),
            ("Au-dessus de la moyenne 200 j", "%d%%" % round(100 * s200 / max(len(actifs), 1)), ""), ("Au-dessus de la moyenne 50 j", "%d%%" % round(100 * s50 / max(len(actifs), 1)), ""),
            ("Valeur echangee (derniere seance)", fmt(val_jour / 1e6) + " M FCFA", ""), ("Moyenne 20 seances", fmt(val_20 / 1e6) + " M FCFA", ""),
            ("Indice equipondere 1 mois", pct(ind_1m), cls(ind_1m)), ("Indice equipondere 1 an", pct(ind_1a), cls(ind_1a))]
    sect_tmp = {}
    for r in actifs:
        sect_tmp.setdefault(r["secteur"], []).append(r)
    ecart = int(np.busday_count(fin.date(), aujourdhui.date()))
    bandeau = ""
    if ecart >= 2:
        bandeau = '<div class="note" style="border-color:#c0392b;background:#fdecea"><b>Cours a mettre a jour :</b> les derniers cours datent du %s. Lance <code>py brvm_data.py</code> (mise a jour rapide), puis <code>py brvm_actus.py</code> et <code>py brvm_tableau.py</code>.</div>' % fin.strftime("%d/%m/%Y")
    p200 = 100 * s200 / max(len(actifs), 1)
    p50 = 100 * s50 / max(len(actifs), 1)
    reculs = sum(1 for r in actifs if r["p1m"] == r["p1m"] and r["p1m"] < -0.05)
    if p200 >= 60 and p50 >= 60:
        phase = "Tendance haussiere large : la majorite des valeurs est au-dessus de ses moyennes de 50 et 200 jours."
    elif p200 >= 50 and p50 < 35:
        phase = "Repli de court terme dans une tendance de fond encore positive : la plupart des valeurs sont repassees sous leur moyenne de 50 jours, alors que plus de la moitie reste au-dessus de celle de 200 jours."
    elif p200 < 40:
        phase = "Marche fragile : moins de 40 % des valeurs sont au-dessus de leur moyenne de 200 jours."
    else:
        phase = "Marche mitige : ni tendance haussiere large, ni repli generalise."
    sects = sorted(((np.nanmean([r["p1m"] for r in l]), k) for k, l in sect_tmp.items()))
    lecture = '<div class="note"><b>Lecture du marche (automatique) :</b> %s Indice equipondere : %s sur 1 mois et %s sur 1 an. %d valeurs sur %d ont recule de plus de 5 %% en 1 mois. Secteur le plus faible sur 1 mois : %s (%s) ; le plus resistant : %s (%s). Cette lecture decrit le passe recent : elle ne permet pas de prevoir la suite.</div>' % (
        phase, pct(ind_1m), pct(ind_1a), reculs, len(actifs), sects[0][1], pct(sects[0][0]), sects[-1][1], pct(sects[-1][0]))
    page1 = [bandeau + lecture, '<div class="cards">' + "".join('<div class="kpi"><span>%s</span><b class="%s">%s</b></div>' % (h(a), c, h(b)) for a, b, c in kpis) + "</div>",
             "<h2>Indice equipondere des valeurs actives (cours seuls, 3 ans, base 100) et sa moyenne sur 200 jours</h2>", courbe(ind, sma=sma)]

    def top(cle, n=6, rev=True):
        l = [r for r in actifs if r[cle] == r[cle]]
        l.sort(key=lambda r: r[cle], reverse=rev)
        return "<table><thead><tr><th>Valeur</th><th>Variation</th><th>Cours</th></tr></thead><tbody>" + "".join(
            '<tr><td>%s <span class="muted">%s</span></td><td class="%s">%s</td><td>%s</td></tr>' % (h(r["t"]), h(r["nom"]), cls(r[cle]), pct(r[cle]), fmt(r["prix"])) for r in l[:n]) + "</tbody></table>"
    page1.append('<div class="two"><div><h2>Plus fortes hausses sur 1 semaine</h2>%s<h2>Plus fortes baisses sur 1 semaine</h2>%s</div><div><h2>Plus fortes hausses sur 1 mois</h2>%s<h2>Plus fortes baisses sur 1 mois</h2>%s</div></div>' % (top("p1s"), top("p1s", rev=False), top("p1m"), top("p1m", rev=False)))
    sect = {}
    for r in actifs:
        sect.setdefault(r["secteur"], []).append(r)
    lignes = []
    for s, l in sorted(sect.items(), key=lambda x: -np.nanmean([r["ytd"] for r in x[1]])):
        lignes.append('<tr><td>%s</td><td>%d</td><td class="%s">%s</td><td class="%s">%s</td><td class="%s">%s</td></tr>' % (
            h(s), len(l), cls(np.nanmean([r["p1m"] for r in l])), pct(np.nanmean([r["p1m"] for r in l])), cls(np.nanmean([r["ytd"] for r in l])), pct(np.nanmean([r["ytd"] for r in l])),
            cls(np.nanmean([r["p1a"] for r in l])), pct(np.nanmean([r["p1a"] for r in l]))))
    page1.append('<h2>Secteurs (moyenne simple des valeurs, classement indicatif)</h2><table style="max-width:620px"><thead><tr><th>Secteur</th><th>Valeurs</th><th>1 mois</th><th>Depuis janvier</th><th>1 an</th></tr></thead><tbody>%s</tbody></table>' % "".join(lignes))

    # ---- Actions
    en = ["Valeur", "Nom", "Secteur", "Cours", "1 j", "1 sem.", "1 mois", "3 mois", "6 mois", "Janv.", "1 an", "Vol.", "Baisse/1an max", "vs MM50", "vs MM200", "Liquid. M/j", "Rend. dern.", "Rend. 3a", "Score", "Etat", "120 j"]
    corps = []
    for r in res:
        corps.append("<tr>" + td(r["t"], "<b>%s</b>" % h(r["t"]), "l") + td(r["nom"], h(r["nom"]), "l") + td(r["secteur"], h(r["secteur"]), "l") + td(r["prix"], fmt(r["prix"]))
                     + "".join(td(r[k], pct(r[k], 1), cls(r[k])) for k in ("p1j", "p1s", "p1m", "p3m", "p6m", "ytd", "p1a"))
                     + td(r["vol"], pct(r["vol"], 0, False)) + td(r["dd"], pct(r["dd"], 0), cls(r["dd"])) + td(r["d50"], pct(r["d50"], 0), cls(r["d50"])) + td(r["d200"], pct(r["d200"], 0), cls(r["d200"]))
                     + td(r["med"], fmt(r["med"] / 1e6, 1)) + td(r["rend_der"], pct(r["rend_der"], 1, False)) + td(r["rend_moy"], pct(r["rend_moy"], 1, False))
                     + td(r["score"], "<b>%d</b>" % r["score"]) + td(r["etat"], h(r["etat"]), "l") + td("", spark(r["spark"], color="#1b7f3b" if r["p6m"] == r["p6m"] and r["p6m"] > 0 else "#c0392b")) + "</tr>")
    page2 = ['<input class="f" placeholder="Filtrer (nom, secteur, etat...)" oninput="filtre(this)"><div style="overflow-x:auto"><table id="tab_actions"><thead><tr>%s</tr></thead><tbody>%s</tbody></table></div>' % (
        "".join('<th onclick="tri(this)"%s>%s</th>' % (' class="l"' if i < 3 else "", h(x)) for i, x in enumerate(en)), "".join(corps)),
             '<p class="muted">Clique sur un titre de colonne pour trier. Cours en FCFA. Liquidite = valeur mediane echangee par jour sur 120 seances. Rend. 3a = moyenne des 3 derniers dividendes / cours actuel.</p>']

    # ---- A surveiller
    etudier = [r for r in res if r["etat"] in ("A etudier", "A surveiller")]
    etudier.sort(key=lambda r: (-r["score"], -r["med"]))
    prudence = [r for r in res if r["etat"] in ("Prudence", "Inactive") or any(f.startswith(("surchauffe", "dividende reduit", "dividende suspect", "annonce recente defavorable")) for f in r["flags"])]
    prudence.sort(key=lambda r: r["score"])
    div_html, cands_json, retenues = liste_diversifiee(res, mapping, n_lignes, completer, profil, part_div)
    n_lignes = n_lignes or REGLES.PROFILS[profil]["n"]
    page3 = ['<div class="note"><b>Comment lire cette page :</b> le score (sur 100) applique des regles fixes et visibles : liquidite (20), tendance (25), dividendes (35), risque (20), moins une penalite si le cours a recule de plus de 5 % en 1 mois. Une valeur n\'est classee <i>a etudier</i> que si elle a au moins 75/100 et aucun point de vigilance grave (surchauffe, repli recent, dividende douteux, forte baisse sur 1 an, annonce defavorable). Ce n\'est ni une prevision ni un conseil : c\'est une liste de valeurs a etudier avant toute decision. Les annonces recentes sont lues par mots-cles.</div>',
             div_html,
             "<h2>Toutes les valeurs a etudier ou a surveiller</h2>",
             composition([r for r in etudier if r["etat"] == "A etudier"], mapping).replace("Composition de cette liste", "Composition de la liste 'a etudier' (sans limites)"),
             "<h2>A etudier / a surveiller (%d valeurs)</h2>" % len(etudier), '<div class="grid">' + "".join(carte(r) for r in etudier[:12]) + "</div>",
             "<h2>Prudence ou points de vigilance (%d valeurs)</h2>" % len(prudence), '<div class="grid">' + "".join(carte(r, True) for r in prudence[:12]) + "</div>"]

    # ---- Dividendes
    prochains = actus.get("dividendes_a_venir", [])
    pl = "".join("<tr><td>%s</td><td class='l'>%s</td><td>%s</td><td>%s</td></tr>" % (h(x["date"]), h(NOMS.get(x["ticker"], (x["nom"],))[0] if x["ticker"] in NOMS else x["nom"]) + " <span class='muted'>%s</span>" % h(x["ticker"]), fmt(x["montant"], 0) if x["montant"] else "-", pct(x["rendement"] / 100 if x["rendement"] else None, 2, False)) for x in prochains) or "<tr><td colspan=4>Aucun dividende a venir (ou calendrier non charge : lance brvm_actus.py)</td></tr>"
    annees = sorted({int(a) for d in divs.values() for a in d.index})[-5:]
    dl = []
    for r in sorted(res, key=lambda r: -(r["rend_moy"] if r["rend_moy"] == r["rend_moy"] else -1)):
        d = r["div"]
        if d is None:
            continue
        dl.append("<tr><td><b>%s</b> <span class='muted'>%s</span></td>%s<td>%s</td><td>%s</td><td>%d</td><td class='%s'>%s</td><td class='l'>%s</td></tr>" % (
            h(r["t"]), h(r["nom"]), "".join("<td>%s</td>" % (fmt(d.get(a), 0) if a in d.index else "-") for a in annees), pct(r["rend_der"], 1, False), pct(r["rend_moy"], 1, False), r["serie"],
            cls(r["croiss"]), pct(r["croiss"], 0), h("; ".join(f for f in r["flags"] if "dividende" in f))))
    page4 = ["<h2>Dividendes a venir (dates de detachement)</h2><table style='max-width:640px'><thead><tr><th>Date</th><th class='l'>Valeur</th><th>Montant (FCFA)</th><th>Rendement</th></tr></thead><tbody>%s</tbody></table>" % pl,
             "<h2>Historique par exercice (FCFA par action, ajuste des fractionnements)</h2><div style='overflow-x:auto'><table><thead><tr><th class='l'>Valeur</th>%s<th>Rend. dernier</th><th>Rend. 3 ans</th><th>Serie</th><th>Evol.</th><th class='l'>Alertes</th></tr></thead><tbody>%s</tbody></table></div>" % ("".join("<th>%d</th>" % a for a in annees), "".join(dl)),
             '<p class="muted">Un rendement tres eleve peut signaler un dividende exceptionnel ou un cours qui a beaucoup baisse. Le dividende de l\'exercice N est verse en N+1.</p>']

    # ---- Actualites et macro
    def ligne_actu(x):
        s = {1: "+", 0: "=", -1: "&minus;"}[x.get("sentiment", 0)]
        tk = ", ".join(x.get("tickers", []))
        return "<tr><td>%s</td><td class='l'>%s</td><td class='l'>%s</td><td class='l'><a href='%s' target='_blank'>%s</a>%s</td><td class='s-%d'>%s</td></tr>" % (
            h(x["date"][:10]), h(x["categorie"]), h(tk), h(x["url"]), h(x["titre"][:130]), " <span class='muted'>(abonnes)</span>" if x.get("premium") else "", x.get("sentiment", 0), s)
    recents = [x for x in toutes if x["jours"] <= 21]
    importants = [x for x in recents if x.get("score", 0) >= 2]
    autres = [x for x in recents if x.get("score", 0) < 2][:25]
    th_actu = "<thead><tr><th>Date</th><th class='l'>Type</th><th class='l'>Valeurs</th><th class='l'>Titre</th><th>Ton</th></tr></thead>"
    mat = actus.get("matieres", [])
    ml = []
    for m in mat:
        cible = next((c for c in IMPACT if c[0] in (m["nom"] + " ").upper()), None)
        ml.append("<tr><td class='l'>%s</td><td>%s</td><td class='%s'>%s</td><td class='l'>%s</td><td class='l'>%s</td></tr>" % (
            h(m["nom"]), fmt(m["dernier"], 2), cls(m["variation"]), ("%+.2f %%" % m["variation"]).replace(".", ",") if m["variation"] is not None else "-", h(cible[1]) if cible else "", h(", ".join(cible[2])) if cible else ""))
    ev = []
    if os.path.exists(EVENTS):
        try:
            e = pd.read_csv(EVENTS, sep=None, engine="python", encoding="utf-8-sig")
            for _, x in e.iterrows():
                dd = pd.to_datetime(x["date"], dayfirst=True, errors="coerce")
                if pd.notna(dd) and dd >= aujourdhui - pd.Timedelta(days=1):
                    ev.append((dd, x))
        except Exception as ex:
            ev.append((aujourdhui, {"date": "", "titre": "evenements.csv illisible : %s" % ex, "valeurs": "", "impact": ""}))
    evl = "".join("<tr><td>%s</td><td class='l'>%s</td><td class='l'>%s</td><td class='l'>%s</td></tr>" % (h(dd.strftime("%d/%m/%Y")), h(x["titre"]), h(x.get("valeurs", "")), h(x.get("impact", ""))) for dd, x in sorted(ev, key=lambda z: z[0])) or "<tr><td colspan=4>Aucun evenement saisi. Cree le fichier evenements.csv (colonnes : date;titre;valeurs;impact) pour y noter les rendez-vous qui comptent (Comite de politique monetaire de la BCEAO, assemblees generales, publications de resultats...).</td></tr>"
    page5 = ['<div class="note">Les annonces viennent de Sikafinance (actualites, communiques officiels des societes, matieres premieres). Le tri par importance et le ton (+ / - / &middot;) sont deduits de <b>mots-cles</b> : ils aident a reperer, ils ne remplacent pas la lecture du document. Derniere mise a jour : %s.</div>' % h(actus.get("maj", "jamais - lance brvm_actus.py")),
             "<h2>Annonces importantes (21 derniers jours)</h2><table>%s<tbody>%s</tbody></table>" % (th_actu, "".join(ligne_actu(x) for x in importants) or "<tr><td colspan=5>Aucune</td></tr>"),
             "<h2>Matieres premieres et impact sur les valeurs</h2><table><thead><tr><th class='l'>Produit</th><th>Dernier</th><th>Variation</th><th class='l'>Pourquoi ca compte</th><th class='l'>Valeurs</th></tr></thead><tbody>%s</tbody></table>" % ("".join(ml) or "<tr><td colspan=5>Non charge</td></tr>"),
             "<h2>Agenda (saisi par toi)</h2><table><thead><tr><th>Date</th><th class='l'>Evenement</th><th class='l'>Valeurs</th><th class='l'>Impact attendu</th></tr></thead><tbody>%s</tbody></table>" % evl,
             "<h2>Autres informations recentes</h2><table>%s<tbody>%s</tbody></table>" % (th_actu, "".join(ligne_actu(x) for x in autres) or "<tr><td colspan=5>Aucune</td></tr>")]

    noms_tabs = ["Marche", "Actions", "A surveiller", "Dividendes", "Annonces et macro"]
    pages = [page1, page2, page3, page4, page5]
    corps_html = "".join('<div class="page%s" id="p%d">%s</div>' % (" on" if i == 0 else "", i, "".join(p)) for i, p in enumerate(pages))
    tabs_html = "".join('<div class="tab%s" id="t%d" onclick="tab(%d)">%s</div>' % (" on" if i == 0 else "", i, i, h(n)) for i, n in enumerate(noms_tabs))
    doc = ('<!DOCTYPE html><html lang="fr"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Tableau de bord BRVM</title><style>%s</style></head><body>'
           '<header><h1>Tableau de bord BRVM</h1><div class="sub">Donnees jusqu\'au %s &middot; genere le %s &middot; outil d\'aide a la decision, ce n\'est pas un conseil financier</div></header>'
           '<div class="tabs">%s</div>%s<script>%s</script></body></html>') % (CSS, fin.strftime("%d/%m/%Y"), time.strftime("%d/%m/%Y %H:%M"), tabs_html, corps_html, JS)
    with open(SORTIE, "w", encoding="utf-8") as f:
        f.write(doc)
    try:
        json.dump({"maj": time.strftime("%Y-%m-%d %H:%M"), "profil": profil, "part_div": part_div, "candidats": cands_json}, open(CANDIDATS, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    except Exception:
        pass
    print("Tableau de bord enregistre : %s" % os.path.abspath(SORTIE))
    print("A etudier / a surveiller : " + ", ".join("%s (%d)" % (r["t"], r["score"]) for r in etudier[:10]))
    print("Liste diversifiee, profil %s (%d lignes) : %s" % (profil, n_lignes, ", ".join(c["t"] for c in retenues)))
    print("Prudence : " + ", ".join("%s (%d)" % (r["t"], r["score"]) for r in prudence[:10]))
    if ouvrir:
        webbrowser.open("file:///" + os.path.abspath(SORTIE).replace("\\", "/"))


if __name__ == "__main__":
    main()
