# AUDIT_REPORT — Call of the Wintermon

**Audyt architektury, pamięci i wydajności gry na Atari 8-bit (MOS 6502)**

Zakres: cały projekt (kod 6502 + pipeline Pythona). **Stan wyjściowy audytu: `d97e4d2`**; weryfikacja po wdrożeniu: `9bd1545`.
Tryb: **wyłącznie odczyt** — żaden plik projektu nie został zmieniony poza utworzeniem tego raportu.

### Status wdrożenia (stan na `9bd1545`, po audycie)

Dwa błędy funkcjonalne zgłoszone w tym raporcie zostały naprawione przez autora projektu:

| Commit | Zmiana | Dotyczy |
|---|---|---|
| `163ce06` | `player_init`: odczyt tabel platform **przed** czyszczeniem PMG + sprawdzenie zakresu `SCENE_COUNT`; `sta active_scene_id` | **STAB-006 — naprawione** |
| `163ce06` | `title_init`: `sta active_scene_id` + `jsr status_line_reset`; sprawdzenia zakresu w `game_init`, `secrets_init`, `status_line_init` | **STAB-004 — naprawione** |
| `75073bb` | dodatkowe zabezpieczenie przed przycięciem skoku pionowego o sufit wyższej platformy (poza zakresem tego audytu) | — |
| `9bd1545` | dokumentacja (README/HISTORY); brak zmian w kodzie gry | — |

**Aktualne liczby po wdrożeniu:** XEX 39 206 B, segmenty **39 140 B**, wolne **1 820 B** (wzrost kodu o 9 B względem `d97e4d2`).
**Uwaga:** numery linii w raporcie odnoszą się do stanu `d97e4d2`. Po `163ce06` przesunęły się one w `engine/player.asm`, `engine/secrets.asm`, `engine/status_line.asm` i `scenes/title.asm` (np. pętla czyszczenia `PMG_PLAYER0` jest teraz w `engine/player.asm:155-161`, a `dli_title_restore` w `scenes/title.asm:281`). Wszystkie rekomendacje MEM/CPU/ROM/ARCH pozostają **otwarte** — wdrożono wyłącznie STAB-004 i STAB-006.

---

## 1. Podsumowanie wykonawcze

### 1.1. Ocena ogólna

Projekt jest w dobrym stanie technicznym, znacznie lepszym niż typowy hobbystyczny kod 6502:

* brak stosu w DLI (zapis/odtworzenie rejestrów przez zero page) i jeden wspólny handler DLI dla wszystkich scen — `engine/dli.asm`,
* spójny układ danych SoA (Structure-of-Arrays) w danych scen — `gen/scenes_data.asm`, `gen/scenes_dli_data.asm`,
* jeden font 1 KB współdzielony przez intro, kartę tytułu sceny i pasek statusu (`FONT_ADDR = $2400`),
* prekomputowane tabele (odwracanie bajtu 2bpp, offsety wierszy playfieldu, offsety wierszy tilesetów),
* rozbudowany zestaw testów py65 (m.in. `tests/test_player_movement.py`, `tests/test_dli_system.py`) z gotowym harnessem `load_xex_and_symbols` / `run_subroutine`, który nadaje się do pomiaru cykli,
* deterministyczna kontrola mapy pamięci (`scripts/check_memory.py`) i generowanie mapy (`scripts/generate_memory_map.py`).

**Główny problem nie leży w jakości kodu, lecz w gospodarce pamięcią.** Z 40 960 bajtów przestrzeni `$2000–$BFFF` zajęte jest 39 131 B, a wolne jest **1 829 B** — przy czym jedna bitmapa tilesetów (`DEPTHS` + `HELL`) zajmuje **10 641 B**, mimo że żadna scena jej nie używa. To 27 % całego obrazu i 66 % bloku tilesetów.

Przy okazji audytu znalazłem **błąd funkcjonalny w fizyce** (STAB-006): `player_init` zerował rejestr X pętlą czyszczenia PMG i od tego miejsca indeksował tabele platform **sceną 0**, niezależnie od `active_scene_id`; scena 2 („Be Quick or Be Dead”) używała więc geometrii platform sceny 1. Testy tego nie wychwytywały: `test_player_init_scene1_custom_color` (`tests/test_player_movement.py:71-90`) wywołuje `player_init` z `A = 1`, ale sprawdza tylko pozycję, kolor i zawartość PMG — nie `zp_plat_count`/`zp_plat_ptr_*`. **Błąd został naprawiony w `163ce06`** (odczyt tabel platform przeniesiony przed czyszczenie PMG + kontrola zakresu; dodano też test regresyjny w `tests/test_player_movement.py`).

### 1.2. Najważniejsze liczby (zmierzone, nie szacowane)

| Pozycja | Wartość | Źródło |
|---|---:|---|
| Rozmiar pliku XEX | 39 197 B | `Get-Item call_of_the_wintermon.xex` |
| Suma segmentów w RAM | 39 131 B | `scripts/check_memory.py` |
| Wolne poniżej `$C000` | 1 829 B | `scripts/check_memory.py` |
| Kod 6502 (12 modułów) | 5 892 B | adresy z `gen/main.lab` |
| Bitmapy tilesetów | 16 237 B | `check_memory`, `$8000–$BF6C` |
| Nieużywane bitmapy (`depths`, `hell`) | **10 641 B** | `scenes_data.asm` + JSON scen |
| Martwe tabele w `gen/scenes_data.asm` | **526 B** | brak referencji w kodzie 6502 |
| Bufor PMG niewykorzystany (`$6800–$6AFF`) | **768 B** | `PMBASE=$68`, tylko `+$300..+$7FF` |
| Zerowe bufory w pliku XEX (VRAM gry + PMG) | 5 888 B | `:2048 .byte 0`, `:3840 .byte 0` |

*Wartości w tabeli pochodzą ze stanu `d97e4d2`. Po wdrożeniu poprawek (`9bd1545`): XEX 39 206 B, segmenty 39 140 B, wolne 1 820 B — różnica to wyłącznie kod dodany przez STAB-004/STAB-006.*

### 1.3. Pięć najważniejszych rekomendacji

1. **MEM-001** — usunąć z binarki tilesety `DEPTHS` i `HELL` (10 641 B) do czasu dodania scen, które ich używają. Największa pojedyncza oszczędność w projekcie, znikome ryzyko funkcjonalne.
2. **MEM-003** — usunąć z generatora i z binarki 526 B martwych tabel scen (`scene_obj_*`, `scene_plat_color_sl1..8`, `scene_plat_type`, `scene_plat_h`, `scene_*_elem_*_px`, `scene_*_secret_color`, `scene_*_name`) — żadna nie jest czytana przez kod 6502.
3. **MEM-006** — odzyskać 768 B w bloku PMG (`$6800–$6AFF`), które w trybie single-line nigdy nie są odczytywane przez GTIA; wymaga skrócenia pętli czyszczących PMG do `$6B00–$6FFF`.
4. **MEM-002** — przyciąć tileset `CASTLES` do wykorzystywanego bounding-boxu (168 px zamiast 270 px) — 1 144 B.
5. **MEM-005** — nie emitować do XEX zerowych buforów VRAM gry (3 840 B) i PMG (2 048 B); plik maleje o 5 888 B (15 %), RAM bez zmian.

Po wdrożeniu punktów 1–4 zapas RAM rośnie z **1 829 B do ok. 15 077 B** (37 % okna `$2000–$BFFF`), co pozwala dodać 2–3 kolejne sceny z własnymi tilesetami bez stronicowania pamięci; punkt 5 dodatkowo zmniejsza plik XEX o 5,9 KB.

### 1.4. Największe ograniczenia audytu

* **Brak pomiarów na sprzęcie/emulatorze.** Nie uruchamiałem Altirry ani nie wykonywałem kompilacji (zakaz tworzenia plików w projekcie). Wszystkie liczby cykli są **szacunkami z listingu rozkazów** i są tak oznaczone. Rozmiary bajtowe są **zmierzone** (adresy z `gen/main.lab` + `check_memory.py`).
* **Nie analizowałem `scripts/compile_scenes.py` w całości** (1 700 linii) — tylko sekcje generujące dane scen i DLI. Edytor scen (~480 KB kodu PySide6) leży poza zakresem audytu wydajności gry, bo nie trafia do binarki.
* **Nie weryfikowałem brzmienia muzyki** (`lib/player.asm`) poza analizą rozmiaru i struktury.
* Lokalne, niezacommitowane zmiany w `main.asm` i `scenes/title.asm` mogą przesunąć adresy o kilka bajtów; wszystkie adresy pochodzą z istniejącego `gen/main.lab`.

---

## 2. Charakterystyka projektu

### 2.1. Technologie i narzędzia

| Element | Wartość | Źródło |
|---|---|---|
| Platforma | Atari 800XL / 65XE, 64 KB RAM, PAL | `Makefile:1-3`, `manifest.yaml:11-16` |
| Asembler | MADS 2.1.7 build 21 | nagłówek `gen/main.lab` |
| Składnia | dyrektywy MADS (`.proc`, `.byte`, `dta`, `:N`, `ins`, `icl`, `org`) | pliki `.asm` |
| Toolchain | Python 3.14 + Pillow + numpy + pytest + py65 | `requirements.txt`, `tests/` |
| Edytor | PySide6 (`atari-scene-editor/`, `sprite_studio/`) — poza binarką | `README.md:29-34` |
| Emulator | Altirra 4.40 (`make run`) | `Makefile:9,151-152` |
| Kontrola pamięci | `scripts/check_memory.py`, `scripts/generate_memory_map.py` | `Makefile:140-146` |
| Testy | pytest + emulacja 6502 (py65) | `tests/test_dli_system.py` |

Uwaga: `Makefile` używa **ścieżek bezwzględnych** do MADS i Altirry (`c:/Apps/...`) — build jest przenośny tylko przez nadpisanie `MADS=` / `ALTIRRA=`.

### 2.2. Architektura i moduły

Gra jest **jednym monolitycznym plikiem XEX** ładowanym w całości do `$2000`; nie ma loadera dyskowego ani stronicowania. Podział na moduły istnieje tylko na poziomie źródeł (`icl`), nie na poziomie segmentów pamięci — wszystkie `org` są ustalone ręcznie w `main.asm:12-27`.

| Moduł | Adresy | Rozmiar | Odpowiedzialność |
|---|---|---:|---|
| `main.asm` (dyspozytor) | `$2000–$2068` | 105 B | pętla stanu, inicjalizacja, PORTB, display listy gry i tytułu |
| `scenes/intro.asm` | `$2069–$211A` | 178 B | ekran intro, odczyt klawiatury/fire |
| `scenes/game.asm` | `$211B–$2389` | 623 B | init sceny, 4 fazy karty tytułu, gra, kolizje sekretów, przejście scen |
| `scenes/gameover.asm` | `$6710–$67AD` | 158 B | ekran końcowy (stub) |
| `scenes/title.asm` | `$2D98–$2F68` | 465 B | tytuł, DLI scrolla, ticker tekstu |
| `engine/dli.asm` | `$6382–$6705` (kod) | 900 B | DLI 3-fazowy, staging/swap buforów, hook paska statusu |
| `engine/render.asm` | `$7BC0–$7D80` | 449 B | czyszczenie VRAM, paleta sceny, blitter elementów |
| `engine/secrets.asm` | `$556A–$5768` | 511 B | stan sekretów, animacja, kopiowanie klatek do PMG |
| `engine/player.asm` | `$5769–$5D13` | 1 451 B | fizyka bohatera, skok, spadanie, render PMG |
| `engine/status_line.asm` | `$7F09–$7F8A` | 130 B | HUD: serca, nazwa sceny, licznik CD |
| `lib/player.asm` (muzyka) | `$7000–$738D` | 910 B | 4-kanałowy odtwarzacz POKEY |
| `init_disable_basic` | `$7F8B–$7F95` | 11 B | wyłączenie ROM BASIC przez PORTB |
| **Razem kod** | | **5 892 B** | |

Przepływ sterowania (`main.asm:69-160`):

```
start → PORTB (BASIC off) → game_state=STATE_TITLE, current_state=$FF
main_loop:
   if game_state == current_state → skok do „run” aktywnego stanu
   else current_state = game_state; dispatch init (title/intro/game/over)
   → title_run | intro_run | game_run | gameover_run   (każdy czeka na RTCLOK+2)
```

`game_run` (`scenes/game.asm:92-277`) realizuje 4 fazy: `TITLE_IN` (fade-in nazwy sceny, 8 kroków × 3 klatki), `TITLE_HOLD` (100 klatek), `TITLE_OUT` (24 klatki), `PLAYING`. W fazie `PLAYING`: `dli_vblank_update` → `secrets_update` → `player_update` → `secrets_check_player_collision`.

### 2.3. Zależności między modułami

* `main.asm` włącza pozostałe moduły przez `icl` w ustalonych segmentach; kolejność `org` musi być rosnąca — wymusza to `check_memory.py:111-116`.
* `engine/render.asm` czyta wyłącznie tabele z `gen/scenes_data.asm` (`compile_scenes.py`) i `gen/tiles_data.asm` (`convert_tiles.py`).
* `engine/dli.asm` czyta `gen/scenes_dli_data.asm` (219 B/scenę) i `scene_pmg_patterns_*`.
* `scenes/game.asm` jest jedynym „klejem” logiki: woła renderer, DLI, sekrety, bohatera i pasek statusu. Sprzężenie logika↔wyświetlanie jest silne, ale akceptowalne przy tej skali.
* `engine/secrets.asm` i `engine/player.asm` **niezależnie** operują na tym samym buforze PMG (`$6B00` vs `$6C00`) i na tym samym ZP (`zp_ptr_src`, `zp_ptr_dst`, `zp_temp_a/x/y`) — brak kolizji czasowej, bo wywołania są sekwencyjne, ale to kruche sprzężenie (patrz STAB-001).

### 2.4. Pipeline budowania

`Makefile` → 4 etapy zależne od siebie: `assets` (tytuł PNG→bin, scroll→asm, intro text→bin) → `tiles` → `music` → `data` (sprite'y, sceny, DLI) → `xex` (MADS) → `tests` (pytest) → `check_memory`.

Koszt: `gen/main.lst` ma 342 KB, `gen/main.lab` 31 KB; oba są artefaktami diagnostycznymi i nie trafiają do XEX. Cały build to 9 wywołań Pythona + 1 MADS — **nie ma tu oczywistej nadmiarowości**; jedyne, co warto zmienić, to dodanie do `check_memory.py` kontroli „zarezerwowane, ale nieemitowane” segmentów (patrz MEM-005).


---

## 3. Mapa pamięci

### 3.1. Rzeczywisty rozkład (adresy z `gen/main.lab`, rozmiary z `check_memory.py`)

| Zakres | Rozmiar | Zawartość | Typ |
|---|---:|---|---|
| `$2000–$238A` | 907 B | dyspozytor + intro + logika gry | kod |
| `$238B–$23FF` | (szczelina 117 B) | wolne | — |
| `$2400–$27FF` | 1 024 B | font (CHBASE) — intro, HUD, karta sceny | dane |
| `$2800–$298F` | 400 B | VRAM tekstu intro (40×10, Mode 2) | bufor |
| `$2A00–$2A1D` | 30 B | display list intro | dane |
| `$2A30–$2C1D` | 494 B | metadane tilesetów + tabele offsetów wierszy | dane |
| `$2C1E–$2D97` | 378 B | klatki animacji bohatera (PMG 1bpp) | dane |
| `$2D98–$2F68` | 465 B | kod ekranu tytułowego + DLI scrolla + tekst | kod/dane |
| `$3000–$3EFF` | 3 840 B | VRAM gry (Mode D, 40 B × 96 linii) | bufor |
| `$3F00–$3F6C` | 109 B | display list gry | dane |
| `$3F6D–$3F79` | 13 B | display list karty tytułu sceny | dane |
| `$3F8B–$3FB2` | 40 B | VRAM paska statusu (Mode 2) | bufor |
| `$4000–$4BFF` | 3 072 B | bitmapa ekranu tytułowego (Mode D narrow) | dane+bufor |
| `$4C00–$4C2F` | 48 B | bufor scrolla (Mode 2, HSCROL) | bufor |
| `$4C30–$4CC6` | 151 B | tekst marquee (screen codes) | dane |
| `$4CC7–$4FFF` | (szczelina **825 B**) | wolne — największy dostępny blok | — |
| `$5000–$5387` | 904 B | dane scen (SoA) + 42 pary wskaźników | dane |
| `$5388–$5561` | 478 B | dane DLI scen (2 × 219 B + 2 × 18 B + wskaźniki) | dane |
| `$556A–$5768` | 511 B | kod + stan sekretów | kod+RAM |
| `$5769–$5D13` | 1 451 B | kod bohatera + tabele trajektorii | kod |
| `$5D14–$5FFC` | 745 B | dane muzyki intro | dane |
| `$6000–$606F` | 112 B | display list tytułu | dane |
| `$6100–$6381` | 642 B | podwójne bufory DLI (34 tabele × 16 B + wskaźniki) | bufor |
| `$6382–$6705` | 900 B | kod DLI (6 procedur) | kod |
| `$6710–$67AD` | 158 B | ekran końcowy | kod |
| `$6800–$6AFF` | **768 B** | **nieużywane** (PMG single-line startuje od `+$300`) | — |
| `$6B00–$6BFF` | 256 B | PMG missiles (5. gracz = sekrety) | bufor |
| `$6C00–$6FFF` | 1 024 B | PMG Player 1–3 (platformy) + Player 0 (bohater) | bufor |
| `$7000–$738D` | 910 B | odtwarzacz muzyki | kod |
| `$738E–$79D9` | 1 612 B | dane muzyki tytułu | dane |
| `$7A00–$7AFF` | 256 B | tabela odwracania bajtu 2bpp | dane |
| `$7B00–$7BBF` | 192 B | offsety wierszy playfieldu (96 × lo/hi) | dane |
| `$7BC0–$7D80` | 449 B | renderer | kod |
| `$7D81–$7F08` | 392 B | klatki sprite'ów obiektów | dane |
| `$7F09–$7F8A` | 130 B | pasek statusu | kod |
| `$7F8B–$7F95` | 11 B | `init_disable_basic` | kod |
| `$8000–$BF6C` | 16 237 B | bitmapy 4 tilesetów | dane |
| `$BF6D–$BFFF` | (147 B) | wolne do końca RAM | — |

Suma segmentów: **39 131 B**; wolne: **1 829 B** (z tego 825 B w jednej szczelinie `$4CC7–$4FFF` oraz 768 B niewidocznych dla `check_memory.py` w bloku PMG).

### 3.2. Rezerwacje pozaokienkowe (nieujęte w `check_memory.py`)

| Obszar | Uwaga |
|---|---|
| `$0000–$007F` | zero page OS — niedostępna |
| `$0080–$00DB` | zero page aplikacji (`zeropage.asm`), **92 B**, brak wolnych |
| `$0100–$01FF` | stos sprzętowy — używany oszczędnie (maks. 4–6 bajtów na raz) |
| `$0200–$06FF` | OS: VDSLST, cienie, bufor klawiatury; aplikacja korzysta z `$2E0` (RUNAD) i `$2E2` (INITAD) |
| `$0700–$1FFF` | DOS + wolne poniżej `MEMLO`; **niewykorzystane przez grę** — patrz 3.3 |
| `$C000–$CFFF`, `$D000–$DFFF`, `$E000–$FFFF` | OS ROM / rejestry / OS ROM (BASIC wyłączony bitem 1 PORTB) |

### 3.3. Obszar `$0800–$1FFF` — potencjalnie 6 KB, praktycznie niedostępne

Gra startuje na `$2000`, więc `$0800–$1FFF` (6 KB) leży poniżej pierwszego segmentu. To **nie jest** wolna pamięć w sensie użytkowym: przy uruchomieniu z DOS obszar ten zajmuje DOS (typowo `MEMLO ≈ $1C00–$2000`), a gra nie przenosi się nad niego ani go nie nadpisuje. Wykorzystanie go wymagałoby albo zrezygnowania z DOS (boot loader — jak w `main.asm:401-409` użyty tylko do `PORTB`), albo ładowania XEX-a spod innego loadera. **Rekomendacja: nie liczyć na ten obszar bez zmiany modelu ładowania.** To potencjalnie największa rezerwa w całym projekcie (6 KB), ale poza obecnym modelem pamięci.


---

## 4. Szczegółowy audyt pamięci

### 4.1. Model pamięci — tabela zbiorcza

Obszary nie nakładają się na siebie; „Bitmapa tytułu” jest jednocześnie danymi i buforem ekranu (ta sama pamięć).

| Obszar | Obecny rozmiar | Możliwa oszczędność | Pewność oszacowania |
|---|---:|---:|---|
| Kod programu (12 modułów) | 5 892 B | ~250–400 B | wysoka (rozmiary), średnia (efekt refaktorów) |
| Bitmapy tilesetów (4 szt.) | 16 237 B | **11 785 B** (10 641 + 1 144) | wysoka |
| Bufor VRAM gry | 3 840 B | 0 B RAM / −3 840 B pliku XEX | wysoka |
| Bitmapa ekranu tytułowego | 3 072 B | 0 B (patrz 4.2, wariant odrzucony) | wysoka |
| PMG (2 KB) | 2 048 B | **768 B** (obszar `+$000..+$2FF`) | wysoka |
| Bufory DLI (34 tabele × 2) | 642 B | 18 B (martwe) / 136 B (odrzucone) | wysoka |
| Dane scen + dane DLI | 1 382 B | **526 B** | wysoka |
| Muzyka (kod + 2 moduły) | 3 267 B | 0–745 B | niska |
| Sprite'y (bohater + obiekty) | 770 B | **112 B** | wysoka |
| Font + teksty (intro, scroll) | 1 575 B | 0 B | wysoka |
| Tabele renderowania (flip + wiersze) | 448 B | 0 B | wysoka |
| Metadane tilesetów + tabele wierszy | 494 B | 20 B | wysoka |
| Display listy + pasek statusu | 304 B | 0 B | wysoka |
| Zero page aplikacji | 92 B | 1 B (nieużywane) | wysoka |

**Uwaga metodologiczna:** sumowanie wierszy daje 39 109 B, czyli o 22 B mniej niż 39 131 B z `check_memory.py` — różnica to 4 B wektorów `RUNAD/INITAD` i zaokrąglenia granic (`$238A` vs `$238B`).

### 4.2. RAM — co jest marnowane i dlaczego

**(a) Nieużywane tilesety — 10 641 B (MEM-001).**
`gen/scenes_data.asm` zawiera wyłącznie `TILESET_TREES` i `TILESET_CASTLES`:

```
scene_sc_01_forest_elem_tileset         .byte TILESET_TREES  × 5
scene_sc_02_forest_castle_elem_tileset  .byte TILESET_CASTLES, TILESET_CASTLES, TILESET_TREES, TILESET_TREES
```

`TILESET_DEPTHS` i `TILESET_HELL` **nie występują w żadnym pliku `.asm`** (weryfikacja: `Select-String` po `main.asm`, `engine/*.asm`, `scenes/*.asm`, `lib/*.asm` → 0 trafień), a mimo to `main.asm:420-428` wstawia ich bitmapy (`ins 'gen/tiles_depths.bin'` i `gen/tiles_hell.bin'`) do `$A500–$BF6C`. To 10 641 B martwego balastu w RAM.

**(b) Przycięcie `CASTLES` — 1 144 B (MEM-002).**
`convert_tiles.py:278-313` konwertuje **cały PNG** (`w_bytes = (w + 3) // 4`), bez analizy wykorzystania. Faktyczny bounding-box elementów obu scen:

| Tileset | Wymiary PNG | Wykorzystany bbox | Stride oryg. | Stride potrzebny | Rozmiar teraz | Rozmiar po cropie | Oszczędność |
|---|---|---:|---:|---:|---:|---:|---:|
| `castles` | 270×44 | 0,0–168,44 | 68 B | 42 B | 2 992 B | 1 848 B | **1 144 B** |
| `trees` | 246×42 | 0,0–246,42 | 62 B | 62 B | 2 604 B | 2 604 B | 0 B |
| `depths` | 360×72 | brak użycia | 90 B | — | 6 480 B | 0 B | 6 480 B |
| `hell` | 291×57 | brak użycia | 73 B | — | 4 161 B | 0 B | 4 161 B |

**`trees` jest już w 100 % wykorzystany — nie ma czego przycinać.** To ważne, by nie „optymalizować” go na siłę.

**(c) Martwe tabele wygenerowane dla scen — 526 B (MEM-003).**
`compile_scenes.py` generuje 42 pary tabel wskaźników i 42 tabele danych na scenę; kod 6502 czyta tylko 17 z nich (`render.asm`: 8 tabel elementów, `dli.asm`: `scene_dli_data`, `scene_pmg_patterns`, `status_line.asm`: `scene_name_line`, `player.asm`: `scene_player_*`, `secrets.asm`: 9 tabel sekretów, `game.asm`: `scene_plat_x/y/w`).

| Martwa tabela (na scenę) | Bajty danych | Bajty wskaźników | Uwaga |
|---|---:|---:|---|
| `scene_*_name` (ASCII + `scene_name_lo/hi`) | 55 | 4 | nazwa używana tylko jako `name_line` |
| `scene_*_elem_src_x_px`, `_w_px`, `_dst_x_px` | 27 | 0 | wersje „px” nieużywane (renderer używa `_byte`) |
| `scene_*_plat_type` | 25 | 4 | brak silnika wrogów |
| `scene_*_plat_h` | 25 | 4 | zawsze 4, kod nie czyta |
| `scene_*_plat_color_sl1..sl8` | 200 | 32 | DLI czyta gotowe `scenes_dli_data.asm` |
| `scene_*_obj_*` (10 tabel) | 100 | 40 | **brak jakiegokolwiek runtime wrogów** |
| `scene_*_secret_color` | 6 | 4 | kolor pochodzi z DLI (`COLPF3`) |
| **Razem** | **438** | **88** | **526 B** |

Konsekwencja praktyczna: `scene_obj_*` (140 B) to dane wrogów, których **nie ma w kodzie** — 6 wrogów w scenie 1 i 1 w scenie 2 istnieje tylko w JSON-ach i w tabelach. Warto to rozstrzygnąć przed dalszym rozwojem: albo silnik wrogów powstanie i tabele zostaną, albo dane należy usunąć.

**(d) Obszar `$6800–$6AFF` wewnątrz bloku PMG — 768 B (MEM-006).**
`PMBASE=$68` (`game.asm:25-26`), gracze pod `+$400..+$7FF`, pociski pod `+$300`. W trybie single-line (`DMACTL=$3E`, bit 4 = 0) ANTIC/GTIA **nie adresuje** `$6800–$6AFF`. Mimo to trzy pętle czyszczące zapisują tam zera:
`scenes/title.asm:46-58`, `scenes/gameover.asm:33-45`, `engine/dli.asm:120-133` (po 8 × `sta` na iterację, 2 KB).

To 768 B, które można przeznaczyć na dowolne dane CPU (najlepiej: bufory DLI z `$6100` lub tabelę tekstów) — pod warunkiem skrócenia pętli czyszczących do `$6B00–$6FFF` (1 280 B).

**(e) Podwójne bufory DLI — 136 B nieużywanych (rezygnacja).**
Każda z 34 tabel to `:16 .byte 0` = dwa bufory po 8 wpisów, ale DLI obsługuje **6 pasów** (`dli.asm:614` — `cmp #6`). Dwa wpisy na bufor (34 × 2 × 2 = 136 B) nigdy nie są zapisywane ani czytane. Zmiana stride 8→6 wymaga zastąpienia `and #$07 / cmp #6` arytmetyką modulo 6 w handlerze DLI — czyli **dodania cykli w najbardziej krytycznym miejscu**. **Nie rekomenduję**: 136 B nie jest warte ryzyka w timingu.

**(f) Duplikat `dli_z0_colpf0/1/2` — 6 B (MEM-007).**
`dli_z0_colpf*` (2 bufory × 3 rejestry) przechowują dokładnie tę samą wartość co pierwszy wpis `dli_bg_colpf0/1/2` (np. dla sceny 0: `$C4, $C8, $DC` w obu miejscach). Można je wyliczyć, nie przechowywać.

**(g) Zero page — 92 B, jedna zmienna martwa.**
`zp_frame_cnt = $87` (`zeropage.asm:18`) nie występuje w żadnym kodzie (1 trafienie = definicja). Reszta ZP jest wykorzystana; **brak wolnego miejsca w ZP** to istotne ograniczenie przy dalszym rozwoju (np. nowy wskaźnik = 2 B, których nie ma).


### 4.3. ROM / rozmiar kodu

Kod (5 892 B) nie jest problemem sam w sobie, ale zawiera mierzalne duplikaty:

| Powielenie | Lokalizacje | Koszt | Uwaga |
|---|---:|---:|---|
| Pętla czyszczenia 2 KB PMG (8 × `sta` + `inx/bne`) | `title.asm:46-58`, `gameover.asm:33-45`, `dli.asm:120-133` | ~3 × 17 B = 51 B | wspólna procedura = ~17 B → zysk ~34 B |
| Czyszczenie 256 B `PMG_PLAYER0` | `player.asm:135-141`, `player.asm:1102-1108` | ~2 × 10 B | duplikat tej samej pętli (uwaga: ta pętla jest też źródłem STAB-006) |
| Debounce fire + odczyt `CH` | `intro.asm:83-118`, `gameover.asm:68-100`, `title.asm:154-195`, `game.asm:174-197` | ~4 × 25 B = 100 B | identyczna struktura, różni się akcją |
| Oczekiwanie na VBLANK (`RTCLOK+2`) | `game.asm:97-101`, `intro.asm:74-78`, `title.asm:136-140`, `gameover.asm:62-66` | ~4 × 8 B = 32 B | `jsr` + 6 B ciała |
| `sta SDMCTL` + `sta DMACTL` | `game.asm:134-136,166-168,212-214,250-252,267-269`, `title.asm:117-119,128-130`, `intro.asm:66-68` | 8 × 6 B = 48 B | patrz 4.3.1 |
| Wypisanie `HPOSP0 = player_x + PLAYER_HPOS_OFFSET` | `engine/player.asm` (4 miejsca) | ~4 × 12 B | kandydat na `player_sync_hpos` |
| Pętla „znajdź platformę pod stopami” | `player.asm:84-214` (start), `854+` (sufit), `725-1010` (lądowanie po skoku), `1039-1070` (spadanie) | **4 kopie, ~150–200 B** | największy duplikat logiki |
| Rozgałęzienia `jump_up`/`jump_short`/`jump_long` | `player.asm:725-790` | ~60 B | wybór tabel mógłby być wskaźnikiem |

Pozycje martwe: `dli_title_restore` (`title.asm:277-279`) — procedura `rti` bez referencji (0 wywołań); dyspozytor w `main.asm` ma dwie rozpisane 4-drogowe drabiny (`init` i `run`).

#### 4.3.1. Podwójny zapis `SDMCTL`/`DMACTL` — czy to błąd?

Nie błąd, lecz **redundancja**: `NMIEN=$C0` zostawia włączony VBI systemowy, a OS w VBI kopiuje `SDMCTL → DMACTL` (oraz `SDLSTL → DLISTL` i cienie kolorów). Wystarczyłby zapis do cienia. Zapis bezpośredni do `DMACTL` **wewnątrz DLI** jest konieczny i tam został użyty poprawnie (`title.asm:264-265`). Zysk z usunięcia to ~8 cykli/klatkę — **nie warto** go wdrażać „dla cykli”; wartość jest w uproszczeniu.

### 4.4. Grafika i animacje

| Zasób | Rozmiar | Ocena |
|---|---:|---|
| `title.bin` (Mode D narrow 128×96) | 3 072 B | OK — realna bitmapa, nie bufor zerowy |
| `tiles_*.bin` | 16 237 B | 10 641 B martwe, 1 144 B do przycięcia |
| Klatki bohatera (17 × 20 B) | 340 B + 34 B wskaźników | 160 B to lustrzane kopie `left`/`right` |
| Klatki sprite'ów obiektów | 392 B | **112 B duplikatów bajt-w-bajt** |
| `flip_byte_2bpp` | 256 B | używana tylko przy `flip_x` (5 elementów) — uzasadniona |
| Tabele wierszy playfieldu | 192 B | 96 wierszy × lo/hi — uzasadnione |

**Duplikaty klatek sprite'ów (MEM-004)** — zweryfikowane porównaniem bajtów w `gen/sprites_data.asm`:

| Sprite | Klatki identyczne | Oszczędność |
|---|---|---:|
| ID 1 (CD, 6 klatek) | `frame_4`=`frame_2`, `frame_5`=`frame_1` | 32 B |
| ID 3 (Key, 12 klatek) | `frame_7`=`frame_5`, `frame_8`=`frame_4`, `frame_9`=`frame_3`, `frame_10`=`frame_2`, `frame_11`=`frame_1` | 80 B |
| **Razem** | | **112 B** |

Wystarczy, by `compile_sprites.py:225-230` emitował etykietę tylko dla unikalnych ramek, a tablicę `sprite_N_frames` wypełniał powtórzonymi adresami — bez zmian w kodzie 6502.

**Lustrzane klatki bohatera — świadomie NIE rekomenduję.** 160 B (`right`/`left` × 8 klatek × 20 B) dałoby się wygenerować z prawej strony, ale odwrócenie bitu w 1bpp wymaga tabeli 256 B (`flip_byte_2bpp` odwraca grupy 2-bitowe, nie bity), odwracanie „w locie” to ~8 iteracji × 20 linii na klatkę (800+ cykli/klatkę — niedopuszczalne), a prekomputacja do RAM kosztuje dokładnie 160 B. **Zysk zerowy.**

**Kompresja — zmierzona i odrzucona.** Bajtowy RLE na istniejących binarkach (pomiar na plikach, bez zapisu):

| Plik | Rozmiar | RLE | Współczynnik |
|---|---:|---:|---:|
| `title.bin` | 3 072 | 3 223 | **0,95× (gorzej)** |
| `tiles_castles.bin` | 2 992 | 2 688 | 1,11× |
| `tiles_trees.bin` | 2 604 | 2 126 | 1,22× |
| `tiles_depths.bin` | 6 480 | 5 879 | 1,10× |
| `tiles_hell.bin` | 4 161 | 3 827 | 1,09× |
| `intro_text.bin` | 400 | 380 | 1,05× |

Grafiki są z ditheringiem, więc RLE daje 9–22 %, a dla bitmapy tytułu jest **ujemny**. **Nie rekomenduję kompresji** — dekompresor ~150 B + czas ładowania nie zwracają się.


### 4.5. Dane poziomów i obiektów

* Rekord sceny jest „spłaszczony” do SoA — to dobre rozwiązanie dla 6502 (indeks `,x`/`,y` bez mnożenia).
* Współrzędne są 1-bajtowe (0–159 px, 0–95 linii) — poprawnie dobrane; brak nadmiarowych 16-bitów.
* `scene_*_elem_w_byte` i `_h_lines` to jedyne potrzebne wymiary (wersje `_px` martwe).
* **Nadmiarowość semantyczna:** `scene_*_secret_height`, `_frame_dur`, `_frame_count` dublują tabele `sprite_height`, `sprite_frame_dur`, `sprite_frame_count` (`gen/sprites_data.asm`, 12 B), których `secrets.asm` **nie czyta** (0 referencji) — czyta wersje scenowe. Trzy tabele globalne są martwe.
* Format DLI: 219 B/scenę = 34 tabele × 6 pasów + 15 B strefy 0. Format jest gęsty; oszczędność ≤ 30 B (MEM-007) — **nie warto przebudowywać**.
* **Koszt skalowania:** każda nowa scena dodaje 2 B × 42 pary wskaźników = **84 B samego narzutu**. Przy 6 scenach to 504 B. Powyżej 3 scen warto zastąpić 42 pary wskaźników jednym wskaźnikiem bazowym na scenę + stałą tabelą offsetów (~80 B/scenę, koszt ~40 B kodu) — patrz DATA-001.

### 4.6. Bufory i pozostałe zasoby

* **Bufory ekranu nie są współdzielone:** VRAM gry (3 840 B) i bitmapa tytułu (3 072 B) istnieją jednocześnie. Wariant „nałóż tytuł na VRAM gry i odtwarzaj z kopii” **nie daje oszczędności**, bo gra wraca do tytułu po `STATE_OVER` (`gameover.asm:96-100`) — bitmapa musi przetrwać całą rozgrywkę. Oszczędność dałoby tylko ponowne wczytanie z nośnika, a gra nie ma loadera. **Odrzucone świadomie.**
* **Muzyka:** dwa moduły (1 612 B + 745 B) są rezydentne równocześnie, choć nigdy nie grają naraz. Bez loadera dyskowego **nie ma jak odzyskać tych bajtów**. Kod odtwarzacza (910 B) jest adekwatny do 4 kanałów z envelope — przepisywanie na RMT dałoby 100–200 B przy ryzyku regresji brzmienia.
* **Bufory DLI (642 B)** to najdroższy bufor po VRAM, ale w pełni uzasadniony: 408 realnie używanych bajtów + 136 nieużywanych + 68 B wskaźników + 30 B strefy 0.


---

## 5. Audyt wydajności procesora

Poniższe liczby cykli są **szacunkami** z listingu rozkazów (PAL ~114 cykli/linia, 19 656 cykli/klatkę). Nie były mierzone na emulatorze — patrz sekcja 10.

### 5.1. Pętla główna — budżet klatki

| Etap (faza `PLAYING`) | Szacowane cykle | % klatki PAL |
|---|---:|---:|
| synchronizacja `RTCLOK+2` (busy-wait) | ~10–20 | <1 % |
| `dli_vblank_update` | ~450–550 | ~2,5 % |
| `secrets_update` (bez zmiany klatki) | ~150–250 | ~1 % |
| `secrets_update` (ze zmianą klatki: 1–3 × `render_secret_frame`) | +350–1 100 | do 6 % |
| `player_update` (idle/walk, bez zmiany PMG) | ~250–350 | ~1,5 % |
| `player_render_frame` | **~700–1 400** | **3,5–7 %** |
| `secrets_check_player_collision` (bez kolizji sprzętowej) | ~40 | <1 % |
| DLI 7 × ~350 cykli (poza pętlą, w tle) | ~2 450 | 12,5 % |
| OS VBI | ~1 000+ | 5 % |

**Wniosek:** pętla gry jest lekka; dominują DLI (konieczne) i `player_render_frame`. Nie ma wąskiego gardła grożącego zgubionymi klatkami.

### 5.2. `player_render_frame` — najdroższa procedura gry (`engine/player.asm:222-313`)

Procedura wykonuje **dwie** pętle po 20 iteracji:

1. czyszczenie poprzednich linii (`player.asm:224-240`) — na linię `tya/clc/adc/cmp/bcs/tax/lda/sta/dey/bpl` ≈ 27–31 cykli → **~600 cykli**,
2. rysowanie nowej klatki (`player.asm:297-310`) — analogicznie **~600 cykli**.

Kluczowe: `player_pmg_y` zmienia się **wyłącznie** przy skoku/spadaniu (`player_jump_update`, `player_fall_update`). Podczas chodzenia i stania `player_prev_pmg_y == player_pmg_y`, więc czyszczenie jest **w całości nadpisywane** w tym samym wywołaniu.

**CPU-001:** porównanie `player_pmg_y` z `player_prev_pmg_y` przed pętlą czyszczenia — ~600 cykli/klatkę (3 % klatki) w ~90 % klatek, koszt +6 B kodu.

Druga obserwacja: obie pętle liczą `tya/clc/adc/cmp #224/bcs` **na każdą linię**, by obsłużyć `player_pmg_y ≥ 224`. Wystarczy policzyć `count = min(20, 224 − player_pmg_y)` **raz** i użyć `lda (zp_ptr_src),y / sta (zp_ptr_dst),y` z `zp_ptr_dst = PMG_PLAYER0 + player_pmg_y` — ~17–18 cykli/linia zamiast ~30.

**CPU-002:** ~250 cykli/klatkę i eliminacja 40 rozgałęzień; kod ~−10 B. Ryzyko: clipping przeniesiony do obliczeń wstępnych (pokryte przez `tests/test_player_movement.py`).

### 5.3. `dli_vblank_update` (`engine/dli.asm:342-441`)

~450–550 cykli/klatkę: ~40 zapisów, w tym **przepisywanie `VDSLST` co klatkę** (`dli.asm:397-402`), choć `dli_status_line` i tak przywraca `VDSLST` do `dli_handler` (`dli.asm:661-664`) — 12 cykli/klatkę, pomijalne, ale zbędne.

Strefa 0 jest kopiowana i odczytywana **rozunrolledowanymi** `lda (zp_ptr_src),y / sta dli_z0_*,x` — 15 razy w `dli_stage_scene` (`dli.asm:283-327`, ~90 B kodu) i podobnie w `dli_vblank_update`. Zmiana layoutu strefy 0 z przeplotu (`:2`) na dwa bloki po 15 B pozwoliłaby na zwykłą pętlę (~15 B kodu) — **ROM-003**, ~75 B oszczędności, koszt ~30 cykli przy zmianie sceny (poza pętlą klatki).

### 5.4. `dli_handler` (`engine/dli.asm:444-628`)

Najlepiej napisany fragment projektu: zero stosu, zero wskaźników pośrednich w ZP, `abs,Y` z przesunięciem `dli_pas_idx`, 3 fazy z jawnym budżetem cykli i komentarzami `[n]` przy instrukcjach. Faza B (~40 cykli/linia) mieści się w linii z dużym zapasem. **Nie zgłaszam tu optymalizacji** — każda zmiana groziłaby rozjechaniem timingu przy kosmetycznym zysku.

Niewykorzystane: `dli_zone_prior` (tabela 34.) jest zapisywana do bufora, ale **handler nigdy jej nie czyta** — `PRIOR` ustawiany jest raz na klatkę na stałe `#$11` (`dli.asm:414`). To martwa tabela (MEM-007) i nieużywany mechanizm.

### 5.5. `secrets_update` / `render_secret_frame` (`engine/secrets.asm:307-352`)

* Pętla sprawdza wszystkie sekrety (`MAX_SECRETS = 6`) co klatkę — ~20 cykli na nieaktywny sekret, pomijalne.
* `render_secret_frame` wołane tylko przy zmianie klatki animacji (co 4–5 klatek), kopiuje 14–16 bajtów przez `(zp),y` — efektywnie.
* `txa/pha/jsr/pla/tax` wokół wywołań (`secrets.asm:288-292, 340-344`) to ~28 cykli i 4 B kodu — zbędne, bo `render_secret_frame` zachowuje X (nie zawiera `tax`). Drobiazg, nieszkodliwy.
* `clear_secret_rows` (`secrets.asm:86-103`) ładuje `#>PMG_MISSILES` przy każdym wywołaniu — 2 cykle, pomijalne.

### 5.6. Kosztowne operacje arytmetyczne

* `status_line_refresh_cds` (`status_line.asm:96-119`) dzieli przez 10 przez powtarzane odejmowanie (do 9 iteracji × ~10 cykli). Wywoływane tylko przy zebraniu CD, nie w pętli klatki → **nie warto** tablicować.
* `render_scene_background` kopiuje ~4 400 bajtów w pętli `(zp),y` (~11 cykli/bajt) ≈ 50 000 cykli ≈ 2,5 klatki, plus `clear_game_vram` ~20 700 cykli ≈ 1 klatka. Raz na scenę — akceptowalne. W tym czasie DMA jest wyłączone (`game.asm:19-22`), więc obraz jest czarny ~3,5 klatki; świadomy kompromis.
* `dli_apply_pmg_patterns` (`dli.asm:161-214`) wykonuje 48 iteracji z 4 `sta` — ~1 400 cykli, raz na scenę. OK.


---

## 6. Audyt grafiki i sprzętu Atari

### 6.1. Tryby ANTIC i display listy

| Ekran | Tryb | Rozdzielczość | Pamięć obrazu | DL |
|---|---|---|---:|---|
| Tytuł | D (narrow `$21`) + 1 linia Mode 2 | 128×96 + 40 znaków | 3 072 B + 48 B scroll | 112 B (`main.asm:320-351`) |
| Intro | 10 × Mode 2 z `DL_BLANK8` | 40×10 | 400 B | 30 B (`main.asm`, `$2A00`) |
| Karta tytułu sceny | 1 × Mode 2 wyśrodkowana | 40×1 | 40 B | 13 B (`main.asm:261-273`) |
| Gra | D + 1 × Mode 2 (HUD) | 160×96 + 40 znaków | 3 840 B + 40 B | 109 B (`main.asm:222-252`) |

* `dlist_game` ma **dokładnie 240 linii rastra** (24 górne blank + 192 Mode D + 8 blank + 8 Mode 2 + 8 dolne) — poprawnie dopasowane do PAL. Brak zapasu na NTSC (240 linii to tam granica) — **uwaga na kompatybilność**, jeśli projekt miałby działać na NTSC.
* DLI hooki są rozmieszczone co 16 linii Mode D (`main.asm:231-241`), z hookiem 7. na `DL_BLANK8` przed paskiem statusu (`main.asm:245`). Każdy z 6 pasów ustawia 8-scanline'owy gradient kolorów platformy (6 × 8 = 48 linii z 192); pozostałe linie zachowują ostatnio ustawione kolory `COLPF`/`COLPM`, co jest zgodne z projektem (gradient tylko na krawędzi platformy).
* Display listy mieszczą się w 1 KB bez przekraczania granicy — zweryfikowane przez `check_memory.py`.

### 6.2. Player/Missile Graphics

| Element | Adres | Przeznaczenie | Ocena |
|---|---|---|---|
| Missiles (5. gracz) | `$6B00` | sekrety (CD/klucz/drabina) | 8 px szer. × 4 pociski, `SIZEM=0` |
| Player 0 | `$6C00` | bohater | 8×20, `SIZEP0=0` |
| Player 1–3 | `$6D00–$6F00` | platformy (DMI) | wzorce 8 px × 8 linii, `SIZEPn=3` (×4) |

* Rozdzielczość **single-line** (`DMACTL=$3E`, bit 4 = 0) — poprawnie, bo bohater porusza się co 1 linię rastra.
* `$6800–$6AFF` (768 B) nie jest adresowane przez GTIA → **MEM-006**.
* Platformy są rysowane jako 8 linii `$FF` w każdym z 6 pasów, na offsets `base+48..55` (`dli_apply_pmg_patterns`, `dli.asm:161-214`) — sprytne: 3 graczy × 6 pasów = 18 platform bez ruchu w czasie gry. Koszt: brak możliwości animacji platform.
* Kolor platform pochodzi z DLI (`COLPM1..3` per pas i per linia), a nie z `COLPM` ustawianego raz — to konieczne dla gradientu 8-liniowego.
* **Ograniczenie:** tylko 4 gracze + 4 pociski. Bohater (P0) jest wyłączony z DLI (`engine/dli.asm` — komentarz „Player 0 never touched”), więc `HPOSP0`/`COLPM0`/`SIZEP0` są własnością `engine/player.asm`. To dobra decyzja projektowa.

### 6.3. DLI — koszt i architektura

* Jeden handler dla wszystkich scen (`dli_handler`), 6 wywołań na klatkę + 1 dla paska statusu.
* Faza A (~40 cykli, przed `WSYNC`), Faza B (8 × ~40 cykli), Faza C (~150 cykli na linii ochronnej) — komentarze cykli w źródle są zgodne z rzeczywistością.
* Zero użycia stosu — `dli_save_a/x/y` w ZP (`zeropage.asm:56-58`). To eliminuje ryzyko przepełnienia stosu w przerwaniu.
* **Podwójne buforowanie** (`dli_active_offset` 0/8, `dli_pending_offset` 8/0, `dli_swap_requested`) — poprawne i bezpieczne: swap tylko w VBLANK. Jedyny mankament: `dli_swap_requested` nie jest sprawdzany przed ponownym `dli_stage_scene`, więc dwa wywołania przed jednym VBLANK nadpisałyby ten sam bufor (dziś niemożliwe — staging jest raz na scenę).
* **Martwy mechanizm:** `dli_zone_prior` (patrz 5.4).

### 6.4. DLI ekranu tytułowego (`scenes/title.asm:207-279`)

* DLI przełącza `DMACTL` narrow→normal na jednej linii i przywraca narrow po linii scrolla — to jedyny sposób na 40-znakowy scroll przy 128-px bitmapie. Poprawnie, z `WSYNC` przed każdą zmianą koloru.
* `dli_title_restore` (`title.asm:277-279`) to pusta procedura `rti` — **martwy kod**.
* `VDSLST` jest ustawiany ponownie **w każdej klatce** (`title.asm:142-146`) — zbędne 12 cykli/klatkę; `title_init` już go ustawia (`title.asm:77-81`).
* Gradient tęczy w `COLPF2` (8 linii × `lda #imm/sta/sta WSYNC`) to ~90 B kodu i 8 × ~24 cykle — **można by zastąpić tabelą + pętlą**, ale zysk (~40 B) nie jest wart zmiany w timingu DLI.

### 6.5. VBI i synchronizacja

* Projekt **nie instaluje własnego VBI**; używa `RTCLOK+2` do synchronizacji i pozostawia OS-owy VBI (który kopiuje cienie). To najprostsze i najmniej ryzykowne rozwiązanie — poprawnie.
* `NMIEN` jest ustawiane w `title_init` (`$C0`), wyłączane do `$40` przy przejściu do intro (`title.asm:189-190`) i ponownie włączane w `dli_init` (`dli.asm:149-150`). Spójne.
* **Ryzyko timingowe (STAB-001):** po synchronizacji z VBLANK pętla gry wykonuje `dli_vblank_update` + `secrets_update` + `player_update` + `player_render_frame`, które **piszą do PMG w trakcie aktywnego wyświetlania**, jeśli nie zdążą w ~24 linie górnego blanku (~2 700 cykli). Szacunkowo mieszczą się (patrz 5.1), ale zapas jest jednoklatkowy — każda nowa praca w tej fazie może spowodować widoczne „rozjechanie” pierwszej linii ducha. **Do zmierzenia (sekcja 10), nie do naprawy „na wszelki wypadek”.**
* `PRIOR` jest ustawiany na `#$11` (`dli.asm:414`). Bit 0 = 5. gracz (konieczny). Bit 4 ($10) nie ma udokumentowanej funkcji w trybie standardowym — wpisanie go jest nieszkodliwe, ale `#$01` byłoby bardziej jednoznaczne. Brak aktualizacji `GPRIOR` (cień OS) — bez znaczenia, bo nikt nie czyta cienia.


---

## 7. Audyt architektury i jakości kodu

### 7.1. Modułowość

Podział na pliki jest czytelny i logiczny: `hardware.asm` (rejestry), `zeropage.asm` (mapa ZP z komentarzami i zakresami), `engine/*` (mechanizmy), `scenes/*` (stany), `lib/*` (biblioteki). Nagłówki plików opisują odpowiedzialność i adresy — to poziom, którego brakuje w większości projektów 8-bitowych.

Słabe punkty:

* **`main.asm` pełni trzy role:** dyspozytor stanów, mapa pamięci (12 `org`) i właściciel dwóch display listów. Przy 105 B kodu to nie problem rozmiarowy, ale każde przeniesienie segmentu wymaga edycji `main.asm` + `check_memory.py` + `generate_memory_map.py` (3 miejsca zduplikowanej wiedzy o adresach).
* **`scenes/game.asm` jest „boskim obiektem”** — 623 B, 5 procedur, 4 fazy, kolizje, progresja scen. To najgęstsze sprzężenie w projekcie.
* **`engine/player.asm` (1 451 B) jest największym modułem** i zawiera 4 kopie logiki platform (patrz 4.3) + 3 osobne tabele trajektorii. Naturalny kandydat na podział: `player_physics.asm`, `player_render.asm`, `player_tables.asm` — ale **podział sam w sobie nie zmniejsza kodu**; oszczędność daje dopiero wspólna procedura kolizji (ROM-002).

### 7.2. Powielanie logiki — podsumowanie

| Wzorzec | Wystąpienia | Ocena |
|---|---|---|
| Debounce fire + `CH` | 4 (`intro`, `gameover`, `title`, `game`) | warto ujednolicić (ROM-001) |
| Czekanie na VBLANK | 4 | warto ujednolicić (ROM-001) |
| Czyszczenie PMG | 3 × 2 KB + 2 × 256 B | warto ujednolicić (ROM-001) |
| Skan platform w `player.asm` | 4 | największy zysk (ROM-002), wyższe ryzyko |
| Inicjalizacja kolorów/DMA | 4 fazy `game_run` + `title_init` + `intro_init` | akceptowalne, każda faza ma inne kolory |

### 7.3. Zarządzanie stanem i pamięcią

* Stan gry trzymany jest w ZP (`game_state`, `current_state`, `game_phase`, `scene_card_*`) — poprawne i szybkie.
* **Brak resetu stanu między rozgrywkami (naprawione w `163ce06`):** `gameover_run` → `STATE_TITLE` → `intro` → `game_init`. `game_init` **nie zerował** `player_lives` ani `player_cds` (zachowuje je celowo między scenami — `game.asm:46-49`), a `status_line_reset` było wołane tylko, gdy `player_lives == 0`. Po przegranej (0 żyć) działało poprawnie; po **wygranej** (`GAME_SUCCESS`, `game_next_scene` → `STATE_OVER`) `player_lives` pozostawało > 0, więc nowa gra startowała z pozostałymi życiami i licznikiem CD z poprzedniej rozgrywki. Fix: `title_init` wykonuje `sta active_scene_id` + `jsr status_line_reset`. **Szczegóły — STAB-004.**
* `active_scene_id` było zerowane tylko przy starcie (`main.asm:66-67`); po powrocie do tytułu pozostawało na ostatniej scenie. Po **wygranej** wynosiło `SCENE_COUNT` (bo `game_next_scene` inkrementuje je przed sprawdzeniem), więc kolejna rozgrywka wchodziła do `game_init` z indeksem poza zakresem: `render_scene_background` i `dli_stage_scene` po cichu wracały, a `secrets_init`/`player_init`/`status_line_init` czytały tablice o 1 element poza końcem. **Naprawione w `163ce06`** (reset w `title_init` + sprawdzenia `cmp #SCENE_COUNT` w `game_init`, `secrets_init`, `player_init`, `status_line_init`).
* Bufory nie są współdzielone między stanami (VRAM gry, bitmapa tytułu) — świadoma decyzja, koszt 3 072 B (patrz 4.6).

### 7.4. Ryzyka utrzymaniowe

* **Wiedza o adresach w trzech miejscach:** `main.asm` (`org`), `check_memory.py:65-98` (mapowanie `$XXXX → opis`) i `generate_memory_map.py`. Dodanie segmentu wymaga edycji wszystkich trzech.
* **`check_memory.py` liczy tylko to, co jest w pliku.** Po wdrożeniu MEM-005 (nieemitowane bufory) raportowałby fałszywe 7 717 B zapasu. Trzeba by dodać listę „obszarów zarezerwowanych” — inaczej narzędzie straci sens.
* **Brak asercji na rozmiary.** MADS wspiera `.pages`/`.assert`; obecnie jedyną kontrolą jest post-build `check_memory.py`. Asercja „`dli_stage_scene` czyta 34 tabele, a `DLI_TABLE_COUNT = 34`” zapobiegłaby cichej regresji przy dodaniu tabeli.
* **Testy są silnie związane z konkretnymi adresami etykiet** (dobrze), ale kilka testów (`test_platform_profiles.py:404-414`, `test_compile_scenes.py:171-176`) **wymusza istnienie martwych tabel** (`scene_plat_color_sl*`, `scene_obj_*`). Usunięcie MEM-003 wymaga równoczesnej aktualizacji tych testów — to główny koszt tej rekomendacji.
* **`manifest.yaml` deklaruje 4 tilesety jako zasoby gry**, a używa się 2. Manifest jest „SSOT”, więc po MEM-001 trzeba go zaktualizować (albo oznaczyć tilesety jako „nieaktywne”), inaczej dokumentacja kłamie.

### 7.5. Błędy potwierdzone, problemy potencjalne, możliwości optymalizacji

**Potwierdzone (analiza kodu, bez uruchamiania):**

| ID | Opis | Lokalizacja |
|---|---|---|
| STAB-006 | `player_init` zerował X pętlą czyszczenia PMG, więc `scene_plat_count,x` i `scene_plat_x/y/w_lo/hi,x` były zawsze liczone dla sceny 0 — **kolizje w scenie 2 używały platform sceny 1**. **NAPRAWIONE w `163ce06`** | `engine/player.asm:85`, `135-141`, `144-160` (stan `d97e4d2`) |
| STAB-004 | Brak resetu `active_scene_id`, `player_lives`, `player_cds` przy powrocie do tytułu → kolejna rozgrywka wchodziła do `game_init` z `active_scene_id = SCENE_COUNT` i indeksowała tablice scen poza zakresem. **NAPRAWIONE w `163ce06`** | `scenes/title.asm:19-124`, `scenes/game.asm:46-51`, `main.asm:57-67` (stan `d97e4d2`) |
| MEM-003 | 526 B martwych tabel generowanych i ładowanych do RAM | `gen/scenes_data.asm`, `scripts/compile_scenes.py` |
| MEM-007 | Martwe: `dli_zone_prior`, `dli_z0_prior`, `tileset_w_px*`, `tileset_h_lines`, `tileset_size*`, `sprite_height/frame_count/frame_dur`, `zp_frame_cnt`, `dli_title_restore` | patrz sekcja 8 |
| 7.1 | Brak jakiegokolwiek runtime dla wrogów — dane `scene_obj_*` istnieją, kod nie | `gen/scenes_data.asm` |

**Potencjalne (wymagają testu/uruchomienia):**

| ID | Opis | Dlaczego potencjalny |
|---|---|---|
| STAB-001 | Zapisy PMG po VBLANK mogą trafić w aktywny obraz przy przeciążeniu klatki | szacunek mieści się w budżecie, ale bez pomiaru nie da się potwierdzić |
| STAB-002 | `secrets_pmg_y + height > 255` zawinie kopię w obrębie strony `$6B` | obecne dane (126+16=142) nie powodują problemu; nowa scena może |
| STAB-003 | `dli_stage_scene` nadpisze bufor, jeśli zostanie wywołane 2× przed VBLANK | dziś nieosiągalne (staging raz na scenę) |
| STAB-005 | `dec player_lives` bez sprawdzenia zera (`player.asm:1114`) — podwójna śmierć w jednej klatce da 255 żyć | wymaga nietypowego stanu; tanie zabezpieczenie |

**Możliwości optymalizacji:** MEM-001…007, CPU-001…002, ROM-001…003, DATA-001, ARCH-001…002 (sekcja 8).


---

## 8. Lista rekomendacji

Kolejność wdrożenia: patrz indeks 8.0 (posortowany według priorytetu) oraz plan w sekcji 9. Każda pozycja ma 12 pól wymaganych przez specyfikację audytu.

### 8.0. Indeks rekomendacji w kolejności priorytetu

Poniższa tabela jest **listą posortowaną według priorytetu** (krytyczny → wysoki → średni → niski, z uwzględnieniem stosunku korzyści do kosztu). Szczegółowe opisy (12 pól każdy) są niżej, pogrupowane dla czytelności: RAM/dane → CPU → ROM → stabilność → architektura.

| # | ID | Priorytet | Kategoria | Efekt | Etap |
|---:|---|---|---|---|---:|
| 1 | STAB-006 | krytyczny | stabilność (błąd) | naprawa kolizji w scenie 2, 2 B kodu — **✅ wdrożone w `163ce06`** | 1.0 |
| 2 | MEM-001 | krytyczny | RAM | −10 641 B | 1.2 |
| 3 | STAB-004 | wysoki | stabilność (błąd) | usunięcie odczytu poza zakresem, ~14 B kodu — **✅ wdrożone w `163ce06`** | 1.1 |
| 4 | MEM-003 | wysoki | RAM | −526 B | 2.2 |
| 5 | MEM-006 | wysoki | RAM | +768 B | 1.4 |
| 6 | MEM-002 | wysoki | dane | −1 144 B | 2.1 |
| 7 | CPU-001 | wysoki | CPU | ~−600 cykli/klatkę, +6 B | 2.4 |
| 8 | MEM-004 | średni | dane | −112 B | 1.3 |
| 9 | MEM-005 | średni | plik XEX | −5 888 B pliku | 1.5 |
| 10 | MEM-007 | średni | RAM/ROM | −57 B RAM, −20 B ROM | 2.3 |
| 11 | CPU-002 | średni | CPU | ~−250 cykli/klatkę, −10 B | 2.5 |
| 12 | ROM-001 | średni | ROM/kod | −150…−200 B | 1.4 / 2.6 |
| 13 | ROM-002 | średni | ROM/kod | −120…−180 B, wysokie ryzyko | 3.1 |
| 14 | ARCH-002 | średni | architektura | usuwa sufit skalowania (brak natychmiastowych B) | 3.5 |
| 15 | ROM-003 | niski | ROM/kod | −75 B | 3.2 |
| 16 | DATA-001 | niski | dane | −80 B/scenę powyżej 3. sceny | 3.4 |
| 17 | ARCH-001 | niski | architektura | −10…−16 B, głównie czytelność | 3.3 |
| 18 | STAB-002 | niski | stabilność | ochrona przed zawinięciem strony PMG | — |
| 19 | STAB-005 | niski | stabilność | ochrona licznika żyć | 1.6 |

### MEM-001 — Nieużywane tilesety `DEPTHS` i `HELL` zajmują 10 641 B RAM

* **ID:** MEM-001
* **Tytuł:** Usunąć z binarki bitmapy tilesetów, których nie używa żadna scena
* **Priorytet:** krytyczny (największa pojedyncza oszczędność)
* **Kategoria:** RAM / dane
* **Lokalizacja:** `main.asm:420-428` (`ins 'gen/tiles_depths.bin'`, `ins 'gen/tiles_hell.bin'`), `gen/tiles_data.asm:8-12,19-26,46-48,71-95`, `scripts/convert_tiles.py:250-322`, `Makefile:29-36,87-89`
* **Obserwacja:** Do `$8000` wstawiane są 4 bitmapy: `castles` 2 992 B, `depths` 6 480 B, `hell` 4 161 B, `trees` 2 604 B. `gen/scenes_data.asm` zawiera wyłącznie `TILESET_TREES` i `TILESET_CASTLES`; identyfikatory `TILESET_DEPTHS`/`TILESET_HELL` nie występują w żadnym pliku `.asm` (0 trafień w `main.asm`, `engine/*`, `scenes/*`, `lib/*`).
* **Problem/potencjał:** 10 641 B (27 % obrazu, 66 % bloku tilesetów) jest ładowane do RAM i nigdy nie odczytane. Przy 1 829 B wolnego RAM to główne ograniczenie rozwoju.
* **Rozwiązanie:** Filtrować tilesety po rzeczywistym użyciu w scenach: `compile_scenes.py` już zna listę `tileset_id`, więc `convert_tiles.py` może przyjąć `--only <nazwy>` (lub listę z `manifest.yaml`), a `main.asm` wstawiać tylko wygenerowane `ins`. Alternatywnie: przenieść `depths`/`hell` do osobnego pliku `.xex`/`.bin` ładowanego przez loader (koszt: nowy kod I/O, patrz ARCH-002).
* **Szacowany efekt:** **−10 641 B RAM** i tyle samo w pliku XEX (39 197 → ~28 556 B).
* **Koszt i ryzyko:** niski. Wymaga renumberacji `TILESET_*` (sceny odwołują się przez equaty, więc zmiana jest automatyczna) oraz aktualizacji `manifest.yaml` (deklaruje 4 tilesety) i testów `tests/test_convert_tiles.py`.
* **Pewność oceny:** wysoka (użycie zweryfikowane grepem + zawartością `scenes_data.asm`).
* **Weryfikacja:** `check_memory.py` (segment `$8000` maleje o 10 641 B), `pytest`, uruchomienie obu scen w Altirrze.

### MEM-003 — 526 B martwych tabel scen w `gen/scenes_data.asm`

* **ID:** MEM-003
* **Tytuł:** Usunąć z generatora i binarki tabele, których nie czyta żaden kod 6502
* **Priorytet:** wysoki
* **Kategoria:** RAM / dane
* **Lokalizacja:** `scripts/compile_scenes.py:1168-1171` (`_name`), `1180,1186,1192` (`_px`), `1219-1231` (`plat_type`, `plat_h`, `plat_color_sl1..8`), `1247-1266` (`obj_*`), `1303` (`secret_color`), `1392-1420` (pary wskaźników)
* **Obserwacja:** Generator tworzy 42 pary tabel na scenę; kod czyta 17. Martwe: `scene_*_name` (55 B), `elem_*_px` (27 B), `plat_type` (25 B), `plat_h` (25 B), `plat_color_sl1..8` (200 B), `obj_*` 10 tabel (100 B), `secret_color` (6 B) + 88 B martwych par wskaźników.
* **Problem/potencjał:** 526 B stałego narzutu w RAM i 526 B w pliku. Większość to pozostałości po funkcjach, które nie trafiły do runtime (wrogowie) albo zostały zastąpione (kolory platform → `scenes_dli_data.asm`).
* **Rozwiązanie:** Usunąć generowanie tych tabel z `compile_scenes.py` (albo za bramką `--with-enemies`, dopóki silnik wrogów nie powstanie), usunąć odpowiadające pary `*_lo/*_hi`, zaktualizować `tests/test_compile_scenes.py:171-176` i `tests/test_platform_profiles.py:404-414` (te testy **wymagają** istnienia martwych tabel), a także `manifest.yaml`.
* **Szacowany efekt:** **−526 B RAM** i pliku.
* **Koszt i ryzyko:** średni (dotyka generatora i 2 plików testów). Ryzyko regresji funkcjonalnej ~zero, bo brak referencji w kodzie; ryzyko regresji testów — pewne.
* **Pewność oceny:** wysoka (0 referencji w `.asm` dla każdej z tabel).
* **Weryfikacja:** `pytest -q`, `check_memory.py`, porównanie `gen/main.lab` (zniknięcie etykiet).

### MEM-006 — 768 B w bloku PMG nie jest adresowane przez GTIA

* **ID:** MEM-006
* **Tytuł:** Wykorzystać `$6800–$6AFF` jako pamięć dla CPU
* **Priorytet:** wysoki
* **Kategoria:** RAM / architektura pamięci
* **Lokalizacja:** `main.asm:377-379` (`org PMG_ADDR`), `scenes/title.asm:46-58`, `scenes/gameover.asm:33-45`, `engine/dli.asm:120-133`
* **Obserwacja:** `PMBASE = $68`; przy `DMACTL = $3E` (bit 4 = 0 → single line) GTIA czyta wyłącznie `+$300` (pociski, `$6B00`) i `+$400..+$7FF` (gracze, `$6C00–$6FFF`). Obszar `+$000..+$2FF` (`$6800–$6AFF`, 768 B) nie jest adresowany, ale trzy pętle czyszczące zapisują tam zera.
* **Problem/potencjał:** 768 B „niewidocznej” pamięci, której `check_memory.py` nie widzi w ogóle (segment `$6800–$79D9` jest traktowany jako całość).
* **Rozwiązanie:** Skrócić pętle czyszczenia PMG do `$6B00–$6FFF` (1 280 B: 5 × `sta` zamiast 8 × `sta`) i przenieść w to miejsce dane, które są rzadko zapisywane (np. bufory DLI z `$6100`, teksty, tabele). Wymaga też korekty komentarzy w `main.asm:368-376`.
* **Szacowany efekt:** **+768 B dostępnego RAM** oraz −768 B operacji `sta` przy każdej inicjalizacji sceny.
* **Koszt i ryzyko:** niski/średni. Ryzyko: jeśli ktoś kiedyś włączy double-line (bit 4 = 1), dane zostaną nadpisane przez DMA. Warto dodać asercję/komentarz w `hardware.asm`.
* **Pewność oceny:** wysoka (mapa PMG wg dokumentacji GTIA + brak odwołań do `$6800–$6AFF` poza czyszczeniem).
* **Weryfikacja:** uruchomienie gry (brak artefaktów na ekranie), `check_memory.py` po dodaniu obszaru do raportu.


### MEM-002 — Tileset `CASTLES` jest o 1 144 B szerszy niż potrzebuje

* **ID:** MEM-002
* **Tytuł:** Przyciąć bitmapę `castles` do bounding-boxu wykorzystanych elementów
* **Priorytet:** wysoki
* **Kategoria:** dane / grafika
* **Lokalizacja:** `scripts/convert_tiles.py:278-293` (`w_bytes = (w + 3) // 4`, brak przycinania), `gen/tiles_castles.bin`, `gen/tiles_data.asm:15-18,62-69`
* **Obserwacja:** PNG ma 270 px × 44 linie → 68 B/linia × 44 = 2 992 B. Elementy obu scen sięgają maks. `x = 168` (`scenes/02-forest-castle.json:11-23` — `source_rect.x=0,width=92` oraz `x=93,width=75`); kolumny 168–269 nigdy nie są czytane.
* **Problem/potencjał:** 26 B/linia × 44 = **1 144 B** martwego miejsca. `trees` jest wykorzystany w 100 % (bbox 0–246 = pełna szerokość), więc **jego nie należy przycinać**.
* **Rozwiązanie:** Dodać do `convert_tiles.py` opcjonalne `--crop-to-scenes` (analiza `source_rect` ze wszystkich plików w `scenes/`), wyliczyć `width_bytes` z rzeczywistego bbox i wygenerować nowe `TILESET_CASTLES_W_BYTES = 42`. Uwaga: strona `tiles_data_end` i `check_memory.py` (segment `$8000`) przeliczą się automatycznie.
* **Szacowany efekt:** **−1 144 B RAM** i pliku.
* **Koszt i ryzyko:** średni. Ryzyko: przycięcie musi respektować kolejność tilesetów (`castles` leży pierwszy, więc kolejne adresy się przesuną — kod używa `tileset_data_lo/hi`, więc jest bezpieczny). Konieczne testy w `tests/test_convert_tiles.py` i wizualna kontrola w emulatorze (flip_x elementów na krawędzi).
* **Pewność oceny:** wysoka (bbox policzony z JSON-ów scen).
* **Weryfikacja:** rozmiar `gen/tiles_castles.bin` = 1 848 B, `check_memory.py`, wizualne porównanie sceny 2 przed/po.

### MEM-004 — 112 B identycznych klatek sprite'ów

* **ID:** MEM-004
* **Tytuł:** Deduplikować identyczne klatki animacji w `compile_sprites.py`
* **Priorytet:** średni
* **Kategoria:** dane / grafika
* **Lokalizacja:** `scripts/compile_sprites.py:200-235` (sekcja `generate_sprites_asm`), `gen/sprites_data.asm`
* **Obserwacja:** `sprite_1_frame_4` = `sprite_1_frame_2`, `sprite_1_frame_5` = `sprite_1_frame_1`; `sprite_3_frame_7/8/9/10/11` = `frame_5/4/3/2/1`. Razem 7 duplikatów × 16 B = 112 B.
* **Problem/potencjał:** Animacja „obraca się” w tę i z powrotem, więc połowa klatek to powtórzenia. Dziś każda jest emitowana osobno.
* **Rozwiązanie:** W generatorze zbudować mapę `bytes → pierwsza etykieta` i dla duplikatów emitować do tablicy `sprite_N_frames` adres istniejącej klatki (bez nowej etykiety). Zero zmian w kodzie 6502 — `render_secret_frame` używa tylko tablicy wskaźników.
* **Szacowany efekt:** **−112 B** (dane), 0 B kodu, 0 cykli.
* **Koszt i ryzyko:** niski. Ryzyko: etykiety `sprite_*_frame_N` są używane w testach (`tests/test_secrets_runtime.py`) — trzeba je zachować jako aliasy (`= `).
* **Pewność oceny:** wysoka (porównanie bajtów).
* **Weryfikacja:** `gen/sprites_data.asm` (7 etykiet mniej), `pytest`, animacja CD/klucza w grze.

### MEM-005 — 5 888 B zer w pliku XEX

* **ID:** MEM-005
* **Tytuł:** Nie emitować do XEX zerowych buforów VRAM gry i PMG
* **Priorytet:** średni (rozmiar pliku, nie RAM)
* **Kategoria:** rozmiar kodu/danych wynikowych
* **Lokalizacja:** `main.asm:212-214` (`:GAME_VRAM_SIZE .byte 0`), `main.asm:377-379` (`:PMG_SIZE .byte 0`)
* **Obserwacja:** `game_vram_buf` emituje 3 840 zer, `pmg_memory` 2 048 zer — łącznie 5 888 B (15 % pliku). Oba obszary są i tak w pełni inicjalizowane w runtime: `clear_game_vram` (`render.asm:13-35`) i `dli_init`/`title_init` (`dli.asm:120-133`, `title.asm:46-58`).
* **Problem/potencjał:** Plik jest o 5 888 B większy niż konieczne → dłuższe ładowanie z napędu i z taśmy; RAM się nie zmienia.
* **Rozwiązanie:** Usunąć bufory z `org`-owanych segmentów i zdefiniować je jako etykiety bez danych (np. `game_vram_buf = GAME_VRAM`), a segment DL rozpocząć od `org GAME_DLIST`. **Uwaga:** `check_memory.py` liczy zajętość z segmentów — po zmianie trzeba dodać listę „obszarów zarezerwowanych”, inaczej zacznie raportować fałszywe 7 717 B zapasu.
* **Szacowany efekt:** **−5 888 B pliku** (39 197 → ~33 309 B), 0 B RAM, krótsze ładowanie.
* **Koszt i ryzyko:** średni (ryzyko: jeśli coś czyta VRAM przed pierwszym `clear_game_vram`, zobaczy śmieci — dziś nie czyta; narzędzie `check_memory.py` wymaga aktualizacji).
* **Pewność oceny:** wysoka (oba bufory są zerowane przed użyciem); efekt „krótszego ładowania” — szacunek.
* **Weryfikacja:** rozmiar pliku, `check_memory.py` po aktualizacji, uruchomienie wszystkich 4 stanów gry.


### MEM-007 — Drobne martwe tabele i zmienne (57 B RAM + 20 B ROM)

* **ID:** MEM-007
* **Tytuł:** Usunąć martwe metadane tilesetów/sprite'ów, tabelę `prior` w DLI i nieużywaną zmienną ZP
* **Priorytet:** średni (zbiorczo)
* **Kategoria:** RAM / ROM
* **Lokalizacja:** `engine/dli.asm:61` (`dli_zone_prior`), `engine/dli.asm:75` (`dli_z0_prior`), `engine/dli.asm:64-78` (`dli_z0_colpf0..2`), `gen/tiles_data.asm:33-44` (`tileset_w_px_lo/hi`, `tileset_h_lines`, `tileset_size_lo/hi`), `gen/sprites_data.asm:72-77` (`sprite_height`, `sprite_frame_count`, `sprite_frame_dur`), `zeropage.asm:18` (`zp_frame_cnt`), `scenes/title.asm:277-279` (`dli_title_restore`)
* **Obserwacja:** Wszystkie wymienione mają 0 referencji w kodzie (poza własną definicją) albo są zapisywane i nigdy nie czytane (`dli_zone_prior` → zapis w buforze, odczytu brak; `PRIOR` ustawiany na stałe `#$11` w `dli.asm:414`).
* **Problem/potencjał:** 18 B RAM (`dli_zone_prior` 16 + `dli_z0_prior` 2) + 6 B RAM (`dli_z0_colpf*`) + 8 B RAM (metadane tilesetów/sprite'ów są w RAM) + 1 B ZP + ~2 B kodu; 20 B w danych DLI scen (12 B `prior` + 6 B `z0_colpf` + 1+1 B `z0_prior`).
* **Rozwiązanie:** Usunąć tabele, zredukować `DLI_TABLE_COUNT` z 34 do 33 (i usunąć 33. wpis ze źródła danych w `compile_scenes.py`), pominąć emisję `z0_colpf*` i przy stage'owaniu brać te 3 bajty z pierwszego wpisu `dli_bg_colpf*`.
* **Szacowany efekt:** ~57 B RAM + 20 B ROM + 2 B kodu.
* **Koszt i ryzyko:** niski/średni (zmiana liczby tabel w DLI wymaga zgodności generatora i buforów; timing bez zmian, bo tabela nie była czytana).
* **Pewność oceny:** wysoka.
* **Weryfikacja:** `gen/main.lab` (brak etykiet), `tests/test_dli_system.py`, obraz w grze (kolory platform bez zmian).

### CPU-001 — Pomiń czyszczenie PMG, gdy bohater nie zmienił linii

* **ID:** CPU-001
* **Tytuł:** Warunkowe pominięcie pętli czyszczenia w `player_render_frame`
* **Priorytet:** wysoki (najlepszy stosunek cykli do kosztu)
* **Kategoria:** CPU
* **Lokalizacja:** `engine/player.asm:222-240`
* **Obserwacja:** Procedura zawsze czyści 20 linii od `player_prev_pmg_y`, a następnie rysuje 20 linii od `player_pmg_y`. `player_pmg_y` zmienia się tylko w `player_jump_update` (`player.asm:826-830`) i `player_fall_update` (`player.asm:1015-1020`).
* **Problem/potencjał:** Podczas chodzenia/stania `prev == current`, więc 20 zapisów `sta` i ~600 cykli są marnowane w ~90 % klatek (3 % budżetu klatki PAL).
* **Rozwiązanie (koncepcja, nie wdrażać bez testu):**
  ```
  ; przed pętlą czyszczenia
        lda player_pmg_y
        cmp player_prev_pmg_y
        beq @skip_clear          ; brak ruchu pionowego → nic do wyczyszczenia
  ```
* **Szacowany efekt:** ~600 cykli/klatkę mniej (szacunek z liczby rozkazów), +6 B kodu.
* **Koszt i ryzyko:** bardzo niski; jedyne ryzyko to pominięcie czyszczenia w scenariuszu, w którym `player_pmg_y` wraca do tej samej wartości po klatce z inną animacją (niemożliwe — ten sam adres = ten sam obszar pamięci).
* **Pewność oceny:** wysoka co do mechanizmu; efekt cyklowy szacunkowy.
* **Weryfikacja:** `mpu.processorCycles` w py65 przed/po dla sekwencji 60 klatek chodzenia; wizualna kontrola „duchów” w Altirrze.

### CPU-002 — Szybszy blit PMG z wcześniej policzonym clippingiem

* **ID:** CPU-002
* **Tytuł:** Zastąpić test `cmp #224` na każdą linię jednym obliczeniem `count`
* **Priorytet:** średni
* **Kategoria:** CPU
* **Lokalizacja:** `engine/player.asm:296-310` (rysowanie) i `224-240` (czyszczenie)
* **Obserwacja:** Obie pętle wykonują `tya/clc/adc/cmp #224/bcs/tax` dla każdej z 20 linii, by obsłużyć `player_pmg_y ≥ 224` (bohater wchodzący na pasek statusu).
* **Problem/potencjał:** ~30 cykli/linia zamiast ~17; 40 zbędnych rozgałęzień na klatkę.
* **Rozwiązanie (koncepcja):** policzyć raz `count = 224 - player_pmg_y` (0..20), ustawić `zp_ptr_dst = PMG_PLAYER0 + player_pmg_y`, a pętlę oprzeć na `lda (zp_ptr_src),y / sta (zp_ptr_dst),y / iny / cpy count / bne`.
* **Szacowany efekt:** ~250 cykli/klatkę, −~10 B kodu.
* **Koszt i ryzyko:** średni — clipping jest testowany w `tests/test_player_movement.py`, więc regresja zostanie wychwycona; ryzyko błędu granicznego przy `count = 0`.
* **Pewność oceny:** wysoka co do liczby cykli na linię, średnia co do realnego zysku (zależy od CPU-001).
* **Weryfikacja:** pomiar `processorCycles` dla klatki z bohaterem przy dolnej krawędzi (`player_pmg_y` 200–260).


### ROM-001 — Ujednolicić debounce, oczekiwanie VBLANK i czyszczenie PMG

* **ID:** ROM-001
* **Tytuł:** Trzy wspólne procedury zamiast 11 kopii
* **Priorytet:** średni
* **Kategoria:** ROM/kod
* **Lokalizacja:** `intro.asm:64-118`, `gameover.asm:57-100`, `title.asm:126-195`, `game.asm:92-101`, `title.asm:46-58`, `gameover.asm:33-45`, `dli.asm:120-133`, `player.asm:196-203,1102-1108`
* **Obserwacja:** Struktura „czekaj na VBLANK → sprawdź zwolnienie fire → sprawdź STRIG0/CH → przejdź dalej” jest powtórzona 4×, pętla czyszczenia 2 KB PMG 3×, a 256 B `PMG_PLAYER0` 2×.
* **Problem/potencjał:** ~34 B (PMG) + ~75 B (VBLANK) + ~75 B (debounce) = **~180 B kodu** do odzyskania.
* **Rozwiązanie:** `wait_vblank` (6 B), `clear_pmg_full` (17 B), `poll_fire_released / poll_fire_pressed` zwracające flagę w A; każdy stan woła je zamiast powielać ciało. Zachować obecne różnice (intro/gameover czyszczą `CH`, title nie).
* **Szacowany efekt:** −150…−200 B kodu, −~30 cykli/klatkę (mniej duplikatów `jsr`/`rts`).
* **Koszt i ryzyko:** niski/średni; ryzyko: różnice w obsłudze `CH` między ekranami muszą zostać zachowane.
* **Pewność oceny:** wysoka co do rozmiaru duplikatów, średnia co do dokładnej liczby bajtów po refaktorze.
* **Weryfikacja:** różnica rozmiaru segmentów w `gen/main.lab`, `pytest`, przejście wszystkich 4 ekranów.

### ROM-002 — Cztery kopie skanu platform w `engine/player.asm`

* **ID:** ROM-002
* **Tytuł:** Wydzielić wspólną procedurę wyszukiwania platformy (X/Y)
* **Priorytet:** średni
* **Kategoria:** ROM/kod, architektura
* **Lokalizacja:** `player.asm:84-214` (start), `player.asm:854-905` (sufit), `player.asm:725-1010` (lądowanie po skoku), `player.asm:1039-1070` (spadanie)
* **Obserwacja:** Cztery pętle iterują po `zp_plat_count`, porównują `plat_x <= mid_x < plat_x + plat_w` i `plat_y` względem stóp/głowy. Różnią się tylko warunkiem Y i akcją po trafieniu.
* **Problem/potencjał:** ~150–200 B kodu w największym module; każda zmiana geometrii wymaga 4 edycji (ryzyko rozjazdu logiki — np. skok „long” wyłącza sprawdzanie sufitu, `player.asm:839-841`).
* **Rozwiązanie:** Procedura `find_platform` z parametrem trybu (bit 0: szukaj pod stopami / nad głową, bit 1: pomiń sufit) w `zp_temp_x`, zwracająca indeks w Y lub `$FF`. Koszt: ~15 cykli narzutu na wywołanie (3×/klatkę w skoku).
* **Szacowany efekt:** −120…−180 B kodu, −0 cykli w typowej klatce, +~45 cykli w klatce skoku.
* **Koszt i ryzyko:** **wysoki** — to najbardziej ryzykowna optymalizacja w projekcie: dotyka fizyki, która jest już dopracowana (commity `11433ab`, `48616ca`). Wymaga testów regresyjnych wszystkich 3 typów skoku i spadania z krawędzi.
* **Pewność oceny:** średnia (rozmiar), niska (brak regresji bez rozszerzenia testów).
* **Weryfikacja:** `tests/test_player_movement.py`, `tests/test_player_spawn.py` + nowe przypadki (skok w sufit, lądowanie na krawędzi, spadanie z platformy).

### ROM-003 — Strefa 0 DLI: 90 B kodu na 15 przypisań

* **ID:** ROM-003
* **Tytuł:** Zmienić layout strefy 0 z przeplotu na dwa bloki i skopiować pętlą
* **Priorytet:** niski
* **Kategoria:** ROM/kod
* **Lokalizacja:** `engine/dli.asm:64-78` (deklaracje `:2`), `engine/dli.asm:283-327` (kopiowanie), `engine/dli.asm:342-441` (odczyt)
* **Obserwacja:** 15 tabel po 2 bajty (bufor 0/1) jest kopiowanych i odczytywanych 15 osobnymi parami `lda (zp),y / sta abs,x` — ~90 B kodu w `dli_stage_scene` i podobnie w `dli_vblank_update`.
* **Problem/potencjał:** ~75 B kodu do odzyskania.
* **Rozwiązanie:** zadeklarować `dli_z0_buf0 :15` i `dli_z0_buf1 :15` (albo `:30` z offsetem 0/15), wtedy kopiowanie i odczyt to zwykłe pętle `ldy #14 … dey/bpl`.
* **Szacowany efekt:** −75 B kodu, +~30 cykli przy zmianie sceny (poza pętlą klatki).
* **Koszt i ryzyko:** średni — dotyka VBLANK-owej części DLI, ale nie handlera przerwania (tam nic się nie zmienia).
* **Pewność oceny:** wysoka co do rozmiaru, wysoka co do braku wpływu na timing DLI.
* **Weryfikacja:** `tests/test_dli_system.py` (porównanie zawartości buforów po `dli_stage_scene` dla obu scen).


### STAB-004 — Brak resetu stanu przy powrocie do tytułu → indeks sceny poza zakresem

* **ID:** STAB-004
* **Tytuł:** Nowa gra po zakończeniu startuje z `active_scene_id = SCENE_COUNT` i indeksuje tablice poza zakresem
* **Priorytet:** **wysoki (błąd funkcjonalny, nie optymalizacja)**
* **Kategoria:** stabilność / architektura
* **Lokalizacja:** `scenes/game.asm:438-449` (`game_next_scene`), `scenes/gameover.asm:96-100`, `scenes/title.asm:19-124` (`title_init`), `engine/secrets.asm:110-116`, `engine/player.asm:84-92`, `engine/status_line.asm:39-48`
* **Obserwacja:**
  1. `game_next_scene` robi `inc active_scene_id`, a gdy `active_scene_id == SCENE_COUNT` ustawia `GAME_SUCCESS` i `STATE_OVER` — **`active_scene_id` pozostaje równe `SCENE_COUNT` (2)**.
  2. `gameover_run` wraca do `STATE_TITLE`; `title_init` **nie zeruje** `active_scene_id`, `player_lives` ani `player_cds`.
  3. Nowa gra: `intro` → `STATE_GAME` → `game_init` z `active_scene_id = 2`.
  4. `render_scene_background` (`render.asm:56-59`) i `dli_stage_scene` (`dli.asm:216-219`) sprawdzają `cmp #SCENE_COUNT` i **cicho wracają** — ekran i bufory DLI zostają z poprzedniej rozgrywki.
  5. `secrets_init` (`secrets.asm:110-116`), `player_init` (`player.asm:84-92`) i `status_line_init` (`status_line.asm:44-48`) **nie mają żadnego sprawdzenia zakresu** — czytają `scene_secret_count,x`, `scene_player_start_x,x`, `scene_name_line_lo,x` dla `x = 2`, czyli **poza tablicami 2-elementowymi**, a następnie kopiują dane spod wskaźników z tych śmieci.
* **Problem/potencjał:** Po ukończeniu gry (lub po powrocie do tytułu z niezerowym `active_scene_id`) kolejna rozgrywka może czytać spod dowolnych adresów, wyświetlić śmieci na pasku statusu i umieścić bohatera w losowym miejscu. Nie jest to crash *gwarantowany*, ale to niezdefiniowane zachowanie w kodzie, który ma testy jednostkowe — a żaden test nie pokrywa ścieżki „tytuł → gra” po `STATE_OVER`. Dodatkowo po przegranej licznik CD nie jest zerowany (`status_line_reset` woła się tylko, gdy `player_lives == 0`, a zeruje `player_cds` — czyli raz tak, raz nie).
* **Rozwiązanie (opis, nie wdrożenie):** wyzerować stan w jednym miejscu przy wejściu w nową rozgrywkę — np. w `title_init`:
  ```
        jsr status_line_reset      ; lives=3, cds=0, result=NONE
        lda #0
        sta active_scene_id
  ```
  oraz dodać sprawdzenia zakresu w `secrets_init`, `player_init`, `status_line_init` (wzorzec jak w `render.asm:56-59`). Warto też rozstrzygnąć projektowo, czy „continue” po utracie żyć ma startować od sceny 1 (dziś: od sceny, na której gracz zginął).
* **Szacowany efekt:** eliminacja niezdefiniowanego zachowania; 0 B oszczędności (dodaje ~10–14 B kodu).
* **Koszt i ryzyko:** niski; jedyne ryzyko to zmiana zachowania „continue”, jeśli była to funkcja zamierzona.
* **Pewność oceny:** wysoka (ścieżka prześledzona w kodzie, brak resetu potwierdzony grepem).
* **Weryfikacja:** test py65: ustawić `game_state=STATE_OVER`, `active_scene_id=SCENE_COUNT`, wywołać `title_init` + `game_init`, sprawdzić, że `active_scene_id == 0` i `secrets_count` mieści się w `0..MAX_SECRETS`.

_Status: **WDROŻONE** w `163ce06` — `title_init` robi `sta active_scene_id` + `jsr status_line_reset`, a `game_init`, `secrets_init`, `player_init` i `status_line_init` mają sprawdzenie `cmp #SCENE_COUNT`. Testy: `tests/test_state_machine_and_fade.py` (rozszerzone). Zostaje do rozstrzygnięcia wyłącznie decyzja projektowa o „continue” po utracie żyć._

### STAB-006 — `player_init` zawsze używa platform sceny 0

* **ID:** STAB-006
* **Tytuł:** Zachowany rejestr X jest nadpisywany pętlą czyszczenia PMG, więc wskaźniki platform nie zależą od `active_scene_id`
* **Priorytet:** **krytyczny (błąd funkcjonalny w rozgrywce)**
* **Kategoria:** stabilność / logika gry
* **Lokalizacja:** `engine/player.asm:84-85` (`tax`), `engine/player.asm:135-141` (czyszczenie `PMG_PLAYER0`), `engine/player.asm:144-160` (odczyt `scene_plat_*`)
* **Obserwacja:**
  1. `player_init` zaczyna się od `tax` (X = numer sceny z A) i poprawnie czyta `scene_player_start_x,x`, `scene_player_start_y,x`, `scene_player_color,x` (linie 88–92, 121).
  2. Następnie krok 5 czyści 256 B bufora `PMG_PLAYER0`:
     ```
     lda #0
     tax                  ; ← X = 0, numer sceny bezpowrotnie tracony
     @clr_p0
     sta PMG_PLAYER0,x
     inx
     bne @clr_p0          ; wyjście z X = 0
     ```
  3. Krok 6 (`lda scene_plat_count,x`, `scene_plat_x_lo,x`, `scene_plat_x_hi,x`, `scene_plat_y_*`, `scene_plat_w_*`) używa tego X = 0.
  4. `zp_plat_ptr_x/y/w` i `zp_plat_count` są ustawiane **wyłącznie** w tym miejscu (grep po `engine/*.asm`, `scenes/*.asm`: brak innych zapisów), a `player_update`, `player_jump_update`, `player_fall_update` i wyszukiwanie startowej platformy korzystają tylko z nich (linie 178–196, 562–640, 850–896, 939–969, 1035–1051).
* **Problem/potencjał:** W scenie 2 („Be Quick or Be Dead”: 14 platform, `start_x=90`, `start_y=68`) bohater stoi i koliduje z **11 platformami sceny 1**. Częściowe podobieństwo układów (obie sceny mają platformę na `y=88` obejmującą `x=90`) maskuje problem: gracz „stoi w powietrzu” na niewidzialnej powierzchni albo przelatuje przez widoczną. To tłumaczy, dlaczego błąd nie został zauważony — jedyny test wywołujący `player_init` ze sceną 1 (`test_player_init_scene1_custom_color`, `tests/test_player_movement.py:71-90`) sprawdza pozycję, kolor i PMG, ale nie wskaźniki platform, a pozostałe testy fizyki używają `mpu.a = 0` (np. `test_player_movement.py:665`).
* **Rozwiązanie (opis, nie wdrożenie):** przenieść odczyt tabel platform **przed** czyszczenie PMG albo odtworzyć X z `active_scene_id` (`ldx active_scene_id`) tuż przed krokiem 6. Minimalna poprawka to jedna instrukcja:
  ```
        ldx active_scene_id      ; przywróć indeks sceny po pętli czyszczenia
        lda scene_plat_count,x
  ```
  Warto też dodać test: `player_init` z `A = 1` → `zp_plat_count == SCENE_SC_02_FOREST_CASTLE_PLAT_COUNT (14)` oraz `zp_plat_ptr_x` wskazujący na `scene_sc_02_forest_castle_plat_x`.
* **Szacowany efekt:** naprawa rozgrywki w scenie 2; 2 B kodu, 0 cykli (poza inicjalizacją).
* **Koszt i ryzyko:** **bardzo niski** (jedna instrukcja), ale zmienia zachowanie fizyki w scenie 2 — po naprawie może się okazać, że część platform sceny 2 wymaga korekty w edytorze (np. zbyt duże odstępy do przeskoczenia).
* **Pewność oceny:** wysoka (prześledzona ścieżka X + grep potwierdzający jedyne miejsce zapisu `zp_plat_*`).
* **Weryfikacja:** nowy test py65 (`PLAYER_INIT` z `A=1`, porównanie `ZP_PLAT_COUNT` i wskaźników z etykietami sceny 1), a następnie przejście sceny 2 w Altirrze (bohater musi stać tylko na widocznych platformach).

_Status: **WDROŻONE** w `163ce06` — krok „Setup platform pointer tables” (obecnie `engine/player.asm:135-155`) wykonuje się **przed** czyszczeniem `PMG_PLAYER0` (`engine/player.asm:155-161`), a `player_init` ma dodatkowo `cmp #SCENE_COUNT` + `sta active_scene_id`. Test regresyjny dodany w `tests/test_player_movement.py`. Zalecana pozostaje ręczna weryfikacja sceny 2 w emulatorze._


### STAB-002 — Zawijanie kopii sekretu w obrębie strony `$6B`

* **ID:** STAB-002
* **Tytuł:** `secrets_pmg_y + height > 255` powoduje zapis na początku strony PMG
* **Priorytet:** niski (dziś nieosiągalne)
* **Kategoria:** stabilność
* **Lokalizacja:** `engine/secrets.asm:60-74` (`render_secret_frame`), `secrets.asm:86-103` (`clear_secret_rows`)
* **Obserwacja:** `zp_ptr_dst = PMG_MISSILES + secrets_pmg_y` (8-bit), kopiowanie przez `(zp_ptr_dst),y`. Przy `pmg_y = 250` i `height = 16` zapisy 250–265 zawijają się do `$6B00–$6B0F`.
* **Problem/potencjał:** Obecne dane (126+16=142, 62+16=78, 64+14=78) są bezpieczne, ale edytor scen pozwala ustawić sekret nisko na ekranie — nowa scena może to ujawnić.
* **Rozwiązanie:** Liczyć `count = min(height, 256 - pmg_y - 1)` przed kopiowaniem (jak w CPU-002), albo odrzucać w `compile_scenes.py` sekrety z `pmg_y + height > 240` (walidacja w edytorze już istnieje dla platform).
* **Szacowany efekt:** ochrona przed artefaktem; ~8 B kodu.
* **Koszt i ryzyko:** niski.
* **Pewność oceny:** wysoka co do mechanizmu, średnia co do prawdopodobieństwa wystąpienia.
* **Weryfikacja:** test py65 z `secrets_pmg_y = 250`, sprawdzenie, że `$6B00` pozostaje nietknięte.

### DATA-001 — 84 B narzutu na wskaźniki dla każdej nowej sceny

* **ID:** DATA-001
* **Tytuł:** Zastąpić 42 pary wskaźników scen pojedynczym deskryptorem sceny
* **Priorytet:** niski dziś, wysoki przy 4+ scenach
* **Kategoria:** dane / architektura
* **Lokalizacja:** `gen/scenes_data.asm` (sekcja `MASTER SCENE INDEX TABLES`), `scripts/compile_scenes.py:1320-1520`
* **Obserwacja:** Dla każdej z 42 tabel danych emitowana jest para `*_lo/*_hi` z 1 bajtem na scenę — 84 B/scenę (dziś 168 B dla 2 scen).
* **Problem/potencjał:** Narzut rośnie liniowo i przy 6 scenach wyniesie 504 B, czyli więcej niż cała sekcja DLI jednej sceny.
* **Rozwiązanie:** Tabele jednej sceny są emitowane **blokowo i w stałej kolejności** — wystarczy jeden wskaźnik bazowy na scenę + wspólna (jedna) tabela offsetów wewnątrz bloku. Wtedy `scene_elem_tileset_lo,x` staje się `base + ELEM_TILESET_OFF`.
* **Szacowany efekt:** −80 B na każdą scenę powyżej pierwszej; −168 B już dziś, ale kosztem ~40 B kodu i przepisania 17 miejsc odczytu.
* **Koszt i ryzyko:** średni/wysoki (dotyka renderera, sekretów, DLI, status line). **Nie zalecam teraz** — dopiero gdy powstaną >3 sceny.
* **Pewność oceny:** wysoka co do arytmetyki, średnia co do realnego zysku netto.
* **Weryfikacja:** `gen/main.lab` (zniknięcie par wskaźników), `pytest`, testy `test_render_scene.py`.


### ARCH-001 — Dwie rozpisane drabiny dyspozytora stanów

* **ID:** ARCH-001
* **Tytuł:** Zastąpić 8 porównań `cmp` tablicą skoków (init i run)
* **Priorytet:** niski
* **Kategoria:** architektura / ROM
* **Lokalizacja:** `main.asm:69-160`
* **Obserwacja:** Dla 4 stanów istnieją dwa łańcuchy `sta current_state / cmp #STATE_x / bne` i 4 osobne `jmp`.
* **Problem/potencjał:** ~30–40 B kodu i 4 miejsca do edycji przy każdym nowym stanie (np. ekran „credits”).
* **Rozwiązanie:** dwie tablice `dl init_vec_lo/hi`, `run_vec_lo/hi` + `asl/tay/lda (tab),y/jmp`. Koszt: ~24 B tablic.
* **Szacowany efekt:** −10…−16 B netto (oszczędność kosmetyczna), głównie czytelność i rozszerzalność.
* **Koszt i ryzyko:** niski, ale **zysk bajtowy jest na granicy szumu** — traktować jako porządek, nie optymalizację.
* **Pewność oceny:** wysoka co do rozmiaru, niska co do opłacalności.
* **Weryfikacja:** `gen/main.lab`, przejście wszystkich przejść stanów (`pytest` + Altirra).

### ARCH-002 — Model pamięci nie pozwoli dodać kolejnych scen bez stronicowania

* **ID:** ARCH-002
* **Tytuł:** Zaplanować jeden slot tilesetu ładowany per scena
* **Priorytet:** średni (strategiczny)
* **Kategoria:** architektura / pamięć
* **Lokalizacja:** `main.asm:27,420-429` (`TILES_ADDR`, `ins`), `Makefile:87-89`, `manifest.yaml:78-92`
* **Obserwacja:** Wszystkie 4 tilesety są rezydentne (`$8000–$BF6C`, 16 237 B). Manifest i katalog `tiles/` zapowiadają kolejne światy (`castles`, `depths`, `hell`, `trees`), a każdy nowy tileset to 2–6,5 KB.
* **Problem/potencjał:** Nawet po MEM-001/002/003/006 zapas ~15 KB wystarczy na 2–3 tilesety i dane scen; powyżej tego projekt utknie. Dodatkowo `tilesets` są mapowane na stałe identyfikatory (`TILESET_CASTLES = 0`…), więc każda zmiana zestawu wymaga renumberacji.
* **Rozwiązanie (koncepcja, nie wdrożenie):**
  1. jeden slot 6 144 B w `$A000–$B7FF` na „aktywny” tileset sceny,
  2. mały loader (SIO/DCB lub `OS` `open/read`) czytający `TILESn.BIN` przy `game_init` (~150–250 B kodu),
  3. w `scenes_data.asm` podmiana `tileset_id` na numer pliku, a `tileset_data_lo/hi` na adres slotu.
  Koszt: ~300–400 B kodu + nośnik z plikami; zysk: nieograniczona liczba tilesetów przy stałym RAM.
* **Szacowany efekt:** brak oszczędności natychmiastowej; **usuwa sufit skalowania** (dziś ~15 KB po Tier 1).
* **Koszt i ryzyko:** wysoki (nowy kod I/O, obsługa błędów, zależność od DOS-u, czas ładowania ~0,5–2 s na scenę). Wymaga też zmiany `Makefile` na budowę wielu plików i dyskietki/ATR.
* **Pewność oceny:** wysoka co do ograniczenia, średnia co do wybranej techniki (SIO vs DOS vs kompresja).
* **Weryfikacja:** pomiar czasu przejścia między scenami w Altirrze, `check_memory.py` z jednym slotem.

### STAB-005 — `dec player_lives` bez kontroli zera

* **ID:** STAB-005
* **Tytuł:** Zabezpieczyć licznik żyć przed niedomknięciem do 255
* **Priorytet:** niski
* **Kategoria:** stabilność
* **Lokalizacja:** `engine/player.asm:1113-1128`
* **Obserwacja:** `dec player_lives` jest wykonywane bez sprawdzenia, czy wartość jest > 0. `status_line_lose_life` (`status_line.asm:139-146`) ma takie zabezpieczenie, `player_handle_death` — nie.
* **Problem/potencjał:** Podwójne wywołanie w jednej klatce (np. przyszła kolizja z wrogiem + upadek) da 255 żyć.
* **Rozwiązanie:** `lda player_lives / beq @game_over / dec player_lives` (6 B).
* **Szacowany efekt:** ochrona przed błędem; 0 B oszczędności.
* **Koszt i ryzyko:** bardzo niski.
* **Pewność oceny:** wysoka.
* **Weryfikacja:** test py65 z `player_lives = 0` i wywołaniem `player_handle_death`.


---

## 9. Plan optymalizacji

### Etap 1 — duża korzyść, niskie ryzyko (można wdrożyć niezależnie, w dowolnej kolejności)

| Krok | ID | Zmiana | Efekt |
|---|---|---|---|
| 1.0 | **STAB-006** | `ldx active_scene_id` przed odczytem tabel platform + test dla sceny 1 | **✅ zrobione w `163ce06`** |
| 1.1 | STAB-004 | reset `active_scene_id`/żyć/CD + sprawdzenia zakresu w `secrets_init`, `player_init`, `status_line_init` | **✅ zrobione w `163ce06`** |
| 1.2 | MEM-001 | usunięcie `depths`/`hell` z binarki i manifestu | −10 641 B RAM/pliku |
| 1.3 | MEM-004 | deduplikacja klatek w `compile_sprites.py` | −112 B |
| 1.4 | MEM-006 + ROM-001a | skrócenie czyszczenia PMG do `$6B00–$6FFF`, wspólna procedura `clear_pmg` | +768 B RAM, −~34 B kodu |
| 1.5 | MEM-005 | usunięcie zerowych buforów z XEX + aktualizacja `check_memory.py` | −5 888 B pliku |
| 1.6 | STAB-005 | kontrola zera w `player_handle_death` | brak ryzyka 255 żyć |

**Po etapie 1:** segmenty ~28 398 B, wolne ~12 582 B + 768 B w ogonie PMG = **~13 350 B**; plik ~22,5 KB.

### Etap 2 — wymaga umiarkowanych prac (dotyka generatorów i testów)

| Krok | ID | Zmiana | Efekt |
|---|---|---|---|
| 2.1 | MEM-002 | `--crop-to-scenes` w `convert_tiles.py`, przycięcie `castles` | −1 144 B |
| 2.2 | MEM-003 | usunięcie martwych tabel scen + aktualizacja 2 plików testów | −526 B |
| 2.3 | MEM-007 | martwe tabele DLI/metadanych + `zp_frame_cnt` + `dli_title_restore` | −57 B RAM, −20 B ROM |
| 2.4 | CPU-001 | warunkowe pominięcie czyszczenia PMG | ~−600 cykli/klatkę |
| 2.5 | CPU-002 | blit PMG z policzonym `count` | ~−250 cykli/klatkę |
| 2.6 | ROM-001b | wspólne `wait_vblank` i debounce fire | −~110 B kodu |

**Po etapie 2:** wolne **~15 077 B** (37 % okna `$2000–$BFFF`), plik ~20,8 KB.

### Etap 3 — większe zmiany architektoniczne (tylko jeśli planujesz rozwój)

| Krok | ID | Zmiana | Kiedy |
|---|---|---|---|
| 3.1 | ROM-002 | wspólna procedura skanu platform | gdy fizyka ma być dalej rozbudowywana (wymaga testów regresyjnych) |
| 3.2 | ROM-003 | restrukturyzacja strefy 0 DLI | gdy brakuje 75 B w kodzie (niski priorytet) |
| 3.3 | ARCH-001 | tablice skoków dyspozytora | porządek, nie zysk |
| 3.4 | DATA-001 | deskryptor sceny zamiast 42 par wskaźników | gdy liczba scen > 3 |
| 3.5 | ARCH-002 | slot tilesetu + loader per scena | gdy tilesety przestaną się mieścić (po ~3 nowych światach) |

### Zależności między zmianami

```
STAB-004 ── niezależne (zrobić pierwsze: bug)
MEM-001 ── niezależne, ale MUSI poprzedzić MEM-002 (renumberacja TILESET_*)
MEM-006 ── łączyć z ROM-001a (te same pętle czyszczenia) i aktualizacją komentarzy main.asm
MEM-003 ── MUSI być zsynchronizowane z compile_scenes.py + test_compile_scenes.py + test_platform_profiles.py
MEM-007 ── zmienia DLI_TABLE_COUNT 34→33 ⇒ musi być zrobione razem z generatorem danych DLI
MEM-005 ── wymaga rozszerzenia check_memory.py o „obszary zarezerwowane, nieemitowane”
CPU-001 ── łączyć z CPU-002 (ta sama procedura player_render_frame)
DATA-001 ── dopiero PO MEM-003 (inaczej przepisujesz martwe tabele)
ARCH-002 ── po MEM-001/MEM-002 (dopiero wtedy wiadomo, ile zostaje miejsca)
```

**Czego nie robić:** kompresji RLE (zmierzona, nieopłacalna), redukcji stride buforów DLI z 8 na 6 (136 B za ryzyko w timingu), przepisywania lustrzanych klatek bohatera (zysk zerowy), usuwania podwójnego zapisu `SDMCTL`/`DMACTL` (8 cykli), zamiany `dli_handler` na cokolwiek innego (jest wzorowy).


---

## 10. Plan pomiarów i weryfikacji

### 10.1. Pomiar zużycia RAM i rozmiaru kodu

| Co mierzyć | Jak | Punkt odniesienia (dziś) |
|---|---|---|
| Zajętość segmentów i zapas | `.venv\Scripts\python.exe scripts\check_memory.py call_of_the_wintermon.xex` | 39 131 B / 1 829 B |
| Mapa adresowa symboli | `gen/main.lab` (MADS `-t:`) + porównanie adresów etykiet między buildami | np. `DLI_HANDLER = $656C`, `TILES_DATA_END = $BF6D` |
| Rozmiar konkretnej procedury | różnica adresów kolejnych etykiet w `gen/main.lab` (np. `PLAYER_JUMP_UPDATE $5B22` − `PLAYER_UPDATE $5928` = 506 B) | — |
| Szczeliny między segmentami | skrypt liczący `next_start - prev_end` z `parse_xex_segments()` (`check_memory.py:17-45`) | 825 B @ `$4CC7`, 151 B @ `$2F69`, 147 B @ `$BF6D`… |
| Rozmiar pliku | `Get-Item call_of_the_wintermon.xex` | 39 197 B |

**Uwaga:** po MEM-005 `check_memory.py` będzie zaniżał zajętość o 5 888 B. Przed wdrożeniem trzeba dodać statyczną listę obszarów zarezerwowanych (`$3000–$3EFF`, `$6800–$6FFF`) i sumować je niezależnie od segmentów pliku.

### 10.2. Pomiar cykli krytycznych procedur

W projekcie **już istnieje** harness, którego nie trzeba pisać od zera (`tests/test_dli_system.py`: `load_xex_and_symbols()`, `run_subroutine()`). Wystarczy dodać pomiar `mpu.processorCycles`:

```python
# koncepcja testu pomiarowego — wyłącznie szkic do raportu, nie plik projektu
from py65.devices.mpu6502 import MPU
mem, labels = load_xex_and_symbols()
mpu = MPU(memory=mem)
mpu.sp = 0xFD
mem[labels["ACTIVE_SCENE_ID"]] = 0
start = mpu.processorCycles
run_subroutine(mpu, labels["PLAYER_RENDER_FRAME"])
print("player_render_frame:", mpu.processorCycles - start)   # oczekiwane ~600-1400
```

Procedury do zmierzenia (kolejność wg wpływu):

| Procedura | Co porównać | Oczekiwany kierunek |
|---|---|---|
| `player_render_frame` | 60 klatek chodzenia (bez ruchu pionowego) i 20 klatek skoku | CPU-001: −~600 cykli w klatkach chodzenia |
| `game_run` w fazie `PLAYING` (cała ścieżka) | suma cykli na klatkę | CPU-001/002: −~850 cykli |
| `dli_vblank_update` | 1 wywołanie | bez zmian (kontrola regresji) |
| `render_scene_background` | 1 wywołanie dla obu scen | bez zmian (kontrola regresji) |
| `secrets_update` | klatka ze zmianą animacji | bez zmian |

**Czego py65 nie zmierzy:** realnego timingu DLI względem `WSYNC`/`VCOUNT` — do tego potrzebny Altirra (podgląd `VCOUNT` w debuggerze / Performance Analyzer). Zalecany test: wstrzymać grę w losowych klatkach i sprawdzić, czy `VCOUNT` w handlerze DLI mieści się w oczekiwanym zakresie linii.

### 10.3. Weryfikacja poprawności po zmianach

1. **Automatycznie:** `.venv\Scripts\python.exe -m pytest -q` — kluczowe zestawy: `test_player_movement.py`, `test_player_spawn.py`, `test_secrets_runtime.py`, `test_dli_system.py`, `test_render_scene.py`, `test_status_line.py`, `test_state_machine_and_fade.py`, `test_compile_scenes.py`, `test_convert_tiles.py`, `test_compile_sprites.py`.
2. **Po MEM-003:** testy `test_compile_scenes.py:171-176` i `test_platform_profiles.py:404-414` **muszą** zostać zmienione razem z generatorem — inaczej build będzie „czerwony” z powodu usunięcia tabel, nie z powodu błędu.
3. **Po MEM-001/002:** nowy test w `test_convert_tiles.py` sprawdzający, że każdy tileset użyty w `scenes/*.json` ma wygenerowaną bitmapę (zabezpieczenie przed „scena wskazuje usunięty tileset”).
4. **Ręcznie w Altirrze (checklista):** tytuł → scroll → intro → gra; w **scenie 2** bohater musi stać wyłącznie na widocznych platformach (STAB-006); zebranie wszystkich CD w scenie 1 → scena 2 → ukończenie → ekran końcowy → powrót do tytułu → **nowa gra od sceny 1 z 3 życiami i 0 CD** (STAB-004); upadek poza ekran → respawn; wyczerpanie żyć → ekran końcowy.

### 10.4. Porównanie „przed/po”

| Metryka | Przed | Po etapie 1 | Po etapie 2 |
|---|---:|---:|---:|
| Segmenty w XEX | 39 131 B | ~28 398 B | ~26 651 B |
| Wolne poniżej `$C000` | 1 829 B | ~13 350 B | **~15 077 B** |
| Rozmiar pliku XEX | 39 197 B | ~22,5 KB | ~20,7 KB |
| Cykle `player_render_frame` (chodzenie) | ~1 400 | ~800 | ~550 |
| Liczba tabel DLI | 34 | 34 | 33 |


---

## 11. Ograniczenia i niepewności

**Czego nie udało się ustalić:**

1. **Rzeczywistego czasu wykonania** żadnej procedury — wszystkie wartości cykli w raporcie to szacunki z listingu. Nie uruchamiałem emulatora ani testów (zakaz tworzenia plików; `pytest` dopisałby nowe wpisy do `.pytest_cache`).
2. **Czy `active_scene_id = SCENE_COUNT` prowadzi do widocznego błędu** — prześledziłem kod (brak sprawdzeń zakresu w `secrets_init`/`player_init`/`status_line_init`), ale nie wywołałem tej ścieżki. Pewność: wysoka co do kodu, średnia co do objawu.
3. **Czy zapisy PMG po VBLANK mieszczą się w górnym blanku** (STAB-001) — potrzebny pomiar `VCOUNT` w Altirrze.
4. **Czy `title.bin` i tilesety są optymalnie skwantyzowane** — konwersja używa k-means na luminancji (`convert_tiles.py:62-100`); ocena jakości wymaga porównania wizualnego, nieobjętego audytem.
5. **Czy muzyka w `gen/title_music.asm` (1 612 B) nie zawiera powtarzalnych wzorców** do skompresowania przez referencje — nie analizowałem struktury utworu (tylko rozmiar i API).
6. **Czy region `$0800–$1FFF` jest realnie wolny** przy typowym `MEMLO` DOS-u 2.5 — zależy od sposobu uruchamiania; nie testowałem.

**Wnioski oparte na szacunkach:** wszystkie liczby cykli (sekcja 5, CPU-001/002), wpływ MEM-005 na czas ładowania, wpływ ARCH-002 na czas przejścia między scenami.

**Wnioski oparte na pomiarach:** rozmiary segmentów, adresy etykiet, rozmiary plików, bounding-boxy tilesetów, liczba duplikatów klatek, współczynniki RLE, liczba referencji do martwych tabel (grep).

---

## 12. Końcowe wnioski

### 12.1. Najbardziej opłacalne kierunki

1. **Pamięć jest jedynym realnym ograniczeniem projektu — i jest w większości odzyskiwalna tanio.** 10 641 B martwych tilesetów, 768 B niewidocznego PMG, 526 B martwych tabel scen i 1 144 B niepotrzebnej szerokości `castles` to łącznie **13 079 B**, czyli 33 % obecnego obrazu — do odzyskania bez zmiany architektury i bez ryzyka dla rozgrywki. Zapas rośnie z 1 829 B do ~15 KB.
2. **Kod jest w dobrym stanie i nie wymaga refaktoryzacji „dla porządku”** — 5 892 B na grę z 4 ekranami, DLI, PMG i muzyką to wynik bardzo dobry. Realne rezerwy w kodzie (~150–400 B) są mniejsze niż w danych i wiążą się z wyższym ryzykiem.
3. **Jedyne miejsce, gdzie architektura naprawdę przeszkadza, to brak stronicowania zasobów.** Dopóki wszystkie tilesety są rezydentne, każdy nowy świat kosztuje 2–6,5 KB z wąskiego budżetu. To decyzja na przyszłość, ale warto ją podjąć **przed** narysowaniem trzeciego tilesetu.
4. **Timing DLI jest zrobiony dobrze i nie należy go ruszać.** Jedyny „dług” w tym obszarze to martwa tabela `prior` i 136 B nieużywanych wpisów buforów — pierwsza do usunięcia, druga do zostawienia.

### 12.2. Proponowana kolejność wdrażania

1. ~~**STAB-006** (platformy sceny 0 w scenie 2)~~ — **✅ zrobione w `163ce06`**.
2. ~~**STAB-004** (bug resetu stanu)~~ — **✅ zrobione w `163ce06`**.
3. **MEM-001** — jedna zmiana, 10,6 KB.
4. **MEM-004 + MEM-006/ROM-001a + MEM-005** — trzy małe, niezależne zmiany, kolejne ~0,9 KB RAM i 5,9 KB pliku.
5. **MEM-002 + MEM-003 + MEM-007** — wymagają pracy w generatorach i testach, ale są przewidywalne.
6. **CPU-001 + CPU-002** — po ustabilizowaniu pamięci; mierzalne w py65.
7. **ROM-001** — porządki w kodzie, na końcu etapu 2.
8. **ROM-002 / DATA-001 / ARCH-002** — tylko jeśli projekt ma rosnąć; wtedy najpierw decyzja o modelu ładowania zasobów.

### 12.3. Jedno zdanie podsumowania

Gra jest napisana lepiej niż przeciętnie, ale wozi w RAM 13 KB danych, których nie używa — i to, a nie liczba instrukcji w pętli gry, jest realnym hamulcem rozwoju projektu.

