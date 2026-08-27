# Panel wersji modułów i statusu buildu

## Cel

Administrator ma móc jednoznacznie sprawdzić, jaki kod uruchamia aktualny
program oraz czy lokalne repozytorium zawiera zmiany wymagające ponownego
zbudowania EXE. Panel rozwiązuje niepewność, czy testowana aplikacja zawiera
ostatnie poprawki, w szczególności w OCR.

## Zakres

Nowa administracyjna zakładka **Wersje modułów** w Ustawieniach pokaże:

- wariant i wersję uruchomionej aplikacji;
- commit oraz czas utworzenia buildu;
- listę logicznych modułów wraz z commitem i datą ich ostatniej zmiany w
  uruchomionym buildzie;
- porównanie każdego modułu z lokalnym repozytorium Git, gdy jest dostępne;
- osobne wpisy generatora lokalnego i generatora webowego.

Zakres obejmuje tylko porównanie z lokalnym Git. Panel nie komunikuje się z
GitHubem i nie wykonuje builda ani operacji Git modyfikujących stan.

## Rejestr modułów

Jeden rejestr w Pythonie definiuje stabilne identyfikatory, etykiety i ścieżki
repozytorium. Obejmuje co najmniej: aplikację i dane, sloty, FTP, SQL,
Pimcore, OCR, tester OCR, ustawienia, web UI, generator lokalny i generator
webowy. Moduł może wskazywać wiele plików lub katalogów.

Rejestr jest jedynym źródłem listy w UI i w generatorze manifestu. Dzięki temu
logiczne moduły nie są zgadywane z nazw plików, a rozszerzenie listy wymaga
wyłącznie dodania jednego wpisu.

## Manifest buildu

Podczas każdego builda generator uruchamia narzędzie tworzące manifest JSON.
Manifest zawiera wersję schematu, wariant buildu, czas UTC wygenerowania,
commit całego repozytorium oraz dla każdego modułu: identyfikator, etykietę,
ostatni commit i jego datę UTC.

Manifest jest generowany w katalogu roboczym buildu i dołączany do paczki
PyInstaller jako dane aplikacji. Odczyt następuje przez zasoby pakietu, więc
działa także po przeniesieniu EXE poza repozytorium. Brak manifestu w starszym
EXE nie jest błędem: panel pokaże stan `brak danych buildu`.

Oba skrypty generatorów — lokalny i webowy — korzystają z tego samego
narzędzia. Wiersz generatora w tabeli obejmuje odpowiedni skrypt buildu oraz
wspólną konfigurację pakowania.

## Porównanie z lokalnym repozytorium

W runtime serwis najpierw szuka repozytorium od katalogu aplikacji w górę.
Opcjonalna zmienna środowiskowa może wskazać katalog repozytorium jawnie.
Jeżeli odnaleziony katalog jest poprawnym repozytorium Git, serwis dla każdej
ścieżki modułu odczytuje ostatni commit, datę i stan niezacommitowanych zmian.

Status wiersza ma jedną z wartości:

- `zgodny` — commit modułu w buildzie odpowiada lokalnemu commitowi i nie ma
  zmian roboczych;
- `wymaga ponownego builda` — lokalny commit modułu różni się od manifestu;
- `niezacommitowane zmiany` — lokalny moduł ma zmiany robocze;
- `repozytorium niedostępne` — EXE nie ma dostępu do lokalnego Git;
- `brak danych buildu` — uruchomiono starszy build bez manifestu.

Porównanie jest wyłącznie odczytowe, ma ograniczony czas wykonania oraz zwraca
bezpieczny status zamiast błędu, gdy Git nie jest zainstalowany lub polecenie
się nie powiedzie.

## API i interfejs

Endpoint administracyjny zwraca nagłówek buildu, wykrycie repozytorium i listę
modułów. Nie ujawnia ścieżek plików ani pełnego stanu Git użytkownikom bez
uprawnień. Ten sam endpoint służy do pierwszego ładowania i ręcznego
odświeżenia.

Zakładka pokazuje kartę uruchomionego buildu, legendę statusów i tabelę:
**Moduł**, **Uruchomiony build**, **Lokalne repozytorium**, **Status**. Przycisk
**Odśwież porównanie** ponownie odczytuje lokalne Git i nie zapisuje ustawień.

## Testowanie

- testy rejestru i generowania manifestu z deterministycznymi danymi Git;
- testy bez Git, z uszkodzonym manifestem i ze starszym EXE bez manifestu;
- testy porównania commitów oraz niezacommitowanych zmian;
- test endpointu: tylko administrator otrzymuje dane;
- testy JS renderowania tabeli, statusów i ręcznego odświeżenia;
- testy skryptów obu generatorów potwierdzające dołączenie manifestu.

## Poza zakresem

Panel nie pobiera informacji z GitHub, nie sprawdza aktualności względem
zdalnej gałęzi, nie buduje EXE i nie naprawia samego problemu pionowego OCR.
Ma dostarczyć wiarygodnej informacji, czy poprawka OCR znajduje się w aktualnie
uruchomionym buildzie.
