# Plan rozwoju PicOrgFTP-SQL

Data utworzenia planu: 2026-04-26  
Ostatnia aktualizacja planu: 2026-04-26

## Zasady aktualizacji

Ten plik jest glownym rejestrem planowanych i wykonanych zmian w projekcie.

- Przy kazdym wykonanym zadaniu nalezy zaktualizowac jego `Status`, `Data aktualizacji` oraz `Data wykonania`.
- Jezeli zadanie zostalo wykonane czesciowo, status zmienia sie na `W toku`, a w polu `Opis / notatki` nalezy dopisac co zostalo zrobione i co zostalo do zamkniecia.
- Zadania bardziej zlozone musza miec opis oraz warunki wykonania, zeby bylo jasne kiedy mozna oznaczyc je jako `Wykonane`.
- Zadania wykonane zostaja w tej samej kategorii, aby historia rozwoju byla widoczna razem z planem.
- Nowe zadania nalezy dopisywac z data dodania i priorytetem.

## Legenda

Priorytet:

- `P0` - krytyczne: blokuje dzialanie, bezpieczenstwo lub wydanie.
- `P1` - wysokie: wazne dla stabilnosci, poprawnosci danych albo glownego przeplywu pracy.
- `P2` - srednie: poprawia wygode, utrzymanie lub jakosc, ale nie blokuje pracy.
- `P3` - niskie: usprawnienie pomocnicze, porzadkowe albo kosmetyczne.

Status:

- `Planowane` - zadanie jest wpisane do wykonania.
- `W toku` - prace zostaly rozpoczete, ale zadanie nie spelnia jeszcze warunkow wykonania.
- `Wykonane` - zadanie spelnia warunki wykonania i zostalo oznaczone data.
- `Wstrzymane` - zadanie czeka na decyzje, dane dostepowe, zewnetrzna zaleznosc albo zmiane zakresu.

## Stabilnosc i bezpieczenstwo

| ID | Zadanie | Priorytet | Status | Data dodania | Data aktualizacji | Data wykonania | Opis / notatki |
| --- | --- | --- | --- | --- | --- | --- | --- |
| STAB-001 | Przeglad obslugi bledow w operacjach FTP, SQL i plikowych | P1 | Planowane | 2026-04-26 | 2026-04-26 | - | Sprawdzic, czy bledy sa logowane czytelnie, nie przerywaja niepotrzebnie calego przeplywu i daja uzytkownikowi jasny komunikat. |
| STAB-002 | Uporzadkowanie walidacji danych produktu przed zapisem i wysylka | P1 | Planowane | 2026-04-26 | 2026-04-26 | - | Warunki wykonania: walidacja EAN, wymaganych pol formularza, nazw katalogow i mapowania slotow jest pokryta testami. |
| STAB-003 | Utrzymanie blokady pojedynczej instancji aplikacji | P2 | Wykonane | 2026-04-26 | 2026-04-26 | 2026-04-26 | W repozytorium istnieje modul `runtime_lock.py`; zadanie oznaczone jako wykonane na podstawie obecnego stanu projektu. |

## Konfiguracja i dane lokalne

| ID | Zadanie | Priorytet | Status | Data dodania | Data aktualizacji | Data wykonania | Opis / notatki |
| --- | --- | --- | --- | --- | --- | --- | --- |
| CONF-001 | Doprecyzowanie migracji i kompatybilnosci `config.json` | P1 | Planowane | 2026-04-26 | 2026-04-26 | - | Warunki wykonania: starszy plik konfiguracji uruchamia sie bez recznej edycji, brakujace pola sa uzupelniane domyslnie, a testy potwierdzaja kompatybilnosc. |
| CONF-002 | Przeglad szyfrowania sekretow i komunikatow dla `APP_SECRET` | P1 | Planowane | 2026-04-26 | 2026-04-26 | - | Sprawdzic scenariusze braku klucza, zmiany klucza i odczytu istniejacej konfiguracji. |
| CONF-003 | Obsluga katalogu roboczego w `local_settings.json` | P2 | Wykonane | 2026-04-26 | 2026-04-26 | 2026-04-26 | README opisuje automatyczne tworzenie i ponowny wybor katalogu roboczego; zadanie oznaczone jako wykonane na podstawie obecnego stanu projektu. |

## FTP i SQL

| ID | Zadanie | Priorytet | Status | Data dodania | Data aktualizacji | Data wykonania | Opis / notatki |
| --- | --- | --- | --- | --- | --- | --- | --- |
| INT-001 | Rozszerzenie testow integracji FTP bez realnego serwera | P1 | Planowane | 2026-04-26 | 2026-04-26 | - | Warunki wykonania: testy pokrywaja wysylke, usuwanie starych plikow, blad logowania i brak pliku zdalnego z uzyciem mockow albo lokalnego serwera testowego. |
| INT-002 | Rozszerzenie testow SQL dla MS SQL i MySQL | P1 | Planowane | 2026-04-26 | 2026-04-26 | - | Warunki wykonania: testy sprawdzaja parametryzacje zapytan, mapowanie kolumn, brak kolumny oraz blad polaczenia bez potrzeby dostepu do produkcyjnej bazy. |
| INT-003 | Obecnosci LOCAL/FTP/SQL przy slotach zdjec | P2 | Wykonane | 2026-04-26 | 2026-04-26 | 2026-04-26 | Funkcja jest opisana w README i widoczna w logice aplikacji; zadanie oznaczone jako wykonane na podstawie obecnego stanu projektu. |

## Obsluga zdjec i indeks plikow

| ID | Zadanie | Priorytet | Status | Data dodania | Data aktualizacji | Data wykonania | Opis / notatki |
| --- | --- | --- | --- | --- | --- | --- | --- |
| IMG-001 | Audyt przetwarzania duzych zestawow zdjec | P2 | Planowane | 2026-04-26 | 2026-04-26 | - | Sprawdzic wydajnosc miniatur, kopiowania, kompresji i indeksowania przy wielu plikach jednoczesnie. |
| IMG-002 | Doprecyzowanie zasad nazw plikow i bezpiecznych znakow | P1 | Planowane | 2026-04-26 | 2026-04-26 | - | Warunki wykonania: nazwy generowane dla EAN, slotu i danych produktu sa stabilne, bezpieczne dla Windows oraz pokryte testami. |
| IMG-003 | Automatyczna organizacja zdjec do struktury katalogow produktu | P1 | Wykonane | 2026-04-26 | 2026-04-26 | 2026-04-26 | Funkcja jest opisana w README i wspierana przez uslugi plikowe; zadanie oznaczone jako wykonane na podstawie obecnego stanu projektu. |

## Interfejs i lokalizacja

| ID | Zadanie | Priorytet | Status | Data dodania | Data aktualizacji | Data wykonania | Opis / notatki |
| --- | --- | --- | --- | --- | --- | --- | --- |
| UI-001 | Przeglad spojnosci tlumaczen PL/ENG/UA | P2 | Planowane | 2026-04-26 | 2026-04-26 | - | Warunki wykonania: brak brakujacych kluczy, brak oczywistych literowek i zgodne nazewnictwo podstawowych akcji w trzech jezykach. |
| UI-002 | Usprawnienie diagnostyki UI po zmianach w oknach ustawien | P2 | Planowane | 2026-04-26 | 2026-04-26 | - | Sprawdzic, czy raport diagnostyczny wykrywa brakujace przyciski, niespojny stan slotow i problemy z lokalizacja. |
| UI-003 | Przelaczanie jezyka interfejsu | P2 | Wykonane | 2026-04-26 | 2026-04-26 | 2026-04-26 | README opisuje jezyki `auto`, `pl`, `ua`, `eng`; zadanie oznaczone jako wykonane na podstawie obecnego stanu projektu. |

## Testy, CI i wydania

| ID | Zadanie | Priorytet | Status | Data dodania | Data aktualizacji | Data wykonania | Opis / notatki |
| --- | --- | --- | --- | --- | --- | --- | --- |
| QA-001 | Uruchomienie pelnego zestawu testow po wiekszych zmianach | P1 | Planowane | 2026-04-26 | 2026-04-26 | - | Przy wiekszych zmianach uruchamiac `pytest`; wynik testow dopisywac w notatkach zadania albo w podsumowaniu zmiany. |
| QA-002 | Rozbudowa testow regresji dla glownego przeplywu pracy | P1 | Planowane | 2026-04-26 | 2026-04-26 | - | Warunki wykonania: testy potwierdzaja zapis lokalny, opcjonalna wysylke FTP, opcjonalna aktualizacje SQL i reset stanu formularza. |
| QA-003 | Budowanie EXE przez GitHub Actions | P2 | Wykonane | 2026-04-26 | 2026-04-26 | 2026-04-26 | W repozytorium istnieje workflow `.github/workflows/build-exe.yml`; zadanie oznaczone jako wykonane na podstawie obecnego stanu projektu. |

## Dokumentacja

| ID | Zadanie | Priorytet | Status | Data dodania | Data aktualizacji | Data wykonania | Opis / notatki |
| --- | --- | --- | --- | --- | --- | --- | --- |
| DOC-001 | Utrzymanie README zgodnie z aktualnym zachowaniem aplikacji | P2 | Planowane | 2026-04-26 | 2026-04-26 | - | Przy zmianach w konfiguracji, FTP, SQL, lokalizacji albo budowaniu EXE aktualizowac README w tej samej zmianie. |
| DOC-002 | Dodanie sekcji znanych ograniczen | P3 | Planowane | 2026-04-26 | 2026-04-26 | - | Wypisac ograniczenia dotyczace zaleznosci systemowych, sterownikow ODBC, dostepu do FTP/SQL i budowania EXE. |
| DOC-003 | Dwujezyczny opis dzialania i konfiguracji | P2 | Wykonane | 2026-04-26 | 2026-04-26 | 2026-04-26 | README zawiera sekcje English oraz Polski; zadanie oznaczone jako wykonane na podstawie obecnego stanu projektu. |

## Szablon nowego zadania

```text
| ID | Zadanie | Priorytet | Status | Data dodania | Data aktualizacji | Data wykonania | Opis / notatki |
| --- | --- | --- | --- | --- | --- | --- | --- |
| KAT-000 | Nazwa zadania | P2 | Planowane | RRRR-MM-DD | RRRR-MM-DD | - | Opis, warunki wykonania albo powiazane pliki. |
```
