"""Construit la version marque blanche d'une SGI : python construire_vitrine.py marques/demo.json
Sortie : vitrine_<id>.html (fichier unique, avec les donnees du jour)."""
import json, sys
src = open("brvm_assistant.html", encoding="utf-8").read()
m = json.load(open(sys.argv[1] if len(sys.argv) > 1 else "marques/demo.json", encoding="utf-8"))
import os
obl = json.load(open("obligations.json", encoding="utf-8")).get("obligations", []) if os.path.exists("obligations.json") else []
inj = "<script>window.MARQUE = %s; window.OBL_INLINE = %s;</script>\n<script>\n/*DATA_DEBUT*/" % (json.dumps(m, ensure_ascii=False), json.dumps(obl, ensure_ascii=False))
assert src.count("<script>\n/*DATA_DEBUT*/") == 1
out = src.replace("<script>\n/*DATA_DEBUT*/", inj)
out = out.replace("<title>NAFA – comprendre le marché avant d’investir</title>", "<title>%s – propulsé par NAFA</title>" % m["nom"])
nom = "vitrine_%s.html" % m["id"]
open(nom, "w", encoding="utf-8").write(out)
print(nom, "pret")
