"""Met a jour l'application brvm_assistant.html avec les donnees du jour (cours, scores, dividendes).
Utilisation : py brvm_assistant.py   (a lancer apres brvm_data.py et brvm_actus.py)"""
import json
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
    news, _ = T.preparer_news(actus, aujourdhui)
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
                       "grave": bool(r.get("grave")), "vigilance": bool(r.get("vigilance"))})
    fin = max(r["fin"] for r in res)
    return stocks, fin


def main():
    if not os.path.exists(FICHIER):
        raise SystemExit("%s introuvable : place le fichier telecharge dans ce dossier." % FICHIER)
    html = open(FICHIER, encoding="utf-8").read()
    m = re.search(r"/\*DATA_DEBUT\*/const DATA = (.*?);/\*DATA_FIN\*/", html, re.S)
    if not m:
        raise SystemExit("Bloc de donnees introuvable dans %s" % FICHIER)
    ancien = json.loads(m.group(1))
    stocks, fin = construire()
    fees = ancien["fees"]
    if os.path.exists("frais_sgi.json"):
        fees = json.load(open("frais_sgi.json", encoding="utf-8"))
    data = {"maj": fin.strftime("%d/%m/%Y"), "stocks": stocks, "fees": fees}
    nouveau = html[:m.start()] + "/*DATA_DEBUT*/const DATA = " + json.dumps(data, ensure_ascii=False, separators=(",", ":")) + ";/*DATA_FIN*/" + html[m.end():]
    open(FICHIER, "w", encoding="utf-8").write(nouveau)
    n_etude = sum(1 for s in stocks if s["etat"] == "A etudier")
    print("%s mis a jour : %d valeurs, cours au %s, %d a etudier, %d SGI." % (FICHIER, len(stocks), data["maj"], n_etude, len(fees)))
    if "--sans-ouverture" not in sys.argv:
        webbrowser.open("file:///" + os.path.abspath(FICHIER).replace("\\", "/"))


if __name__ == "__main__":
    main()
