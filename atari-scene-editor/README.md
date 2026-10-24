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
- `atari_color` — opcjonalny numer koloru GTIA Atari (liczba 0–255, wprowadzana jako hex lub dec). **Konwersja kolorów działa tylko w jedną stronę:** po wpisaniu/zmianie koloru Atari edytor wylicza odpowiadający mu kolor RGB z palety GTIA (`atari_color_to_rgb`) i wypełnia pola RGB (zaznaczając przy okazji **Enable RGB Color**, aby wyliczona trójka została zapisana razem z wpisem). Edycja pól RGB lub wybór koloru w oknie RGB **nie** zmienia `atari_color` — ten pozostaje wyłącznie autorskim wyborem z palety sprzętowej. Wczytanie istniejącego wpisu także nie nadpisuje zapisanego `rgb_color`.
- `blink` — flaga logiczna (domyślnie `false`) oznaczająca cykliczne migotanie jasności w silniku gry.
- `special` — flaga logiczna **dostępna wyłącznie dla sekretów** (domyślnie `false`). Ustawiana w oknie kartotek (`Ctrl+K` → zakładka **Secrets**) polem **Special (specjalny sekret)**. W pliku JSON zapisywana jest jako `"special": true` tylko dla wpisów, w których jest włączona (brak klucza = `false`), więc istniejące kartoteki pozostają bez zmian. Flaga trafia do ROM-u (tablica `scene_<scena>_secret_special`) i steruje **dźwiękiem zbierania sekretu**: `false` → krótki dwunutowy blip (6 klatek), `true` → wyższy, dłuższy blip trójnutowy (9 klatek). Gdy zbierany sekret jest **ostatnim na scenie**, dźwięk zbierania nie jest odgrywany — gra odtwarza wtedy fanfarę ukończenia poziomu.

### Zasady rozmieszczania obiektów:
- Obiekt może być dodany wyłącznie na platformę (`y = platform.y - height`).
- Obiekt przechowuje jedynie referencję `definition_id` — pełne dane definicji nie są duplikowane w pliku sceny.
- `channel` — kanał PMG, na którym gra rysuje sekret (tylko sekrety, domyślnie `"missiles"`). Ustawiany w oknie kartotek (`Ctrl+K` → zakładka **Secrets**) listą **Sprite channel (PMG)**: `5th player (missiles)` albo `Players 1..3 (player sprite)`. W pliku JSON zapisywany jest tylko gdy różni się od domyślnej wartości (`"channel": "player"`), więc istniejące kartoteki pozostają bez zmian. Kompilator pakuje sprite pod wybrany kanał (`missiles` → cztery pociski składane w sprite 8 px, `player` → zwykła bitmapa gracza) i wpisuje kanał do tablicy `scene_<scena>_secret_channel`, z której silnik (`engine/secrets_channel.asm`) wybiera rejestry `HPOSP1..3`/`COLPM1..3` + `PMG_PLAYER1..3` albo `HPOSM0..M3`/`COLPF3` + `PMG_MISSILES`. Jedna grafika nie może obsłużyć obu kanałów — kompilacja zgłasza wtedy konflikt ról. Kanał `player` daje sekretowi własny kolor z rejestru `COLPM`, więc sekret nie musi już udostępniać koloru z `COLPF3` (piątego gracza).
- **Odblokowywanie kolejnych etapów:** sekret z `dependency` = N pojawia się dopiero po zebraniu **wszystkich** sekretów bieżącego etapu, jeśli wśród zebranych jest choć jeden sekret o definicji N. Etap może więc mieszać definicje (np. klucze + czaszki) — liczy się komplet zebranych, a nie „ostatni” sekret.
- **Pojemność sekretów:** silnik trzyma dane sekretów w tablicach o rozmiarze `MAX_SECRETS` (`engine/secrets.asm`, obecnie 12 na scenę). Kompilator odrzuca scenę z większą liczbą sekretów i w komunikacie podpowiada, co zmienić (`MAX_SECRETS` razem z `MAX_SECRETS_TOTAL` w `scripts/sprite_roles.py`).
- Obowiązuje ścisły budżet kanałów sprite'ów na wiersz platformy **i etap sekretów**: `wrogowie + sekrety tego etapu <= 4` (trzej gracze P1..P3 + piąty gracz). Wrogowie zajmują swoje kanały pierwsi, a sekret na kanale `player` potrzebuje wolnego kanału P1..P3, sekret `missiles` — jedynego kanału piątego gracza (maksymalnie jeden taki sekret na etap w wierszu). Wrogów nadal może być najwyżej 3 w wierszu. Edytor liczy to samo co kompilator (`Scene.get_row_channel_usage()`), więc nie da się zapisać sceny, której build nie przyjmie.
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
  ],
  "background_palette": {
    "upper": [148, 214, 234],
    "lower": [196, 200, 220]
  }
}
```

### Reguły formatu:
- **`schema_version`**: Liczba całkowita identyfikująca wersję (obecnie `1`).
- **`scene`**: Obiekt definiujący metadane sceny (`name`, konfigurowalna rozdzielczość `width` i `height`, domyślnie `160 × 192`).
- **`elements`**: Lista zwykłych elementów kafelków w kolejności rysowania.
- **`platforms`**: Lista platform sprzętowych PMG z pozycją `x`, `y` (`y % 16 == 8`), szerokością i wysokością 4 px.
- **`objects`**: Lista instancji obiektów na scenie wskazujących `definition_id` z kartoteki oraz `platform_id`.
- **`background_palette`** (opcjonalne): Kolory tła sceny dla dwóch stref ekranu. `upper` i `lower` to po 3 kody kolorów Atari (COLPF0..COLPF2, wartości `0..254`, parzyste — GTIA ignoruje bit 0); kolor piksela 0 to zawsze czerń (COLBK). Wartości mogą być liczbami lub łańcuchami hex (`"$94"`, `"0x94"`, `"94"`). Gdy klucz jest nieobecny, kompilator wyprowadza kolory z tilesetów sceny (zachowanie wsteczne).
- **Zapis atomowy:** Wszystkie pliki (sceny oraz kartoteki `enemies.json` i `secrets.json`) zapisywane są atomowo z użyciem plików tymczasowych.

---

## 8. Obsługa edytora

### Główne panele:
1. **Biblioteka grafik (lewy górny róg):**
   - Wyświetla listę plików graficznych z katalogu `tiles/` z miniaturami.
2. **Edytor wycinania (lewy dolny róg):**
   - Umożliwia zaznaczanie kafelków myszą i dodawanie do sceny.
   - **Siatka bajtowa dla wycinka (`source_rect.x` i `source_rect.width`):** ANTIC Mode E pakuje 4 piksele w jeden bajt, a silnik gry czyta bitmapy tilesetów **całymi bajtami** (`src_x_byte = src_x // 4`, `w_bytes = (w + 3) // 4`). Dlatego:
     - **`X`** jest przyciągane **w dół** do wielokrotności 4 (mysz i pole `X:`, krok strzałek = 4) — inaczej gra rysowałaby fragment od piksela `76` przy wycinku `x = 79`.
     - **`W`** jest przyciągane **w górę** do wielokrotności 4 (mysz i pole `W:`, krok strzałek = 4) — gra i tak czyta całe bajty, więc wycinek `77 px` jest rysowany jako `80 px`; zaokrąglenie w górę nie gubi zaznaczonych pikseli i sprawia, że podgląd = obraz w grze.
     - Ograniczeniem pozostaje rozmiar grafiki: jeśli `x + w` przekracza szerokość PNG, przycinanie do granic obrazu ma pierwszeństwo nad siatką (przy szerokościach PNG będących wielokrotnością 4 nie występuje).
   - **Automatyczne wyrównanie przy wczytywaniu i zapisie:** starsze sceny z `x`/`W` spoza siatki są wyrównywane automatycznie (z ostrzeżeniem w logu, z listą poprawionych elementów). Nie zmienia to obrazu w grze (renderer i tak czyta te same bajty), a jedynie sprawia, że podgląd zgadza się z ROM-em.
3. **Płótno sceny (środek):**
   - Obszar sceny z siatką pomocniczą i subtelnymi prowadnicami dozwolonych wierszy platform (`y = 8, 24, 40...`).
   - Przesuwanie elementów i platform myszą lub klawiaturą.
4. **Właściwości i panele (prawy panel):**
   - **Zakładka "Tiles & Elements":** rozdzielczość sceny, właściwości zaznaczonego kafelka, odbicie `flip_x`, warstwy i lista elementów.
   - **Zakładka "Hardware Platforms":** tworzenie nowej platformy (wybór typu sprite/missile, dozwolonej szerokości, wiersza, pozycji X), edycja właściwości zaznaczonej platformy, licznik użycia zasobów w wierszu oraz lista platform.
   - **Zakładka "Objects":** zarządzanie kartotekami (`Ctrl+K`), dodawanie instancji wrogów i sekretów na wybrane platformy, wybór definicji z listy, podgląd właściwości definicji oraz edycja pozycji X. W oknie kartotek zakładka **Secrets** zawiera dodatkowo flagę **Special (specjalny sekret)** — zapisywaną w kartotece i sterującą dźwiękiem zbierania sekretu w grze — oraz listę **Sprite channel (PMG)** wybierającą kanał rysowania sekretu (`5th player (missiles)` lub `Players 1..3 (player sprite)`) — szczegóły w sekcji 6.
   - **Zakładka "Background Colors":** kolory tła sceny dla **górnej** i **dolnej** strefy ekranu (po 3 kolory: `COLPF0`, `COLPF1`, `COLPF2`). Każdy kolor ma pole z kodem Atari (`$00-$FE`, krok 2, wartość nieparzysta jest przycinana do parzystej — GTIA ignoruje bit 0), etykietę hex (`$94`) oraz **próbnik otwierający paletę GTIA** (16 odcieni × 8 luminancji). Kolor piksela 0 to zawsze czerń (COLBK) i nie wymaga definiowania. Zmiany są w pełni cofalne (`Ctrl+Z`). Przycisk *Clear (derive colours from the tilesets)* usuwa zapisaną paletę — kompilator wraca wtedy do wyprowadzania kolorów z tilesetów.

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
