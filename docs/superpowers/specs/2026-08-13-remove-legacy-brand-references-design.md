# Usunięcie historycznych referencji firmowych

## Cel

Usunąć z repozytorium historyczne referencje firmowe oraz lokalne notatki, które nie są częścią produktu.

## Zakres

- Usunąć `OLD_EXAMPLE_BASE_URL` i warunek migracyjny w normalizacji ustawień Pimcore. Każdy poprawny adres podany w konfiguracji pozostaje bez zmian.
- Usunąć dwa testy, których jedynym celem było sprawdzenie tej wycofanej migracji.
- Zamienić pozostałe firmowe adresy w aktywnych testach na neutralne domeny `.test`.
- Usunąć lokalne archiwum `.superpowers/sdd` i `REVIEW_WYDAJNOSCI.md`.

## Poza zakresem

- Nie zmieniać informacji o właścicielu repozytorium, licencji ani współpracownikach.
- Nie usuwać nazw technologii używanych przez obsługiwane integracje.
- Nie zmieniać `docs/superpowers`, ponieważ zawiera wersjonowaną dokumentację projektu.
- Nie zmieniać konfiguracji ścieżek aplikacji ani systemowego wykrywania Windows Defender.

## Weryfikacja

- Wyszukiwanie produkcyjnego kodu i testów nie zwraca usuniętych referencji firmowych.
- Testy konfiguracji Pimcore, warstwy webowej i obsługi Pimcore przechodzą.
