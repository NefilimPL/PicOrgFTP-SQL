# Pimcore 6.6 REST

PicOrgFTP-SQL może korzystać z Pimcore 6.6 REST do odczytu konfiguracji klas, wyszukiwania produktu po EAN oraz tworzenia brakujących obiektów produktu.

## Konfiguracja

1. W Pimcore włącz `Settings > System Settings > Web Service API`.
2. Utwórz albo wybierz dedykowanego użytkownika Pimcore i skopiuj jego klucz API.
3. Nadaj temu użytkownikowi uprawnienia REST do odczytu informacji o serwerze, listy klas, definicji klasy, folderów i obiektów.
4. Do pracy runtime dodaj uprawnienia tworzenia i aktualizacji obiektów.
5. Uprawnienie usuwania jest potrzebne tylko dla testu zapisu z opcją `Usun po tescie`.
6. W PicOrgFTP-SQL otwórz `Ustawienia > Pimcore`.
7. Pierwsza konfiguracja jest czteroetapowym kreatorem dla administratora: połączenie, klasa i folder obiektów, pola produktu oraz test i zapis.

Kreator potrafi pobrać klasy, foldery z drzewa `Objects` oraz pola klasy. Ręczne wpisanie klasy albo parenta jest tylko awaryjnym fallbackiem. Folder docelowy oznacza parent w drzewie obiektów Pimcore, a nie katalog zdjęć, assetów ani folder systemu plików.

## Mapowanie pól

EAN musi być mapowany jako wymagane pole. Wyszukiwanie EAN obejmuje całą skonfigurowaną klasę, niezależnie od folderu. Folder docelowy jest używany tylko podczas tworzenia nowego obiektu.

Dla tekstowego pola mapowania przycisk `Konstruuj` otwiera kreator automatycznej wartości. Szablon może korzystać z danych produktu, innych mapowań Pimcore, funkcji tekstowych, grup warunkowych oraz opcjonalnego tłumaczenia. Zmiany są zapisywane razem z ustawieniami Pimcore.

Przykład szablonu:

```text
{NAZWA} - {TYP} {KOLOR 1}(/{KOLOR 2})(/{KOLOR 3})
```

Tekst i znaki poza placeholderami są kopiowane do wyniku. Grupa `(...)` znika w całości, jeżeli któryś zawarty w niej placeholder jest pusty. Wielkość zapisu aliasu steruje wielkością liter (`{NAZWA}`, `{Nazwa}`, `{nazwa}`), a funkcje dopisuje się po `|`, np. `{Nazwa|trim|upper}`.

Dostępne funkcje: `keep`, `trim`, `normalize_spaces`, `upper`, `lower`, `title`, `capitalize`, `replace`, `default`, `substring`, `truncate`, `strip_diacritics`, `slug`, `number`, `filled`, `any_filled`, `count_filled` i `if_filled`.

### Wymiary z obrazów

Kreator szablonu może lokalnie odczytać szerokość, głębokość albo wysokość z rysunku wymiarowego w wybranym slocie zdjęcia. W sekcji `Wymiar z obrazu` włącz opcję, wybierz slot, rodzaj wymiaru i minimalną pewność tekstu. Domyślny próg wynosi 80%; wynik o mniejszej pewności nie wypełnia pola.

Przycisk danych w kreatorze wstawia do formuły wartość w tym formacie:

```text
{IMAGE_DIMENSION:15:WIDTH|keep}
```

Liczby są zwracane bez jednostki i z kropką dziesiętną, więc `130,5 cm` staje się `130.5`. Obraz jest analizowany wyłącznie na komputerze lub serwerze, na którym działa aplikacja; nie jest wysyłany do zewnętrznego API.

Jednorazowo zainstaluj lokalny OCR w środowisku aplikacji:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-vision.txt
```

Jeżeli w slocie nie ma obrazu, OCR nie jest zainstalowany, nie znaleziono wymiaru albo pewność jest niższa od progu, dane pole pozostaje puste i podgląd pokazuje odpowiedni komunikat. Pozostałe mapowania nadal są przeliczane.

### Sprawdzanie wypełnienia pól

`filled` zamienia wypełnione pole na `1`, a puste pole na `0`. Dzięki temu można policzyć paczki po wpisanej szerokości:

```text
{PIMCORE:parcel_1_width|filled}+{PIMCORE:parcel_2_width|filled}+{PIMCORE:parcel_3_width|filled}+{PIMCORE:parcel_4_width|filled}+{PIMCORE:parcel_5_width|filled}+{PIMCORE:parcel_6_width|filled}+{PIMCORE:parcel_7_width|filled}+{PIMCORE:parcel_8_width|filled}+{PIMCORE:parcel_9_width|filled}+{PIMCORE:parcel_10_width|filled}+{PIMCORE:parcel_11_width|filled}
```

`any_filled` zwraca `1`, gdy jego pole lub któreś z dodatkowych pól ma wartość. Dodatkowe źródła wpisuje się w cudzysłowach. Przykład dla paczki, która ma być liczona po dowolnym wymiarze:

```text
{PIMCORE:parcel_1_depth|any_filled:"PIMCORE:parcel_1_height","PIMCORE:parcel_1_weight","PIMCORE:parcel_1_width"}
```

`count_filled` liczy wszystkie wypełnione pola w tej samej składni. `if_filled:"tekst gdy jest","tekst gdy brak"` zwraca jeden z dwóch tekstów zależnie od tego, czy dane pole jest wypełnione.

## Testy i zapis

`Sprawdz konfiguracje` wykonuje test read-only i pokazuje szczegóły techniczne w rozwijanych blokach.

`Testowo dodaj obiekt` pobiera za każdym razem nowe, unikalne i nadal edytowalne wartości. Opcja `Usun po tescie` próbuje potem usunąć obiekt.

Normalne tworzenie brakującego produktu z głównego panelu automatycznie przelicza zapisane szablony i publikuje obiekt. Edycja pokazuje aktualne wartości bez nadpisywania; tylko `Przelicz pole` stosuje szablon do wybranego pola. Zapis odrzuca zmianę, jeżeli obiekt został w międzyczasie zmieniony w Pimcore.

Zwykli użytkownicy nie widzą kreatora ani ustawień Pimcore. Gdy integracja jest wyłączona albo konfiguracja jest niekompletna, panel nie pokazuje kontrolek runtime Pimcore, nie odpala lookupu EAN i nie pokazuje promptu tworzenia produktu.

## Profile SQL dla Pimcore

Domyślny profil SQL jest zawsze używany przez Sloty. Dodatkowe profile SQL można tworzyć w zakładce ustawień SQL i wybierać tylko w mapowaniach Pimcore, których pole szablonu jest ustawione na `SQL`.

W tym trybie mapowanie używa osobnego pola zapytania SQL i zapisuje pierwszą kolumnę pierwszego wiersza do formularza Pimcore. Formularze tworzenia i testu stosują wyniki SQL tylko do pustych pól. Formularze edycji wymagają jawnego przeliczenia i pokazują różnice względem wartości ręcznie wpisanej przed zastosowaniem wyliczonej wartości.

## Sekrety i audyt

Klucz API jest przechowywany w postaci zaszyfrowanej. Standardowy endpoint ustawień ani logi operacji Pimcore nigdy go nie zwracają.

Operacje tworzenia, testu i edycji zapisują zredagowany audyt z ID, kluczem albo ścieżką obiektu, gdy są znane. Jeżeli automatyczne usuwanie obiektu testowego się nie powiedzie, użyj danych z raportu operacji, aby usunąć go ręcznie w Pimcore.
