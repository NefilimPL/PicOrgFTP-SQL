# Usunięcie historycznych referencji firmowych

## Cel

Usunąć z repozytorium historyczne referencje `xml.wipmebgroup.pl` i `http://10.10.0.5` oraz lokalne notatki, które nie są częścią produktu.

## Zakres

- Usunąć `OLD_EXAMPLE_BASE_URL` i warunek migracyjny w normalizacji ustawień Pimcore. Każdy poprawny adres podany w konfiguracji pozostaje bez zmian.
- Usunąć dwa testy, których jedynym celem było sprawdzenie tej wycofanej migracji.
- Zamienić wszystkie pozostałe użycia `http://10.10.0.5` w aktywnych testach na neutralny `http://pimcore.example.test` oraz `xml.wipmebgroup.pl` na `cdn.example.test`.
- Usunąć lokalne archiwum `.superpowers/sdd` i `REVIEW_WYDAJNOSCI.md`.

## Poza zakresem

- Nie zmieniać informacji o właścicielu repozytorium, licencji ani współpracownikach.
- Nie usuwać nazw technologii używanych przez obsługiwane integracje.
- Nie zmieniać `docs/superpowers`, ponieważ zawiera wersjonowaną dokumentację projektu.
- Nie zmieniać konfiguracji ścieżek aplikacji ani systemowego wykrywania Windows Defender.

## Weryfikacja

- Wyszukiwanie produkcyjnego kodu i testów nie zwraca `wipmebgroup` ani `10.10.0.5`.
- Testy konfiguracji Pimcore, warstwy webowej i obsługi Pimcore przechodzą.
