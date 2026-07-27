# Integracje SQL, Pimcore i tłumaczenia — specyfikacja

Status: do przeglądu

Priorytet: P1

Pakiet: 5 z 7

## Cel

Zmniejszyć koszt zestawiania połączeń oraz liczbę round-tripów podczas
renderowania szablonów, operacji Pimcore i aktualizacji slotów SQL, bez
zmiany istniejących konfiguracji, uwierzytelnienia i kontraktów integracji.

## Nienegocjowalne ograniczenia

- Istniejące profile, sekrety, endpointy, timeouty i nagłówki pozostają
  zgodne.
- Keep-alive Pimcore nie może współdzielić niebezpiecznie mutowalnej sesji
  między równoległymi jobami.
- Błąd nowej ścieżki ma bezpieczny fallback do obecnego transportu.
- Zapytania zależne od wcześniejszych wyników zachowują kolejność.
- Niestandardowe szablony SQL, których nie da się bezpiecznie zgrupować,
  zachowują ścieżkę legacy.
- Nie zmienia się kolejność biznesowa: odczyt, zapis produktu, weryfikacja.

## Zakres

- keep-alive w czasie życia jednego klienta Pimcore;
- jawne zamykanie transportu;
- zachowanie certyfikatów, proxy, auth i timeoutów;
- jedno połączenie SQL na profil w czasie renderowania;
- kontrolowana równoległość tylko niezależnych integracji;
- cache tłumaczeń;
- pojedynczy `UPDATE` dla zgodnych slotów zdjęć;
- fallbacki i diagnostyka per integracja;
- pomiar liczby połączeń i round-tripów.

## Poza zakresem

- zmiana API Pimcore;
- usunięcie odczytu weryfikacyjnego po create/update;
- nowe providery SQL lub tłumaczeń;
- zmiana treści zapytań skonfigurowanych przez użytkownika;
- trwała współdzielona pula połączeń między wszystkimi jobami;
- przechowywanie sekretów w nowym miejscu;
- automatyczna równoległość bez analizy zależności mapowań.

## Pimcore HTTP

### Transport

`PimcoreClient` otrzymuje transport z jawnym lifecycle. Zalecany transport
używa `requests.Session`, które jest już zależnością projektu.

Jedna instancja `PimcoreClient` i jej sesja są używane przez jedną operację
biznesową, na przykład:

```text
GET duplikatu
  -> POST create
  -> GET weryfikacyjny
  -> close
```

Sesja nie jest globalna i nie jest współdzielona między jobami ani wątkami.
Daje to ponowne użycie TCP/TLS dla sekwencji requestów bez ryzyka
współdzielenia cookies i mutowalnych nagłówków.

Transport musi odwzorować:

- obecną metodę auth i nagłówki;
- timeout connect/read;
- konfigurację certyfikatów i `certifi`;
- zachowanie proxy środowiskowego;
- kodowanie JSON;
- redakcję błędów;
- dotychczasową interpretację statusów HTTP.

Klient implementuje `close()` i context manager. Każda ścieżka sukcesu i
błędu zamyka sesję.

### Fallback

Transport legacy oparty na obecnej implementacji pozostaje dostępny przez
wewnętrzną flagę kompatybilności. Automatyczny fallback w połowie operacji
jest dopuszczalny wyłącznie przed requestem zmieniającym stan. Po wysłaniu
POST/PUT nie wolno automatycznie powtarzać operacji nieidempotentnej bez
jednoznacznego potwierdzenia wyniku.

Jeżeli sesja keep-alive traci połączenie podczas idempotentnego GET, klient
może wykonać jedno ponowienie na nowym połączeniu. POST i PUT zachowują
obecną politykę retry.

## SQL w szablonach

Przed renderowaniem mapowania są analizowane i grupowane po profilu SQL.
Każda grupa otwiera jedno połączenie i wykonuje mapowania w dotychczasowej
kolejności. Połączenie jest zamykane w `finally`.

Nie wprowadzamy równoległych kursorów na jednym połączeniu. Jeżeli mapowanie
zależy od wartości powstałej wcześniej, pozostaje sekwencyjne.

Równolegle można wykonać tylko grupy spełniające wszystkie warunki:

- różne profile lub niezależne transporty;
- brak odwołań do wyniku drugiej grupy;
- brak operacji modyfikujących;
- limit współbieżności maksymalnie 4;
- anulowanie całej operacji jest poprawnie propagowane.

Pierwsza implementacja może dostarczyć samo ponowne użycie połączenia, a
równoległość włączyć dopiero po osobnym teście zależności.

## Tłumaczenia

Cache tłumaczeń jest kluczowany:

- providerem;
- docelowym językiem;
- dokładnym tekstem wejściowym;
- fingerprintem niesekretnej konfiguracji providera.

Cache ma ograniczenie liczby wpisów i TTL. Nie zapisuje sekretów. Błędy
providera nie są cache'owane jako poprawny wynik. Kilka równoległych próśb o
ten sam klucz korzysta z singleflight.

Mapowania tłumaczeń pozostają sekwencyjne, jeśli późniejszy tekst używa
wyniku wcześniejszego. Niezależne teksty mogą użyć kontrolowanej
równoległości maksymalnie 4.

## Zbiorczy UPDATE slotów

Standardowa konfiguracja aktualizacji zdjęć generuje jedną instrukcję:

```sql
UPDATE <table>
SET <slot_1_column> = ?,
    <slot_2_column> = ?,
    ...
WHERE <existing configured predicate>
```

Nazwy tabel i kolumn nadal przechodzą istniejącą walidację identyfikatorów.
Wartości zawsze są parametrami. Wszystkie zmieniane i czyszczone sloty
wchodzą do jednej instrukcji oraz jednej transakcji.

Wynik `rowcount` zastępuje osobne zapytanie sprawdzające istnienie rekordu,
jeżeli sterownik zwraca wiarygodną wartość. Dla sterowników lub konfiguracji,
gdzie `rowcount` nie jest wiarygodne, pozostaje obecne sprawdzenie.

Jeżeli niestandardowy template nie może zostać bezpiecznie przełożony na
jeden update, aplikacja używa dotychczasowej ścieżki per slot i rejestruje
diagnostyczny powód bez danych wrażliwych.

## Błędy i transakcje

- Każda grupa SQL zamyka kursor i połączenie.
- Błąd jednego wymagającego mapowania zachowuje dotychczasowy błąd produktu.
- Opcjonalne mapowanie może zachować dotychczasowy fallback.
- Zbiorczy update jest atomowy: wszystkie sloty albo żaden.
- Niepewny wynik POST/PUT Pimcore nie jest automatycznie powtarzany.
- Logi podają integrację, etap i typ fallbacku, ale nie sekret ani pełny URL
  zawierający parametry wrażliwe.

## Kompatybilność

- Pliki konfiguracyjne pozostają bez migracji.
- Istniejące profile SQL i Pimcore działają bez ponownego zapisu.
- Wynik renderowania szablonu pozostaje identyczny.
- Odczyt weryfikacyjny Pimcore pozostaje.
- Cache tłumaczeń można wyłączyć i wyczyścić.
- Fallback legacy jest testowany, a nie tylko pozostawiony jako martwy kod.

## Kryteria akceptacji

1. Create/update Pimcore ponownie używa jednego połączenia HTTP w obrębie
   klienta, gdy serwer na to pozwala.
2. Dwa równoległe joby nie współdzielą mutowalnej sesji `requests.Session`.
3. Nagłówki, auth, timeouty, certyfikaty i proxy mają test zgodności z
   transportem legacy.
4. Nieudany POST/PUT nie jest automatycznie powtarzany w niebezpieczny sposób.
5. N mapowań tego samego profilu SQL otwiera jedno połączenie.
6. Mapowania zależne zachowują kolejność i wynik.
7. Powtarzane tłumaczenie tego samego klucza w TTL wykonuje jedno wywołanie
   providera.
8. Standardowa aktualizacja wielu slotów wykonuje jeden `UPDATE`.
9. Nieobsługiwany custom template korzysta z działającego fallbacku.
10. Wyniki integracji są zgodne z zestawem testów regresji sprzed zmiany.

## Testy i benchmark

Testy Pimcore:

- liczba sesji i połączeń dla GET/POST/GET;
- close na sukcesie i wyjątku;
- zgodność requestów legacy/session;
- zerwane keep-alive;
- zasady retry dla GET i operacji zmieniających.

Testy SQL:

- jedno połączenie na profil;
- kolejność zależnych mapowań;
- kontrolowany limit niezależnych grup;
- rollback zbiorczego update;
- `rowcount` wiarygodny i fallback;
- custom template fallback.

Testy tłumaczeń:

- klucz cache, TTL, limit i invalidacja;
- singleflight;
- błąd bez cache'owania;
- zależne i niezależne mapowania.

Benchmark raportuje liczbę:

- handshake TCP/TLS;
- otwarć połączeń SQL;
- requestów tłumaczeń;
- instrukcji aktualizujących sloty;
- czas p50/p95 całego renderowania i zapisu produktu.

## Główne miejsca w kodzie

- `picorgftp_sql/services/pimcore_service.py`
- `picorgftp_sql/services/pimcore_sql_service.py`
- `picorgftp_sql/services/translation_service.py`
- `picorgftp_sql/web_data.py`
- `picorgftp_sql/web/app.py`
- `picorgftp_sql/app.py`
- `tests/test_pimcore_service.py`
- `tests/test_pimcore_operations.py`
- `tests/test_pimcore_sql_service.py`
- `tests/test_pimcore_templates.py`
- `tests/test_translation_service.py`

## Zależności

Pakiet może być wdrażany po pakiecie 1, ale nie wymaga zmian z pakietów
produktu, uploadu ani FTP. Keep-alive, reuse SQL, cache tłumaczeń i zbiorczy
update powinny być osobnymi commitami i osobno przełączalnymi zmianami.
