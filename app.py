import contextlib
import io
import json
import os
import subprocess
import sys
import threading
import time
import traceback

APPDIR = os.path.join(os.environ.get("APPDATA") or os.path.expanduser("~"), "AssistantTrading")
os.makedirs(APPDIR, exist_ok=True)
os.chdir(APPDIR)
CONFIG = os.path.join(APPDIR, "config.json")
JOURNAL = os.path.join(APPDIR, "app.log")
DEFAUT = {"token": "", "chat_id": "", "capital": 100000.0, "poids_etf": 0.7,
          "debut": time.strftime("%Y-%m-%d"), "accepte": False, "brvm_dir": "C:\\trading"}
AVERTISSEMENT = ("Outil d'aide au suivi et a la decision, utilise ici en simulation (paper trading).\n"
                 "Ce n'est pas du conseil financier. Les performances passees ne garantissent pas les performances futures.\n"
                 "Les resultats de tests (backtests) sont optimistes par nature. Tu restes seul responsable de tes decisions.")


def charger():
    cfg = dict(DEFAUT)
    if os.path.exists(CONFIG):
        try:
            with open(CONFIG, encoding="utf-8") as f:
                cfg.update(json.load(f))
        except Exception:
            pass
    return cfg


def sauver(cfg):
    with open(CONFIG, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2)


def appliquer(cfg):
    import agent
    import agent_final
    import plan
    import risque
    import suivi
    import comparaison
    agent.TOKEN = cfg["token"] if cfg["token"] else "COLLE_ICI_LE_TOKEN"
    agent.CHAT_ID = cfg["chat_id"]
    p = float(cfg["poids_etf"])
    for m in (agent_final, plan, risque, suivi, comparaison):
        m.POIDS_ETF = p
    suivi.DEBUT = cfg["debut"]
    suivi.CAPITAL = float(cfg["capital"])
    comparaison.DEBUT = cfg["debut"]
    comparaison.CAPITAL = float(cfg["capital"])
    comparaison.JOURNAL = JOURNAL


def tache_plan(cfg, capital=None):
    import plan
    sys.argv = ["plan", str(capital if capital is not None else cfg["capital"])]
    plan.main()


def tache_risque(cfg, tg=False):
    import risque
    risque.LIGNES.clear()
    sys.argv = ["risque"] + (["tg"] if tg else [])
    risque.main()


def tache_suivi(cfg):
    import suivi
    suivi.main()


def tache_agent(cfg):
    import agent_final
    agent_final.main()


def tache_comparaison(cfg):
    import comparaison
    comparaison.main()


@contextlib.contextmanager
def dans_brvm(cfg):
    d = cfg.get("brvm_dir") or "C:\\trading"
    if not os.path.isdir(d):
        raise RuntimeError("Dossier BRVM introuvable : %s (voir Parametres)" % d)
    ancien = os.getcwd()
    os.chdir(d)
    if d not in sys.path:
        sys.path.insert(0, d)
    try:
        yield d
    finally:
        os.chdir(ancien)


def executer(module, arguments=None):
    anciens = sys.argv
    sys.argv = [module.__name__] + list(arguments or [])
    try:
        module.main()
    except SystemExit as e:
        if e.code not in (None, 0):
            print(e.code)
    finally:
        sys.argv = anciens


def tache_brvm_maj(cfg):
    with dans_brvm(cfg):
        import brvm_data
        import brvm_dividendes
        import brvm_actus
        import brvm_tableau
        import brvm_assistant
        print("== BRVM : cours (la premiere fois, 10 a 20 minutes) ==")
        executer(brvm_data)
        if time.strftime("%d") == "01" or not os.path.isdir("brvm_dividendes"):
            print("== BRVM : dividendes ==")
            executer(brvm_dividendes)
        print("== BRVM : annonces ==")
        executer(brvm_actus)
        print("== BRVM : tableau de bord ==")
        executer(brvm_tableau, ["--sans-ouverture"])
        print("== BRVM : application Mon plan BRVM ==")
        executer(brvm_assistant, ["--sans-ouverture"])
        print("Mise a jour terminee.")


def tache_brvm_tableau(cfg):
    with dans_brvm(cfg):
        import brvm_tableau
        executer(brvm_tableau)


def tache_brvm_plan(cfg):
    import webbrowser
    with dans_brvm(cfg) as d:
        f = os.path.join(d, "brvm_assistant.html")
        if not os.path.exists(f):
            print("brvm_assistant.html est introuvable dans %s." % d)
            return
        webbrowser.open("file:///" + f.replace("\\", "/"))
        print("Application ouverte dans le navigateur : %s" % f)


def tache_brvm_alertes(cfg, options=None):
    with dans_brvm(cfg):
        import brvm_alertes
        executer(brvm_alertes, options or [])


def tache_brvm_quotidien(cfg):
    tache_brvm_maj(cfg)
    print("== BRVM : alertes ==")
    tache_brvm_alertes(cfg)


def tache_telegram(cfg):
    import agent
    if agent.TOKEN.startswith("COLLE"):
        print("Aucun token Telegram n'est enregistre : ouvre Parametres et renseigne le token et le Chat ID.")
        return
    agent.envoyer("Test de l'Assistant Trading : la liaison Telegram fonctionne.")
    print("Message de test envoye (verifie ton Telegram).")


def planifier(supprimer=False):
    if not getattr(sys, "frozen", False):
        return "La planification automatique n'est disponible que dans la version .exe."
    exe = sys.executable
    taches = [("AssistantTrading-Agent", ["/SC", "DAILY", "/ST", "00:05", "/RI", "240", "/DU", "24:00"], "--agent"),
              ("AssistantTrading-Risque", ["/SC", "WEEKLY", "/D", "MON", "/ST", "08:00"], "--risque --tg"),
              ("AssistantTrading-Suivi", ["/SC", "WEEKLY", "/D", "MON", "/ST", "08:10"], "--suivi"),
              ("AssistantTrading-BRVM", ["/SC", "WEEKLY", "/D", "MON,TUE,WED,THU,FRI", "/ST", "18:45"], "--brvm-quotidien")]
    sans_fenetre = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    lignes = []
    for nom, planning, arg in taches:
        if supprimer:
            cmd = ["schtasks", "/Delete", "/F", "/TN", nom]
        else:
            cmd = ["schtasks", "/Create", "/F", "/TN", nom] + planning + ["/TR", '"%s" %s' % (exe, arg)]
        r = subprocess.run(cmd, capture_output=True, text=True, creationflags=sans_fenetre)
        lignes.append("%s : %s" % (nom, "ok" if r.returncode == 0 else "echec - " + (r.stdout + r.stderr).strip()))
    return "\n".join(lignes)


def mode_ligne(args):
    cfg = charger()
    buf = io.StringIO()
    try:
        with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
            if "--planifier" in args:
                print(planifier())
            elif "--deplanifier" in args:
                print(planifier(supprimer=True))
            elif any(a.startswith("--brvm") for a in args):
                if "--brvm-maj" in args:
                    tache_brvm_maj(cfg)
                elif "--brvm-tableau" in args:
                    tache_brvm_tableau(cfg)
                elif "--brvm-plan" in args:
                    tache_brvm_plan(cfg)
                elif "--brvm-alertes" in args:
                    tache_brvm_alertes(cfg, [a for a in args if a in ("--test", "--simuler", "--portefeuille", "--init")])
                elif "--brvm-quotidien" in args:
                    tache_brvm_quotidien(cfg)
                else:
                    print("Option BRVM inconnue : --brvm-maj --brvm-tableau --brvm-plan --brvm-alertes [--test|--simuler|--portefeuille|--init] --brvm-quotidien")
            else:
                appliquer(cfg)
                if "--agent" in args:
                    tache_agent(cfg)
                elif "--suivi" in args:
                    tache_suivi(cfg)
                elif "--comparaison" in args:
                    tache_comparaison(cfg)
                elif "--risque" in args:
                    tache_risque(cfg, tg="--tg" in args)
                elif "--plan" in args:
                    i = args.index("--plan")
                    cap = float(args[i + 1]) if len(args) > i + 1 else None
                    tache_plan(cfg, cap)
                elif "--test-telegram" in args:
                    tache_telegram(cfg)
                else:
                    print("Option inconnue. Options : --agent --suivi --comparaison --risque [--tg] --plan [capital] --test-telegram --brvm-quotidien --planifier --deplanifier")
    except BaseException:
        buf.write("\nERREUR :\n" + traceback.format_exc())
    sortie = buf.getvalue()
    with open(JOURNAL, "a", encoding="utf-8") as log:
        log.write("\n=== %s  %s ===\n%s\n" % (time.strftime("%Y-%m-%d %H:%M:%S"), " ".join(args), sortie))
    if sys.__stdout__ is not None:
        try:
            print(sortie)
        except Exception:
            pass


def interface():
    import tkinter as tk
    from tkinter import messagebox

    root = tk.Tk()
    root.title("Assistant Trading - protocole tendance")
    root.geometry("1000x700")
    etat = {"occupe": False}

    haut = tk.Frame(root)
    haut.pack(fill="x", padx=8, pady=6)
    statut = tk.Label(root, text="Pret.", anchor="w")
    statut.pack(side="bottom", fill="x")
    texte = tk.Text(root, wrap="word", font=("Consolas", 10))
    barre = tk.Scrollbar(root, command=texte.yview)
    texte.configure(yscrollcommand=barre.set)
    barre.pack(side="right", fill="y")
    texte.pack(fill="both", expand=True, padx=8, pady=4)

    def afficher(t):
        texte.configure(state="normal")
        texte.delete("1.0", "end")
        texte.insert("end", t)
        texte.configure(state="disabled")

    def fin(sortie):
        afficher(sortie)
        etat["occupe"] = False
        statut.configure(text="Termine.")

    def lancer(fonction, titre, trading=True):
        if etat["occupe"]:
            return
        etat["occupe"] = True
        statut.configure(text="En cours : %s (1 a 2 minutes la premiere fois)..." % titre)
        afficher("Calcul en cours...")
        cfg = charger()

        def cible():
            buf = io.StringIO()
            try:
                with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
                    if trading:
                        appliquer(cfg)
                    fonction(cfg)
            except BaseException:
                buf.write("\nERREUR :\n" + traceback.format_exc())
            sortie = buf.getvalue() or "(aucune sortie)"
            root.after(0, lambda: fin(sortie))

        threading.Thread(target=cible, daemon=True).start()

    def parametres():
        cfg = charger()
        fen = tk.Toplevel(root)
        fen.title("Parametres")
        champs = [("token", "Token Telegram"), ("chat_id", "Chat ID Telegram"), ("capital", "Capital (USD)"),
                  ("poids_etf", "Part ETF (0.7 = mix 70/30 ; 0.5 = mix 50/50)"),
                  ("debut", "Date de depart du paper trading (AAAA-MM-JJ)"),
                  ("brvm_dir", "Dossier des fichiers BRVM (par defaut C:\\trading)")]
        vars_ = {}
        for i, (k, lab) in enumerate(champs):
            tk.Label(fen, text=lab).grid(row=i, column=0, sticky="w", padx=8, pady=4)
            v = tk.StringVar(value=str(cfg[k]))
            tk.Entry(fen, textvariable=v, width=52, show="*" if k == "token" else "").grid(row=i, column=1, padx=8, pady=4)
            vars_[k] = v

        def enregistrer():
            c = charger()
            try:
                c["token"] = vars_["token"].get().strip()
                c["chat_id"] = vars_["chat_id"].get().strip()
                c["capital"] = float(vars_["capital"].get().replace(",", "."))
                c["poids_etf"] = float(vars_["poids_etf"].get().replace(",", "."))
                c["debut"] = vars_["debut"].get().strip()
                c["brvm_dir"] = vars_["brvm_dir"].get().strip() or "C:\\trading"
                time.strptime(c["debut"], "%Y-%m-%d")
                if not (0 < c["poids_etf"] <= 1) or c["capital"] <= 0:
                    raise ValueError("valeur hors limites")
            except ValueError as e:
                messagebox.showerror("Parametres", "Valeur invalide : %s" % e)
                return
            sauver(c)
            messagebox.showinfo("Parametres", "Enregistre.")
            fen.destroy()

        tk.Button(fen, text="Enregistrer", command=enregistrer).grid(row=len(champs), column=1, sticky="e", padx=8, pady=10)

    def planification():
        if not messagebox.askyesno("Planification", "Activer l'execution automatique (agent toutes les 4 h, rapport de risque et suivi le lundi) ?\n"
                                   "Si tu as deja des taches planifiees d'une ancienne version (AgentCrypto, RapportRisque), supprime-les d'abord."):
            return
        afficher(planifier())

    boutons = [("Plan d'ordres", lambda: lancer(tache_plan, "plan d'ordres")),
               ("Rapport de risque", lambda: lancer(lambda c: tache_risque(c, False), "rapport de risque")),
               ("Risque + Telegram", lambda: lancer(lambda c: tache_risque(c, True), "rapport de risque")),
               ("Suivi paper trading", lambda: lancer(tache_suivi, "suivi")),
               ("Paper vs test", lambda: lancer(tache_comparaison, "comparaison")),
               ("Verifier l'agent", lambda: lancer(tache_agent, "agent")),
               ("Test Telegram", lambda: lancer(tache_telegram, "test Telegram")),
               ("Planification auto", planification),
               ("BRVM : tout mettre a jour", lambda: lancer(tache_brvm_maj, "mise a jour BRVM (peut durer 20 minutes la premiere fois)", False)),
               ("BRVM : tableau de bord", lambda: lancer(tache_brvm_tableau, "tableau de bord BRVM", False)),
               ("BRVM : Mon plan (navigateur)", lambda: lancer(tache_brvm_plan, "Mon plan BRVM", False)),
               ("BRVM : alertes maintenant", lambda: lancer(tache_brvm_alertes, "alertes BRVM", False)),
               ("BRVM : test WhatsApp/Telegram", lambda: lancer(lambda c: tache_brvm_alertes(c, ["--test"]), "test des alertes", False)),
               ("Parametres", parametres)]
    for i, (lab, cmd) in enumerate(boutons):
        tk.Button(haut, text=lab, command=cmd, width=28).grid(row=i // 3, column=i % 3, padx=4, pady=3)

    cfg0 = charger()
    if not cfg0.get("accepte"):
        messagebox.showinfo("Avertissement", AVERTISSEMENT)
        cfg0["accepte"] = True
        sauver(cfg0)
        afficher("Bienvenue. Ouvre d'abord 'Parametres' pour saisir ton capital, ton token Telegram et la date de depart, puis lance 'Plan d'ordres'.\n\n" + AVERTISSEMENT)
    else:
        afficher(AVERTISSEMENT + "\n\nChoisis une action ci-dessus.")
    root.mainloop()


if __name__ == "__main__":
    args = sys.argv[1:]
    if args:
        mode_ligne(args)
    else:
        interface()
