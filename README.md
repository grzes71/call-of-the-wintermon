# Call of the Wintermon

Projekt gry platformowej na komputery **Atari 8-bit (XL/XE)** w architekturze 6502 assembly (MADS) zintegrowanej z pipeline'em narzędziowym w Pythonie.

![Atari 8-bit screen](/cover.png)

To miał być rutynowy koncert.

Wommbath dawał popis growlu

na scenie zamku Wintermon.

Jednak jego gardłowy śpiew dotarł

aż do pradawnych głębin pod górami.

Uśpiona od eonów przedwieczna istota

usłyszała jego śpiew i zażądała płyt CD

z najlepszym metalem na świecie.

Teraz Wommbath musi zebrać albumy

i dostarczyć je, zanim skończy się noc!

---

## Narzędzia i komponenty projektu

- **[atari-scene-editor/](atari-scene-editor/README.md)**: Edytor scen i ekranów platformowych w PySide6 o konfigurowalnej rozdzielczości (domyślnie 160 × 192 px) z obsługą wycinania kafelków z wielu grafik źródłowych, orientacji `flip_x`, warstw, projektowania platform sprzętowych Atari (PMG: sprite'y i missile'e z powiększeniem x4 i limitami zasobów na wiersz) oraz eksportu do JSON.
- **[scripts/png_to_charset.py](scripts/png_to_charset.py)**: Konwerter 4-kolorowych indeksowanych grafik PNG na binarny zestaw znaków Atari 8-bit (`.fnt`, 1024 bajty) i mapowanie kafelków JSON.
- **[tiles/](tiles/)**: Źródłowe grafiki kafelków i elementów otoczenia gry.
- **[tests/](tests/)**: Zautomatyzowane testy pytest dla narzędzi pipeline'u.

---

## Uruchomienie narzędzi

### Środowisko Python:
```bash
python -m venv .venv
.venv\Scripts\Activate.ps1  # Windows
pip install -r requirements.txt
```

### Uruchomienie edytora scen:
Bezpośrednio jako polecenie systemowe w aktywnym środowisku venv:
```bash
atari-scene-editor
```
lub przez skrypt Pythona:
```bash
python atari-scene-editor/main.py
```

### Uruchomienie testów:
```bash
pytest
```
