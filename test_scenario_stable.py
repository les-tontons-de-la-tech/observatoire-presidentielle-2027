"""Départage d'une égalité entre deux scénarios.

Le 29/09/2026, la liste « avec Édouard Philippe » et la liste « sans » comptaient 10 sondages
chacune dans la fenêtre de 90 jours : `max()` a tranché sur l'ordre interne des données, et la
page a changé de scénario — donc de tableau — pour un tirage. La règle : à égalité stricte
(autant de sondages, même fraîcheur), on garde la liste du relevé précédent. Un écart réel
n'est jamais écrasé par cette préférence.
"""
import datetime
import json
import os
import shutil
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import generate as G


def _sondage(institut, fin, noms):
    return {"tour": "1er Tour", "institut": institut, "commanditaire": "Test", "fin_enquete": fin,
            "debut_enquete": fin, "echantillon": 1000, "filename": "test.pdf",
            "hypothese": "Test",
            "candidats": [{"candidat": n, "intentions": 10.0, "parti": "—"} for n in noms]}


def _liste(prefixe):
    return [f"{prefixe}{i}" for i in range(10)]


def main():
    hier = (G.TODAY - datetime.timedelta(days=2)).isoformat()
    a, b = _liste("a"), _liste("b")
    egalite = [_sondage(f"Inst{i}", hier, a) for i in range(3)] \
        + [_sondage(f"Inst{i + 10}", hier, b) for i in range(3)]

    tmp = tempfile.mkdtemp()
    garde = G.DATA
    try:
        G.DATA = tmp

        # 1. Aucun relevé précédent : on retombe sur la règle du maximum, sans préférence.
        assert not os.path.exists(os.path.join(tmp, "summary.json"))
        sans = G.aggregate(egalite)
        assert sans and sans["scenario_sign"] == sorted(a), sans and sans["scenario_sign"]

        # 2. Le relevé précédent portait B : à égalité, B l'emporte.
        with open(os.path.join(tmp, "summary.json"), "w", encoding="utf-8") as f:
            json.dump({"scenario_sign": sorted(b)}, f)
        avec = G.aggregate(egalite)
        assert avec["scenario_sign"] == sorted(b), avec["scenario_sign"]

        # 3. Un écart réel (4 sondages contre 3) n'est pas écrasé par le relevé précédent.
        majorite = G.aggregate(egalite + [_sondage("Inst99", hier, a)])
        assert majorite["scenario_sign"] == sorted(a), majorite["scenario_sign"]
    finally:
        G.DATA = garde
        shutil.rmtree(tmp)
    print("OK — égalité départagée par le relevé précédent, majorité respectée")


if __name__ == "__main__":
    main()
