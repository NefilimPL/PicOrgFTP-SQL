# PicSyncra: pełny rebranding i migracja danych

## Cel

Zastąpić roboczą nazwę produktu nazwą **PicSyncra** we wszystkich
artefaktach produktu. Nazwa ma wynikać z repozytorium
`NefilimPL/PicSyncra`. Obecne dane użytkowników muszą zostać przejęte
przez nową wersję bez utraty danych.

## Zakres

- Zmiana pakietu Pythona z `picorgftp_sql` na `picsyncra` oraz poprawa
  wszystkich importów, ścieżek zasobów, testów i komend uruchomieniowych.
- Zmiana uruchamiaczy na `PicSyncra.pyw`, `PicSyncra-WEB.pyw` i
  `PicSyncra-QtSlots.pyw`.
- Zmiana wszystkich nazw widocznych w aplikacjach desktopowej i webowej,
  tytułów okien, tacy systemowej, komunikatów, e-maili, nagłówków HTTP,
  rozszerzenia przeglądarki oraz metadanych FastAPI.
- Zmiana nazw EXE, paczek, artefaktów, wersji Windows, skryptów buildowych,
  workflow GitHub Actions i dokumentacji na PicSyncra.
- Zmiana repozytorium sprawdzanego przez funkcję statusu GitHub na
  `NefilimPL/PicSyncra`.
- Zmiana nazw prywatnych przestrzeni przeglądarki, zmiennych środowiskowych,
  plików blokad, PID-ów, logów i archiwów na wariant `PICSYNCRA` /
  `picsyncra`.
- Zastąpienie ikon runtime i buildów: lokalnej przez `PIC9_LOCAL.png`,
  webowej przez `PIC9_WEB.png`, a wariantu webowego z OCR przez
  `PIC9_WEB-OCR.png`.

Historyczne dokumenty w `docs/superpowers/` pozostają zapisem decyzji
podjętych wcześniej; ich treść nie będzie przepisywana, aby nie fałszować
historii. Wszystkie aktualne dokumenty produktu, konfiguracje i artefakty
będą używać PicSyncra.

## Architektura nazwy

W nowym pakiecie zostanie zdefiniowany pojedynczy moduł marki, udostępniający
stałe nazwy wyświetlane, techniczne i repozytorium. Ekrany, backend, buildy
i narzędzia Pythona będą pobierać nazwę produktu z tego modułu lub z
`GITHUB_REPOSITORY` w GitHub Actions. Dzięki temu następne zmiany nazwy nie
będą wymagały rozproszonych edycji literałów.

Statyczne pliki HTML i JavaScript otrzymają PicSyncra w elementach
widocznych dla użytkownika oraz w przestrzeniach nazw JavaScript i
`localStorage`. Nazwy identyfikatorów HTTP zostaną zmienione wspólnie po obu
stronach protokołu, aby nie dopuścić do rozbieżności klienta i serwera.

## Migracja danych użytkownika

Pierwsze uruchomienie PicSyncra wykona idempotentną migrację lokalnych
zasobów poprzedniej aplikacji do nowych nazw. Obejmuje to wskazaną bazę
SQLite, plik ustawień lokalnych, pliki historii, PID-y i katalogi robocze,
o ile znajdują się w katalogu aplikacji albo skonfigurowanym katalogu danych.

Migracja działa wyłącznie, gdy nie istnieje już odpowiednik PicSyncra. Dla
plików wykonywane jest kopiowanie z kontrolą powodzenia, a plik docelowy jest
udostępniany atomowo dopiero po pełnym skopiowaniu. Baza SQLite jest
migrowana razem z plikami WAL/SHM. Po powodzeniu pozostaje kopia źródłowa,
aby użytkownik mógł odtworzyć dane ręcznie; nowa aplikacja zawsze otwiera już
tylko lokalizacje PicSyncra. Proces zapisuje czytelne zdarzenia w logu i nie
blokuje startu, gdy nie znajdzie danych do migracji.

Obsługa danych historycznych zostanie odizolowana w module migracji. Jedynie
ten moduł może rozpoznawać poprzednie nazwy plików i kluczy. Żadna stara nazwa
nie może pojawić się w interfejsie, nowych plikach, buildach, opisach albo
normalnych ścieżkach wykonania.

## Ikony i pakowanie

Uruchamiacze desktopowe będą ustawiały odpowiednią ikonę przez wspólny moduł
zasobów. Generator lokalnego EXE utworzy ICO z `PIC9_LOCAL.png`. Generator
webowego EXE wybierze `PIC9_WEB.png` dla wersji bez lokalnych modeli i
`PIC9_WEB-OCR.png` dla wariantu zawierającego OCR. Ten sam wybór zostanie
odtworzony w GitHub Actions.

Artefakty mają otrzymać nazwy `PicSyncra.exe`, `PicSyncra-WEB.exe` oraz
`PicSyncra-web-<wersja>.zip` (z rozróżnieniem wariantu OCR tam, gdzie już
istnieje). Metadane wersji Windows, opisy plików oraz nazwy zasobów GitHub
muszą być z nimi zgodne.

## Obsługa błędów

Nieudana migracja nie może uszkodzić ani usunąć danych źródłowych. Aplikacja
zapisze przyczynę w logu, pokaże komunikat wskazujący lokalizację logu i
uruchomi się tylko wtedy, gdy może bezpiecznie użyć istniejących danych
PicSyncra albo utworzyć nowe. Wykrycie częściowo przeniesionej bazy zatrzyma
migrację i zachowa oba zestawy plików do ręcznego odzyskania.

## Testy i weryfikacja

- Testy migracji plików, ustawień i pary SQLite WAL/SHM: powodzenie,
  powtórne uruchomienie, kolizja z istniejącymi danymi PicSyncra i błąd I/O.
- Testy jednostkowe wspólnego modułu marki oraz statusu GitHub dla nowego
  repozytorium.
- Aktualizacja testów importów, uruchamiaczy, buildów, pakowania rozszerzenia
  i interfejsu webowego.
- Test integralności repozytorium, który odrzuca poprzednią nazwę poza
  dozwolonym, odizolowanym modułem migracji i plikami historii.
- Uruchomienie docelowego zestawu `pytest`, testów JavaScript oraz walidacji
  workflow/buildów po zmianie.

## Poza zakresem

Nie zmieniamy schematu danych aplikacji ani funkcji biznesowych. Nie ma też
kompatybilnego aliasu starego pakietu, uruchamiaczy ani artefaktów: po
migracji obowiązuje wyłącznie PicSyncra.
