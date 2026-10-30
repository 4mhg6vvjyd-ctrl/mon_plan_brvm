import io
import json
import os
import re
import time
import pandas as pd
import requests

H = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"}
DONNEES = "brvm_donnees"
SORTIE = "brvm_dividendes"
os.makedirs(SORTIE, exist_ok=True)
LOG = open("brvm_dividendes_resultats.txt", "w", encoding="utf-8")


def out(*a):
    t = " ".join(str(x) for x in a)
    print(t)
    LOG.write(t + "\n")
    LOG.flush()


def nombre(x):
    s = str(x).replace("\u202f", "").replace("\xa0", "").replace(" ", "").replace("%", "").replace(",", ".")
    try:
        return float(s)
    except Exception:
        return float("nan")


def dividendes(ticker, suffixe):
    url = "https://www.sikafinance.com/marches/cotation_%s.%s" % (ticker, suffixe)
    r = requests.get(url, headers=H, timeout=30)
    html = r.text.replace("\xa0", " ").replace("\u202f", " ")
    tables = pd.read_html(io.StringIO(html), decimal=",", thousands=" ")
    for t in tables:
        cols = [str(c).strip().lower() for c in t.columns]
        if len(cols) >= 3 and cols[0].startswith("ann") and cols[1].startswith("montant") and cols[2].startswith("rend"):
            d = pd.DataFrame({"Annee": t.iloc[:, 0].map(nombre), "Montant": t.iloc[:, 1].map(nombre), "Rendement": t.iloc[:, 2].map(nombre)})
            return d.dropna(subset=["Annee"]).astype({"Annee": int})
    return None


def main():
    fm = os.path.join(DONNEES, "mapping.json")
    if not os.path.exists(fm):
        out("mapping.json introuvable : lance d'abord brvm_data.py")
        return
    mapping = json.load(open(fm))
    ok = 0
    out("%-7s %s" % ("Valeur", "Dividendes par exercice (annee : montant FCFA, rendement %)"))
    for t, s in sorted(mapping.items()):
        try:
            d = dividendes(t, s.lower())
        except Exception as e:
            out("%-7s echec (%s)" % (t, str(e)[:80]))
            time.sleep(0.5)
            continue
        if d is None or len(d) == 0:
            out("%-7s aucun tableau de dividendes sur la page" % t)
        else:
            d.to_csv(os.path.join(SORTIE, "%s.csv" % t), index=False)
            ok += 1
            out("%-7s %s" % (t, " | ".join("%d : %.4g, %.2f %%" % (r.Annee, r.Montant, r.Rendement) for r in d.sort_values("Annee", ascending=False).head(5).itertuples())))
        time.sleep(0.4)
    out("\nValeurs avec dividendes : %d sur %d | copies dans le dossier %s" % (ok, len(mapping), SORTIE))
    out("Colle-moi tout le contenu de brvm_dividendes_resultats.txt")


if __name__ == "__main__":
    main()
