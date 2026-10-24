# Mechanika gry „Call of the Wintermon”

Oct 17, 2026 · @Greg

## 1. Założenia ogólne

„Call of the Wintermon” to platformówka na Atari 8-bit, złożona z kolejnych scen. W każdej scenie gracz porusza się po platformach, zbiera Sekrety i unika Wrogów. Scena jest ukończona, gdy gracz zbierze wszystkie jej Sekrety. Gra jest ukończona, gdy zostaną ukończone wszystkie sceny.

| Pojęcie | Znaczenie |
| --- | --- |
| Scena | Obszar rozgrywki z własnym układem platform, Sekretów i Wrogów oraz własną pozycją startową gracza. |
| Platforma | Element otoczenia będący pełną przeszkodą. |
| Sekret | Obiekt zbierany przez dotknięcie. |
| Etap Sekretów | Grupa Sekretów tego samego typu, która musi być w całości zebrana, by odblokować kolejną grupę. |
| Wróg | Obiekt, którego dotknięcie powoduje śmierć gracza. |
| Życie | Jedna próba kontynuowania gry. Gracz zaczyna grę z 3 życiami. |
| Linia statusowa | Dolna linia ekranu (ANTIC 2) prezentująca stan żyć, nazwę sceny i zebrane płyty CD. |

## 2. Sekrety

### 2.1. Zbieranie

Sekret zbiera się przez bezpośredni kontakt z nim, bez żadnego dodatkowego przycisku. Zebrany Sekret znika z ekranu, przestaje być aktywny i nie może zostać zebrany ponownie. Każda scena zawiera co najmniej jeden Sekret.

### 2.2. Etapy i zależności

Zależności między Sekretami definiuje się w Atari Scene Editor. Zależność dotyczy całej grupy Sekretów danego typu, nie pojedynczych egzemplarzy.

Przykład: Etap 1 to wszystkie Sekrety typu `Klucz`. Etap 2 to wszystkie Sekrety typu `Drzwi`, zależne od `Klucza`. Kolejne etapy działają tak samo, jeśli scena je zawiera.

1. Na początku sceny widoczne i aktywne są wszystkie Sekrety bez zależności (Etap 1).
2. Sekrety zależne od innej grupy są ukryte i nieaktywne.
3. Gdy gracz zbierze wszystkie Sekrety bieżącego etapu, następny etap aktywuje się: wszystkie jego Sekrety pojawiają się jednocześnie w pozycjach zapisanych w danych sceny.
4. Zebranie części Sekretów etapu nie odblokowuje niczego.
5. Etapy tworzą jeden liniowy łańcuch. Nie występują rozgałęzienia, zależności cykliczne ani równoległe łańcuchy.
6. Jeśli scena nie ma żadnych zależności, wszystkie jej Sekrety są dostępne od początku i tworzą jeden etap.
7. Scena jest ukończona dopiero po zebraniu wszystkich Sekretów ze wszystkich etapów.

**Kanały sprite'ów (ograniczenie sprzętowe):** każdy wiersz platformy dysponuje czterema kanałami PMG - trzech graczy (P1..P3) oraz piątego gracza (cztery pociski złożone w jeden sprite 8 px). Wrogowie zawsze zajmują swoje kanały pierwsi, a Sekrety danego etapu wypełniają pozostałe, dlatego w jednym wierszu i jednym etapie zmieści się razem najwyżej cztery obiekty (wrogowie + Sekrety). Kanał wybiera się per definicja Sekretu w katalogu edytora: `player` (sprite gracza, 8 px, własny kolor `COLPM1..3`) albo `missiles` (domyślny, piąty gracz, `COLPF3`). Sprite jest pakowany pod wybrany kanał, więc jedna grafika nie może obsłużyć obu kanałów naraz.

### 2.3. Sekrety a śmierć gracza

Śmierć nie cofa postępu w scenie:

- zebrane Sekrety pozostają zebrane,
- odblokowane etapy pozostają odblokowane,
- niezebrane Sekrety odblokowanych etapów zostają na swoich miejscach,
- Sekrety nieodblokowanych etapów pozostają ukryte.

Stan Sekretów jest przechowywany przez cały czas trwania sceny. Po wejściu do nowej sceny stan Sekretów jest budowany od początku zgodnie z danymi tej sceny.

### 2.4. Przejście do następnej sceny

Po zebraniu ostatniego Sekretu sceny:

1. Rozgrywka w bieżącej scenie zostaje zakończona.
2. Jeśli istnieje następna scena, wyświetla się jej nazwa z efektem `fade-in`.
3. Nazwa pozostaje na ekranie przez 2 sekundy.
4. Następuje `fade-out`.
5. Rozpoczyna się rozgrywka w nowej scenie, z graczem na jej pozycji startowej.

Liczba żyć zachowuje się między scenami. Po ukończeniu ostatniej sceny gra kończy się sukcesem (patrz p. 7.2) bez sekwencji prezentacji nazwy.

### 2.5. Linia statusowa (HUD) i licznik płyt CD

Na dole ekranu wyświetlana jest stała linia statusowa (jeden wiersz tekstu w trybie ANTIC 2, 40 znaków):

- **Po lewej stronie:** liczba pozostałych żyć w postaci symboli serc (początkowo 3 serca, znak o kodzie wewnętrznym 64 / `@`). Każda utrata życia natychmiast gasi jedno serce.
- **Na środku:** wycentrowana nazwa bieżącej sceny.
- **Po prawej stronie:** dwucyfrowy licznik zebranych płyt CD (zakres od `00` do `99`).

Zebranie Sekretu typu płyta CD (`cd`) zwiększa licznik o 1 (do maksymalnej wartości 99). Licznik CD oraz liczba pozostałych żyć są zachowywane pomiędzy kolejnymi scenami. Śmierć gracza nie cofa zebranych płyt CD ani nie zmniejsza licznika. Stan licznika CD zeruje się dopiero po zakończeniu całej gry (`Game Over`) i rozpoczęciu nowej rozgrywki.

## 3. Platformy i ruch

### 3.1. Platformy jako pełne przeszkody

Platformy nie są jednostronne. Kolizje uwzględniają rzeczywiste położenie i rozmiar postaci oraz platformy:

- **Od góry:** gracz ląduje na platformie i może po niej chodzić.
- **Od dołu:** gracz nie może przejść przez platformę. Skok w górę kończy się zetknięciem z platformą i gracz zaczyna opadać.
- **Z boków:** platforma zatrzymuje ruch poziomy gracza.

### 3.2. Spadanie

Zejście poza krawędź platformy nie jest śmiercią, gracz zaczyna spadać. Jeśli w trakcie spadania zetknie się z niższą platformą zgodnie z zasadami kolizji, ląduje na niej i gra toczy się dalej. Jeśli spadnie poniżej dolnej granicy sceny, ginie.

## 4. Gracz

### 4.1. Reprezentacja i animacje

Gracz to jeden sprzętowy obiekt Player o indeksie 0. Korzysta z animacji zdefiniowanych w `player.sprite.json`:

| Animacja | Użycie |
| --- | --- |
| `right`, `left` | Ruch po platformie w prawo i w lewo |
| `right-jump`, `left-jump` | Skok, zgodnie ze zwrotem postaci |
| `kneel-right`, `kneel-left` | Klękanie, zgodnie ze zwrotem postaci |
| `death` | Śmierć |

### 4.2. Sterowanie

| Wejście | Efekt |
| --- | --- |
| Joystick w lewo / w prawo | Ruch w wybranym kierunku |
| FIRE | Skok krótki |
| Lewo lub prawo + FIRE | Skok długi w wybranym kierunku |
| Góra + FIRE | Skok długi do góry |
| Dół (poza skokiem) | Klękanie |

Typ skoku wybierany jest w chwili jego rozpoczęcia, na podstawie kombinacji wejść, i nie zależy od czasu przytrzymania FIRE. Trzy warianty skoku różnią się parametrami, aby umożliwić pokonywanie platform o różnej odległości i wysokości. Skok można rozpocząć tylko z podłoża.

Po wybiciu tor lotu nie zmienia się: prędkość pozioma jest stała w danym wariancie skoku, a joystick nie steruje postacią w powietrzu. Skok krótki i skok długi do góry nie mają własnego kierunku, więc używają animacji i zwrotu zgodnych z ostatnim kierunkiem ruchu postaci (`left-jump` albo `right-jump`). Nie ma osobnej animacji skoku pionowego.

### 4.3. Parametry skoków

Każdy wariant skoku ma własny, konfigurowalny zestaw parametrów:

| Parametr | Skok krótki | Skok długi w bok | Skok długi w górę |
| --- | --- | --- | --- |
| Prędkość pozioma | … | … | … |
| Początkowa prędkość pionowa | … | … | … |
| Maksymalna wysokość | … | … | … |
| Maksymalny zasięg poziomy | … | … | … |

Grawitacja jest wspólna dla wszystkich skoków. Wartości muszą być dobrane tak, aby wszystkie platformy przewidziane w scenach były osiągalne.

### 4.4. Klękanie

Gracz klęka, gdy joystick jest wychylony w dół, a gracz nie skacze i nie ginie. Po zwolnieniu kierunku dół wraca do ruchu lub bezruchu. Klękanie nie przerywa animacji śmierci i nie rozpoczyna skoku. Naciśnięcie FIRE podczas klękania jest ignorowane.

## 5. Wrogowie

Wróg jest zawsze aktywny. Dotknięcie Wroga powoduje śmierć gracza. Kolizje wykrywa sprzętowy mechanizm kolizji Atari. Jedno zetknięcie z Wrogiem to jedno zdarzenie śmierci i odejmuje dokładnie jedno życie. Ruch i parametry Wrogów są określone w danych gry i mechanika gracza ich nie zmienia.

Jeśli ostatni Sekret sceny zostaje zebrany w tej samej klatce, w której gracz dotyka Wroga, pierwszeństwo ma zebranie: scena zostaje ukończona, a śmierć nie następuje.

## 6. Śmierć i odrodzenie

Gracz ginie, gdy dotknie Wroga albo spadnie poniżej dolnej granicy sceny. Upadek na niższą platformę nie jest śmiercią.

### 6.1. Procedura śmierci

1. Gracz przechodzi w stan śmierci. Sterowanie i rozpoczynanie skoków są zablokowane, a dalsze kolizje z Wrogami są ignorowane.
2. Odtwarzana jest animacja `death`.
3. Odejmowane jest dokładnie jedno życie, jednorazowo, niezależnie od długości animacji.
4. Po zakończeniu animacji:
   - jeśli pozostało co najmniej jedno życie, gracz odradza się na pozycji startowej bieżącej sceny,
   - jeśli nie pozostało żadne, gra kończy się porażką.

### 6.2. Odrodzenie

Po odrodzeniu gracz stoi na pozycji startowej bieżącej sceny, a jego stan ruchu i skoku jest zresetowany. Odzyskuje sterowanie. Zebrane Sekrety i odblokowane etapy pozostają bez zmian. Pozycje i stan Wrogów nie są resetowane.

Gracz nie ma nietykalności po odrodzeniu. Nie jest ona potrzebna: pozycja startowa w każdej scenie (miejsce pierwszego pojawienia się i odrodzenia) jest bezpieczna i nie ma w jej pobliżu Wrogów.

## 7. Stany gry i zakończenie

Gra rozróżnia stany: aktywna rozgrywka, śmierć gracza, prezentacja nazwy sceny, zakończenie sukcesem, zakończenie porażką.

### 7.1. Porażka

Gdy po śmierci nie zostało żadne życie: ustawiana jest flaga `GAME_FAILED`, gra przechodzi do stanu `Game Over` i wyświetla planszę porażki. Rozgrywka nie może być kontynuowana.

### 7.2. Sukces

Po ukończeniu ostatniej sceny: ustawiana jest flaga `GAME_SUCCESS`, gra przechodzi do stanu `Game Over` i wyświetla planszę sukcesu. Flaga nie jest ustawiana po ukończeniu sceny, po której są kolejne.

Flagi `GAME_SUCCESS` i `GAME_FAILED` wzajemnie się wykluczają. Po `Game Over` nowa gra zawsze zaczyna się od pierwszej sceny z 3 życiami.

## 8. Scenariusze akceptacyjne

1. Na początku sceny widoczne są wyłącznie Sekrety bez zależności.
2. Zebranie części Sekretów etapu nie odblokowuje następnego etapu.
3. Zebranie wszystkich Sekretów etapu odblokowuje następny.
4. Scena nie kończy się przed zebraniem wszystkich Sekretów ostatniego etapu.
5. Po śmierci i odrodzeniu zebrane Sekrety i odblokowane etapy pozostają bez zmian.
6. Gracz może spaść na niższą platformę bez utraty życia, a spadek poniżej dolnej granicy sceny kończy się śmiercią.
7. Gracz nie przechodzi przez platformy od dołu ani z boków.
8. Każdy z trzech skoków jest wybierany zgodnie z kombinacją wejść.
9. Klękanie działa po wychyleniu joysticka w dół poza skokiem.
10. Kontakt z Wrogiem powoduje jedną śmierć i odejmuje dokładnie jedno życie.
11. Po śmierci gracz odradza się w bieżącej scenie, jeśli ma życia.
12. Po utracie ostatniego życia ustawiana jest flaga `GAME_FAILED`.
13. Po ukończeniu wszystkich scen ustawiana jest flaga `GAME_SUCCESS`, a nie po ukończeniu pojedynczej.
14. Zmiana sceny pokazuje nazwę: `fade-in`, 2 s pauzy, `fade-out`.
15. Zachowanie Wrogów nie zmienia się w wyniku działania mechaniki gracza.
16. Naciśnięcie FIRE podczas klękania nie rozpoczyna skoku.
17. Gdy ostatni Sekret zostaje zebrany w tej samej klatce co kolizja z Wrogiem, scena zostaje ukończona i śmierć nie następuje.
18. Po `Game Over` nowa gra zaczyna się od pierwszej sceny z 3 życiami.
19. Zebranie płyty CD zwiększa dwucyfrowy licznik CD na linii statusu o 1 (do maks. 99), a jego wartość jest zachowywana po śmierci gracza oraz po przejściu do następnej sceny.
20. Linia statusowa na dole ekranu na bieżąco odzwierciedla liczbę żyć (serca), wycentrowaną nazwę bieżącej sceny oraz aktualny stan licznika CD.
