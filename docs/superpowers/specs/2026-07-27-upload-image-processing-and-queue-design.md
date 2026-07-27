# Upload, przetwarzanie obrazów i kolejka — specyfikacja

Status: zatwierdzona

Priorytet: P0

Pakiet: 3 z 7

## Cel

Zapobiec blokowaniu pętli FastAPI podczas uploadu, ograniczyć liczbę pełnych
dekodowań i kodowań obrazu oraz zapewnić kontrolowany backpressure dla
zadań przetwarzania.

Zmiana ma zachować obecną walidację, skan antywirusowy, nazewnictwo plików,
reguły slotów, wynik API i integralność procesu FTP/SQL.

## Zakres

- odbiór i zapis uploadu poza event loop;
- walidacja obrazów i skan antywirusowy w dedykowanym executorze;
- jeden końcowy pipeline transformacji obrazu;
- ograniczenie liczby prób kodowania do limitu rozmiaru;
- wspólna kolejka dla synchronicznego i background process;
- limit kolejki, workerów i zadań użytkownika;
- anulowanie i cleanup plików tymczasowych;
- pomiar responsywności `/api/health` podczas uploadu.

## Poza zakresem

- zmiana obsługiwanych slotów;
- osłabienie walidacji plików lub wyłączenie Microsoft Defender;
- zmiana docelowych nazw, formatów i katalogów produktów;
- zmiana zasad FTP albo SQL poza wywołaniem po zakończeniu pipeline;
- cache miniaturek;
- zmiana limitów rozmiaru skonfigurowanych przez użytkownika;
- przetwarzanie w zewnętrznym brokerze zadań.

## Stan obecny

Asynchroniczne funkcje uploadu wykonują synchroniczne operacje dyskowe,
Pillow `verify`, usuwanie metadanych z ponownym kodowaniem i
`subprocess.run` dla skanu antywirusowego.

Po zapisaniu uploadu obraz może zostać ponownie otwarty i zakodowany podczas
właściwego resize/crop/compress. Osiągnięcie limitu rozmiaru zmniejsza jakość
JPEG krokowo, co może wykonać wiele pełnych zapisów.

Background process korzysta z executora z jednym workerem i nieograniczoną
kolejką. Endpoint foreground korzysta z innej ścieżki wykonania, przez co
omija backpressure.

## Projekt komponentów

### Upload staging

Nowy, wewnętrzny komponent przygotowania uploadu odpowiada za:

1. strumieniowe skopiowanie `UploadFile` do unikalnego katalogu joba;
2. limit liczby bajtów egzekwowany podczas kopiowania;
3. walidację typu i sygnatury;
4. Pillow `verify`;
5. skan antywirusowy;
6. utworzenie niemutowalnego opisu pliku staged.

Odczyt `UploadFile` pozostaje asynchroniczny, a blokujące zapisy i wszystkie
operacje CPU/subprocess są wykonywane przez ograniczony executor. Plik
nieprzechodzący walidacji jest zamykany i usuwany przed zwróceniem błędu.

Staging nie wykonuje pełnego zapisu obrazu tylko po to, aby usunąć metadane.
Metadane są usuwane w końcowym kodowaniu.

### Pipeline obrazu

Każdy obraz jest pełnie dekodowany raz w ramach końcowego przetwarzania.
Pipeline wykonuje kolejno:

1. bezpieczne otwarcie i wymuszenie odczytu danych;
2. EXIF transpose;
3. konwersję trybu kolorów;
4. content fit/crop;
5. resize;
6. wybór formatu;
7. zapis bez kopiowania EXIF i pozostałych metadanych;
8. atomowe przeniesienie gotowego pliku do celu.

Pillow `verify` w stagingu może odczytać plik wcześniej, ale nie może
powodować pośredniego ponownego kodowania. Wszystkie operacje transformacji
wykorzystują wspólny helper dla web i desktopu.

### Limit rozmiaru

Pierwszy zapis używa skonfigurowanej jakości. Jeżeli wynik jest zbyt duży,
jakość jest dobierana przez wyszukiwanie binarne w dozwolonym zakresie.
Cały proces wykonuje najwyżej sześć prób kodowania JPEG.

Jeżeli minimalna jakość nadal przekracza limit, stosowana jest istniejąca
polityka błędu albo resize zdefiniowany jawnie w konfiguracji. Implementacja
nie może samodzielnie zmienić tej polityki.

PNG zachowuje jakość wizualną i nie jest wielokrotnie kodowany w pętli
przeznaczonej dla jakości JPEG.

### Kolejka

Oba endpointy procesowania delegują do jednego `ProcessQueueService`.
Usługa utrzymuje:

- konfigurowalną liczbę workerów, domyślnie 1;
- maksymalnie 8 zadań oczekujących;
- maksymalnie 2 aktywne lub oczekujące zadania na użytkownika;
- jawne stany `queued`, `running`, `completed`, `failed`, `cancelled`;
- pozycję zadania w kolejce;
- kontrolowane zamknięcie.

Gdy kolejka jest pełna, serwer nie materializuje wszystkich plików bez
końca. Rezerwacja miejsca następuje przed kosztownym stagingiem. Brak miejsca
zwraca `429` z `Retry-After`. Jeżeli staging po rezerwacji się nie powiedzie,
rezerwacja jest zwalniana.

W instalacji bez uwierzytelnienia limit per użytkownik używa istniejącej,
stabilnej tożsamości klienta. Nie wolno używać danych, które zmieniają się
przy każdym requestcie.

### Anulowanie i cleanup

Anulowanie zadania oczekującego usuwa je z kolejki i czyści katalog joba.
Anulowanie zadania działającego ustawia token, który jest sprawdzany między
etapami. Nie przerywa operacji w środku atomowego zapisu, uploadu FTP ani
transakcji SQL.

Katalog joba jest usuwany po sukcesie, błędzie lub anulowaniu. Okresowy
cleanup usuwa tylko katalogi o znanym prefiksie aplikacji, starsze od
ustalonego TTL i niepowiązane z aktywnym jobem.

## Przepływ

```text
request
  -> próba rezerwacji miejsca w kolejce
  -> streaming uploadu do katalogu joba
  -> walidacja + Defender w ograniczonym executorze
  -> job queued
  -> worker:
       jeden pipeline obrazu na slot
       zapis produktu / FTP / SQL zgodnie z obecną kolejnością
       wymuszony stan końcowy
  -> cleanup katalogu joba
```

## Błędy i bezpieczeństwo

- Walidacja i Defender pozostają obowiązkowe.
- Timeout skanera zachowuje obecną politykę błędu.
- Niepełny plik docelowy nigdy nie zastępuje poprawnego pliku.
- Błąd jednego slotu jest raportowany w obecnym formacie procesu.
- Odrzucone i anulowane zadania nie pozostawiają uchwytów ani plików.
- Wyjątek executora jest przenoszony do stanu joba i observability.
- Dane tymczasowe nie są współdzielone między jobami.

## Kompatybilność

- Istniejące payloady i odpowiedzi pozostają zgodne; mogą otrzymać
  dodatkowe pola `queue_position` i `retry_after`.
- Endpoint foreground może poczekać na wynik wspólnej kolejki, ale nie
  omija limitów.
- Kolejność integracji końcowych nie zmienia się.
- Domyślna liczba workerów 1 zachowuje dotychczasową serializację.
- Nie zmienia się format i jakość, jeśli obraz mieści się w limicie przy
  pierwszym zapisie.

## Kryteria akceptacji

1. Pillow, Defender i finalne kodowanie nie wykonują się w event loop.
2. Podczas przetwarzania 26 reprezentatywnych zdjęć `/api/health` zachowuje
   p95 poniżej 250 ms na maszynie benchmarkowej bez zewnętrznych opóźnień.
3. Jedno zdjęcie nie jest pośrednio ponownie kodowane podczas stagingu.
4. Dobieranie jakości JPEG wykonuje najwyżej sześć kodowań.
5. Endpoint foreground i background korzystają z tej samej kolejki i limitów.
6. Dziewiąte oczekujące zadanie przy domyślnej konfiguracji zostaje
   odrzucone przed pełnym stagingiem.
7. Limit per użytkownik działa także przy równoległych requestach.
8. Po każdym stanie końcowym katalog joba zostaje usunięty.
9. Walidacja, Defender, nazwy plików i wynik procesu nie mają regresji.

## Testy i benchmark

Testy jednostkowe:

- rezerwacja, pełna kolejka i zwolnienie rezerwacji;
- limit per użytkownik;
- przejścia stanów i anulowanie;
- cleanup bez naruszania aktywnych katalogów;
- liczba kodowań JPEG;
- brak pośredniego metadata re-encode;
- atomowy zapis finalny.

Testy integracyjne:

- równoległy upload i health;
- foreground oraz background;
- błędy walidacji, Defendera, Pillow, FTP i SQL;
- restart z zapisanymi stanami jobów;
- pełne 26 slotów z mieszanymi formatami.

Benchmark raportuje:

- event-loop lag;
- p50/p95 `/api/health`;
- czas i liczbę kodowań na obraz;
- czas całego produktu;
- maksymalny rozmiar kolejki, RAM i katalogów tymczasowych.

## Główne miejsca w kodzie

- `picorgftp_sql/web/app.py`
- `picorgftp_sql/web_workflow.py`
- `picorgftp_sql/image_utils.py`
- `picorgftp_sql/app.py`
- `picorgftp_sql/observability.py`
- testy web uploadu, workflow i obrazów
- `tests/test_image_utils.py`
- `tests/test_ci_performance_smoke.py`

## Zależności

Pakiet korzysta z lifecycle i throttlingu SQLite z pakietu 1. Może być
wdrażany niezależnie od optymalizacji FTP, ale końcowy test regresji musi
obejmować istniejący upload FTP i synchronizację SQL.
