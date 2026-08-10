# Wykrywanie plików z podobnych produktów w panelu webowym

## Cel

Panel webowy ma proponować pliki istniejące lokalnie w wariantach kolorystycznych tego samego produktu. Propozycje mają pomagać operatorowi, ale nie mogą samoczynnie modyfikować formularza ani zostać zapisane bez wyraźnej akceptacji dla każdego pliku.

Pierwszy zakres obejmuje panel webowy. Aplikacja desktopowa pozostaje poza zakresem tej implementacji.

## Definicja podobnego produktu

Produkt źródłowy jest podobny, gdy ma identyczne z produktem edytowanym wartości: `nazwa`, `typ`, `model` i `dodatek`, ale różni się zestawem kolorów. Wyszukiwanie obejmuje wyłącznie lokalne foldery produktów w istniejącej strukturze katalogów. Nie pobiera danych z FTP, SQL ani Pimcore.

Kolory są porównywane po znormalizowanym zestawie wartości, dzięki czemu kolejność pól koloru nie tworzy fałszywie innego wariantu. Folder bieżącego wariantu kolorystycznego jest zawsze wykluczony.

## Konfiguracja

Do wspólnej konfiguracji aplikacji zostanie dodana sekcja wykrywania plików podobnych:

- `enabled`: przełącznik globalny, domyślnie `false`;
- `slot_prefixes`: lista identyfikatorów slotów dopuszczonych do wykrywania, domyślnie pusta.

W widoku ustawień webowych administrator zobaczy przełącznik oraz listę checkboxów aktualnie zdefiniowanych slotów. Usunięte lub nieistniejące identyfikatory są pomijane podczas normalizacji. Jeżeli funkcja jest wyłączona lub lista slotów jest pusta, panel nie uruchamia wyszukiwania i nie pokazuje sugestii.

## Wykrywanie i deduplikacja

Po uzupełnieniu wymaganych pól produktu frontend wysyła odczytowe żądanie wykrywania. Żądanie jest opóźnione, a wynik jest ignorowany, gdy w międzyczasie zmieniła się tożsamość formularza.

Backend znajduje foldery o wspólnej nazwie, typie, modelu i dodatku, a następnie zbiera z nich wyłącznie pliki przypisane do dozwolonych slotów. Wykorzystuje istniejący indeks lokalnych plików, gdy jest dostępny, z bezpiecznym fallbackiem do katalogów na dysku.

Kandydaci są porządkowani stabilnie po folderze źródłowym i nazwie pliku. Różne nazwy nie oznaczają różnych kandydatów: pliki są porównywane po zawartości. Ten sam binarnie plik jest proponowany najwyżej raz. Niedostępne i nieczytelne pliki są pomijane oraz nie blokują formularza.

## Rozmieszczanie kandydatów

Każdy kandydat najpierw próbuje zająć taki sam dozwolony slot, z jakiego pochodzi w produkcie źródłowym. Gdy kilka folderów ma w tym samym slocie różne pliki, pierwszy zgodnie z porządkiem pozostaje w swoim odpowiadającym slocie; kolejne różne pliki trafiają kolejno do pierwszych wolnych dozwolonych slotów.

Slot jest niedostępny dla propozycji, gdy zawiera plik wybrany przez użytkownika albo już przypisanego kandydata. Własny upload lub usunięcie slotu odrzuca przypisaną do niego sugestię w bieżącym formularzu. Sugestia odrzucona w ten sposób nie jest automatycznie przenoszona do innego slotu.

## Interfejs slotów

Wykryty kandydat jest pokazany w slocie jako półprzezroczysty podgląd o kryciu 60% z informacją o folderze lub kolorze źródłowym i przyciskiem `Wczytaj z podobnego`.

Propozycje są domyślnie odrzucone: samo wykrycie, wyświetlenie lub przełączenie podglądu nie dołącza pliku do formularza ani zadania zapisu. Dopiero kliknięcie `Wczytaj z podobnego` akceptuje pojedynczy kandydat, dodaje go do roboczego stanu slotu i powoduje, że zostanie przetworzony przy późniejszym zapisie formularza.

Obok istniejących przełączników źródeł `LOCAL`, `FTP` i `SQL` pojawi się przycisk `PODOBNE`, ale wyłącznie dla slotu z wykrytym automatycznie kandydatem. Przycisk działa jak pozostałe przełączniki źródeł: zmienia podgląd w tym samym slocie na kandydata. Dla obrazu wyświetlana jest miniatura, a dla PDF osadzony, przeglądarkowy podgląd dokumentu w obszarze miniatury. Przycisk `Otwórz` otwiera aktualnie wybrane źródło podglądu w nowej karcie przeglądarki.

## API i bezpieczeństwo

Nowe API wymaga zalogowanego użytkownika i zwraca metadane kandydata, jego slot, identyfikator źródła oraz bezpieczny token pliku. Nie zwraca bezwzględnych ścieżek lokalnych. Token korzysta z istniejącej walidacji tokenów plików, a każdy endpoint pliku nadal wymaga zalogowanego użytkownika; podgląd i otwarcie pliku pozostają ograniczone do dozwolonych katalogów aplikacji.

Akceptowany kandydat korzysta z istniejącej ścieżki obsługi pliku istniejącego w formularzu. Backend traktuje go tak samo jak jawnie wybrany plik do slotu; nie ma osobnej automatycznej operacji kopiowania ani zapisu.

## Obsługa błędów

Brak folderów podobnych, brak dozwolonych slotów lub brak pasujących plików zwraca pustą listę sugestii. Błąd pojedynczego pliku zostaje pominięty. Błędy samego wyszukiwania są komunikowane krótkim stanem formularza i nie usuwają ręcznie wybranych plików, wcześniej wczytanych zdjęć ani danych produktu.

## Testy

Testy jednostkowe obejmą:

- normalizację ustawień i odrzucenie nieistniejących slotów;
- dopasowanie wyłącznie po nazwie, typie, modelu i dodatku przy innym zestawie kolorów;
- wykluczenie bieżącego wariantu kolorystycznego;
- filtrowanie wyłącznie do skonfigurowanych slotów;
- deduplikację po zawartości, niezależnie od nazwy pliku;
- przypisanie najpierw do slotu źródłowego i przepełnienie do kolejnych wolnych slotów;
- brak automatycznej akceptacji oraz akceptację dopiero po kliknięciu;
- odrzucenie sugestii po własnym uploadzie lub usunięciu slotu.

Testy API potwierdzą autoryzację, brak wycieku ścieżek lokalnych oraz działanie tokenów podglądu. Testy interfejsu potwierdzą widoczność `PODOBNE`, przełączanie źródła podglądu i przekazywanie zaakceptowanego pliku do istniejącego procesu zapisu.
