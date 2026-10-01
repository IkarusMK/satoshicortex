"""Was jeder Kanal eingebracht hat -- und was er gekostet hat.

DER ANLASS. Aus dem Betrieb, 30.09.2026: wer ein Routing-Netz aufbaut, muss
wissen, welcher Kanal sich lohnt. Bis dahin zeigte die Anwendung eine Summe
("so viele Weiterleitungen, so viel verdient") -- keinen Kanal, keine Kosten,
keinen Zeitraum.

WO DIE GEBUEHR ZAEHLT. Beim AUSGEHENDEN Kanal: dort wurde Liquiditaet
verkauft, dort wird der Kanal dafuer leerer. Der Durchsatz herein steht
trotzdem dabei -- ein Kanal, ueber den viel hereinkommt, ist die Quelle, die
die anderen wieder auffuellt.

WO DIE KOSTEN ZAEHLEN.
  Oeffnen      beim Kanal, wenn DU ihn eroeffnet hast (nur dann zahlt deine
               Wallet die Transaktion)
  Umschichten  beim Kanal, der AUFGEFUELLT wurde -- fuer ihn wurde bezahlt
  Schliessen   beim Kanal, soweit LND die Gebuehr deiner Wallet zuordnet

Was LND nicht sieht, steht hier nicht: Gebuehren fremder Tauschdienste
(Boltz und aehnliche) laufen ausserhalb des Knotens.

Diese Datei fragt niemanden. Sie bekommt, was lnd.py gelesen hat, und rechnet.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional

TAG_S = 86_400
MONATE = 6


def _leer() -> Dict[str, int]:
    return {"weiterleitungen": 0, "raus_sat": 0, "rein_sat": 0,
            "eingenommen_msat": 0, "oeffnen_sat": 0, "umschichten_sat": 0,
            "schliessen_sat": 0}


def _monat(zeit_s: int) -> str:
    return datetime.fromtimestamp(int(zeit_s), timezone.utc).strftime("%Y-%m")


def _letzte_monate(jetzt_s: int, anzahl: int) -> List[str]:
    jetzt = datetime.fromtimestamp(int(jetzt_s), timezone.utc)
    jahr, monat = jetzt.year, jetzt.month
    liste = []
    for _ in range(anzahl):
        liste.append(f"{jahr:04d}-{monat:02d}")
        monat -= 1
        if monat == 0:
            jahr, monat = jahr - 1, 12
    return list(reversed(liste))


def alter_tage(nummer: str, hoehe: Optional[int]) -> Optional[int]:
    """Wie alt ein Kanal ist -- aus der Blockhoehe in seiner Nummer.

    Die oberen 24 Bit der short_channel_id sind der Block, in dem er
    eroeffnet wurde (BOLT 7). LNDs "lifetime" taugt dafuer nicht: sie
    zaehlt nur, seit LND zuletzt gestartet ist.
    """
    try:
        block = int(nummer) >> 40
    except (TypeError, ValueError):
        return None
    if not hoehe or block <= 0 or block > hoehe:
        return None
    return max(1, (int(hoehe) - block) // 144)


def _zusammen(summen: Dict[str, int]) -> Dict[str, int]:
    """Die Summen in der Form, die die Oberflaeche liest."""
    ein = summen["eingenommen_msat"] // 1000
    kosten = (summen["oeffnen_sat"] + summen["umschichten_sat"]
              + summen["schliessen_sat"])
    return {"weiterleitungen": summen["weiterleitungen"],
            "raus_sat": summen["raus_sat"], "rein_sat": summen["rein_sat"],
            "eingenommen_sat": ein, "kosten_sat": kosten,
            "netto_sat": ein - kosten}


def rechnen(weiterleitungen: Iterable[Dict[str, Any]],
            oeffnen: Dict[str, Dict[str, int]],
            schliessen: Dict[str, Dict[str, int]],
            umschichtungen: Iterable[Dict[str, Any]],
            offene: List[Dict[str, Any]],
            geschlossene: List[Dict[str, Any]],
            tage: int, jetzt_s: int, hoehe: Optional[int]) -> Dict[str, Any]:
    """Je Kanal: im Zeitraum, in den letzten 30 Tagen, seit Eroeffnung.

    tage = 0 heisst "seit Beginn".
    """
    seit = jetzt_s - tage * TAG_S if tage else 0
    seit30 = jetzt_s - 30 * TAG_S
    fenster = {"zeitraum": seit, "tage30": seit30, "gesamt": 0}
    je: Dict[str, Dict[str, Dict[str, int]]] = {}
    namen: Dict[str, str] = {}
    monate = {m: {"eingenommen_msat": 0, "kosten_sat": 0}
              for m in _letzte_monate(jetzt_s, MONATE)}

    def konto(nummer: str) -> Dict[str, Dict[str, int]]:
        return je.setdefault(nummer, {f: _leer() for f in fenster})

    def buchen(nummer: str, zeit_s: int, feld: str, wert: int) -> None:
        for name, ab in fenster.items():
            if zeit_s >= ab:
                konto(nummer)[name][feld] += wert

    for e in weiterleitungen:
        zeit, raus, rein = int(e["zeit_s"]), str(e.get("raus") or ""), str(e.get("rein") or "")
        if raus:
            buchen(raus, zeit, "weiterleitungen", 1)
            buchen(raus, zeit, "raus_sat", int(e.get("raus_sat") or 0))
            buchen(raus, zeit, "eingenommen_msat", int(e.get("gebuehr_msat") or 0))
            if e.get("raus_name"):
                namen.setdefault(raus, e["raus_name"])
        if rein:
            buchen(rein, zeit, "rein_sat", int(e.get("rein_sat") or 0))
            if e.get("rein_name"):
                namen.setdefault(rein, e["rein_name"])
        monat = monate.get(_monat(zeit))
        if monat is not None:
            monat["eingenommen_msat"] += int(e.get("gebuehr_msat") or 0)

    def kosten(nummer: str, zeit_s: int, feld: str, sat: int) -> None:
        buchen(nummer, zeit_s, feld, sat)
        monat = monate.get(_monat(zeit_s))
        if monat is not None:
            monat["kosten_sat"] += sat

    for nummer, k in oeffnen.items():
        kosten(str(nummer), int(k["zeit_s"]), "oeffnen_sat", int(k["sat"]))
    for nummer, k in schliessen.items():
        kosten(str(nummer), int(k["zeit_s"]), "schliessen_sat", int(k["sat"]))
    for u in umschichtungen:
        kosten(str(u["rein_kanal"]), int(u["zeit_s"]), "umschichten_sat",
               int(u["gebuehr_sat"]))

    zeilen = []
    summe = _leer()
    summe30 = _leer()
    for kanal, offen in ([(k, True) for k in offene]
                         + [(k, False) for k in geschlossene]):
        nummer = str(kanal["nummer"])
        k = konto(nummer)
        zeitraum = _zusammen(k["zeitraum"])
        dreissig = _zusammen(k["tage30"])
        gesamt = _zusammen(k["gesamt"])
        kapazitaet = int(kanal.get("kapazitaet") or 0)
        dauer = tage or alter_tage(nummer, hoehe)
        rate = (round(zeitraum["eingenommen_sat"] / (kapazitaet / 1e6) * 30 / dauer)
                if offen and kapazitaet and dauer else None)
        zeilen.append({
            "nummer": nummer,
            "name": kanal.get("gegenstelle") or kanal.get("name") or namen.get(nummer, ""),
            "offen": offen,
            "kapazitaet": kapazitaet,
            "zeitraum": zeitraum,
            "tage30": {"eingenommen_sat": dreissig["eingenommen_sat"],
                       "netto_sat": dreissig["netto_sat"]},
            "gesamt": {"eingenommen_sat": gesamt["eingenommen_sat"],
                       "oeffnen_sat": k["gesamt"]["oeffnen_sat"],
                       "umschichten_sat": k["gesamt"]["umschichten_sat"],
                       "schliessen_sat": k["gesamt"]["schliessen_sat"],
                       "netto_sat": gesamt["netto_sat"],
                       "weiterleitungen": gesamt["weiterleitungen"]},
            "pro_mio_monat_sat": rate,
        })
        for feld in summe:
            summe[feld] += k["zeitraum"][feld]
            summe30[feld] += k["tage30"][feld]

    def kurz(s: Dict[str, int]) -> Dict[str, int]:
        z = _zusammen(s)
        return {f: z[f] for f in ("eingenommen_sat", "kosten_sat", "netto_sat",
                                  "weiterleitungen", "raus_sat")}

    return {
        "zeitraum_tage": tage,
        "summe": kurz(summe),
        "summe_30": kurz(summe30),
        "kanaele": zeilen,
        "monate": [{"monat": m, "eingenommen_sat": w["eingenommen_msat"] // 1000,
                    "kosten_sat": w["kosten_sat"]} for m, w in monate.items()],
    }
