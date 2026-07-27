# SQLite lifecycle i telemetria — specyfikacja

Status: zatwierdzona

Priorytet: P0

Pakiet: 1 z 7

## Cel

Usunąć koszt wielokrotnej inicjalizacji schematu SQLite, poprawić zachowanie
bazy przy równoległych odczytach i zapisach oraz ograniczyć nadmiarowe zapisy
postępu bez zmiany kontraktów danych aplikacji.

Po wdrożeniu zwykła operacja magazynu nie może wykonywać migracji ani poleceń
DDL. Równoległe żądania webowe, worker powiadomień i observability mają
korzystać z przewidywalnej konfiguracji połączeń i nie powinny powodować
lawiny błędów `database is locked`.

## Zakres

Specyfikacja obejmuje:

- lifecycle `SqliteStore` i aktywnego data store;
- jednokrotną, bezpieczną wielowątkowo inicjalizację schematu;
- konfigurację połączeń SQLite do pracy równoległej;
- jawne unieważnianie store po zmianie lub odtworzeniu bazy;
- ograniczenie częstotliwości trwałego zapisu postępu jobów;
- ograniczenie powtarzalnych informacyjnych zdarzeń etapów;
- testy współbieżności i benchmark liczby operacji bazodanowych.

## Poza zakresem

- zmiana struktury danych domenowych;
- zmiana formatu backupów lub procesu ich przywracania poza unieważnieniem
  starego store;
- zmiana historii, incydentów, retencji i treści powiadomień;
- zastąpienie SQLite inną bazą;
- zmiana SSE i sposobu dostarczania logów do przeglądarki;
- usuwanie wpisów `warning`, `error` albo `critical`.

## Stan obecny

`SqliteStore.initialize()` jest wywoływane z większości publicznych metod
magazynu. Inicjalizacja otwiera połączenie, sprawdza wersję schematu, wykonuje
instrukcje `CREATE TABLE IF NOT EXISTS`, sprawdza migracje i spójność części
danych. `observability_store()` dodatkowo tworzy nową instancję store przed
operacją zapisu.

Połączenia ustawiają `foreign_keys`, ale nie mają wspólnej polityki
`busy_timeout`, trybu dziennika ani poziomu `synchronous`. Web, worker
powiadomień i przetwarzanie produktów zapisują do tej samej bazy z wielu
wątków.

Aktualizacja postępu joba może zapisywać pełny stan dla każdej drobnej zmiany
procentu i każdego etapu. Każdy zapis ponosi obecnie również koszt
inicjalizacji.

## Projekt

### Rejestr store

Warstwa `data_store` będzie utrzymywać jedną aktywną instancję
`SqliteStore` dla kanonicznej, rozwiązanej ścieżki bazy. Rejestr ma być
chroniony blokadą i nie może zwracać tej samej instancji dla dwóch różnych
ścieżek.

Instancja przechowuje:

- flagę zakończonej inicjalizacji;
- blokadę inicjalizacji;
- tożsamość ścieżki, dla której została utworzona;
- opcjonalne dane diagnostyczne konfiguracji SQLite.

Publiczne metody mogą nadal wywoływać tanią funkcję `ensure_initialized()`,
ale po pierwszym sukcesie funkcja nie otwiera połączenia i nie wykonuje SQL.
Pierwsze równoległe wywołania stosują double-check pod blokadą, tak aby pełna
inicjalizacja została wykonana dokładnie raz.

### Unieważnianie

Cache store musi zostać jawnie unieważniony, gdy:

- zmienia się aktywna ścieżka SQLite;
- baza zostaje przywrócona z backupu;
- baza jest naprawiana lub zastępowana;
- test podmienia ścieżkę aktywnego magazynu;
- aplikacja jest zamykana.

Po unieważnieniu nowe wywołanie tworzy nową instancję i wykonuje pełną
inicjalizację. Nie wolno przenosić flagi inicjalizacji między plikami bazy.

### Konfiguracja połączeń

Każde nowe połączenie zachowuje `foreign_keys = ON` i otrzymuje:

- konfigurowalny `busy_timeout`, domyślnie 5000 ms;
- `synchronous = NORMAL` po skutecznym uruchomieniu WAL;
- spójny timeout przekazany do `sqlite3.connect`;
- rejestrację istniejących funkcji SQLite.

`journal_mode = WAL` jest ustawiane podczas inicjalizacji, a nie przy każdej
operacji. Kod odczytuje wartość zwróconą przez SQLite. Jeżeli WAL nie może
zostać aktywowany, aplikacja zachowuje poprzedni tryb dziennika, emituje jedno
zredagowane ostrzeżenie i działa dalej. Brak WAL nie może uniemożliwić startu,
szczególnie przy bazie na udziale sieciowym.

Każdy wątek nadal korzysta z własnego, krótko żyjącego połączenia. Jedno
połączenie `sqlite3` nie jest współdzielone między wątkami. Nie wprowadzamy
ogólnego poola połączeń.

### Transakcje

Istniejące granice atomowych operacji pozostają zachowane. Operacje zapisu
mają wykonywać przygotowanie danych przed otwarciem transakcji i utrzymywać
blokadę zapisu możliwie krótko. Zewnętrzne wywołania FTP, SQL, HTTP i Pillow
nie mogą odbywać się wewnątrz transakcji SQLite.

### Ograniczenie zapisów postępu

Trwały zapis postępu jest wykonywany, gdy wystąpi co najmniej jeden warunek:

- zmienił się etap;
- zmienił się stan joba;
- od poprzedniego zapisu upłynęło 500 ms;
- job zakończył się sukcesem, błędem albo anulowaniem.

Zmiany procentu wewnątrz okna 500 ms są scalane do najnowszej wartości.
Stan końcowy zawsze jest zapisywany synchronicznie przed wysłaniem odpowiedzi
końcowej.

Zdarzenia `warning`, `error` i `critical` nie są throttlowane. Powtarzalne
zdarzenia informacyjne `process.stage_started` nie mogą być emitowane drugi
raz dla tego samego `job_id` i etapu.

## Przepływ

```text
żądanie operacji store
  -> resolve aktywnej ścieżki
  -> pobranie instancji z rejestru
  -> ensure_initialized()
       -> szybki powrót, jeśli gotowe
       -> pełna inicjalizacja raz pod blokadą
  -> nowe połączenie z polityką PRAGMA
  -> krótka operacja / transakcja
  -> zamknięcie połączenia
```

```text
aktualizacja postępu
  -> pamięciowy stan joba zawsze aktualizowany
  -> zmiana etapu/stanu lub minęło 500 ms?
       -> tak: trwały zapis najnowszego snapshotu
       -> nie: zapis zostaje scalony
  -> zakończenie: wymuszony zapis końcowy
```

## Błędy i diagnostyka

- Nieudana migracja pozostaje błędem startu i nie ustawia flagi gotowości.
- Kolejne wywołanie może ponowić inicjalizację po usunięciu przyczyny.
- Nieudane włączenie WAL jest ostrzeżeniem, nie błędem startu.
- Ostrzeżenie o fallbacku nie może zawierać danych wrażliwych.
- Timeout blokady ma zachować obecny mechanizm raportowania wyjątków.
- Diagnostyka zdrowia może raportować aktywny tryb dziennika i timeout, ale
  nie ujawnia ścieżki bazy użytkownikom bez uprawnień administracyjnych.

## Kompatybilność i wdrożenie

- Numer schematu zmienia się tylko wtedy, gdy implementacja faktycznie doda
  migrację; sama konfiguracja połączeń nie wymaga migracji.
- Istniejące bazy i backupy pozostają czytelne.
- Pierwszy start po aktualizacji wykonuje tę samą inicjalizację co obecnie.
- Fallback bez WAL zachowuje dotychczasowy tryb dziennika.
- Zmiany throttlingu nie zmieniają końcowego stanu ani komunikatów błędów.

## Kryteria akceptacji

1. Dwadzieścia równoległych pierwszych wywołań tej samej instancji wykonuje
   pełny blok inicjalizacji dokładnie raz.
2. Po inicjalizacji 1000 zwykłych operacji magazynu nie wykonuje instrukcji
   DDL, kontroli migracji ani skanowania spójności.
3. Zmiana ścieżki i restore tworzą nową instancję oraz ponawiają
   inicjalizację dokładnie raz.
4. Test z co najmniej ośmioma czytelnikami i dwoma zapisującymi kończy się
   bez nieobsłużonych `database is locked`.
5. Jeżeli WAL jest niedostępny, aplikacja uruchamia się w trybie fallback i
   rejestruje jedno ostrzeżenie.
6. Sto aktualizacji postępu w ciągu sekundy generuje najwyżej trzy trwałe
   zapisy, o ile etap i stan się nie zmieniają.
7. Stan końcowy joba i wszystkie zdarzenia błędów są zawsze trwałe.
8. Publiczne kontrakty data store i API pozostają zgodne.

## Testy i benchmark

Testy jednostkowe:

- wyścig inicjalizacji wielu wątków;
- brak SQL inicjalizacyjnego po pierwszym sukcesie;
- ponowienie po błędzie inicjalizacji;
- unieważnienie po zmianie ścieżki i restore;
- polityka PRAGMA i fallback WAL;
- throttling, zmiana etapu i wymuszony zapis końcowy.

Test integracyjny:

- mieszany workload odczytów i zapisów na tym samym pliku SQLite;
- równoległy zapis eventów, jobów i powiadomień;
- poprawne zamknięcie i ponowne otwarcie bazy.

Benchmark zapisuje przed i po:

- liczbę otwartych połączeń;
- liczbę instrukcji inicjalizacyjnych;
- czas p50/p95 operacji store;
- liczbę zapisów postępu na job;
- liczbę timeoutów blokady.

## Główne miejsca w kodzie

- `picorgftp_sql/sqlite_store.py`
- `picorgftp_sql/data_store.py`
- `picorgftp_sql/storage_settings.py`
- `picorgftp_sql/observability.py`
- `picorgftp_sql/web/app.py`
- `picorgftp_sql/notification_service.py`
- `tests/test_sqlite_store.py`
- testy observability, jobów i powiadomień

## Zależności

Ten pakiet powinien zostać wdrożony jako pierwszy. Pakiety wyszukiwania,
uploadu i procesów w tle skorzystają z tańszego store i stabilniejszej
współbieżności.
