/* QR-Codes, selbst gerechnet.

   Aus dem Betrieb, 15.09.2026: "aus ner bitcoin adresse mal direkt nen QR code
   machen ... zum scannen macht das ueberweissen einfacher".

   Keine fremde Bibliothek und kein Dienst: der Code entsteht hier im
   Browser, aus der Adresse, die der eigene Knoten gerade erzeugt hat. Ein
   Bild, das ein fremder Server baut, waere eine Adresse, die ein Fremder
   zuerst kennt.

   Zwei Modi, und der zweite kam am 16.09.2026 dazu, als das Empfangen ueber
   Lightning gebaut wurde:

     * BYTE fuer alles Gemischte -- "bitcoin:bc1p..." mit Klein- und
       Grossbuchstaben.
     * ALPHANUMERISCH fuer Texte aus Ziffern, Grossbuchstaben und einer
       Handvoll Zeichen. Er packt zwei Zeichen in 11 Bit statt 16. Eine
       Lightning-Rechnung passt im Byte-Modus NICHT (ueber 213 Byte), in
       Grossbuchstaben und alphanumerisch dagegen schon -- bech32 ist
       gegenueber Gross- und Kleinschreibung gleichgueltig, und genau dafuer
       sieht BOLT 11 die Grossschreibung im QR-Code vor.

   Fehlerkorrektur M (etwa 15 %), Versionen 1 bis 10: bis 213 Byte oder 311
   alphanumerische Zeichen. Aufbau nach ISO/IEC 18004; die Maske wird nach den
   Strafpunkten der Norm gewaehlt. Geprueft in tests/test_qr.py gegen feste
   Werte der Norm und durch Zuruecklesen. */
(function (umgebung) {
  "use strict";

  // Fehlerkorrektur M, Index = Version: ECC-Bytes je Block, Anzahl Bloecke.
  const ECC_JE_BLOCK = [0, 10, 16, 26, 18, 24, 16, 18, 22, 22, 26];
  const BLOECKE = [0, 1, 1, 1, 2, 2, 4, 4, 4, 5, 5];
  const HOECHSTE_VERSION = 10;
  const STUFE_M = 0;           // Formatbits der Stufe: L=01, M=00, Q=11, H=10
  const RUHEZONE = 4;          // helle Module rundherum, so verlangt es die Norm
  // Die 45 Zeichen des alphanumerischen Modus, in der Reihenfolge der Norm.
  const ALNUM = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ $%*+-./:";

  // Module, die fuer Daten und Fehlerkorrektur bleiben.
  function rohModule(v) {
    let n = (16 * v + 128) * v + 64;
    if (v >= 2) {
      const ausrichtung = Math.floor(v / 7) + 2;
      n -= (25 * ausrichtung - 10) * ausrichtung - 55;
      if (v >= 7) n -= 36;
    }
    return n;
  }

  function datenBytes(v) {
    return Math.floor(rohModule(v) / 8) - ECC_JE_BLOCK[v] * BLOECKE[v];
  }

  // Wie lang die Laengenangabe ist -- je Modus und Version verschieden.
  function zaehlerBits(v, alnum) {
    if (alnum) return v < 10 ? 9 : 11;
    return v < 10 ? 8 : 16;
  }

  // Wieviel in Version v passt: Bytes, oder Zeichen im alphanumerischen Modus
  // (zwei Zeichen in 11 Bit, ein einzelnes in 6).
  function kapazitaet(v, alnum) {
    const bits = datenBytes(v) * 8 - 4 - zaehlerBits(v, !!alnum);
    if (!alnum) return Math.floor(bits / 8);
    return 2 * Math.floor(bits / 11) + (bits % 11 >= 6 ? 1 : 0);
  }

  function istAlnum(text) {
    for (const zeichen of text) {
      if (ALNUM.indexOf(zeichen) < 0) return false;
    }
    return text.length > 0;
  }

  // ── Reed-Solomon ueber GF(256), Polynom 0x11D ───────────────────────────
  function gfMal(x, y) {
    let z = 0;
    for (let i = 7; i >= 0; i--) {
      z = (z << 1) ^ ((z >>> 7) * 0x11d);
      z ^= ((y >>> i) & 1) * x;
    }
    return z & 0xff;
  }

  function rsTeiler(grad) {
    const teiler = new Array(grad).fill(0);
    teiler[grad - 1] = 1;
    let potenz = 1;
    for (let i = 0; i < grad; i++) {
      for (let j = 0; j < teiler.length; j++) {
        teiler[j] = gfMal(teiler[j], potenz);
        if (j + 1 < teiler.length) teiler[j] ^= teiler[j + 1];
      }
      potenz = gfMal(potenz, 0x02);
    }
    return teiler;
  }

  function rsRest(daten, teiler) {
    const rest = teiler.map(() => 0);
    for (const b of daten) {
      const faktor = b ^ rest.shift();
      rest.push(0);
      teiler.forEach((k, i) => { rest[i] ^= gfMal(k, faktor); });
    }
    return rest;
  }

  // ── Daten ──────────────────────────────────────────────────────────────
  function waehleVersion(laenge, alnum) {
    for (let v = 1; v <= HOECHSTE_VERSION; v++) {
      if (laenge <= kapazitaet(v, alnum)) return v;
    }
    throw new Error("QR: zu lang fuer Version " + HOECHSTE_VERSION
                    + " (" + laenge + (alnum ? " Zeichen)" : " Byte)"));
  }

  function codewoerter(inhalt, v, alnum) {
    const bits = [];
    const schreibe = (wert, anzahl) => {
      for (let i = anzahl - 1; i >= 0; i--) bits.push((wert >>> i) & 1);
    };
    schreibe(alnum ? 0x2 : 0x4, 4);            // Modus
    schreibe(inhalt.length, zaehlerBits(v, alnum));
    if (alnum) {
      for (let i = 0; i < inhalt.length; i += 2) {
        const erstes = ALNUM.indexOf(inhalt[i]);
        if (i + 1 < inhalt.length) {
          schreibe(erstes * 45 + ALNUM.indexOf(inhalt[i + 1]), 11);
        } else {
          schreibe(erstes, 6);
        }
      }
    } else {
      inhalt.forEach((b) => schreibe(b, 8));
    }
    const platz = datenBytes(v) * 8;
    schreibe(0, Math.min(4, platz - bits.length));   // Endekennung
    schreibe(0, (8 - (bits.length % 8)) % 8);
    const daten = [];
    for (let i = 0; i < bits.length; i += 8) {
      let b = 0;
      for (let j = 0; j < 8; j++) b = (b << 1) | bits[i + j];
      daten.push(b);
    }
    for (let fueller = 0xec; daten.length < datenBytes(v);
         fueller ^= 0xec ^ 0x11) {
      daten.push(fueller);
    }
    return daten;
  }

  // Bloecke bilden, je Block die Fehlerkorrektur anhaengen, verschraenken.
  function mitFehlerkorrektur(daten, v) {
    const anzahl = BLOECKE[v];
    const eccLaenge = ECC_JE_BLOCK[v];
    const roh = Math.floor(rohModule(v) / 8);
    const kurze = anzahl - (roh % anzahl);
    const kurzLaenge = Math.floor(roh / anzahl);
    const teiler = rsTeiler(eccLaenge);
    const bloecke = [];
    for (let i = 0, k = 0; i < anzahl; i++) {
      const teil = daten.slice(k, k + kurzLaenge - eccLaenge + (i < kurze ? 0 : 1));
      k += teil.length;
      const ecc = rsRest(teil, teiler);
      if (i < kurze) teil.push(0);
      bloecke.push(teil.concat(ecc));
    }
    const ergebnis = [];
    for (let i = 0; i < bloecke[0].length; i++) {
      bloecke.forEach((block, j) => {
        if (i !== kurzLaenge - eccLaenge || j >= kurze) ergebnis.push(block[i]);
      });
    }
    return ergebnis;
  }

  // ── Formatinformation und Versionsinformation (BCH) ────────────────────
  function formatBits(maske) {
    const daten = (STUFE_M << 3) | maske;
    let rest = daten;
    for (let i = 0; i < 10; i++) rest = (rest << 1) ^ ((rest >>> 9) * 0x537);
    return ((daten << 10) | rest) ^ 0x5412;
  }

  function versionsBits(v) {
    let rest = v;
    for (let i = 0; i < 12; i++) rest = (rest << 1) ^ ((rest >>> 11) * 0x1f25);
    return (v << 12) | rest;
  }

  function ausrichtungen(v) {
    if (v === 1) return [];
    const anzahl = Math.floor(v / 7) + 2;
    const schritt = Math.ceil((v * 4 + 4) / (anzahl * 2 - 2)) * 2;
    const lagen = [6];
    for (let pos = 4 * v + 17 - 7; lagen.length < anzahl; pos -= schritt) {
      lagen.splice(1, 0, pos);
    }
    return lagen;
  }

  function maskiert(maske, x, y) {
    switch (maske) {
      case 0: return (x + y) % 2 === 0;
      case 1: return y % 2 === 0;
      case 2: return x % 3 === 0;
      case 3: return (x + y) % 3 === 0;
      case 4: return (Math.floor(x / 3) + Math.floor(y / 2)) % 2 === 0;
      case 5: return ((x * y) % 2) + ((x * y) % 3) === 0;
      case 6: return (((x * y) % 2) + ((x * y) % 3)) % 2 === 0;
      default: return (((x + y) % 2) + ((x * y) % 3)) % 2 === 0;
    }
  }

  // ── Strafpunkte der Norm, um die lesbarste Maske zu finden ─────────────
  function strafpunkte(modul, n) {
    let summe = 0;
    const verlaufDazu = (laenge, verlauf) => {
      if (verlauf[0] === 0) laenge += n;
      verlauf.pop();
      verlauf.unshift(laenge);
    };
    const finderMuster = (verlauf) => {
      const k = verlauf[1];
      const kern = k > 0 && verlauf[2] === k && verlauf[3] === k * 3
        && verlauf[4] === k && verlauf[5] === k;
      return (kern && verlauf[0] >= k * 4 && verlauf[6] >= k ? 1 : 0)
        + (kern && verlauf[6] >= k * 4 && verlauf[0] >= k ? 1 : 0);
    };
    const lauf = (lesen) => {
      for (let a = 0; a < n; a++) {
        let farbe = false;
        let laenge = 0;
        const verlauf = [0, 0, 0, 0, 0, 0, 0];
        for (let b = 0; b < n; b++) {
          if (lesen(a, b) === farbe) {
            laenge++;
            if (laenge === 5) summe += 3;
            else if (laenge > 5) summe++;
          } else {
            verlaufDazu(laenge, verlauf);
            if (!farbe) summe += finderMuster(verlauf) * 40;
            farbe = lesen(a, b);
            laenge = 1;
          }
        }
        if (farbe) { verlaufDazu(laenge, verlauf); laenge = 0; }
        laenge += n;
        verlaufDazu(laenge, verlauf);
        summe += finderMuster(verlauf) * 40;
      }
    };
    lauf((a, b) => modul[a][b]);
    lauf((a, b) => modul[b][a]);
    let dunkel = 0;
    for (let y = 0; y < n; y++) {
      for (let x = 0; x < n; x++) {
        if (modul[y][x]) dunkel++;
        if (y < n - 1 && x < n - 1) {
          const f = modul[y][x];
          if (f === modul[y][x + 1] && f === modul[y + 1][x] && f === modul[y + 1][x + 1]) {
            summe += 3;
          }
        }
      }
    }
    const gesamt = n * n;
    summe += (Math.ceil(Math.abs(dunkel * 20 - gesamt * 10) / gesamt) - 1) * 10;
    return summe;
  }

  // ── Die Matrix ─────────────────────────────────────────────────────────
  function matrix(text) {
    const roh = String(text);
    const alnum = istAlnum(roh);
    const inhalt = alnum ? roh : Array.from(new TextEncoder().encode(roh));
    const v = waehleVersion(inhalt.length, alnum);
    const n = 4 * v + 17;
    const modul = Array.from({ length: n }, () => new Array(n).fill(false));
    const fest = Array.from({ length: n }, () => new Array(n).fill(false));
    const setze = (x, y, dunkel) => { modul[y][x] = dunkel; fest[y][x] = true; };

    // Taktlinien
    for (let i = 0; i < n; i++) {
      setze(6, i, i % 2 === 0);
      setze(i, 6, i % 2 === 0);
    }
    // Suchmuster mit Trennstreifen
    for (const [cx, cy] of [[3, 3], [n - 4, 3], [3, n - 4]]) {
      for (let dy = -4; dy <= 4; dy++) {
        for (let dx = -4; dx <= 4; dx++) {
          const x = cx + dx;
          const y = cy + dy;
          if (x < 0 || y < 0 || x >= n || y >= n) continue;
          const abstand = Math.max(Math.abs(dx), Math.abs(dy));
          setze(x, y, abstand !== 2 && abstand !== 4);
        }
      }
    }
    // Ausrichtungsmuster
    const lagen = ausrichtungen(v);
    lagen.forEach((a, i) => lagen.forEach((b, j) => {
      const ecke = (i === 0 && j === 0) || (i === 0 && j === lagen.length - 1)
        || (i === lagen.length - 1 && j === 0);
      if (ecke) return;
      for (let dy = -2; dy <= 2; dy++) {
        for (let dx = -2; dx <= 2; dx++) {
          setze(a + dx, b + dy, Math.max(Math.abs(dx), Math.abs(dy)) !== 1);
        }
      }
    }));
    const zeichneFormat = (maske) => {
      const bits = formatBits(maske);
      const bit = (i) => ((bits >>> i) & 1) === 1;
      for (let i = 0; i <= 5; i++) setze(8, i, bit(i));
      setze(8, 7, bit(6));
      setze(8, 8, bit(7));
      setze(7, 8, bit(8));
      for (let i = 9; i < 15; i++) setze(14 - i, 8, bit(i));
      for (let i = 0; i < 8; i++) setze(n - 1 - i, 8, bit(i));
      for (let i = 8; i < 15; i++) setze(8, n - 15 + i, bit(i));
      setze(8, n - 8, true);                 // das immer dunkle Modul
    };
    zeichneFormat(0);                        // reserviert die Flaechen
    if (v >= 7) {
      const bits = versionsBits(v);
      for (let i = 0; i < 18; i++) {
        const dunkel = ((bits >>> i) & 1) === 1;
        const a = n - 11 + (i % 3);
        const b = Math.floor(i / 3);
        setze(a, b, dunkel);
        setze(b, a, dunkel);
      }
    }

    // Daten im Zickzack von rechts unten
    const woerter = mitFehlerkorrektur(codewoerter(inhalt, v, alnum), v);
    let i = 0;
    for (let rechts = n - 1; rechts >= 1; rechts -= 2) {
      if (rechts === 6) rechts = 5;
      for (let schritt = 0; schritt < n; schritt++) {
        for (let j = 0; j < 2; j++) {
          const x = rechts - j;
          const aufwaerts = ((rechts + 1) & 2) === 0;
          const y = aufwaerts ? n - 1 - schritt : schritt;
          if (!fest[y][x] && i < woerter.length * 8) {
            modul[y][x] = ((woerter[i >>> 3] >>> (7 - (i & 7))) & 1) === 1;
            i++;
          }
        }
      }
    }

    const maskiere = (maske) => {
      for (let y = 0; y < n; y++) {
        for (let x = 0; x < n; x++) {
          if (!fest[y][x] && maskiert(maske, x, y)) modul[y][x] = !modul[y][x];
        }
      }
    };
    let beste = 0;
    let wenigste = Infinity;
    for (let maske = 0; maske < 8; maske++) {
      maskiere(maske);
      zeichneFormat(maske);
      const punkte = strafpunkte(modul, n);
      if (punkte < wenigste) { beste = maske; wenigste = punkte; }
      maskiere(maske);                       // XOR: zweimal heisst zurueck
    }
    maskiere(beste);
    zeichneFormat(beste);
    return { version: v, groesse: n, maske: beste,
             modus: alnum ? "alnum" : "byte", module: modul, fest };
  }

  // Als SVG: dunkel auf hell, auch auf dunklem Grund. Viele Scanner lesen
  // helle Module auf dunklem Grund nicht.
  function svg(text, dokument) {
    const d = matrix(text);
    const seite = d.groesse + 2 * RUHEZONE;
    const ns = "http://www.w3.org/2000/svg";
    const bild = dokument.createElementNS(ns, "svg");
    bild.setAttribute("viewBox", "0 0 " + seite + " " + seite);
    bild.setAttribute("shape-rendering", "crispEdges");
    const grund = dokument.createElementNS(ns, "rect");
    grund.setAttribute("width", String(seite));
    grund.setAttribute("height", String(seite));
    grund.setAttribute("fill", "#ffffff");
    let pfad = "";
    d.module.forEach((zeile, y) => zeile.forEach((dunkel, x) => {
      if (dunkel) pfad += "M" + (x + RUHEZONE) + "," + (y + RUHEZONE) + "h1v1h-1z";
    }));
    const flaeche = dokument.createElementNS(ns, "path");
    flaeche.setAttribute("d", pfad);
    flaeche.setAttribute("fill", "#000000");
    bild.append(grund, flaeche);
    return bild;
  }

  const QR = {
    matrix,
    svg,
    // Nur fuer die Tests.
    _kapazitaet: kapazitaet,
    _formatBits: formatBits,
    _versionsBits: versionsBits,
    _istAlnum: istAlnum,
    _rsRest: (daten, grad) => rsRest(daten, rsTeiler(grad)),
  };
  if (typeof module !== "undefined" && module.exports) module.exports = QR;
  else umgebung.QR = QR;
})(typeof window !== "undefined" ? window : this);
