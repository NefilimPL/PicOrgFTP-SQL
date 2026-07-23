# Globalna strefa czasu i zwarty nagłówek zasobów — projekt

## Cel

Panel ma używać jednej, wspólnej dla instalacji strefy czasu we wszystkich
widokach. Administrator wybiera ją z pełnej listy stref IANA. Równocześnie
nagłówek ma zajmować mniej miejsca, a szczegóły zasobów mają używać jasnych
określeń klientów i alarmów.

## Ustawienie strefy czasu

- Globalne ustawienie `display_time_zone` jest trwałe, domyślnie `UTC` i może
  zostać zmienione wyłącznie zwykłą ścieżką zapisu ustawień administratora.
- Backend tworzy pełną, posortowaną listę nazw IANA z `zoneinfo.available_timezones()`;
  `UTC` jest zawsze dostępne i znajduje się na początku listy.
- Backend waliduje zapis: dozwolone są tylko `UTC` i nazwy zwrócone przez tę
  listę. Nieprawidłowa wartość nie zastępuje ostatniego poprawnego ustawienia.
- Ustawienia pokazują wyszukiwalny wybór z pełnej listy, bez ręcznego wpisywania
  niezweryfikowanej wartości.

## Formatowanie czasu

- JavaScript używa jednego formattera dla wszystkich widocznych timestampów.
  Przyjmuje on epoch lub ISO UTC i formatuje wartość w `display_time_zone`.
- Formatter używa `Intl.DateTimeFormat` z wybraną nazwą IANA. Strefa
  `Europe/Warsaw` automatycznie wyświetla właściwy dla daty CET/CEST oraz
  offset UTC+01:00/UTC+02:00; nazwa CEST nie jest przechowywana jako ustawienie.
- Nieobsługiwana przez przeglądarkę strefa ma bezpieczny fallback do UTC i nie
  zmienia danych źródłowych.
- Backendowe odpowiedzi zawierają surowy epoch lub ISO dla każdego widoku,
  który obecnie otrzymuje jedynie gotowy tekst lokalnego czasu. UI nie próbuje
  odgadywać strefy z takiego tekstu.
- Przełącznik obejmuje wszystkie daty i czasy panelu: health, zasoby, alarmy,
  historię, operacje, logi na żywo oraz szczegóły tożsamości/użytkowników.

## Układ nagłówka i terminologia zasobów

- Wersja i lokalizacja są zwarte, w jednej kolumnie nad nagłówkiem.
- Obok stanu opóźnienia widoczny jest zwarty, jednoliniowy skrót metryk systemu
  i backendu. Szczegółowy panel nadal otwiera się przez hover, fokus lub klik.
- `Aktywni klienci` zmienia się na `Aktywni w ostatnich 3 min`; jest to liczba
  unikalnych klientów z nie-statycznym żądaniem w tym oknie, a nie liczba
  otwartych połączeń.
- Alarm oczekujący oznacza pierwszą wysoką próbkę backendu. Alarm aktywny oznacza
  dwa kolejne przekroczenia progu backendu; dwa kolejne normalne odczyty go
  zwalniają.

## Testy i bezpieczeństwo

- Testy konfiguracji obejmują domyślne ustawienie, walidację IANA, trwałość i
  ekspozycję listy stref bez sekretów.
- Testy web/API obejmują zapis przez administratora oraz odrzucenie niepoprawnej
  strefy.
- Testy integralności UI wymagają użycia centralnego formattera we wszystkich
  zidentyfikowanych miejscach i wyszukiwalnego wyboru strefy.
- Testy formatowania pokrywają UTC, Europe/Warsaw dla dat letnich i zimowych
  oraz fallback do UTC.
