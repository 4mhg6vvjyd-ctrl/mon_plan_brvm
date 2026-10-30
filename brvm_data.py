import io
import json
import os
import re
import time
import numpy as np
import pandas as pd
import requests

H = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"}
DOSSIER = "brvm_donnees"
API = "https://www.sikafinance.com/api/general/GetHistos"
PAGES = ["https://www.brvm.org/fr/cours-actions/0", "https://afx.kwayisi.org/brvm/"]
SUFFIXES = ["ci", "sn", "bf", "tg", "bj", "ml", "ne"]
DEBUT = "2015-01-01"
PAS = 85            # jours par requete (l'API limite la plage a environ 3 mois)
SECOURS = ["SNTS", "ORAC", "SGBC", "ETIT", "CBIBF", "SIBC", "BICC", "BOAB", "BOABF", "BOAC", "BOAM", "BOAN", "BOAS",
           "CABC", "CFAC", "CIEC", "ECOC", "FTSC", "LNBB", "NEIC", "NSBC", "NTLC", "ONTBF", "ORGT", "PALC", "PRSC",
           "SAFC", "SCRC", "SDCC", "SDSC", "SEMC", "SHEC", "SICC", "SIVC", "SLBC", "SMBC", "SOGC", "SPHC", "STAC",
           "STBC", "SVOC", "TTLC", "TTLS", "UNLC", "UNXC", "ABJC", "BNBC"]
os.makedirs(DOSSIER, exist_ok=True)
LOG = open("brvm_donnees_resultats.txt", "w", encoding="utf-8")
DIAG = {"n": 0}


def out(*a):
    t = " ".join(str(x) for x in a)
    print(t)
    LOG.write(t + "\n")
    LOG.flush()


def liste_tickers():
    trouves = set()
    for url in PAGES:
        try:
            r = requests.get(url, headers=H, timeout=30)
            try:
                for t in pd.read_html(io.StringIO(r.text)):
                    for c in t.columns:
                        if str(c).strip().lower() in ("symbole", "symbol", "ticker", "code"):
                            for v in t[c].dropna().astype(str):
                                v = v.strip().upper()
                                if re.fullmatch(r"[A-Z0-9]{3,7}", v):
                                    trouves.add(v)
            except Exception:
                pass
            for m in re.findall(r'href="(?:\./|/brvm/)?([A-Za-z0-9]{3,7})\.html"', r.text):
                trouves.add(m.upper())
        except Exception:
            pass
    trouves -= {"INDEX", "SECTORS", "ABOUT", "HOME"}
    if len(trouves) >= 30:
        return sorted(trouves | set(SECOURS))
    out("(liste en ligne illisible : liste de secours utilisee)")
    return SECOURS


def histos(code, d0, d1):
    for essai in range(2):
        try:
            r = requests.post(API, json={"ticker": code, "datedeb": d0, "datefin": d1, "xperiod": 0}, headers=H, timeout=30)
            j = r.json()
            lst = j.get("lst")
            if not lst:
                if DIAG["n"] < 3 and "nodata" not in str(j.get("error", "")):
                    DIAG["n"] += 1
                    out("  (diagnostic) %s %s->%s : statut %s, reponse %s" % (code, d0, d1, r.status_code, r.text[:160]))
                return None
            df = pd.DataFrame(lst)
            df["Date"] = pd.to_datetime(df["Date"], format="%d/%m/%Y")
            return df.set_index("Date")[["Open", "High", "Low", "Close", "Volume"]].astype(float)
        except Exception as e:
            if DIAG["n"] < 3:
                DIAG["n"] += 1
                out("  (diagnostic) %s : erreur %s" % (code, str(e)[:120]))
            time.sleep(1)
    return None


def trouver_suffixe(ticker, mapping, aujourdhui):
    d0 = (aujourdhui - pd.Timedelta(days=60)).strftime("%Y-%m-%d")
    d1 = aujourdhui.strftime("%Y-%m-%d")
    ordre = ([mapping[ticker]] if ticker in mapping else []) + [s for s in SUFFIXES if s != mapping.get(ticker)]
    for s in ordre:
        if histos("%s.%s" % (ticker, s.lower()), d0, d1) is not None:
            return s
        time.sleep(0.2)
    return None


def fenetres(debut, fin):
    d = pd.Timestamp(debut)
    while d <= fin:
        e = min(d + pd.Timedelta(days=PAS - 1), fin)
        yield d.strftime("%Y-%m-%d"), e.strftime("%Y-%m-%d")
        d = e + pd.Timedelta(days=1)


def telecharger(ticker, suffixe, aujourdhui):
    f = os.path.join(DOSSIER, "%s.csv" % ticker)
    ancien = pd.read_csv(f, index_col=0, parse_dates=True) if os.path.exists(f) else None
    debut = DEBUT if ancien is None or len(ancien) == 0 else (ancien.index[-1] - pd.Timedelta(days=10)).strftime("%Y-%m-%d")
    morceaux = []
    for d0, d1 in fenetres(debut, aujourdhui):
        df = histos("%s.%s" % (ticker, suffixe.lower()), d0, d1)
        if df is not None:
            morceaux.append(df)
        time.sleep(0.25)
    if not morceaux:
        return ancien
    nouveau = pd.concat(morceaux)
    if ancien is not None:
        nouveau = pd.concat([ancien, nouveau])
    nouveau = nouveau[~nouveau.index.duplicated(keep="last")].sort_index()
    nouveau.to_csv(f)
    return nouveau


def main():
    aujourdhui = pd.Timestamp.now().normalize()
    fm = os.path.join(DOSSIER, "mapping.json")
    mapping = json.load(open(fm)) if os.path.exists(fm) else {}
    tickers = liste_tickers()
    out("Valeurs a traiter : %d (la premiere execution dure 10 a 20 minutes ; ne ferme pas la fenetre)" % len(tickers))
    resume = []
    for t in tickers:
        s = trouver_suffixe(t, mapping, aujourdhui)
        if s is None:
            out("  %-7s introuvable chez Sikafinance (ignoree)" % t)
            continue
        mapping[t] = s
        json.dump(mapping, open(fm, "w"))
        df = telecharger(t, s, aujourdhui)
        if df is None or len(df) < 20:
            out("  %-7s trop peu de donnees" % t)
            continue
        ret = df["Close"].pct_change()
        sauts = ret[ret.abs() > 0.08]
        sans = float((df["Volume"] == 0).mean()) * 100
        retard = (aujourdhui - df.index[-1]).days
        resume.append((t, s, len(df), df.index[0].date(), df.index[-1].date(), sans, len(sauts), retard))
        out("  %-7s ok : %d jours (%s -> %s)" % (t, len(df), df.index[0].date(), df.index[-1].date()))
        if len(sauts) > 0:
            out("          ATTENTION %d variation(s) quotidienne(s) au-dela de 8 %% (fractionnement ou erreur ?) : %s" % (
                len(sauts), "; ".join("%s %+.0f %%" % (d.date(), v * 100) for d, v in sauts.head(3).items())))
    out("\n=== RESUME (valeur, pays, jours, premiere date, derniere date, %% de jours sans volume, variations > 8 %%, jours de retard) ===")
    for r in resume:
        out("%-7s .%s %5d  %s -> %s | sans volume %5.1f %% | sauts %d | retard %d j" % r)
    out("\nValeurs avec donnees : %d | copies locales dans le dossier %s" % (len(resume), DOSSIER))
    out("Colle-moi tout le contenu de brvm_donnees_resultats.txt")


if __name__ == "__main__":
    main()
