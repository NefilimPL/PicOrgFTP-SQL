# Procesy w tle, polling i aktywni klienci — specyfikacja

Status: do przeglądu

Priorytet: P1/P2

Pakiet: 6 z 7

## Cel

Ograniczyć bezczynne zapytania workera powiadomień i liczbę requestów
statusowych frontendu. Usunąć synchroniczny zapis pełnego JSON aktywnych
klientów z sekcji chronionej blokadą.

## Zakres

- scheduler powiadomień budzony zdarzeniem lub najbliższym terminem;
- dłuższy bezpieczny polling awaryjny;
- sygnał wake-up po utworzeniu nowej dostawy;
- jeden lekki snapshot runtime dla frontendu;
- adaptacyjny polling aktywnej i ukrytej karty;
- zachowanie SSE dla logów;
- snapshot aktywnych klientów kopiowany pod blokadą i zapisywany poza nią;
- pojedynczy writer, dirty generation i flush przy zamknięciu;
- metryki częstotliwości pobudek, requestów i zapisów.

## Poza zakresem

- zmiana treści, odbiorców i kanałów powiadomień;
- usunięcie endpointów health, kolejki, indeksu lub aktywnych klientów;
- zastąpienie wszystkich endpointów WebSocketem;
- zmiana autoryzacji albo zasad widoczności aktywnych klientów;
- zmiana formatu pliku aktywnych klientów bez zgodnego odczytu;
- przebudowa observability SSE;
- nowe funkcje interfejsu.

## Worker powiadomień

### Scheduler

Pętla workera używa `threading.Condition` albo równoważnego bezpiecznego
mechanizmu. Po każdej iteracji wylicza najbliższy termin:

- dostawy `pending` lub wymagającej retry;
- raportu dziennego;
- okresowego prune;
- maksymalnego pollingu awaryjnego.

Worker czeka do najbliższego terminu. Domyślny maksymalny czas bezczynnego
oczekiwania wynosi 60 sekund zamiast dwóch sekund.

Kod tworzący nową intencję lub dostawę wywołuje `wake()`. Sygnał nie musi
zapamiętywać liczby zadań, ponieważ po przebudzeniu worker odczytuje
aktualny stan z trwałego magazynu.

### Odporność

Po restarcie worker nie polega na pamięciowych sygnałach i znajduje zaległe
zadania w SQLite. Wyjątek pojedynczego cyklu zachowuje dotychczasowe
raportowanie, a następna próba następuje według ograniczonego backoffu.

Przy zamknięciu `stop_event` budzi warunek natychmiast. Shutdown nie czeka
pełnych 60 sekund.

## Snapshot runtime dla frontendu

Powstaje lekki endpoint agregujący tylko statusy potrzebne do nagłówka i
bieżącego widoku, na przykład:

- podstawowy health;
- stan file index;
- liczba oraz stan procesów użytkownika;
- liczba aktywnych klientów, jeżeli użytkownik ma uprawnienia;
- znaczniki wersji danych wskazujące, czy potrzebny jest pełny refresh.

Endpoint nie zwraca pełnych logów, list jobów ani list użytkowników. Istniejące
endpointy szczegółowe pozostają i są wywoływane po zmianie wersji albo
otwarciu odpowiedniego widoku.

Frontend utrzymuje jeden scheduler statusu:

- karta aktywna: domyślnie co 5 sekund;
- karta ukryta: co 30 sekund;
- po błędzie: ograniczony exponential backoff;
- po powrocie do karty: natychmiastowy refresh;
- jeden request w locie, bez nakładania kolejnych.

Logi nadal używają istniejącego SSE, gdy widok logów jest otwarty. Polling
nie może równolegle pobierać pełnej listy logów.

## Aktywni klienci

### Aktualizacja w pamięci

Middleware aktualizuje rekord pod blokadą i oznacza stan jako dirty przez
zwiększenie numeru generacji. Nie wykonuje zapisu pliku pod blokadą.

### Asynchroniczny writer

Pojedynczy writer:

1. pod blokadą kopiuje snapshot i numer generacji;
2. zwalnia blokadę;
3. serializuje i zapisuje plik tymczasowy;
4. atomowo zastępuje plik docelowy;
5. pod blokadą oznacza generację jako zapisaną;
6. jeśli w międzyczasie powstała nowa generacja, planuje następny zapis.

Nie może działać dwóch writerów równocześnie. Minimalny odstęp między
zapisami pozostaje konfigurowalny, domyślnie 15 sekund.

Przy shutdown wykonywany jest wymuszony flush z ograniczonym timeoutem.
Błąd zapisu nie blokuje requestu użytkownika; jest raportowany przez
observability, a dirty state pozostaje do kolejnej próby.

## Błędy i zgodność

- Brak sygnału wake-up nie gubi zadań dzięki pollingowi awaryjnemu.
- Endpoint agregujący respektuje istniejące uprawnienia każdego fragmentu.
- Błąd jednego fragmentu statusu zwraca jego stan `unknown`, nie cały duży
  traceback.
- Stare endpointy pozostają kompatybilne.
- Plik aktywnych klientów nadal jest zapisywany atomowo i czytelny przez
  obecną ścieżkę startową.
- Dane requestu nie są rozszerzane o nowe identyfikatory ani informacje
  wrażliwe.

## Kryteria akceptacji

1. Bezczynny worker wykonuje najwyżej dwa cykle bazodanowe w ciągu minuty.
2. Nowa dostawa budzi worker bez czekania do pollingu awaryjnego.
3. Shutdown workera kończy oczekiwanie w czasie poniżej jednej sekundy.
4. Pięć otwartych kart generuje jeden request statusowy na kartę na interwał,
   bez dodatkowych nakładających się pollerów.
5. Ukryta karta nie odpytuje częściej niż co 30 sekund.
6. Szczegółowe dane są pobierane tylko po otwarciu widoku albo zmianie
   znacznika wersji.
7. Serializacja i zapis aktywnych klientów odbywają się bez trzymania
   `_ACTIVE_CLIENTS_LOCK`.
8. Równoległe aktualizacje podczas zapisu nie są tracone.
9. Shutdown flush zapisuje ostatnią generację albo raportuje kontrolowany
   timeout.
10. Istniejące endpointy, uprawnienia i format pliku pozostają zgodne.

## Testy i benchmark

Testy workera:

- bezczynne oczekiwanie;
- wake po enqueue;
- wyliczenie najbliższego retry i raportu;
- wyjątek i backoff;
- restart z zaległą dostawą;
- natychmiastowy stop.

Testy frontend/API:

- kontrakt snapshotu runtime;
- uprawnienia do fragmentów;
- jeden scheduler;
- active/hidden/backoff;
- brak równoległego pollingu logów przy SSE;
- refresh szczegółów po zmianie wersji.

Testy aktywnych klientów:

- zapis poza blokadą;
- jedna instancja writera;
- generacja zmieniona podczas I/O;
- błąd zapisu i retry;
- atomowa podmiana;
- shutdown flush.

Benchmark raportuje:

- cykle workera na minutę bez pracy;
- czas enqueue-to-attempt;
- requesty statusowe na klienta/minutę;
- czas oczekiwania na blokadę aktywnych klientów;
- liczbę i czas zapisów JSON.

## Główne miejsca w kodzie

- `picorgftp_sql/notification_service.py`
- `picorgftp_sql/web/app.py`
- `picorgftp_sql/web/static/app.js`
- `picorgftp_sql/observability.py`
- `tests/test_notification_service.py`
- `tests/test_notification_outbox.py`
- testy aktywnych klientów, runtime statusu i frontendu

## Zależności

Pakiet powinien korzystać z tańszego lifecycle SQLite z pakietu 1.
Scheduler powiadomień, agregacja pollingu i writer aktywnych klientów są
niezależnymi etapami i mogą być wdrażane osobno.
