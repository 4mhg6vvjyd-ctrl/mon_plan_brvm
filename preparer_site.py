"""Prepare le dossier 'site' (application installable) a partir de brvm_assistant.html.
Lance automatiquement par la mise a jour quotidienne ; peut aussi etre lance a la main : py preparer_site.py"""
import os
import re
import shutil
import time

MODELE = "pwa_modele"
SORTIE = "site"
BALISES = ('<meta name="theme-color" content="#2a3f8f">\n<link rel="manifest" href="manifest.webmanifest">\n<link rel="apple-touch-icon" href="apple-touch-icon.png">\n'
           '<meta name="apple-mobile-web-app-capable" content="yes">\n<meta name="mobile-web-app-capable" content="yes">\n<meta name="apple-mobile-web-app-title" content="Mon plan BRVM">\n'
           '<meta name="apple-mobile-web-app-status-bar-style" content="default">\n')
ENREGISTREMENT = 'if ("serviceWorker" in navigator) { window.addEventListener("load", () => { navigator.serviceWorker.register("sw.js").catch(() => { /* hors ligne indisponible */ }); }); }\n'


def main():
    h = open("brvm_assistant.html", encoding="utf-8").read()
    if "manifest.webmanifest" not in h:
        h = re.sub(r'(<meta name="viewport"[^>]*>\n)', lambda m: m.group(1) + BALISES, h, count=1)
        h = h.replace("rendre();\n</script>", "rendre();\n" + ENREGISTREMENT + "</script>", 1)
    shutil.rmtree(SORTIE, ignore_errors=True)
    shutil.copytree(MODELE, SORTIE)
    open(os.path.join(SORTIE, "index.html"), "w", encoding="utf-8").write(h)
    sw = open(os.path.join(SORTIE, "sw.js"), encoding="utf-8").read()
    sw = re.sub(r'const VERSION = "[^"]*";', 'const VERSION = "%s";' % time.strftime("%Y%m%d%H%M"), sw)
    open(os.path.join(SORTIE, "sw.js"), "w", encoding="utf-8").write(sw)
    print("Dossier '%s' pret (%d fichiers)." % (SORTIE, len(os.listdir(SORTIE))))


if __name__ == "__main__":
    main()
