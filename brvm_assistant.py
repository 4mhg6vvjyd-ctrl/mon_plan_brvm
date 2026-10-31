"""Met a jour l'application brvm_assistant.html avec les donnees du jour (cours, scores, dividendes).
Utilisation : py brvm_assistant.py   (a lancer apres brvm_data.py et brvm_actus.py)"""
import json
import math
import os
import re
import sys
import time
import webbrowser
import numpy as np
import pandas as pd
import brvm_tableau as T
import brvm_regles as REGLES

FICHIER = "brvm_assistant.html"
ACC = {"Cote d'Ivoire": "Côte d’Ivoire", "Senegal": "Sénégal", "Benin": "Bénin", "Telecoms": "Télécoms", "Energie": "Énergie",
       "Conso. de base": "Consommation de base", "Transport / services": "Transport et services", "Nestle": "Nestlé", "Bernabe": "Bernabé"}


def acc(x):
    if not isinstance(x, str):
        return x
    for a, b in ACC.items():
        x = x.replace(a, b)
    return x


def nb(x):
    try:
        x = float(x)
    except Exception:
        return None
    return None if x != x else x


def construire():
    mapping, px, divs, actus = T.charger()
    if not px:
        raise SystemExit("Aucune donnee : lance d'abord brvm_data.py")
    aujourdhui = pd.Timestamp.now().normalize()
    news, toutes = T.preparer_news(actus, aujourdhui)
    res = [T.analyser(t, df, divs, news) for t, df in px.items() if len(df) >= 60]
    stocks = []
    for r in res:
        d = divs.get(r["t"])
        dv = {}
        if d is not None:
            for a, m in d.items():
                dv[str(int(a))] = nb(m)
        stocks.append({"t": r["t"], "nom": acc(r["nom"]), "secteur": acc(r["secteur"]), "pays": acc(REGLES.PAYS.get(mapping.get(r["t"], ""), "?")),
                       "prix": int(round(r["prix"])), "score": int(r["score"]), "etat": r["etat"], "p1m": nb(r["p1m"]), "p3m": nb(r["p3m"]), "p6m": nb(r["p6m"]), "p1a": nb(r["p1a"]),
                       "vol": nb(r["vol"]), "dd": nb(r["dd"]), "d50": nb(r["d50"]), "d200": nb(r["d200"]), "med": float(r["med"]), "rend_der": nb(r["rend_der"]), "rend_moy": nb(r["rend_moy"]),
                       "divs": dv, "serie": int(r["serie"]), "croiss3": nb(r["croiss3"]), "suspect": bool(r.get("suspect")), "coupe": bool(r.get("coupe")),
                       "grave": bool(r.get("grave")), "vigilance": bool(r.get("vigilance")),
                       "p1j": nb(r.get("p1j")), "ytd": nb(r.get("ytd")), "h": historique(px[r["t"]]), "news": actus_valeur(news.get(r["t"], []))})
    fin = max(r["fin"] for r in res)
    fond, nb_act = lire_json("fondamentaux.json"), lire_json("actions.json")
    ops = fond.get("_operations", {})
    for c in actus.get("communiques", []):  # fractionnements annonces, meme si leur PDF n'a pas encore ete lu
        t = c.get("ticker")
        if t and re.search(r"fractionnement|division du nominal|split", c.get("titre", ""), re.I) and not any(o.get("url") == c.get("url") for o in ops.get(t, [])):
            ops.setdefault(t, []).append({"date": c.get("date"), "url": c.get("url"), "facteur": None})
    for st in stocks:
        st["fond"] = fondamentaux(st, fond.get(st["t"]), nb_act.get(st["t"]), ops.get(st["t"], []))
    return stocks, fin, agenda(actus), actus_marche(toutes, {s["t"] for s in stocks})


def lire_json(nom):
    try:
        return json.load(open(nom, encoding="utf-8")) if os.path.exists(nom) else {}
    except Exception:
        return {}


DIVISIONS = [2, 4, 5, 10, 20, 25, 50, 100]


def fondamentaux(st, par_exercice, nb_officiel, fractionnements=()):
    """Derniers etats financiers annuels de la societe, prets pour la fiche (montants en FCFA).
    Les chiffres par action d'un rapport publie avant un fractionnement sont ramenes au nombre d'actions actuel."""
    if not par_exercice:
        return None
    an = max(par_exercice, key=int)
    e = par_exercice[an]
    n, n1 = e["valeurs"].get(an, {}), e["valeurs"].get(str(int(an) - 1), {})
    benef = "res_net_part_groupe" if "res_net_part_groupe" in n else "res_net"
    notes, a_verifier = list(e.get("notes", [])), bool(e.get("a_verifier"))
    nb_rap, dpa_rap = e.get("nombre_actions"), e.get("dividende_brut_par_action")
    der = [v for a, v in sorted(st["divs"].items()) if v]
    pub = e.get("date_publication") or "%d-12-31" % int(an)
    apres = sorted([o for o in fractionnements if (o.get("date") or "") > pub], key=lambda o: o["date"])
    date_fr = lambda d: "/".join(reversed(d.split("-"))) if d else "?"
    plus_proche = lambda r: min(DIVISIONS, key=lambda k: abs(math.log(r / k)))
    facteur = None
    lus = [o["facteur"] for o in apres if o.get("facteur")]
    if lus:
        facteur = math.prod(lus)
        notes.append("Fractionnement par %d annoncé le %s : les chiffres par action du rapport, publié avant, ont été ajustés." % (facteur, date_fr(apres[-1]["date"])))
    elif nb_officiel and nb_rap and nb_officiel / nb_rap >= 1.8:
        facteur = plus_proche(nb_officiel / nb_rap)
        notes.append("Le rapport compte environ %s actions contre %s aujourd’hui%s : chiffres par action divisés par %d." % (
            format(nb_rap, ",").replace(",", " "), format(nb_officiel, ",").replace(",", " "),
            (", après le fractionnement annoncé le " + date_fr(apres[-1]["date"])) if apres else "", facteur))
    elif dpa_rap and der and dpa_rap / der[-1] >= 4 and abs(math.log(dpa_rap / der[-1] / plus_proche(dpa_rap / der[-1]))) < math.log(1.6):
        facteur = plus_proche(dpa_rap / der[-1])
        if apres:
            notes.append("Fractionnement annoncé le %s ; parité non lue automatiquement, estimée à %d d’après les dividendes : à confirmer dans actions.json." % (date_fr(apres[-1]["date"]), facteur))
        else:
            notes.append("Le rapport semble antérieur à une division du nominal par %d : chiffres par action ajustés automatiquement, à confirmer." % facteur)
        a_verifier = True
    elif apres:
        notes.append("Fractionnement annoncé le %s après la publication de ces comptes : vérifiez les chiffres par action." % date_fr(apres[-1]["date"]))
        a_verifier = True
    notes = [x for x in notes if not x.startswith("Nombre d’actions déduit") or not nb_officiel]
    nb_actions = nb_officiel or (nb_rap * facteur if nb_rap and facteur else nb_rap)
    dpa = round(dpa_rap / facteur, 2) if dpa_rap and facteur else dpa_rap
    if dpa is None and e.get("dividende_total") and nb_actions:
        dpa = round(e["dividende_total"] / nb_actions, 2)
    if dpa and der and dpa / der[-1] < 0.4:
        notes.append(f"Le dividende proposé dans ces comptes ({str(round(dpa, 2)).replace('.', ',')} FCFA brut par action) est très inférieur au dernier versé ({str(round(der[-1], 2)).replace('.', ',')} FCFA) : vérifiez la décision finale de l’assemblée générale, qui a pu puiser dans les réserves.")
        a_verifier = True
    if not nb_actions:
        notes.append("Nombre d’actions inconnu : à renseigner dans actions.json.")
    garde = lambda d: {k: d[k] for k in d if k != "bpa"}
    return {"an": int(an), "norme": e["norme"], "n": garde(n), "n1": garde(n1), "benef": benef, "nb_actions": nb_actions,
            "dpa": dpa, "signaux": e.get("signaux", []), "a_verifier": a_verifier, "notes": notes,
            "controles_ko": [c["texte"] for c in e.get("controles", []) if not c["ok"]], "source": e.get("source"), "url": e.get("url")}


def historique(df):
    """Cours de cloture hebdomadaires sur 2 ans, pour la courbe de la fiche valeur."""
    c = df["Close"].resample("W-FRI").last().dropna().tail(105)
    if not len(c):
        return {"d0": None, "v": []}
    return {"d0": c.index[0].strftime("%Y-%m-%d"), "d1": c.index[-1].strftime("%Y-%m-%d"), "v": [int(round(x)) for x in c.values]}


def actus_valeur(lst, n=4, jours=120):
    """Titres et liens seulement (pas d'extraits) : les dernieres annonces d'une societe."""
    out = []
    for x in lst:
        if x.get("jours", 999) <= jours and x.get("url"):
            out.append({"d": x["date"][:10], "titre": x.get("titre", "")[:140], "url": x["url"], "type": x.get("type", "")})
        if len(out) >= n:
            break
    return out


def actus_marche(toutes, cotees, n=12):
    out = []
    for x in toutes:
        if x.get("url") and (set(x.get("tickers", [])) & cotees or "BRVM" in x.get("titre", "").upper()):
            out.append({"d": x["date"][:10], "titre": x.get("titre", "")[:140], "url": x["url"], "t": (x.get("tickers") or [""])[0]})
        if len(out) >= n:
            break
    return out


def agenda(actus):
    out = []
    for x in actus.get("dividendes_a_venir", []):
        out.append({"date": x.get("date", ""), "t": x.get("ticker", ""), "montant": nb(x.get("montant")), "rendement": nb(x.get("rendement"))})
    return out


def main():
    if not os.path.exists(FICHIER):
        raise SystemExit("%s introuvable : place le fichier telecharge dans ce dossier." % FICHIER)
    html = open(FICHIER, encoding="utf-8").read()
    m = re.search(r"/\*DATA_DEBUT\*/const DATA = (.*?);/\*DATA_FIN\*/", html, re.S)
    if not m:
        raise SystemExit("Bloc de donnees introuvable dans %s" % FICHIER)
    ancien = json.loads(m.group(1))
    stocks, fin, agd, act = construire()
    fees = ancien["fees"]
    if os.path.exists("frais_sgi.json"):
        fees = json.load(open("frais_sgi.json", encoding="utf-8"))
    data = {"maj": fin.strftime("%d/%m/%Y"), "stocks": stocks, "fees": fees, "agenda": agd, "actus": act}
    nouveau = html[:m.start()] + "/*DATA_DEBUT*/const DATA = " + json.dumps(data, ensure_ascii=False, separators=(",", ":")) + ";/*DATA_FIN*/" + html[m.end():]
    open(FICHIER, "w", encoding="utf-8").write(nouveau)
    n_etude = sum(1 for s in stocks if s["etat"] == "A etudier")
    print("%s mis a jour : %d valeurs, cours au %s, %d a etudier, %d SGI." % (FICHIER, len(stocks), data["maj"], n_etude, len(fees)))
    if "--sans-ouverture" not in sys.argv:
        webbrowser.open("file:///" + os.path.abspath(FICHIER).replace("\\", "/"))


if __name__ == "__main__":
    main()
