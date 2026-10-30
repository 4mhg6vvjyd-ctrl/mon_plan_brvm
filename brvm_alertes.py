"""Suivi de portefeuille BRVM et alertes (WhatsApp et/ou Telegram).

Utilisation :
  py brvm_alertes.py --init        cree config_alertes.json et mes_achats.csv (modeles)
  py brvm_alertes.py --test        envoie un message de test sur les canaux actifs
  py brvm_alertes.py --portefeuille  affiche votre portefeuille
  py brvm_alertes.py --simuler     affiche les alertes sans les envoyer
  py brvm_alertes.py               verifie et envoie les alertes (a lancer chaque soir)
"""
import csv
import json
import os
import re
import sys
import time
import requests
import pandas as pd

CONFIG = "config_alertes.json"
ACHATS = "mes_achats.csv"
ETAT = "alertes_etat.json"
DONNEES = "brvm_donnees"
MODELE_CONFIG = {
    "whatsapp": {"actif": False, "phone_number_id": "", "token": "", "destinataire": "223XXXXXXXX", "template": "alerte_brvm", "langue": "fr", "version_api": "v23.0"},
    "telegram": {"actif": False, "token": "", "chat_id": ""},
    "seuils": {"variation_jour": 0.05, "dividende_jours": 7, "annonce_score": 2, "chute_score": 10, "poids_max": 0.25},
    "versement": {"montant": 250000, "frequence": "trimestre", "prochaine_date": "2026-12-01", "rappel_jours": 2},
    "resume_hebdo": True,
}
MOIS_FREQ = {"mois": 1, "trimestre": 3, "semestre": 6, "an": 12}


def fmt(n):
    return "{:,.0f}".format(n).replace(",", " ")


def pct(x, signe=True):
    return ("{:+.1f}" if signe else "{:.1f}").format(x * 100).replace(".", ",") + " %"


def charger_config():
    if not os.path.exists(CONFIG):
        return json.loads(json.dumps(MODELE_CONFIG))
    cfg = json.load(open(CONFIG, encoding="utf-8"))
    for k, v in MODELE_CONFIG.items():
        if isinstance(v, dict):
            cfg[k] = {**v, **cfg.get(k, {})}
        else:
            cfg.setdefault(k, v)
    cfg["whatsapp"]["token"] = os.environ.get("WHATSAPP_TOKEN", cfg["whatsapp"]["token"])
    return cfg


def charger_etat():
    try:
        return json.load(open(ETAT, encoding="utf-8"))
    except Exception:
        return {"envoyes": {}, "scores": {}, "dernier_resume": "", "prochain_versement": ""}


def init():
    if not os.path.exists(CONFIG):
        json.dump(MODELE_CONFIG, open(CONFIG, "w", encoding="utf-8"), indent=2, ensure_ascii=False)
        print("Cree : %s (remplissez les canaux que vous voulez utiliser)" % CONFIG)
    if not os.path.exists(ACHATS):
        with open(ACHATS, "w", encoding="utf-8", newline="") as f:
            f.write("date;ticker;type;quantite;prix;frais\n2026-11-02;SNTS;achat;11;4425;650\n2026-12-01;SNTS;dividende;11;174;0\n")
        print("Cree : %s (une ligne par achat, vente ou dividende ; type = achat, vente ou dividende ; pour un dividende : quantite et prix = dividende par action)" % ACHATS)


# ---------- canaux ----------
def une_ligne(texte, limite=900):
    t = re.sub(r"\s*\n+\s*", " | ", texte.strip())
    return re.sub(r" {2,}", " ", t)[:limite]


def envoyer_whatsapp(cfg, texte):
    w = cfg["whatsapp"]
    if not (w["phone_number_id"] and w["token"] and w["destinataire"]):
        return False, "WhatsApp : configuration incomplete"
    url = "https://graph.facebook.com/%s/%s/messages" % (w["version_api"], w["phone_number_id"])
    en_tete = {"Authorization": "Bearer " + w["token"], "Content-Type": "application/json"}
    corps = {"messaging_product": "whatsapp", "recipient_type": "individual", "to": w["destinataire"], "type": "text", "text": {"preview_url": False, "body": texte[:4000]}}
    try:
        r = requests.post(url, headers=en_tete, json=corps, timeout=30)
        if r.status_code == 200:
            return True, "WhatsApp : message envoye"
        code = None
        try:
            code = r.json().get("error", {}).get("code")
        except Exception:
            pass
        if code == 131047 or "re-engagement" in r.text.lower():
            modele = {"messaging_product": "whatsapp", "to": w["destinataire"], "type": "template",
                      "template": {"name": w["template"], "language": {"code": w["langue"]}, "components": [{"type": "body", "parameters": [{"type": "text", "text": une_ligne(texte)}]}]}}
            r2 = requests.post(url, headers=en_tete, json=modele, timeout=30)
            if r2.status_code == 200:
                return True, "WhatsApp : message envoye par modele (fenetre de 24 h fermee)"
            return False, "WhatsApp : echec du modele (%s) %s" % (r2.status_code, r2.text[:200])
        return False, "WhatsApp : echec (%s) %s" % (r.status_code, r.text[:200])
    except Exception as e:
        return False, "WhatsApp : erreur reseau (%s)" % str(e)[:100]


def envoyer_telegram(cfg, texte):
    t = cfg["telegram"]
    if not (t["token"] and t["chat_id"]):
        return False, "Telegram : configuration incomplete"
    try:
        r = requests.post("https://api.telegram.org/bot%s/sendMessage" % t["token"], json={"chat_id": t["chat_id"], "text": texte[:4000]}, timeout=30)
        return (r.status_code == 200), "Telegram : " + ("message envoye" if r.status_code == 200 else "echec (%s)" % r.status_code)
    except Exception as e:
        return False, "Telegram : erreur reseau (%s)" % str(e)[:100]


def diffuser(cfg, texte, simuler=False):
    if simuler:
        print("\n[simulation] " + texte.replace("\n", "\n    "))
        return []
    res = []
    if cfg["whatsapp"]["actif"]:
        res.append(envoyer_whatsapp(cfg, texte))
    if cfg["telegram"]["actif"]:
        res.append(envoyer_telegram(cfg, texte))
    for ok, msg in res:
        print("  " + msg)
    return res


# ---------- donnees ----------
def prix_actuels():
    out = {}
    if not os.path.isdir(DONNEES):
        return out
    for f in os.listdir(DONNEES):
        if f.endswith(".csv"):
            try:
                df = pd.read_csv(os.path.join(DONNEES, f), index_col=0, parse_dates=True)
                c = df["Close"].dropna()
                if len(c) >= 2:
                    out[f[:-4]] = {"prix": float(c.iloc[-1]), "veille": float(c.iloc[-2]), "date": c.index[-1]}
            except Exception:
                pass
    return out


def lire_achats():
    if not os.path.exists(ACHATS):
        return []
    with open(ACHATS, encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f, delimiter=";"))
    out = []
    for r in rows:
        try:
            out.append({"date": r["date"].strip(), "t": r["ticker"].strip().upper(), "type": r["type"].strip().lower(), "q": float(str(r["quantite"]).replace(" ", "").replace(",", ".")),
                        "p": float(str(r["prix"]).replace(" ", "").replace(",", ".")), "frais": float(str(r.get("frais") or 0).replace(" ", "").replace(",", ".") or 0)})
        except Exception:
            continue
    return out


def portefeuille(achats, px):
    pos = {}
    divs = 0.0
    for a in sorted(achats, key=lambda x: x["date"]):
        p = pos.setdefault(a["t"], {"q": 0.0, "cout": 0.0})
        if a["type"] == "achat":
            p["q"] += a["q"]; p["cout"] += a["q"] * a["p"] + a["frais"]
        elif a["type"] == "vente" and p["q"] > 0:
            part = min(a["q"], p["q"]) / p["q"]
            p["cout"] -= p["cout"] * part; p["q"] -= min(a["q"], p["q"])
        elif a["type"] == "dividende":
            divs += a["q"] * a["p"]
    lignes = []
    for t, p in pos.items():
        if p["q"] <= 0:
            continue
        cours = px.get(t, {}).get("prix")
        valeur = p["q"] * cours if cours else None
        lignes.append({"t": t, "q": p["q"], "cout": p["cout"], "cours": cours, "valeur": valeur})
    total = sum(l["valeur"] or 0 for l in lignes)
    for l in lignes:
        l["poids"] = (l["valeur"] / total) if total and l["valeur"] else None
    return lignes, total, divs


def afficher_portefeuille():
    achats, px = lire_achats(), prix_actuels()
    lignes, total, divs = portefeuille(achats, px)
    if not lignes:
        print("Aucun achat enregistre : remplissez %s." % ACHATS)
        return
    cout = sum(l["cout"] for l in lignes)
    print("%-7s %8s %12s %10s %12s %9s %7s" % ("Valeur", "Quantite", "Cout", "Cours", "Valeur", "Gain", "Poids"))
    for l in lignes:
        g = (l["valeur"] / l["cout"] - 1) if l["valeur"] and l["cout"] else None
        print("%-7s %8.0f %12s %10s %12s %9s %7s" % (l["t"], l["q"], fmt(l["cout"]), fmt(l["cours"]) if l["cours"] else "-", fmt(l["valeur"]) if l["valeur"] else "-", pct(g) if g is not None else "-", pct(l["poids"], False) if l["poids"] else "-"))
    print("Total investi %s FCFA | valeur %s FCFA | gain des cours %s | dividendes recus %s FCFA" % (fmt(cout), fmt(total), pct(total / cout - 1) if cout else "-", fmt(divs)))


# ---------- verifications ----------
def lire_json(nom):
    try:
        return json.load(open(nom, encoding="utf-8"))
    except Exception:
        return {}


def date_fr(s):
    d = pd.to_datetime(s, dayfirst=True, errors="coerce")
    return None if pd.isna(d) else d


def verifier(cfg, etat, aujourdhui):
    achats, px = lire_achats(), prix_actuels()
    lignes, total, divs = portefeuille(achats, px)
    suivis = {l["t"] for l in lignes}
    actus = lire_json("actualites.json")
    cand = {c["t"]: c for c in lire_json("candidats.json").get("candidats", [])}
    s = cfg["seuils"]
    alertes = []
    # 1. variation du jour
    for l in lignes:
        p = px.get(l["t"])
        if p and p["veille"]:
            v = p["prix"] / p["veille"] - 1
            if abs(v) >= s["variation_jour"] and (aujourdhui - p["date"]).days <= 4:
                alertes.append(("var:%s:%s" % (l["t"], p["date"].date()), "%s %s sur la seance (cours : %s FCFA)." % (l["t"], pct(v), fmt(p["prix"]))))
    # 2. dividendes a venir
    for d in actus.get("dividendes_a_venir", []):
        if d.get("ticker") in suivis:
            dd = date_fr(d.get("date", ""))
            if dd is not None and 0 <= (dd - aujourdhui).days <= s["dividende_jours"]:
                alertes.append(("div:%s:%s" % (d["ticker"], dd.date()), "Dividende %s : detachement le %s, %s FCFA par action. Le cours baisse en general du montant du dividende ce jour-la." % (d["ticker"], dd.strftime("%d/%m"), fmt(d.get("montant") or 0))))
    # 3. annonces
    for x in actus.get("articles", []) + actus.get("communiques", []):
        if x.get("score", 0) >= s["annonce_score"] and set(x.get("tickers", [])) & suivis:
            dt = pd.to_datetime(str(x["date"])[:10], errors="coerce")
            if pd.notna(dt) and (aujourdhui - dt).days <= 2:
                t = sorted(set(x["tickers"]) & suivis)[0]
                ton = {1: "plutot positive", 0: "", -1: "plutot negative"}.get(x.get("sentiment", 0), "")
                alertes.append(("news:" + x["url"], "Annonce %s (%s) : %s%s" % (t, x["categorie"], (x.get("titre") or "")[:120], (" - " + ton) if ton else "")))
    # 4. changement de classement
    for t in suivis:
        c = cand.get(t)
        if not c:
            continue
        ancien = etat["scores"].get(t)
        if ancien and (c["etat"] in ("Prudence", "Inactive") and ancien["etat"] not in ("Prudence", "Inactive") or ancien["score"] - c["score"] >= s["chute_score"]):
            alertes.append(("cls:%s:%s" % (t, c["etat"]), "Classement %s : de %s (%d/100) a %s (%d/100). A reexaminer, sans reagir a chaud." % (t, ancien["etat"], ancien["score"], c["etat"], c["score"])))
        etat["scores"][t] = {"etat": c["etat"], "score": c["score"]}
    # 5. concentration
    for l in lignes:
        if l["poids"] and l["poids"] > s["poids_max"] and len(lignes) >= 3:
            sem = aujourdhui.strftime("%G-%V")
            alertes.append(("conc:%s:%s" % (l["t"], sem), "%s represente %s de votre portefeuille (limite choisie : %s)." % (l["t"], pct(l["poids"], False), pct(s["poids_max"], False))))
    # 6. versement
    v = cfg["versement"]
    prochain = pd.to_datetime(etat.get("prochain_versement") or v["prochaine_date"], errors="coerce")
    if pd.notna(prochain) and v["montant"]:
        pas = MOIS_FREQ.get(v["frequence"], 3)
        while prochain < aujourdhui - pd.Timedelta(days=v["rappel_jours"]):
            prochain = prochain + pd.DateOffset(months=pas)
        if 0 <= (prochain - aujourdhui).days <= v["rappel_jours"]:
            alertes.append(("vers:%s" % prochain.date(), "Rappel : versement de %s FCFA prevu le %s. Repartissez-le sur 2 ou 3 societes de votre liste." % (fmt(v["montant"]), prochain.strftime("%d/%m"))))
        etat["prochain_versement"] = str(prochain.date())
    # 7. resume du lundi
    if cfg.get("resume_hebdo") and aujourdhui.weekday() == 0 and etat.get("dernier_resume") != str(aujourdhui.date()) and lignes:
        cout = sum(l["cout"] for l in lignes)
        top = sorted([l for l in lignes if px.get(l["t"])], key=lambda l: px[l["t"]]["prix"] / px[l["t"]]["veille"] - 1)
        alertes.append(("resume:%s" % aujourdhui.date(), "Resume hebdo : valeur %s FCFA pour %s investis (%s), dividendes recus %s FCFA. %d societes suivies." % (fmt(total), fmt(cout), pct(total / cout - 1) if cout else "-", fmt(divs), len(lignes))))
        etat["dernier_resume"] = str(aujourdhui.date())
    return alertes


def main():
    args = sys.argv[1:]
    if "--init" in args:
        init(); return
    if "--portefeuille" in args:
        afficher_portefeuille(); return
    cfg = charger_config()
    if "--test" in args:
        print("Envoi d'un message de test...")
        res = diffuser(cfg, "Test Mon plan BRVM : si vous lisez ce message, les alertes fonctionnent. Ceci n'est pas un conseil en investissement.")
        if not res:
            print("Aucun canal actif : activez whatsapp ou telegram dans %s." % CONFIG)
        return
    etat = charger_etat()
    aujourdhui = pd.Timestamp.now().normalize()
    alertes = [a for a in verifier(cfg, etat, aujourdhui) if a[0] not in etat["envoyes"]]
    simuler = "--simuler" in args
    print("%d alerte(s) a envoyer." % len(alertes))
    if alertes:
        blocs, courant = [], []
        for a in alertes:
            if courant and sum(len(x[1]) + 3 for x in courant) + len(a[1]) > 700:
                blocs.append(courant); courant = []
            courant.append(a)
        blocs.append(courant)
        for i, bloc in enumerate(blocs):
            entete = "Mon plan BRVM - %s%s\n" % (aujourdhui.strftime("%d/%m/%Y"), " (%d/%d)" % (i + 1, len(blocs)) if len(blocs) > 1 else "")
            texte = entete + "\n".join("- " + a[1] for a in bloc) + ("\nCe n'est pas un conseil en investissement." if i == len(blocs) - 1 else "")
            res = diffuser(cfg, texte, simuler)
            if not simuler and (any(ok for ok, _ in res) or not res):
                for a in bloc:
                    etat["envoyes"][a[0]] = str(aujourdhui.date())
    limite = str((aujourdhui - pd.Timedelta(days=90)).date())
    etat["envoyes"] = {k: v for k, v in etat["envoyes"].items() if v >= limite}
    if not simuler:
        json.dump(etat, open(ETAT, "w", encoding="utf-8"), indent=1, ensure_ascii=False)


if __name__ == "__main__":
    main()
