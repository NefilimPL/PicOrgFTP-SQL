# Kompaktowe logi, historia zmian i ważność sekretu Entra

## Cel

Zmniejszyć ilość przewijania w widoku logów na żywo i historii zmian, usunąć surowe obiekty JSON z głównego interfejsu oraz dodać automatyczne monitorowanie daty wygaśnięcia aktywnego Client Secret Microsoft Entra.

Zmiana nie tworzy nowej bazy danych. Dane operacyjne, cache Entra i deduplikacja przypomnień korzystają z istniejącego SQLite.

## Widok logów na żywo

Każde zdarzenie jest domyślnie jednym gęstym wierszem o wysokości około 32–36 px:

`czas | ważność | komunikat | użytkownik / EAN / zadanie | rozwinięcie`

- Wiersze oddziela cienka linia, a nie osobna karta z dużymi odstępami.
- Długi komunikat jest skracany wielokropkiem; pełna wartość pozostaje dostępna po rozwinięciu i w atrybucie tytułu.
- Kolor sygnalizuje ważność przez mały znacznik i delikatny akcent, bez migotania dla zdarzeń informacyjnych.
- Kliknięcie wiersza lub kontrolki rozwinięcia pokazuje zalecane działanie, typ wyjątku, traceback i ustrukturyzowane szczegóły.
- Na wąskim ekranie kontekst może przejść do drugiej linii; nie powstaje poziomy przewijany blok całej strony.
- Autoscroll, pauza, filtrowanie, bufor SSE i zachowanie kursora pozostają bez zmian.

Zakładki krytyczne, ostrzeżenia i zadania zachowują bogatsze karty incydentów. Gęsty układ dotyczy przede wszystkim zakładki Live.

## Historia zmian

### Widok domyślny

- Metadane operacji są jednym zwartym paskiem: rodzaj, ID zadania i Pimcore ID/ścieżka, gdy występują.
- Zmiany pól produktu oraz Pimcore są pojedynczymi wierszami `etykieta: przed → po`.
- Każdy zmieniony slot jest pojedynczym, rozwijanym wierszem:

  `Slot | operacja | plik przed → plik po | rozmiar przed → po | Local/FTP/SQL status + czas`

- Statusy providerów są krótkimi znacznikami: sukces, pominięcie, błąd, częściowy wynik lub brak żądania.
- Operacje zapisu i usuwania dla tego samego slotu pozostają osobnymi dowodami i nie zasłaniają się wzajemnie.

### Widok rozwinięty

Rozwinięcie slotu pokazuje tylko dane odnoszące się do tego slotu:

- nazwę i rozmiar pliku źródłowego;
- rodzaj przetwarzania, FIT i wstępne przetworzenie;
- czas przetwarzania;
- osobne operacje local/FTP/SQL z wynikiem, czasem i bezpiecznym opisem błędu.

Ogólne wyniki integracji nie są powtarzane pod listą slotów. Jeżeli zawierają informacje nieobecne przy slotach, trafiają do jednego zwijanego bloku `Dane techniczne`. Główny widok nie renderuje obiektów przez ogólny `JSON.stringify`.

Starsze rekordy bez nowego `change_set` zachowują komunikat zgodności. Ich surowe dane są dostępne wyłącznie w zwijanym bloku technicznym.

## Automatyczny odczyt daty Client Secret Entra

### Źródło danych

Backend uzyskuje token aplikacyjny dla istniejącej konfiguracji Tenant ID, Client ID i Client Secret, a następnie odczytuje Microsoft Graph:

- preferowane: `GET /v1.0/applications(appId='{client_id}')`;
- fallback: `GET /v1.0/applications?$filter=appId eq '{client_id}'`;
- pola: `appId`, `displayName`, `passwordCredentials`.

Do odczytu `passwordCredentials` wymagane jest uprawnienie aplikacyjne `Application.Read.All` z admin consent. `Mail.Send` nadal odpowiada wyłącznie za wysyłkę. Data ważności godzinnego access tokenu nie zastępuje daty Client Secret.

### Dopasowanie credentialu

- Backend porównuje bezpieczny `hint` zwrócony przez Graph z pierwszymi znakami skonfigurowanego Secret Value.
- Jedno jednoznaczne dopasowanie zostaje wybrane.
- Gdy nie ma dopasowania, można wybrać jedyny aktywny credential.
- Przy kilku możliwych credentialach backend nie zgaduje. Zwraca status `ambiguous`, nie ustawia daty i nie wysyła przypomnienia.
- Secret Value, access token, nagłówki Authorization oraz pełny identyfikator credentialu nie są zwracane do przeglądarki ani zapisywane w logach lub mailach.

### Blok ustawień

Karta `Microsoft Entra / Graph` pokazuje:

- status kontroli;
- nazwę aplikacji i nazwę credentialu;
- datę wygaśnięcia w czasie lokalnym oraz UTC w podpowiedzi;
- pozostałą liczbę dni;
- czas ostatniej udanej kontroli;
- informację, czy wynik pochodzi z bieżącego odczytu, czy z cache;
- przycisk `Sprawdź teraz`.

Brak `Application.Read.All` daje czytelny status konfiguracji z instrukcją dodania uprawnienia i admin consent. Jest to ostrzeżenie konfiguracyjne, a nie krytyczna awaria aplikacji.

Kontrola wykonuje się:

- po zapisaniu zmienionej konfiguracji Entra;
- po udanym teście kanału Entra;
- na żądanie przyciskiem `Sprawdź teraz`;
- cyklicznie raz na dobę przez istniejący worker powiadomień.

Chwilowa niedostępność Graph nie usuwa ostatniego poprawnego wyniku. UI oznacza go jako zapisany i pokazuje błąd ostatniej próby.

## Krytyczne przypomnienia

Progi przypomnień wynoszą dokładnie `14, 7, 3, 2, 1` dni przed wygaśnięciem.

- Dla jednej kombinacji tenant, aplikacja, credential i data wygaśnięcia każdy próg może utworzyć powiadomienie tylko raz.
- Po rotacji credentialu stan progów zaczyna się od nowa.
- Jeżeli aplikacja nie działała podczas wcześniejszych progów, po uruchomieniu wysyła tylko najbliższy aktualny próg, a nie serię zaległych maili.
- Wygaśnięty credential tworzy osobne, deduplikowane zdarzenie krytyczne.
- Zdarzenia trafiają do zakładki krytycznej i istniejącego outboxa.
- Odbiorcy, kanał podstawowy i fallback są brane z istniejącej reguły `critical`.
- Ponieważ kontrola jest systemowa, opcja `include_actor` nie dodaje odbiorcy — zdarzenie nie ma użytkownika wykonującego operację.
- Wyłączona reguła lub brak odbiorców nie usuwa zdarzenia z aplikacji; jedynie pomija wysyłkę maila.

Mail zawiera datę wygaśnięcia, pozostały czas, nazwę aplikacji/credentialu i krótką instrukcję rotacji. Nie zawiera Secret Value, tokenu, pełnego key ID ani danych autoryzacyjnych.

## Model danych

W istniejącym SQLite powstają tabele lub równoważne rekordy dla:

- ostatniego bezpiecznego statusu credentialu Entra;
- czasu ostatniej próby i ostatniego sukcesu;
- deduplikacji wysłanych progów;
- identyfikacji rotacji credentialu.

Migracja jest idempotentna i podnosi istniejący `user_version`. Czyszczenie logów nie usuwa aktualnego cache konfiguracji Entra ani historii wysłanych przypomnień. Dane mogą zostać zastąpione przy zmianie Tenant ID, Client ID lub Secret Value.

## API i błędy

- Publiczny snapshot ustawień zwraca tylko zredagowany status daty wygaśnięcia.
- Osobny endpoint administratora uruchamia odświeżenie `Sprawdź teraz` i zwraca bezpieczny wynik.
- Błędy Graph są mapowane na stabilne kody, między innymi `permission_required`, `application_not_found`, `credential_ambiguous`, `transport_unavailable` i `invalid_response`.
- Komunikaty z odpowiedzi Graph przechodzą przez istniejący sanitizer sekretów przed logowaniem.
- Wywołania mają ograniczony timeout i nie blokują workera bez końca.

## Testy odbiorcze

- Live pokazuje jedno zdarzenie w jednym wierszu i rozwija pełne szczegóły na żądanie.
- Historia nie wyświetla surowego JSON-u w podstawowym widoku.
- Slot pokazuje kompletne, czytelne dowody local/FTP/SQL, w tym jednoczesny save i delete.
- Długi tekst i mały viewport nie psują układu.
- Graph permission denied daje instrukcję `Application.Read.All`, bez wycieku tokenu.
- Dopasowanie credentialu nie wybiera arbitralnie jednego z kilku kandydatów.
- Progi 14/7/3/2/1 są deduplikowane i przechodzą przez regułę critical oraz fallback.
- Restart workera i ponowienie outboxa nie duplikują przypomnień.
- Rotacja sekretu tworzy nowy stan przypomnień.
- Pełny zestaw testów projektu pozostaje zielony.
