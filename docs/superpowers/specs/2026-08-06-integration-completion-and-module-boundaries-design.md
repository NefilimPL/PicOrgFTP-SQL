# Domknięcie integracji i granice modułów — projekt

Data: 2026-08-06

## Cel

Domknąć rozpoczęty pakiet 5 programu wydajnościowego, usunąć przyczynę
timeoutu testu pollera statusu oraz podzielić odpowiedzialności skupione w
`picorgftp_sql/web/app.py`, `picorgftp_sql/app.py` i
`picorgftp_sql/web/static/app.js`. Zmiana nie modyfikuje publicznych tras,
formatów danych, konfiguracji integracji ani zachowania UI.

Prace powstaną w dwóch commitach na bieżącej gałęzi:

1. domknięcie integracji, poprawka pollera i spójny rejestr statusu;
2. granice modułów, assety builda i pełna regresja.

## Zakres pierwszego commitu

### Integracje

- Każda operacja Pimcore posiada dokładnie jedną prywatną sesję HTTP, o ile
  caller nie dostarczył klienta. Klient dostarczony przez callera nigdy nie
  jest zamykany. Automatyczne ponowienie obejmuje wyłącznie pojedynczy błąd
  połączenia dla `GET`, na świeżej sesji; `POST` i `PUT` nie są ponawiane.
- `SqlExecutionContext` przechowuje jedno połączenie dla jednego fingerprintu
  profilu w obrębie renderu. Kursory pozostają per zapytanie, a wszystkie
  połączenia są zamykane raz przy wyjściu z kontekstu.
- `TranslationCache` jest ograniczonym LRU z TTL i singleflight per klucz.
  Klucz zawiera provider, język, tekst i niejawny fingerprint konfiguracji;
  wyniki z ostrzeżeniem nie są cache'owane.
- Tylko mapowania zależne wyłącznie od danych produktu lub literałów są
  wykonywane równolegle. Limit wynosi cztery workery, a dwa zapytania tego
  samego profilu SQL nie korzystają równocześnie z tego samego połączenia.
- Standardowy, rozpoznany szablon SQL aktualizacji zdjęć jest scalany do
  jednego parametrycznego `UPDATE`. Szablon niestandardowy zachowuje obecną
  pętlę per slot jako fallback.

### Poller statusu

Timeout JavaScriptu zostanie odtworzony w środowisku zawierającym Node. Zmiana
ma usunąć wykrytą przyczynę w lifecycle timera lub promise, a nie wydłużać
limitu ani pomijać test. Test pozostanie deterministycznym sprawdzeniem pięciu
pollerów, limitów żądań oraz braku jednoczesnego requestu.

### Rejestr postępu

`docs/superpowers/STATUS.md` jest jedynym operacyjnym źródłem prawdy:
pakiet, zadanie, stan, commit i ostatnia weryfikacja. Dotychczasowe
`README.md` w katalogach `docs/superpowers`, `plans` i `specs` nie będą
duplikowały statusów; będą odsyłały do rejestru i zachowają tylko opis
przeznaczenia katalogu. Plany i specyfikacje historyczne pozostają jako
niezmienione artefakty wykonawcze.

## Zakres drugiego commitu

- `web/process_models.py` i `web/process_api.py` zawierają modele oraz router
  procesów; `web/app.py` pozostaje composition rootem i dostarcza zależności.
- `web/runtime_api.py` zawiera endpointy runtime, indeksu i presence, bez
  przenoszenia middleware, parsowania sesji lub locków rejestru klientów.
- `desktop_ftp_preview.py` zawiera kontroler podglądu bez Tk i bez importu
  `app`; `App` przekazuje mu callbacki UI oraz zamyka go przed zniszczeniem
  root.
- `static/autocomplete.js` i `static/process-jobs.js` eksportują wyłącznie
  API w `window.PicOrg`. `app.js` tworzy zależności i uruchamia je raz;
  moduły nie zakładają własnych stałych pollerów.
- Konfiguracja builda obejmuje wszystkie rozdzielone assety. Stare shimy są
  usuwane dopiero po potwierdzeniu call sites.

## Obsługa błędów i zgodność

Niezbędne błędy zachowują dotychczasowy kontrakt. Pierwszy błąd wymaganej
operacji mapowania zatrzymuje nierozpoczęte zadania, a zadania już działające
kończą przed zamknięciem kontekstu. Błąd zbiorczego SQL powoduje jeden rollback
i status błędu dla wszystkich objętych slotów. Żadna ścieżka nie loguje API
key, hasła ani fingerprintu zawierającego sekret.

## Weryfikacja

- testy jednostkowe i kontraktowe dla każdego nowego modułu;
- benchmark integracji: jedna sesja Pimcore, dwa profile SQL, cache
  tłumaczeń, maksymalnie cztery workery i jeden standardowy update zdjęć;
- snapshot tras, AST/import guards oraz test assetów PyInstaller;
- pełne `pytest`, kompilacja Python, testy i syntax-check Node;
- kontrola `git diff --check`.

Pełna regresja jest wykonywana w izolowanym środowisku zgodnym z zależnościami
projektu oraz z dostępnym Node. Znane niespójności lokalnego `.venv`, globalnego
`pydantic` i braku Node nie będą uznane za wynik weryfikacji produktu.
