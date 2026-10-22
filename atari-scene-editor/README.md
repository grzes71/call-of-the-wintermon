# Atari 8-Bit Scene Editor (`atari-scene-editor`)

Desktopowa aplikacja graficzna (GUI) napisana w **Pythonie (PySide6)** przeznaczona do projektowania i kompozycji ekranów (scen) platformowych dla komputerów Atari 8-bit o konfigurowalnej rozdzielczości (domyślnie **160 × 192 piksele**).

Edytor pozwala na:
- Wybór dowolnych grafik źródłowych z katalogu `tiles/`, wycinanie z nich prostokątnych fragmentów i swobodne rozmieszczanie ich na jednej scenie z dokładnością do jednego piksela, obsługą nakładania się grafik z wielu plików, odbicia poziomego (`flip_x`), warstw (kolejności rysowania) oraz pełną historią `Undo/Redo`.
- Projektowanie sprzętowych platform Atari (PMG — Player-Missile Graphics) z wykorzystaniem sprite'ów i missile'i o stałej wysokości **4 linii obrazu**, powiększeniu poziomym ×4, ścisłym pozycjonowaniu pionowym w wierszach `y % 16 == 8` oraz sprzętowych limitach (maksymalnie 3 sprite'y i 4 missile'e na wiersz).

---

## 1. Wymagania środowiskowe

- **Python:** 3.11 lub nowszy (testowano na Python 3.11, 3.12, 3.13 oraz 3.14).
- **System operacyjny:** Windows, Linux lub macOS.
- **Sterowniki graficzne / biblioteki:** standardowe wsparcie dla Qt 6 / PySide6.

---

## 2. Instalacja zależności

Zaleca się użycie wirtualnego środowiska (`venv`):

```bash
# Tworzenie wirtualnego środowiska
python -m venv .venv

# Aktywacja (Windows PowerShell)
.venv\Scripts\Activate.ps1

# Aktywacja (Linux/macOS)
source .venv/bin/activate

# Instalacja zależności
pip install -r requirements.txt
```

Plik `requirements.txt` zawiera:
- `PySide6>=6.5.0`
- `pillow>=10.0.0`
- `pytest>=8.0.0`

---

## 3. Sposób uruchomienia

### Bezpośrednio jako polecenie (w aktywnym środowisku venv):
```bash
atari-scene-editor
```

### Przez Pythona z głównego katalogu gry:
```bash
python atari-scene-editor/main.py
```

### Z katalogu modułu `atari-scene-editor/`:
```bash
cd atari-scene-editor
python main.py
```

Jeżeli katalog `tiles/` nie istnieje lub jest pusty, aplikacja uruchamia się bez błędów i wyświetla w panelu biblioteki informację o konieczności umieszczenia plików graficznych (PNG, BMP, GIF, JPEG) w katalogu `tiles/`.

---

## 4. Struktura modułu

```text
atari-scene-editor/
├── main.py                     # Główny punkt wejściowy uruchamiający edytor
├── pyproject.toml              # Konfiguracja pakietu i punkt wejściowy CLI atari-scene-editor
├── README.md                   # Niniejsza dokumentacja techniczna edytora
└── src/
    └── scene_editor/
        ├── __init__.py         # Pakiet edytora
        ├── __main__.py         # Punkt wejściowy dla `python -m scene_editor`
        ├── app.py              # Inicjalizacja QApplication i stylistyki UI
        ├── main_window.py      # Główne okno MainWindow, zakładki, menu, synchronizacja
        ├── scene_view.py       # Płótno widoku sceny (QGraphicsView / QGraphicsScene) z prowadnicami platform
        ├── scene_items.py      # QGraphicsItem elementu kafelka oraz sprzętowej platformy PMG
        ├── tile_browser.py     # Przeglądarka grafik z katalogu tiles/ z miniaturami
        ├── crop_editor.py      # Edytor wycinania fragmentów z interaktywną ramką
        ├── scene_model.py      # Model danych sceny (Scene, SceneElement, PlatformElement, reguły PMG)
        ├── catalogue_model.py  # Model kartotek wrogów i sekretów oraz atomowy zapis enemies.json / secrets.json
        ├── catalogue_dialog.py # Modalny edytor GUI kartotek wrogów i sekretów z walidacją
        ├── asset_manager.py    # Zarządzanie grafikami, cache QPixmap/QImage, wycinanie
        ├── json_serializer.py  # Bezpieczna, atomowa serializacja/deserializacja JSON
        └── commands.py         # Polecenia QUndoCommand (Add, Move, Flip, Reorder, Delete, Platformy, Obiekty)
```

---

## 5. Platformy sprzętowe Atari (PMG)

Edytor umożliwia tworzenie platform opartych na zasobach sprzętowych Atari 8-bit (Player-Missile Graphics):
- **Wysokość:** Stała i wynosi dokładnie **4 linie obrazu**.
- **Szerokości platform Sprite:** `[8, 16, 24, 32, 48, 64, 96]` px.
- **Szerokości platform Missile:** `[8, 32]` px.
- **Obliczanie zużycia zasobów sprzętowych:**
  - Sprite: 24 px wymaga **2 sprite'ów** (16 px podwójny + 8 px normalny, ze względu na brak sprzętowej szerokości 24 px w rejestrach SIZEP procesora GTIA). 8, 16, 32 px: 1 sprite; 48, 64 px: 2 sprite'y; 96 px: 3 sprite'y.
  - Missile: 8 px: **1 missile**, 32 px: **4 missiles** (wszystkie 4 pociski w trybie quad-width).
- **Ograniczenie pionowe:** Początek platformy dozwolony wyłącznie w wierszach `y % 16 == 8` (np. `y = 8, 24, 40, 56, 72, 88, 104, ...`).
- **Limity sprzętowe na wiersz:**
  - Maksymalnie **3 zasoby Sprite** w jednym wierszu platform (suma zasobów sprite'ów <= 3).
  - Maksymalnie **4 zasoby Missile** w jednym wierszu platform (suma zasobów missiles <= 4).
- **Zakaz nakładania się platform:** Żadne dwie platformy (niezależnie od typu: sprite lub missile) nie mogą nachodzić na siebie geometrycznie na scenie. Dozwolone jest wyłącznie bezpośrednie stykanie się krawędziami (bez wspólnych pikseli). Wszystkie operacje dodawania, przesuwania, zmiany rozmiaru i typu podlegają ścisłej walidacji kolizji oraz limitów zasobów.
- **Pozycjonowanie poziome:** Z dokładnością do 1 piksela w granicach sceny (`0 <= x <= scene.width - width`).

---

## 6. Kartoteki wrogów i sekretów oraz obiekty na platformach

Edytor wprowadza podział na **globalne kartoteki definicji typów** na poziomie projektu oraz **instancje obiektów rozmieszczane na scenach**.

### Pliki kartotek:
- `enemies.json` — kartoteka definicji wrogów (przechowywana w katalogu projektu lub `data/`).
- `secrets.json` — kartoteka definicji sekretów (przechowywana w katalogu projektu lub `data/`).

Każda definicja w kartotece zawiera:
- `id` — unikalny identyfikator w obrębie danej kartoteki (np. `orc_warrior`, `golden_key`).
- `name` — czytelna nazwa obiektu.
- `rgb_color` — opcjonalny kolor RGB `[r, g, b]` (0–255) służący do prezentacji obiektu w edytorze.
- `atari_color` — opcjonalny numer koloru GTIA Atari (liczba 0–255, wprowadzana jako hex lub dec; nie jest wyliczana z RGB).
- `blink` — flaga logiczna (domyślnie `false`) oznaczająca cykliczne migotanie jasności w silniku gry.

### Zasady rozmieszczania obiektów:
- Obiekt może być dodany wyłącznie na platformę (`y = platform.y - height`).
- Obiekt przechowuje jedynie referencję `definition_id` — pełne dane definicji nie są duplikowane w pliku sceny.
- Obowiązuje ścisły limit sprzętowy: **maksymalnie 3 obiekty na wiersz** (liczone łącznie dla wrogów i sekretów).
- Wizualizacja w edytorze: czytelny kwadrat 8×8 px z literą typu (`E` dla wroga, `S` dla sekretu) w wybranym kolorze RGB lub neutralnym kolorze zastępczym (karmazynowy dla wrogów, bursztynowy dla sekretów).
- Ochrona integralności: usunięcie definicji, która jest używana przez instancje na scenie, jest blokowane w oknie dialogowym.

---

## 7. Format JSON

Format pliku sceny jest wersjonowany (`schema_version: 1`), czytelny i wstecznie kompatybilny.

### Przykładowy plik sceny:

```json
{
  "schema_version": 1,
  "scene": {
    "name": "castle_ruins",
    "width": 160,
    "height": 192,
    "tile_source": "tiles/castles.png"
  },
  "elements": [
    {
      "id": "element-001",
      "source": "tiles/castles.png",
      "source_rect": {
        "x": 0,
        "y": 0,
        "width": 32,
        "height": 24
      },
      "position": {
        "x": 10,
        "y": 50
      },
      "flip_x": false,
      "z_index": 0
    }
  ],
  "platforms": [
    {
      "id": "platform-001",
      "type": "sprite",
      "position": {
        "x": 24,
        "y": 8
      },
      "width": 16,
      "height": 4
    }
  ],
  "objects": [
    {
      "id": "enemy-001",
      "type": "enemy",
      "definition_id": "orc_warrior",
      "platform_id": "platform-001",
      "x": 24,
      "speed": "medium",
      "movement_strategy": "stationary"
    }
  ]
}
```

### Reguły formatu:
- **`schema_version`**: Liczba całkowita identyfikująca wersję (obecnie `1`).
- **`scene`**: Obiekt definiujący metadane sceny (`name`, konfigurowalna rozdzielczość `width` i `height`, domyślnie `160 × 192`).
- **`elements`**: Lista zwykłych elementów kafelków w kolejności rysowania.
- **`platforms`**: Lista platform sprzętowych PMG z pozycją `x`, `y` (`y % 16 == 8`), szerokością i wysokością 4 px.
- **`objects`**: Lista instancji obiektów na scenie wskazujących `definition_id` z kartoteki oraz `platform_id`.
- **Zapis atomowy:** Wszystkie pliki (sceny oraz kartoteki `enemies.json` i `secrets.json`) zapisywane są atomowo z użyciem plików tymczasowych.

---

## 8. Obsługa edytora

### Główne panele:
1. **Biblioteka grafik (lewy górny róg):**
   - Wyświetla listę plików graficznych z katalogu `tiles/` z miniaturami.
2. **Edytor wycinania (lewy dolny róg):**
   - Umożliwia zaznaczanie kafelków myszą i dodawanie do sceny.
3. **Płótno sceny (środek):**
   - Obszar sceny z siatką pomocniczą i subtelnymi prowadnicami dozwolonych wierszy platform (`y = 8, 24, 40...`).
   - Przesuwanie elementów i platform myszą lub klawiaturą.
4. **Właściwości i panele (prawy panel):**
   - **Zakładka "Tiles & Elements":** rozdzielczość sceny, właściwości zaznaczonego kafelka, odbicie `flip_x`, warstwy i lista elementów.
   - **Zakładka "Hardware Platforms":** tworzenie nowej platformy (wybór typu sprite/missile, dozwolonej szerokości, wiersza, pozycji X), edycja właściwości zaznaczonej platformy, licznik użycia zasobów w wierszu oraz lista platform.
   - **Zakładka "Objects":** zarządzanie kartotekami (`Ctrl+K`), dodawanie instancji wrogów i sekretów na wybrane platformy, wybór definicji z listy, podgląd właściwości definicji oraz edycja pozycji X.

### Skróty klawiszowe:
- `Ctrl+N` — Nowa scena (okno wyboru nazwy i rozdzielczości).
- `Ctrl+O` — Otwórz plik sceny JSON.
- `Ctrl+S` — Zapisz scenę i kartoteki projektu.
- `Ctrl+Shift+S` — Zapisz jako...
- `Ctrl+K` — Otwórz okno zarządzania kartotekami wrogów i sekretów.
- `Ctrl+Z` — Cofnij (Undo).
- `Ctrl+Y` lub `Ctrl+Shift+Z` — Ponów (Redo).
- `Delete` / `Backspace` — Usuń zaznaczony element, platformę lub obiekt.
- `F` lub `H` — Przełącz odbicie poziome zaznaczonego kafelka.
- `Strzałki` — Przesuwanie o 1 piksel (dla platform: strzałki góra/dół skaczą o dozwolony krok 16 linii).
- `Shift + Strzałki` — Przesunięcie o 4 piksele.

---

## 9. Uruchomienie testów

Wszystkie testy jednostkowe i integracyjne uruchamiane są poleceniem:

```bash
pytest
```

W trybie headless (np. na serwerze CI bez środowiska graficznego):
```bash
QT_QPA_PLATFORM=offscreen pytest
```

---

## 8. Ograniczenia pierwszej wersji

- **Brak skalowania elementów:** Skalowanie poszczególnych wycinków nie jest obsługiwane (rozmiar elementu na scenie równa się rozmiarowi wycinka źródłowego 1:1).
- **Format wyjściowy:** Aplikacja skupia się na edycji scen i zapisie do formatu JSON. Na tym etapie nie jest wykonywana bezpośrednia konwersja do pamięci znaków ANTIC ani eksport do binarki XEX.
