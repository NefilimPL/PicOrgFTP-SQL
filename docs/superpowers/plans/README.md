# Aktywne plany implementacyjne

Data programu: 2026-07-27
Stan zweryfikowano: **2026-08-06**

Plany wykonujemy w podanej kolejności zależności. Każdy dokument jest
samodzielnym zleceniem, a pakiety 2–6 zakładają ukończenie pakietu 1.

| Kolejność | Pakiet | Plan | Stan |
| --- | --- | --- | --- |
| 1 | SQLite lifecycle i telemetria | [plan](2026-07-27-sqlite-lifecycle-and-telemetry.md) | **w pełni wykonano** |
| 2 | Wyszukiwanie produktów i start desktopu | [plan](2026-07-27-product-query-and-desktop-startup.md) | **w pełni wykonano** — 7 z 7 zadań |
| 3 | Upload, obrazy i kolejka | [plan](2026-07-27-upload-image-processing-and-queue.md) | **w pełni wykonano** — 6 z 6 zadań |
| 4 | FTP i indeks plików | [plan](2026-07-27-ftp-and-file-indexing.md) | **w pełni wykonano** — 8 z 8 zadań; pełna regresja: 1247 testów i 66 subtestów |
| 5 | Integracje SQL, Pimcore i tłumaczenia | [plan](2026-07-27-integration-throughput.md) | **w toku** — 1 z 7 zadań ukończone; trwa zadanie 2: lifecycle klienta Pimcore i bezpieczne retry GET |
| 6 | Procesy w tle, polling i aktywni klienci | [plan](2026-07-27-background-runtime-and-polling.md) | **w pełni wykonano** |
| 7 | Podział dużych modułów | [plan](2026-07-27-module-boundaries.md) | **nie wykonano** |

## Pakiet 2 — wdrożony zakres

Plan `2026-07-27-product-query-and-desktop-startup.md` został wykonany na
gałęzi `TASK-4`. Najważniejsze rezultaty:

- jedno, współdzielone API zapytań o produkty dla SQLite i źródła Excel oraz
  delegowanie tych operacji przez panel WWW;
- ograniczone, indeksowane wyszukiwanie po ID, EAN i tekście; zapytania krótkie
  i długie korzystają z indeksów FTS, a wyniki zachowują wcześniejszą semantykę;
- ochrona integralności ID/EAN: walidacja importów wsadowych, jasny błąd dla
  historycznych duplikatów i zabezpieczenia przed nieprawidłowymi zapisami;
- anulowanie nieaktualnych podpowiedzi w przeglądarce, z pominięciem zdalnego
  zapytania, gdy lokalnie widoczne wyniki wypełniają listę;
- cache danych Excel oparty na ścieżce, czasie modyfikacji i rozmiarze pliku,
  z defensywnymi kopiami oraz unieważnianiem po udanym zapisie;
- natychmiastowe uruchomienie okna desktopowego i późniejsze ładowanie danych w
  workerze, bez wywołań Tk poza wątkiem UI, z obsługą błędu i ponowienia;
- benchmarki zapytań selektywnych, testy regresji oraz testy startu desktopu i
  obsługi nieaktualnych podpowiedzi.

### Potwierdzenie wdrożenia

Po wdrożeniu należy zrestartować proces panelu WWW i worker uploadu, aby każde
połączenie SQLite zarejestrowało funkcję używaną przez indeks krótkich fraz.
W panelu można następnie wyszukać produkt po ID, pełnym EAN i krótkim fragmencie
nazwy; podpowiedzi powinny reagować bez cofania się do starszego zapytania, a
okno desktopowe ma otwierać się przed zakończeniem ładowania danych.

Ostatnia pełna weryfikacja kodu dla pakietu 2: **1193 testy pytest**, **66
subtestów** i testy JavaScript podpowiedzi — wszystkie zakończone powodzeniem.

Specyfikacje źródłowe znajdują się w `../specs/`.
