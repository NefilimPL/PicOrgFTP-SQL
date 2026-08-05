# Aktywny program optymalizacji wydajności

Data programu: 2026-07-27
Stan realizacji: **2026-08-05**

Ten katalog zawiera aktywne, zatwierdzone specyfikacje programu optymalizacji.
Odpowiadające im plany implementacyjne znajdują się w `../plans/`.

## Pakiety

| Kolejność | Pakiet | Specyfikacja | Zależność | Stan |
| --- | --- | --- | --- | --- |
| 1 | SQLite lifecycle i telemetria | [specyfikacja](2026-07-27-sqlite-lifecycle-and-telemetry-design.md) | brak | **wykonano** |
| 2 | Wyszukiwanie produktów i start desktopu | [specyfikacja](2026-07-27-product-query-and-desktop-startup-design.md) | pakiet 1 | **wykonano** |
| 3 | Upload, obrazy i kolejka | [specyfikacja](2026-07-27-upload-image-processing-and-queue-design.md) | pakiet 1 | nie wykonano |
| 4 | FTP i indeks plików | [specyfikacja](2026-07-27-ftp-and-file-indexing-design.md) | pakiet 1 | nie wykonano |
| 5 | Integracje SQL, Pimcore i tłumaczenia | [specyfikacja](2026-07-27-integration-throughput-design.md) | pakiet 1 | nie wykonano |
| 6 | Procesy w tle, polling i aktywni klienci | [specyfikacja](2026-07-27-background-runtime-and-polling-design.md) | pakiet 1 | **wykonano** |
| 7 | Podział dużych modułów | [specyfikacja](2026-07-27-module-boundaries-design.md) | pakiety 1–6 | nie wykonano |

## Pakiet 2 — zrealizowane decyzje projektowe

Specyfikacja
`2026-07-27-product-query-and-desktop-startup-design.md` jest zrealizowana w
całości. Wdrożenie zachowuje kompatybilność publicznego API, formatów danych i
interfejsu użytkownika, a jednocześnie wprowadza następujące mechanizmy:

| Obszar | Zrealizowana zmiana |
| --- | --- |
| Kontrakt danych | Wspólny interfejs zapytań produktów dla SQLite i Excel; panel WWW korzysta z aktywnego źródła danych. |
| Wyszukiwanie | Indeksy dla ID/EAN oraz FTS dla tekstu, także dla krótkich fraz; limity są egzekwowane po stronie źródła danych. |
| Spójność danych | Normalizacja i unikalność rzeczywistych EAN, wykrywanie niejednoznacznych danych historycznych oraz preflight importów. |
| Podpowiedzi WWW | Anulowanie żądań nieaktualnych, kontrola kolejności odpowiedzi i brak zdalnego zapytania przy wypełnionej lokalnej liście. |
| Excel | Snapshot cache zależny od wersji pliku, defensywne kopie i unieważnianie cache wyłącznie po sukcesie zapisu. |
| Desktop | Najpierw renderowane jest UI, potem dane są ładowane w tle; komunikacja z Tk odbywa się wyłącznie w wątku UI, z retry po błędzie. |
| Wydajność | Dodane benchmarki zapytań i regresje dla wyszukiwania, podpowiedzi oraz startu aplikacji desktopowej. |

W środowisku produkcyjnym procesy zapisujące dane do SQLite muszą być uruchomione
po aktualizacji, aby zarejestrować per-połączenie funkcję pomocniczą używaną
przez indeks krótkich fraz.

## Mapa zatwierdzonych zmian

| Zmiana | Pakiet | Stan |
| --- | --- | --- |
| Wielokrotna inicjalizacja schematu SQLite | 1 | wykonano |
| Ustawienia SQLite dla pracy wielowątkowej | 1 | wykonano |
| Nadmiarowe zapisy postępu i telemetrii | 1 | wykonano |
| Pełne ładowanie produktów przez wyszukiwanie i podpowiedzi | 2 | **wykonano: selektywne, indeksowane zapytania** |
| Pełne listy przed startem desktopu | 2 | **wykonano: ładowanie po starcie UI** |
| Blokowanie event loop podczas uploadu | 3 | nie wykonano |
| Wielokrotne dekodowanie i kodowanie obrazów | 3 | nie wykonano |
| Nieograniczona kolejka przetwarzania | 3 | nie wykonano |
| Pełny listing FTP dla EAN bez zmiany układu katalogów | 4 | nie wykonano |
| Pełny lokalny skan przy każdym starcie | 4 | nie wykonano |
| Podwójny zapis indeksu plików | 4 | nie wykonano |
| Niespójny cleanup plików tymczasowych FTP | 4 | nie wykonano |
| Zdublowane lub nieużywane indeksowanie | 4 | nie wykonano |
| Keep-alive Pimcore z ochroną zgodności | 5 | nie wykonano |
| Sekwencyjne SQL i tłumaczenia | 5 | nie wykonano |
| Osobny UPDATE dla każdego slotu | 5 | nie wykonano |
| Worker powiadomień budzony co dwie sekundy | 6 | wykonano |
| Niezależne pollery frontendu | 6 | wykonano |
| Zapis aktywnych klientów podczas trzymania blokady | 6 | wykonano |
| Duże moduły aplikacji | 7 | nie wykonano |

## Ograniczenia całego programu

- Nie zmieniamy elementów spoza powyższej mapy.
- FTP zachowuje płaski katalog bez subfolderów per EAN.
- Pimcore zachowuje istniejące profile, sekrety, endpointy, autoryzację,
  timeouty i semantykę operacji.
- Publiczne API, formaty danych oraz zachowanie UI pozostają kompatybilne.
- Każdy pakiet wymaga testów regresji, benchmarku przed/po i możliwości
  etapowego wycofania.
- Każda implementacja jest prowadzona według odpowiadającego jej planu z
  `../plans/`.
