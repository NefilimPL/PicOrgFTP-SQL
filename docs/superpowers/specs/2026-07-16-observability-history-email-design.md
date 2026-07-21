# Historia zmian, obserwowalność i powiadomienia e-mail — projekt

**Data:** 2026-07-16

**Status:** zatwierdzony w rozmowie

**Zakres:** dwa kolejne etapy wdrożenia: obserwowalność i historia, następnie powiadomienia e-mail

## Cel

Rozbudować historię produktu tak, aby pokazywała rzeczywiste różnice danych,
plików i integracji, a obecne nieczytelne logi zastąpić ustrukturyzowanym
centrum zdarzeń. Na tym samym modelu powstaną trwałe incydenty, wskaźnik
kondycji aplikacji i automatyczne powiadomienia e-mail.

## Uzgodnione zasady

- SQLite jest docelowym i priorytetowym magazynem danych.
- Aplikacja korzysta z jednego pliku `picorgftp_sql.sqlite`.
- Tryb legacy ma niski priorytet i pozostaje źródłem importu do SQLite. Nowe
  funkcje obserwowalności i poczty nie dostają osobnego magazynu legacy.
- Obecne pliki tekstowe pozostają pomocniczym zapisem technicznym, ale nie są
  podstawą interfejsu, korelacji incydentów ani powiadomień.
- Sekrety, tokeny i hasła nie mogą pojawić się w API, historii, logach,
  tracebackach pokazywanych użytkownikowi ani wiadomościach e-mail.
- Czas jest zapisywany w UTC w formacie ISO 8601 i prezentowany w lokalnej
  strefie przeglądarki.

## Podejście architektoniczne

Zastosowane zostanie podejście hybrydowe. Istotne działania emitują
ustrukturyzowane zdarzenia do SQLite, a wybrane komunikaty nadal są kopiowane
do istniejących logów tekstowych. Dzięki temu nowe funkcje nie zależą od
zawodnego parsowania tekstu, a administrator zachowuje awaryjny ślad
diagnostyczny.

Przepływ danych:

`operacja -> zdarzenie -> SQLite -> korelacja zadania/incydentu -> historia/UI/e-mail`

Warstwy mają osobne odpowiedzialności:

1. Emiter zdarzeń normalizuje dane, przypisuje poziom, kontekst i identyfikatory.
2. Repozytorium SQLite zapisuje i odpytuje zdarzenia, zadania, incydenty oraz
   dostarczenia wiadomości.
3. Korelator łączy zdarzenia w zadania i incydenty bez analizowania tekstu
   prezentacyjnego.
4. API udostępnia widoki filtrowane i strumień zdarzeń.
5. Interfejs renderuje historię, konsolę, alerty i kondycję aplikacji.
6. Kolejka powiadomień wysyła e-maile poza ścieżką wykonywania zadania.

## Model zdarzenia

Każde zdarzenie operacyjne zawiera co najmniej:

- `id`, `created_at`, `severity` i stabilny `event_type`;
- czytelne `summary` i opcjonalne `recommended_action`;
- `module`, `stage` oraz wynik etapu;
- `username` i opcjonalny bezpieczny identyfikator użytkownika;
- `ean`, `product_id`, `slot` oraz `object_id`, jeśli dotyczą zdarzenia;
- `job_id`, `correlation_id` i opcjonalny `incident_id`;
- ustrukturyzowane, zredagowane `details`;
- zredagowany typ wyjątku i traceback tylko dla rzeczywistego wyjątku;
- flagi wskazujące widoczność w konsoli, historii i skrzynkach alertów.

Zdarzenia nie przechowują sekretów. Redakcja jest wykonywana przed zapisem,
a nie dopiero podczas renderowania.

## Poziomy ważności

Obowiązują cztery poziomy:

- `info`: poprawne operacje i zwykły postęp. Nie migają i domyślnie nie
  wysyłają e-maili.
- `warning`: błąd danych użytkownika, zablokowana niewłaściwa operacja,
  niedozwolony plik lub przejściowy problem bez utraty spójności.
- `error`: niepowodzenie konkretnego zadania lub wymaganej integracji, np. brak
  aktualizacji FTP, SQL, profilu dodatkowego albo Pimcore.
- `critical`: nieobsłużony wyjątek frontend/backend, niedostępność usługi
  aplikacyjnej, uszkodzenie danych lub awaria wpływająca na wiele zadań.

Udane utworzenie lub edycja produktu zawsze ma poziom `info`.

## Schemat SQLite i migracja

W istniejącym `picorgftp_sql.sqlite` powstaną tabele odpowiedzialne za:

- zdarzenia operacyjne;
- wykonania zadań i ich etapy;
- incydenty oraz liczbę ich wystąpień;
- stan przeczytania alertów przez użytkowników;
- kolejkę i historię dostarczenia powiadomień.

Istniejąca historia webowa zostanie rozszerzona w zgodny sposób przez nowe
pola w JSON payloadu. Wersja schematu zostanie podniesiona, a inicjalizacja
bazy wykona migrację idempotentnie.

Mechanizmy kopii zapasowych, naprawy, kontroli integralności i porównania bazy
obejmą nowe tabele. Import legacy nadal przenosi stare wpisy do tej samej bazy.
Starsze rekordy bez szczegółowego diffu są poprawne i nie są sztucznie
uzupełniane danymi, których nie da się odtworzyć.

## Korelacja zadań i incydentów

Każde kliknięcie uruchamiające przetwarzanie otrzymuje `job_id`. Wszystkie
etapy lokalne, FTP, SQL, profili dodatkowych i Pimcore dziedziczą ten sam
identyfikator. Działania bez zadania użytkownika mogą otrzymać techniczny
`correlation_id`.

Incydent jest identyfikowany stabilnym odciskiem złożonym z typu zdarzenia,
modułu, etapu, bezpiecznej klasy błędu i istotnego kontekstu. Tekst komunikatu
nie jest jedynym składnikiem odcisku.

Pierwsze wystąpienie tworzy incydent i może natychmiast utworzyć powiadomienie.
Identyczne wystąpienia przez 15 minut zwiększają licznik i uzupełniają kontekst
bez kolejnych wiadomości. Po upływie 15 minut aktywny problem może wysłać
następną aktualizację.

Widok incydentu pokazuje zdarzenia z tego samego `job_id` lub
`correlation_id`: zdarzenia przed problemem, problem i dostępne zdarzenia po
problemie. Nie stosuje arbitralnego grupowania w stałe okna zegarowe.

## Szczegółowa historia zmian produktu

Przy każdym wpisie historii obok przycisku `Czasy` pojawia się przycisk
`Zmiany`. Krótkie podsumowanie pozostaje na karcie, a pełny diff otwiera się w
osobnym modalu.

### Dane produktu

Historia rozróżnia utworzenie nowego wpisu, aktualizację istniejącego wpisu i
synchronizację bez różnic. Dla aktualizacji zapisuje klucz pola, etykietę,
wartość przed i po zmianie. Dla utworzenia pokazuje wartości początkowe.

### Pimcore

Operacje utworzenia, aktualizacji, konfliktu i odrzucenia są włączone do
wspólnej historii EAN. Wpis zawiera ID i ścieżkę obiektu oraz:

- wszystkie zapisane wartości przy utworzeniu;
- różnice `stara -> nowa` przy aktualizacji;
- czytelny powód konfliktu lub błędu;
- czasy etapów wysyłki i weryfikacji.

### Pliki i sloty

Dla każdego slotu zapisywane są:

- typ operacji: dodanie, zamiana, usunięcie albo migracja;
- nazwa i metadane poprzedniego pliku, jeśli były dostępne przed operacją;
- nazwa źródłowa i docelowa nowego pliku;
- rozmiar źródłowy i wynikowy;
- czas przetwarzania;
- zastosowana operacja obrazu, dopasowanie zawartości i informacja o
  preprocessingu;
- wynik lokalny, FTP i SQL właściwy dla slotu.

Brak możliwej do ustalenia poprzedniej wartości jest pokazywany jako brak
danych, a nie jako pusty plik lub fałszywe `0 B`.

### Integracje i czas zadania

Historia pokazuje wynik oraz czas operacji lokalnych, FTP, głównego SQL,
dodatkowych profili SQL i Pimcore. Błąd jednej integracji jest jednoznacznie
powiązany z etapem i nie ukrywa poprawnych wyników pozostałych integracji.

Stare wpisy zachowują dotychczasową prezentację danych. Modal informuje, że
szczegółowy zapis zmian nie był wtedy dostępny.

## Panel logów

Panel ma zakładki wizualnie zgodne z zakładkami ustawień:

- `Na żywo`;
- `Krytyczne`;
- `Błędy`;
- `Ostrzeżenia`;
- `Ostatnie zadania`.

### Na żywo

Konsola korzysta ze strumienia zdarzeń z możliwością wznowienia od ostatniego
ID. Zapewnia autoscroll, pauzę/wznowienie, wyszukiwanie i filtry poziomu,
modułu, użytkownika, EAN oraz zadania.

W konsoli dostępne są maksymalnie 24 godziny zdarzeń. Zadanie porządkowe usuwa
starsze wpisy `info`. Ostrzeżenia, błędy i zdarzenia krytyczne pozostają w
skrzynkach alertów.

### Skrzynki alertów

Każda skrzynka ma własny licznik nieprzeczytanych przypisany do zalogowanego
użytkownika. Lista pobiera najnowsze 20 elementów, a `Wczytaj więcej` dokłada
kolejne przy użyciu kursora. Nie ma klasycznych pustych stron.

Karta pokazuje komunikat, zalecane działanie, EAN, użytkownika, zadanie, moduł,
liczbę powtórzeń i wynik powiadomień. Szczegóły zawierają kontekst
`przed / problem / po` oraz rozwijany, zredagowany traceback.

Przycisk nawigacyjny `Logi` miga tylko dla najwyższego nieprzeczytanego
poziomu. Wpisy `info` nigdy nie uruchamiają alertu.

### Ostatnie zadania

Jedna karta reprezentuje jedno wykonanie. Pokazuje wynik całości i oś etapów:
dane wejściowe, pliki, FTP, SQL, dodatkowe profile i Pimcore. Szczegóły
umożliwiają przejście do powiązanego incydentu lub historii EAN.

Zdarzenia nieinformacyjne i podsumowania zadań są trwałe do czasu
administracyjnego wyczyszczenia logów. Czyszczenie logów nie usuwa historii
produktu.

## Wskaźnik kondycji aplikacji

Obok nazwy `PicOrgFTP-SQL Web` znajduje się status:

- zielony `Online · N ms` dla sprawnego backendu, SQLite i procesora zadań;
- żółty `Wolne · N ms` dla opóźnienia od 300 do 1000 ms lub obniżonej
  sprawności lokalnego komponentu;
- czerwony `Krytyczne · N ms` powyżej 1000 ms lub przy poważnym problemie
  lokalnym;
- `Offline` po trzech kolejnych próbach bez odpowiedzi.

Przeglądarka mierzy czas odpowiedzi co kilka sekund. UI używa wygładzonej
wartości kilku ostatnich prób, aby pojedynczy skok nie powodował migania.

Dymek pokazuje bieżący i średni czas odpowiedzi, stan backendu, SQLite,
procesora zadań oraz ostatni znany stan FTP, SQL, profili dodatkowych i
Pimcore. Wyłączona integracja ma stan `Wyłączona`. Zewnętrzne integracje nie są
aktywnie odpytywane przy każdym pomiarze; prezentowany jest wynik ostatniej
kontroli lub ostatniego zadania. Ich awaria nie ustawia aplikacji jako
`Offline`, ale może pokazać stan obniżony lub krytyczny.

## Konfiguracja poczty

W ustawieniach powstaje zakładka `Poczta`. Istnieje jedna aktywna konfiguracja
z dwoma kanałami i wyborem kanału podstawowego.

### Microsoft Entra / Graph

Pola:

- Tenant ID;
- Client ID;
- Client Secret;
- adres nadawcy `Od`.

Kanał korzysta z uprawnienia aplikacyjnego Microsoft Graph `Mail.Send` i
wymaga zgody administratora organizacji.

### Uniwersalny SMTP

Pola:

- host i port;
- tryb STARTTLS, TLS albo brak szyfrowania;
- login i hasło;
- adres i opcjonalna nazwa nadawcy.

Brak szyfrowania jest dozwolony dla zgodności z lokalnymi relayami, ale UI
pokazuje wyraźne ostrzeżenie. Dostawca może wymagać hasła aplikacji zamiast
hasła głównego konta.

### Kanał podstawowy i fallback

Administrator wybiera Entrę albo SMTP jako kanał podstawowy i może włączyć
fallback na drugi kanał. Niepowodzenie wysyłki podstawowej uruchamia jedną
próbę kanałem zapasowym. Obie próby korzystają z tego samego logicznego ID
wiadomości, a wyniki są zapisywane jako dostarczenie. Interfejs pokazuje użyty
kanał i przyczynę przełączenia.

### Reguły odbiorców

Każdy z czterech poziomów ma osobne ustawienia:

- włączenie lub wyłączenie wysyłki;
- lista odbiorców oddzielonych przecinkami;
- checkbox `Wyślij także do powiązanego użytkownika`.

Wszystkie reguły są domyślnie wyłączone. Adresy są walidowane, normalizowane i
deduplikowane. Powiązanym odbiorcą jest użytkownik wykonujący operację, która
utworzyła dane powiadomienie. Brak poprawnego adresu nie blokuje wysyłki do
odbiorców stałych.

W zakładce `Użytkownicy` pojawia się opcjonalne pole e-mail.

### Treść i dostarczenie

Wiadomość zawiera poziom, typ, czas, EAN, użytkownika, `job_id`, `incident_id`,
krótki kontekst przed/problem/po, wynik integracji, zalecane działanie i liczbę
powtórzeń. Szczegóły są redagowane tak samo jak zdarzenia w SQLite.

Trwała kolejka działa poza ścieżką żądania użytkownika i wznawia elementy
oczekujące po restarcie. Statusy to: `oczekuje`, `wysłano`, `fallback`,
`pominięto` i `błąd`. Niepowodzenie powiadomienia nie zmienia wyniku zadania
produktowego, ale tworzy zdarzenie diagnostyczne bez rekurencyjnego generowania
następnego e-maila o błędzie poczty.

### Testy konfiguracji

Administrator podaje adres odbiorcy i może:

- wysłać test przez Entrę;
- wysłać test przez SMTP;
- przetestować pełną ścieżkę kanału podstawowego z fallbackiem.

Test nie tworzy fałszywego incydentu. Wynik zawiera etapy i zredagowany błąd.

## API i uprawnienia

Nowe endpointy administracyjne obejmują filtrowane zdarzenia, incydenty,
zadania, stan przeczytania, kondycję oraz konfigurację/testy poczty. Strumień
zdarzeń wymaga aktywnej sesji i respektuje uprawnienia administratora.

Pełne logi techniczne, incydenty wszystkich użytkowników, konfiguracja poczty
i testy wysyłki są dostępne tylko administratorowi. Istniejące uprawnienia do
historii produktu pozostają bez zmian, a jej payload nie ujawnia sekretów
systemowych.

## Obsługa błędów

- Błąd zapisu zdarzenia nie może ukryć pierwotnego wyjątku; trafia do
  awaryjnego pliku tekstowego.
- Błąd strumienia powoduje ponowne połączenie i pobranie brakujących zdarzeń.
- Błąd migracji schematu zatrzymuje zapis do zmienionej bazy i prezentuje
  administratorowi błąd krytyczny zamiast częściowo działać.
- Błąd kanału podstawowego poczty uruchamia fallback, jeśli jest włączony.
- Błąd obu kanałów pozostawia element w historii dostarczeń z możliwością
  ponownego testu po poprawie konfiguracji.
- Globalne przechwytywanie wyjątków frontend/backend emituje zdarzenie
  `critical` z identyfikatorem korelacji.

## Strategia testów

Implementacja jest prowadzona test-first. Testy obejmą:

- migrację schematu i zgodność istniejącej bazy;
- zapis, filtrowanie, retencję i kursor zdarzeń;
- klasyfikację każdego poziomu ważności;
- korelację etapów zadania i 15-minutową deduplikację incydentu;
- redakcję sekretów przed zapisem i wysyłką;
- diff danych produktu, Pimcore i plików dla dodania, zamiany, usunięcia i
  migracji;
- zachowanie starszych rekordów historii;
- strumień z ponownym połączeniem;
- liczniki nieprzeczytanych per użytkownik;
- status kondycji, progi opóźnienia i trzy nieudane próby;
- walidację konfiguracji Entra i SMTP;
- wysyłkę podstawową, fallback, testową wiadomość i brak rekurencyjnych
  powiadomień;
- pole e-mail użytkownika i dołączanie powiązanego odbiorcy;
- integralność wymaganych elementów HTML/JS/CSS;
- regresję istniejących endpointów historii, logów, przetwarzania i Pimcore.

## Kolejność wdrożenia

### Etap 1 — obserwowalność i historia

1. Migracja SQLite i repozytorium zdarzeń.
2. Emiter, klasyfikacja, korelacja zadań i incydentów.
3. Szczegółowy diff produktu, plików, integracji i Pimcore.
4. API i strumień zdarzeń.
5. Zakładki logów, liczniki i oś zadań.
6. Wskaźnik kondycji aplikacji.

### Etap 2 — powiadomienia e-mail

1. Pole e-mail użytkownika i bezpieczna konfiguracja poczty.
2. Kanał Microsoft Entra / Graph.
3. Uniwersalny SMTP.
4. Trwała kolejka, reguły poziomów i fallback.
5. Testowe wiadomości i statusy dostarczenia w incydencie.

Każdy etap kończy się pełnym zestawem testów i może zostać wdrożony niezależnie.
