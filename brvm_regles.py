"""Regles de selection et de diversification communes au tableau de bord et au simulateur BRVM.

Un profil fixe : le nombre de lignes par defaut, les limites (part des lignes dans un meme groupe, secteur ou pays),
les valeurs admises et le critere de classement. Les limites sont modifiables ici."""

GROUPES = {"BOA": {"BOAB", "BOABF", "BOAC", "BOAM", "BOAN", "BOAS"}, "Total": {"TTLC", "TTLS"}, "Orange": {"SNTS", "ORAC"}}
PAYS = {"ci": "Cote d'Ivoire", "sn": "Senegal", "bf": "Burkina Faso", "tg": "Togo", "bj": "Benin", "ml": "Mali", "ne": "Niger"}


def _ok_commun(c):
    return not c.get("grave") and not c.get("suspect") and c.get("med", 0) >= 10e6


PROFILS = {
    "prudent": {"nom": "Prudent", "n": 8, "groupe": 0.25, "secteur": 0.40, "pays": 0.65, "etats": ("A etudier",), "cle": "score",
                "filtre": lambda c: not c.get("vigilance"),
                "texte": "valeurs 'a etudier' sans point de vigilance, classees par score"},
    "equilibre": {"nom": "Equilibre", "n": 6, "groupe": 0.34, "secteur": 0.50, "pays": 0.80, "etats": ("A etudier", "A surveiller"), "cle": "score",
                  "filtre": lambda c: _ok_commun(c),
                  "texte": "valeurs 'a etudier' ou 'a surveiller' (vigilance tolerée), classees par score"},
    "rendement": {"nom": "Rendement", "n": 5, "groupe": 0.40, "secteur": 0.60, "pays": 1.00, "etats": ("A etudier", "A surveiller"), "cle": "rend_moy",
                  "filtre": lambda c: _ok_commun(c) and not c.get("coupe") and c.get("d200", -1) > 0,
                  "texte": "classees par rendement moyen des dividendes, cours au-dessus de la moyenne 200 jours, dividende non reduit"},
    "composition": {"nom": "Compounding", "n": 8, "groupe": 0.30, "secteur": 0.45, "pays": 0.70, "etats": ("A etudier", "A surveiller"), "cle": "mixte",
                    "filtre": lambda c: _ok_commun(c) and not c.get("coupe") and c.get("d200", -1) > 0 and c.get("serie", 0) >= 3 and c.get("croiss3") is not None and c["croiss3"] >= -0.05,
                    "texte": "long terme : dividende verse au moins 3 ans de suite et non erode, cours au-dessus de la moyenne 200 jours, classement qui melange rendement du dividende et croissance (dividende en hausse, tendance sur 1 an)"},
    "dynamique": {"nom": "Dynamique", "n": 5, "groupe": 0.40, "secteur": 0.60, "pays": 1.00, "etats": ("A etudier", "A surveiller"), "cle": "p6m",
                  "filtre": lambda c: _ok_commun(c) and not c.get("coupe") and c.get("d200", -1) > 0,
                  "texte": "classees par hausse des 6 derniers mois (chasse a la performance passee, risque d'inversion eleve)"},
}


def groupe_de(t):
    for g, ens in GROUPES.items():
        if t in ens:
            return g
    return None


def plafond(part, n, mini=1):
    return max(mini, int(part * n + 1e-9))


def limites(profil, n):
    P = PROFILS.get(profil, PROFILS["prudent"])
    mini = 2 if n >= 3 else 1   # avec peu de lignes, on tolere 2 valeurs du meme secteur ou du meme pays
    return plafond(P["groupe"], n), plafond(P["secteur"], n, mini), plafond(P["pays"], n, mini)


def _cle(c, nom):
    v = c.get(nom)
    return -1e9 if v is None or v != v else v


def _rang(vals):
    """Rang en pourcentage (0 a 1) ; valeur manquante = 0,4."""
    ordre = sorted(v for v in vals if v is not None and v == v)
    res = []
    for v in vals:
        if v is None or v != v or not ordre:
            res.append(0.4)
        else:
            inf = sum(1 for x in ordre if x < v)
            egal = sum(1 for x in ordre if x == v)
            res.append((inf + 0.5 * egal) / len(ordre))
    return res


def _clip(v, lo, hi):
    return 0.0 if v is None or v != v else max(lo, min(hi, v))


def calculer_mixte(base, part_div):
    y = _rang([c.get("rend_moy") for c in base])
    g = _rang([0.5 * _clip(c.get("croiss3"), -0.2, 0.3) + 0.5 * _clip(c.get("p1a"), -0.2, 0.6) for c in base])
    for c, yy, gg in zip(base, y, g):
        c["mixte"] = part_div * yy + (1 - part_div) * gg


def selection(candidats, n=None, completer=False, profil="prudent", part_div=0.5):
    """Retourne (retenues, ecartees) ; ecartees = liste de (code, raison)."""
    P = PROFILS.get(profil, PROFILS["prudent"])
    n = n or P["n"]
    base = [c for c in candidats if c["etat"] in P["etats"] and P["filtre"](c)]
    if P["cle"] == "mixte":
        calculer_mixte(base, part_div)
    base.sort(key=lambda c: -_cle(c, P["cle"]))
    passes = [base]
    if completer and profil == "prudent":
        passes.append(sorted([c for c in candidats if c["etat"] == "A surveiller" and not c.get("vigilance")], key=lambda c: -c["score"]))
    pg, ps, pp = limites(profil, n)
    retenues, ecartees = [], []
    cg, cs, cp = {}, {}, {}
    for liste in passes:
        for c in liste:
            if len(retenues) >= n:
                ecartees.append((c["t"], "liste complete (%d lignes)" % n))
                continue
            g = groupe_de(c["t"])
            if g and cg.get(g, 0) >= pg:
                ecartees.append((c["t"], "limite du groupe %s atteinte (%d sur %d lignes)" % (g, pg, n)))
                continue
            if cs.get(c["secteur"], 0) >= ps:
                ecartees.append((c["t"], "limite du secteur %s atteinte (%d sur %d lignes)" % (c["secteur"], ps, n)))
                continue
            if cp.get(c["pays"], 0) >= pp:
                ecartees.append((c["t"], "limite du pays %s atteinte (%d sur %d lignes)" % (c["pays"], pp, n)))
                continue
            retenues.append(c)
            if g:
                cg[g] = cg.get(g, 0) + 1
            cs[c["secteur"]] = cs.get(c["secteur"], 0) + 1
            cp[c["pays"]] = cp.get(c["pays"], 0) + 1
    return retenues, ecartees
