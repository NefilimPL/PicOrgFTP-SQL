# OCR: porownanie modeli i diagnostyka wycinkow

## Cel

Tester OCR ma pokazywac, co wykryl model szybki i co dokladny model odczytal z wycinka wykrytego przez pierwszy model. Widok ma umozliwiac szybka diagnoze pomijanych pozycji, bledow dziesietnych, zlych wycinkow oraz kosztu czasowego kazdego etapu.

## Zakres

- Zachowac pochodzenie wyniku: model, region szybkiego modelu i przypisany wycinek modelu dokladnego.
- Zastapic splaszczona liste odczytow lista par w dwoch kolumnach.
- Wyswietlac te same pary na zywo oraz po zakonczeniu testu.
- Usunac redukcje czesci dziesietnej z porownan wartosci OCR.
- Dodac prog kwalifikacji wycinkow do modelu dokladnego oraz jednolity, symetryczny margines wycinka.
- Usunac nakladanie podpisow na obrazie i rozbudowac informacje po najechaniu.

## Model danych i przeplyw

Potok OCR zwraca raport etapowy zamiast samej scalonej listy pol tekstowych. Jedna pozycja raportu reprezentuje region znaleziony przez model szybki i zawiera:

- odczyt(y) szybkiego modelu, jego pole, pewnosc i czas etapu;
- oryginalne pole regionu oraz faktycznie zastosowany wycinek z marginesem;
- decyzje kwalifikacji do modelu dokladnego i jej przyczyne;
- wszystkie odczyty dokladnego modelu z tego wycinka, z polami w ukladzie wspolrzednych pelnego obrazu;
- czas utworzenia wycinka, czas dokladnego OCR i czas laczny pozycji.

Nie wolno scalac pol przed utworzeniem raportu, poniewaz usuneloby to przypisanie do modelu i wycinka. Dotychczasowy wynik diagnostyczny pozostaje dostepny jako zgodny, splaszczony widok pochodny z raportu dla pozostalych odbiorcow.

Dla skanu tylko szybkim modelem prawa kolumna otrzymuje status "model dokladny nie jest wlaczony". Dla skanu tylko dokladnym modelem wynik jest pokazany w prawej kolumnie ze statusem "model szybki nie jest wlaczony". Przy obu modelach kazdy wynik dokladny musi odnosic sie do regionu szybkiego modelu.

## Wartosc i porownanie

Tekst z OCR jest zawsze wyswietlany bez zmian. Klucz porownawczy zachowuje cala czesc dziesietna. Przecinek i kropka sa rownowaznymi separatorami tylko na potrzeby porownania: `23,4` jest rowne `23.4`, ale zadna z tych wartosci nie jest rowna `23`. Znaki niebedace liczba i separatorami pozostaja podstawa do uzasadnienia odrzucenia; nie sa widoczne jako zmodyfikowany tekst OCR.

## Kwalifikacja i wycinek

Ustawienie OCR otrzymuje liczbe calkowita od 0 do 100 z etykieta: "Skanuj dokladnym, gdy pewnosc szybkiego <= [%]". Kontrolka laczy suwak i pole liczbowe, ktore sa dwukierunkowo zsynchronizowane. Wartosc domyslna to 99.

- 100 oznacza skanowanie kazdego regionu (w tym dokladnie 100%).
- 50 oznacza skanowanie regionu o pewnosci 50% lub nizszej.
- Pominiety region nadal wystepuje w raporcie z dokladnym powodem, pewnoscia i aktywnym progiem.

Margines wycinka to 25% dluzszego boku regionu, zaokraglone do najblizszego piksela, z zakresem od 8 do 64 px. Jedna funkcja stosuje te sama wartosc do lewej, prawej, gornej i dolnej krawedzi, a dopiero potem ogranicza pole granicami obrazu. Raport ujawnia pola przed i po ograniczeniu, aby roznica przy krawedzi nie wygladala jak blad algorytmu.

## Interfejs

Tester pokazuje obraz oraz stale widoczna tabele z kolumnami "Szybki" i "Dokladny". Gdy model szybki znajdzie region, wiersz jest natychmiast dodawany; prawa komorka przechodzi przez stany oczekiwania, skanowania, wyniku, pominiecia albo braku odczytu. Komorki dokladnego modelu moga zawierac liste, gdy jeden wycinek zwroci wiele odczytow.

Niebieski oznacza szybki model, a bursztynowy dokladny. Najechanie lub fokus na wiersz podswietla jedynie powiazany region, wycinek i pola jego wyniku. Panel informacji po najechaniu zawiera tekst surowy i porownawczy, pewnosc, wspolrzedne, rozmiary obu pol, prog/decyzje oraz wszystkie czasy etapow i sumy.

Nakladki obrazowe w widoku zywo i koncowym uzywaja wspolnego renderera DOM. Rozmieszcza on podpisy kolejno nad, pod i po bokach pola, sprawdzajac kolizje. Gdy obraz jest za gesty, podpis jest przenoszony do pasa adnotacji przy obrazie; na samym obrazie zostaje zwiazany z nim znacznik. Nie rysuje sie tekstu jeden na drugim.

## Zdarzenia, bledy i czasy

Zdarzenia postepu oraz wynik koncowy przenosza identyfikator regionu i monotoniczne czasy rozpoczecia/zakonczenia. Czasy obejmuja: szybki OCR, przygotowanie wycinka, dokladny OCR na wycinku i caly test. Zdarzenia z modelu dokladnego aktualizuja wylacznie wlasciwy wiersz.

Brak modelu, przekroczony limit zasobow, anulowanie, pominiecie przez prog i brak tekstu sa osobnymi stanami wyswietlanymi w tabeli i panelu diagnostycznym; zaden nie moze zniknac jako pusta prawa kolumna.

## Weryfikacja

Testy jednostkowe i kontraktowe obejma:

- parowanie regionow szybkich z wieloma wynikami dokladnymi i poprawne tlumaczenie wspolrzednych;
- progi 50, 99 i 100 oraz przyczyne pominiecia;
- symetryczny margines, ograniczenie na krawedzi obrazu i raportowanie obu pol;
- klucze `23,4`, `23.4` i `23`, bez utraty cyfr po separatorze;
- czasy oraz identyfikatory regionow w zdarzeniach;
- stany interfejsu, kolumny zywej tabeli, dane diagnostyczne i logike niekolidujacych podpisow.
