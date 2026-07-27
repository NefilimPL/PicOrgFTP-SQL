# Aktywny program optymalizacji wydajności

Data programu: 2026-07-27

Ten katalog zawiera wyłącznie aktywne, zatwierdzone specyfikacje programu
optymalizacji. Odpowiadające im plany implementacyjne znajdują się w
`../plans/`.

## Pakiety

| Kolejność | Pakiet | Specyfikacja | Zależność |
| --- | --- | --- | --- |
| 1 | SQLite lifecycle i telemetria | [specyfikacja](2026-07-27-sqlite-lifecycle-and-telemetry-design.md) | brak |
| 2 | Wyszukiwanie produktów i start desktopu | [specyfikacja](2026-07-27-product-query-and-desktop-startup-design.md) | pakiet 1 |
| 3 | Upload, obrazy i kolejka | [specyfikacja](2026-07-27-upload-image-processing-and-queue-design.md) | pakiet 1 |
| 4 | FTP i indeks plików | [specyfikacja](2026-07-27-ftp-and-file-indexing-design.md) | pakiet 1 |
| 5 | Integracje SQL, Pimcore i tłumaczenia | [specyfikacja](2026-07-27-integration-throughput-design.md) | pakiet 1 |
| 6 | Procesy w tle, polling i aktywni klienci | [specyfikacja](2026-07-27-background-runtime-and-polling-design.md) | pakiet 1 |
| 7 | Podział dużych modułów | [specyfikacja](2026-07-27-module-boundaries-design.md) | pakiety 1–6 |

## Mapa zatwierdzonych zmian

| Zmiana | Pakiet |
| --- | --- |
| Wielokrotna inicjalizacja schematu SQLite | 1 |
| Ustawienia SQLite dla pracy wielowątkowej | 1 |
| Nadmiarowe zapisy postępu i telemetrii | 1 |
| Pełne ładowanie produktów przez wyszukiwanie i podpowiedzi | 2 |
| Pełne listy przed startem desktopu | 2 |
| Blokowanie event loop podczas uploadu | 3 |
| Wielokrotne dekodowanie i kodowanie obrazów | 3 |
| Nieograniczona kolejka przetwarzania | 3 |
| Pełny listing FTP dla EAN bez zmiany układu katalogów | 4 |
| Pełny lokalny skan przy każdym starcie | 4 |
| Podwójny zapis indeksu plików | 4 |
| Niespójny cleanup plików tymczasowych FTP | 4 |
| Zdublowane lub nieużywane indeksowanie | 4 |
| Keep-alive Pimcore z ochroną zgodności | 5 |
| Sekwencyjne SQL i tłumaczenia | 5 |
| Osobny UPDATE dla każdego slotu | 5 |
| Worker powiadomień budzony co dwie sekundy | 6 |
| Niezależne pollery frontendu | 6 |
| Zapis aktywnych klientów podczas trzymania blokady | 6 |
| Duże moduły aplikacji | 7 |

## Ograniczenia całego programu

- Nie zmieniamy elementów spoza powyższej mapy.
- FTP zachowuje płaski katalog bez subfolderów per EAN.
- Pimcore zachowuje istniejące profile, sekrety, endpointy, autoryzację,
  timeouty i semantykę operacji.
- Publiczne API, formaty danych oraz zachowanie UI pozostają kompatybilne.
- Każdy pakiet wymaga testów regresji, benchmarku przed/po i możliwości
  etapowego wycofania.
- Każda implementacja ma być prowadzona według odpowiadającego jej planu z
  `../plans/`.
