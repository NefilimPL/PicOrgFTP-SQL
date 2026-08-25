# OCR: widoczna kolejka i aktywnosc blokujaca

## Cel

Kolejka dopracowywania OCR ma byc krotkim, bezpiecznym podgladem w glownym
widoku aplikacji, a nie elementem ustawien. Ma pokazywac, co jest skanowane i
co zostalo odczytane, bez blokowania pracy w tle przez samo przegladanie
aplikacji. Wycinki maja zawierac niewielki margines oraz byc pokazywane bez
kwadratowego kadrowania.

## Widok kolejki

- Panel `Kolejka dopracowywania OCR` znajduje sie po lewej stronie, bezposrednio
  pod istniejacym panelem kolejki zadan, przed sekcja slotow.
- W liscie widac najwyzej piec pozycji. Kolejnosc to: przetwarzane, oczekujace,
  a potem najnowsze zakonczone pozycje.
- Gdy istnieja dalsze pozycje, naglowek pokazuje liczbe, na przyklad
  `+7 kolejnych`.
- Jedna pozycja ujawnia tylko miniaturke wycinka, stan i wynik OCR. API nie
  przekazuje sciezek, hashy obrazu, nazwy produktu ani danych wlasciciela.
- Administrator zawsze moze zobaczyc panel. Przelacznik
  `Pokaz kolejke dopracowywania OCR uzytkownikom` kontroluje widocznosc panelu
  dla zwyklych zalogowanych uzytkownikow i jest domyslnie wylaczony.
- Zakonczony wynik jest dostepny najwyzej 10 sekund. Po tym czasie kolejkowy
  rekord, wynik i pomocniczy plik wycinka sa usuwane. Oczekujace oraz aktualnie
  przetwarzane pozycje nie podlegaja temu limitowi.

## Wycinki kolejki

- Wycinek kolejki otrzymuje dodatkowy symetryczny margines 8 px z kazdej strony
  przed przycieciem do granic oryginalnego obrazu, a potem jest skalowany i
  wyostrzany jak dotychczas.
- Ramka zadania wskazuje rozszerzony wycinek, dlatego przywracanie wspolrzednych
  wyniku do obrazu zrodlowego odbywa sie wzgledem jego rzeczywistego poczatku.
- Miniatura uzywa proporcjonalnego dopasowania (`contain`), wiec nie jest
  obcinana do kwadratu.

## Aktywnosc OCR

Bezynnosc kolejki jest osobnym sygnalem, a nie skutkiem kazdego zadania HTTP.
Za aktywnosc blokujaca uznawane sa tylko:

1. wyslanie lub zastapienie pliku w slocie;
2. lokalne przeniesienie albo zamiana plikow miedzy slotami;
3. usuniecie pliku ze slotu;
4. uruchomienie `Synchronizuj`;
5. ladowanie danych produktu albo jego zdjec.

Wejscie w ustawienia, odczyt ich statusu, przegladanie logow, zwykle odswiezanie
widokow, edycja i podglady Pimcore oraz pobieranie postepu OCR nie resetuja
okresu bezczynnosci. Kolejka nadal nie rozpoczyna nowego wycinka podczas
trwajacego oznaczonego zadania, a po wykryciu takiej aktywnosci bezpiecznie
odklada juz przejety, lecz jeszcze nieprzetworzony wycinek.

Usuniecie pliku ze slotu natychmiast anuluje oczekujace wycinki o tym samym
haszu zawartosci oraz usuwa ich pomocnicze pliki. Nie usuwa zakonczonych danych
OCR, ktore sa juz bezpiecznie powiazane z niezmiennym obrazem i sa filtrowane
przez aktualnie wybrane sloty.

## Dane i API

- Ustawienia OCR dostaja `background_queue_visible_to_users: bool`.
- Magazyn kolejki dostaje operacje bezpiecznego oczyszczenia zakonczonych zadan
  starszych niz TTL oraz anulowania oczekujacych zadan po haszu obrazu. Obie
  zwracaja wylacznie wewnetrzne sciezki plikow do kontrolowanego sprzatania po
  stronie serwera.
- Publiczny endpoint kolejki zwraca co najwyzej piec bezpiecznych pozycji oraz
  liczbe pozostalych. Dla zwyklego uzytkownika jest dostepny tylko przy
  wlaczonym przelaczniku widocznosci; administrator ma dostep zawsze.
- Middleware rozdziela zwykle zadania HTTP od zadan oznaczonych jako aktywnosc
  OCR. Dla akcji lokalnych bez zadania HTTP przegladarka wysyla maly, chroniony
  CSRF sygnal aktywnosci. Usuniecie wysyla dodatkowo bezpieczny token pliku;
  serwer sam oblicza hash i anuluje pasujace zadania.

## Testy akceptacyjne

1. Zwykly uzytkownik widzi do pieciu bezpiecznych pozycji tylko po wlaczeniu
   widocznosci, a administrator widzi je zawsze.
2. Szosta i kolejne pozycje nie sa zwracane jako elementy listy, lecz zwiekszaja
   licznik pozostalych.
3. Zakonczony wynik i plik wycinka znikaja po 10 sekundach, podczas gdy zadania
   pending i processing pozostaja.
4. Wycinek z regionu przy krawedzi obrazu dostaje 8 px kontekstu, o ile granica
   obrazu na to pozwala, a miniatura zachowuje proporcje.
5. Ustawienia i odczyt Pimcore nie resetuja bezczynnosci; upload, przesuniecie
   slotu, usuniecie, synchronizacja i ladowanie danych resetuja ja.
6. Usuniecie slotu anuluje oczekujace wycinki tego obrazu przed ich skanowaniem.
