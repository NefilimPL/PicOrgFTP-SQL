# Konfigurowalny układ eksportu importowego Pimcore

## Cel

Umożliwić administratorowi przygotowanie eksportu CSV i XLSX, którego nagłówki i kolejność kolumn są zgodne z wymaganiami importu do Pimcore.

## Problem

Aktualny eksport buduje nagłówki z opisowych etykiet mapowań oraz bierze ich kolejność z listy mapowań. Ten układ nie jest niezależnie konfigurowalny i nie pozwala wstawić kolumn wymaganych przez importer, ale niepochodzących z aplikacji.

## Zakres

- Dodać do ustawień Pimcore zapisany, niezależny układ eksportu.
- Udostępnić osobne okno „Edytuj kolejność pól do eksportu” obok akcji eksportu danych Pimcore.
- Każda pozycja układu jest jednym z dwóch typów:
  - pole Pimcore: wskazuje skonfigurowane mapowanie przez techniczną nazwę `pimcore_field`; jego domyślny nagłówek jest tą samą nazwą, ale administrator może wpisać własny;
  - pusta kolumna: ma opcjonalny własny nagłówek i dla każdego rekordu eksportuje pustą wartość.
- Edytor pozwala dodać pozycję, usunąć ją, przesunąć w górę lub w dół oraz zmienić nagłówek.
- Eksport CSV i XLSX używa dokładnie tej samej listy pozycji: kolejność listy wyznacza kolejność nagłówków i danych.
- Wartość pola Pimcore jest odczytywana z zapisanych danych zgłoszenia po jego mapowaniu źródłowym. Zatem np. rekord `values["EAN"]` trafi pod kolumnę nagłówka `ean`, gdy mapowanie `EAN -> ean` zostanie wybrane w układzie.
- Istniejące konfiguracje bez układu działają kompatybilnie: przy odczycie jest tworzony domyślny układ zawierający wszystkie obecne mapowania, w ich obecnej kolejności, z nagłówkami `pimcore_field`.

## Poza zakresem

- Nie zmieniać samych mapowań formularza do Pimcore ani układu formularza.
- Nie implementować importu pliku do Pimcore ani nie zmieniać formatu wymaganego przez zewnętrzny importer poza kolejnością, nagłówkami i pustymi kolumnami.
- Nie dodawać przeciągania elementów myszą; sterowanie góra/dół zapewnia dostępny i jednoznaczny sposób zmiany kolejności.

## Dane i walidacja

- W konfiguracji `pimcore` zostanie dodane pole listowe `export_columns`.
- Pozycja pola zawiera typ `field`, techniczną nazwę `pimcore_field` oraz `header`.
- Pozycja pusta zawiera typ `blank` i `header`.
- Normalizacja odrzuca pozycje o nieznanym typie, a pozycje `field` bez nazwy albo nieodnoszące się do aktualnego mapowania. Nie pozwala też dodać tego samego pola więcej niż raz.
- Pusty nagłówek jest prawidłowy dla pustej kolumny; dla pola techniczna nazwa będzie użyta jako bezpieczna wartość domyślna.

## Interfejs

- Modal układu eksportu pokazuje listę wierszy z numerem pozycji, typem, nazwą pola lub oznaczeniem pustej kolumny, polem nagłówka oraz przyciskami przesunięcia i usunięcia.
- Dodanie pola oferuje wyłącznie pola obecne w bieżących mapowaniach i niewystępujące jeszcze w układzie.
- Dodanie pustej kolumny dodaje nową pozycję na końcu listy.
- Zapis odsyła pełny układ wraz z pozostałymi ustawieniami Pimcore i od razu aktualizuje stan aplikacji.

## Testy

- Normalizacja konfiguracji zachowuje poprawny układ, tworzy domyślny układ dla starszych ustawień i odrzuca pozycje niepoprawne lub zduplikowane.
- Eksport CSV i XLSX sprawdza techniczne nagłówki, własne nagłówki, kolejność pól oraz puste kolumny.
- Test endpointu potwierdza, że odpowiedź nadal poprawnie udostępnia oba formaty.
- Test integralności interfejsu sprawdza przycisk edytora, modal, akcje dodawania, przesuwania i zapisywania.
