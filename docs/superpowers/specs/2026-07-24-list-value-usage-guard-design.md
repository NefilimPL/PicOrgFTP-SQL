# Ochrona usuwania wartości słownikowych i otwieranie produktów

## Cel

Przywrócić blokadę usunięcia używanej wartości z list: nazwy, typu, modelu,
kolorów i dodatków. Po zablokowaniu operator ma zobaczyć produkty korzystające
z wartości oraz móc od razu wczytać wybrany produkt w głównym formularzu
panelu webowego albo aplikacji desktopowej.

## Problem

Obecna warstwa usuwania poprawnie wywołuje sprawdzenie użyć, lecz helper
`find_list_value_usage` odczytuje wyłącznie arkusz Excel. W aktywnym trybie
SQLite listy i wpisy produktów pochodzą z `product_entries`, więc helper zwraca
pustą listę, a wartość może zostać usunięta mimo użycia. Endpoint webowy już
zwraca błąd HTTP 409 z produktami blokującymi usunięcie, ale interfejs pokazuje
je bez przycisku otwierającego produkt. Desktop wyświetla jedynie ostrzeżenie.

## Architektura i przepływ danych

`SqliteStore` otrzyma metodę odczytu użyć wartości z `product_entries`.
Metoda przyjmie klucz arkusza, wartość oraz limit i zwróci ten sam publiczny
kształt rekordu co ścieżka Excel: `product_id`, `ean`, pola produktu,
`fields` i czytelną `label`. Warstwa `SqliteDataStoreAdapter` udostępni tę
metodę, a `excel_utils.find_list_value_usage` wybierze ją, gdy aktywny jest
magazyn SQLite. W trybie legacy pozostanie obecny odczyt arkusza.

Mapowanie list na pola produktu będzie wspólne dla obu magazynów:

- `NAZWY` -> `NAZWA` / `name`;
- `TYPY` -> `TYP` / `type_name`;
- `MODELE` -> `MODEL` / `model`;
- `KOLORY` -> `KOLOR1`, `KOLOR2`, `KOLOR3` / `color1`, `color2`, `color3`;
- `DODATKI` -> `DODATKI` / `extra`.

Porównanie będzie niewrażliwe na wielkość liter i znaki diakrytyczne, tak jak
obecna ścieżka Excel. Dla dodatków podkreślenie i łącznik będą równoważne.
Usunięcie nie wykona się, gdy wynik zawiera co najmniej jeden produkt.

## Interfejs webowy

Po odpowiedzi 409 istniejący modal użyć pokaże każdy produkt jako wiersz z
nazwą, identyfikatorem, EAN i polem/polami powodującymi blokadę. Każdy wiersz
otrzyma przycisk **Wczytaj**. Kliknięcie załaduje przekazany rekord do głównego
formularza, pobierze jego zdjęcia zgodnie z dotychczasowym zachowaniem
`fillForm` i zamknie modal list oraz modal użyć. Lista słownikowa nie zostanie
zmieniona.

## Interfejs desktopowy

Gdy wybrana wartość jest używana, desktop zastąpi samo ostrzeżenie małym oknem
z listą produktów blokujących usunięcie. Lista będzie zawierać identyfikator,
EAN, pola użycia i opis produktu. Przycisk **Wczytaj zaznaczony** załaduje
rekord przez istniejące `_load_entry_record`, zamknie okno i edytor list oraz
przywróci fokus do głównego formularza. Zamknięcie bez wczytania nie zmienia
listy i nadal blokuje usunięcie.

## Błędy i zgodność

Nie zmienia się kontrakt udanego usunięcia ani istniejący kontrakt HTTP 409.
Brak rozpoznanego klucza listy lub pusta wartość nadal oznacza brak użyć.
Zapis i blokada pozostają wykonywane po stronie backendu, więc nie da się
obejść ich samą modyfikacją UI.

## Testy

Testy obejmą:

1. wyszukiwanie użyć w SQLite dla każdej mapowanej listy, w tym wielu pól
   kolorów oraz normalizacji dodatków;
2. blokadę `remove_list_value` w trybie SQLite i brak wywołania fizycznego
   usunięcia;
3. zachowanie ścieżki Excel;
4. odpowiedź HTTP 409 zawierającą rekordy blokujące;
5. statyczny kontrakt webowego przycisku `Wczytaj` i desktopowego okna z
   wczytaniem zaznaczonego rekordu.
