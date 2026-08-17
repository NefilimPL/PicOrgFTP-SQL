# Zaznaczanie i przeciąganie układu eksportu Pimcore

## Cel

Przyspieszyć układanie dużej liczby kolumn eksportu przez zaznaczanie wielu pozycji i przeciąganie ich jako jednej grupy, a także przez dodawanie pustej kolumny dokładnie między wybranymi pozycjami.

## Zakres

- Usunąć strzałki przesuwania pojedynczego wiersza z edytora układu eksportu.
- Pozwolić zaznaczać wiele wierszy przez przeciągnięcie prostokąta po wolnym tle listy.
- Pozwolić dodać lub usunąć pojedynczy wiersz z zaznaczenia przez `Ctrl` + kliknięcie jego wolnej części.
- Umożliwić przeciągnięcie dowolnego zaznaczonego wiersza; wszystkie zaznaczone pozycje są przenoszone razem, z zachowaniem ich wzajemnej kolejności.
- Pokazać podczas przeciągania strefę upuszczenia między wierszami oraz na początku i końcu listy.
- Dodać między każdymi sąsiednimi pozycjami strefę z małym przyciskiem `+`, widocznym po najechaniu kursorem. Kliknięcie wstawia w tym miejscu pustą kolumnę.

## Zachowanie

- Zaznaczenie jest stanem tymczasowym modalu i nie jest zapisywane w konfiguracji.
- Zwykłe kliknięcie na kontrolkę wiersza, np. select, input nagłówka lub Usuń, nie uruchamia zaznaczania ani przeciągania.
- Przeciągnięcie grupy na pozycję wewnątrz tej samej grupy nie zmienia układu.
- Po usunięciu wiersza jest on także usuwany z zaznaczenia.
- Wstawiona pusta kolumna dostaje pusty nagłówek i nie jest automatycznie zaznaczana.
- Zapis układu nadal korzysta z istniejącego `export_columns`; format danych i zachowanie eksportu CSV/XLSX nie zmieniają się.

## Interfejs i dostępność

- Zaznaczone wiersze są wyróżnione kolorem i obramowaniem, a strefa docelowa przeciągania jest wyraźnie widoczna.
- Przycisk `+` ma opis dostępny dla czytnika ekranu, określający pozycję wstawienia.
- Istniejące przyciski usunięcia oraz edycja pola i nagłówka pozostają dostępne z klawiatury.

## Testy

- Test integralności UI obejmie elementy stref wstawiania, stan zaznaczenia oraz obsługę przenoszenia wielu pozycji.
- Kontrola składni JavaScriptu pozostaje obowiązkowa.
- Dotychczasowe testy konfiguracji i generowania eksportu zapewnią brak regresji formatu `export_columns` oraz CSV/XLSX.
