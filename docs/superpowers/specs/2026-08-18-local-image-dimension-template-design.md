# Lokalne rozpoznawanie wymiarów obrazów w szablonach — projekt

## Cel

Umożliwić administratorowi skonfigurowanie w szablonie Pimcore źródła wartości
odczytywanej z jednego wybranego slotu obrazu. Przykład: pole docelowe korzysta
ze źródła „szerokość ze slotu 15” i podczas podglądu lub przeliczenia otrzymuje
wartość wskazaną na rysunku wymiarowym w slocie 15. Rozwiązanie działa lokalnie,
bez płatnego API i bez wysyłania obrazów poza komputer/serwer aplikacji.

## Zakres pierwszej wersji

- Lokalny silnik OCR PaddleOCR, z gotowymi modelami i wynikiem zawierającym
  tekst, położenie oraz pewność rozpoznania.
- Analiza geometrii rysunku oparta na OpenCV: wykrycie linii wymiarowych i
  strzałek oraz powiązanie wartości liczbowej z najbliższą linią.
- Rozpoznawane rodzaje wymiaru: `width` (szerokość), `depth` (głębokość) i
  `height` (wysokość). Kolejność pierwszeństwa: etykieta tekstowa (`W`, `D`,
  `H`, polskie nazwy) → orientacja linii (pozioma, ukośna, pionowa) → brak
  wyniku zamiast zgadywania.
- Konfiguracja źródła w każdym mapowaniu/szablonie Pimcore: numer slotu,
  rodzaj wymiaru i minimalna pewność tekstu. Domyślny próg to `80%`.
- Podgląd pokazuje wykrytą, znormalizowaną wartość bez jednostki (np. `130,5`
  jako `130.5`) albo zrozumiały status, dlaczego pole pozostało puste.
- Wynik jest pamiętany w pamięci tylko dla bieżącego obrazu/formularza, aby
  kilka pól korzystających z tego samego slotu nie wykonywało OCR ponownie.

## Poza zakresem pierwszej wersji

- Trening własnego modelu na ręcznie opisanych rysunkach.
- Zewnętrzne i płatne API Vision/OCR.
- Automatyczne nadpisywanie danych w Pimcore bez wywołania istniejącego
  przeliczenia/zapisu formularza.
- Gwarancja odczytu z każdego rodzaju grafiki. Wynik o niedostatecznej
  pewności jest celowo odrzucany.

## Konfiguracja szablonu

Istniejące mapowania zachowują działanie bez zmian. Nowa opcja źródła będzie
zapisywana przy mapowaniu jako znormalizowany obiekt:

```json
{
  "image_dimension": {
    "slot": 15,
    "dimension": "width",
    "minimum_text_confidence": 0.8
  }
}
```

Walidacja akceptuje wyłącznie skonfigurowane numery slotów, typy `width`,
`depth`, `height` oraz próg od `0` do `1`. Brak progu podczas odczytu starej
konfiguracji oznacza `0.8`. Interfejs pokazuje ten próg jako procent 0–100,
domyślnie 80.

W kreatorze szablonu administrator wybiera „Wymiar z obrazu”, następnie slot i
rodzaj wymiaru, a opcjonalnie zmienia próg. Kreator dodaje do tekstu szablonu
dedykowane źródło, np. `{IMAGE_DIMENSION:15:WIDTH|keep}`; jego ustawienia są
zapisywane w obiekcie mapowania, nie w nazwie pola docelowego ani globalnej
liście slotów. Ta składnia umożliwia także łączenie wartości z istniejącymi
funkcjami szablonów.

## Przepływ danych

1. Użytkownik załącza lub wybiera zdjęcie w slocie.
2. Przeliczenie podglądu zbiera źródła `IMAGE_DIMENSION` użyte przez aktywne
   mapowania i przekazuje rzeczywiste pliki slotów do lokalnego serwisu
   rozpoznawania.
3. Serwis normalizuje obraz, uruchamia PaddleOCR oraz pobiera ramki tekstu i
   pewności. Następnie wykrywa linie/strzałki i tworzy kandydatów wymiarów.
4. Dla każdego żądanego wymiaru serwis zwraca jedną wartość, pewność OCR i
   diagnostykę. Pewność kandydatury musi osiągać próg z konfiguracji.
5. Dostawca źródeł rozszerza katalog szablonów o wartości rozpoznane dla
   konkretnego slotu. Obecny renderer szablonów używa ich tak samo jak danych
   produktu i Pimcore.
6. Wyniki trafiają do podglądu, a podczas zwykłego zapisu do istniejącego
   mechanizmu zapisu mapowań Pimcore.

## Obsługa błędów i bezpieczeństwo

- Nie ma pliku w wybranym slocie: wartość pusta, status „Brak obrazu w slocie
  15”.
- OCR nie wykrył tekstu liczbowego lub nie znalazł wiarygodnego połączenia ze
  strzałką: wartość pusta i konkretny status diagnostyczny.
- Pewność wyniku mniejsza od progu: wartość pusta; status zawiera wykrytą
  pewność i wymagany próg, np. „74% < 80%”.
- Błędna konfiguracja szablonu: walidacja blokuje zapis i wskazuje pole.
- Brak zainstalowanego lokalnego OCR/modelu: aplikacja nie przerywa innych
  mapowań; przy tym źródle pokazuje instrukcję instalacji administratorowi.
- Obrazy są przetwarzane wyłącznie lokalnie. Serwis przyjmuje tylko pliki już
  bezpiecznie wybrane przez istniejący mechanizm slotów.

## Wydajność i wdrożenie

PaddleOCR będzie opcjonalną zależnością z lokalnymi wagami modeli. Pierwsze
uruchomienie może wymagać ich pobrania/instalacji przez administratora;
produkcja może wskazać uprzednio pobrane lokalne modele. Przetwarzanie odbywa
się poza główną pętlą webową. Cache jest kluczowany co najmniej tokenem/hashem
obrazu i wersją konfiguracji, a unieważniany po zmianie pliku slotu.

Niska jakość obrazu lub nietypowy sposób oznaczania wymiarów nie może tworzyć
fałszywych danych. Próg 80% jest ochroną domyślną, a administrator może go
podnieść lub obniżyć dla konkretnej formuły.

## Rozszerzenie po pierwszej wersji

Granica modułu rozpoznawania będzie oparta na małym interfejsie dostawcy.
Później można dodać lokalny model Vision uruchamiany przez Ollama jako drugi
dostawca dla rysunków odrzuconych przez OCR/reguły, bez zmiany konfiguracji
szablonów. Model Vision pozostaje opcjonalny; jego brak nie blokuje działania
wersji OCR.

## Testy akceptacyjne

1. Konfiguracja źródła `slot=15`, `dimension=width` i próg 80% zapisuje się i
   odtwarza w kreatorze.
2. Wynik `130,5` o pewności 92% zwraca `130.5` do podglądu i szablonu.
3. Wynik o pewności 74% przy progu 80% nie wypełnia pola oraz wyświetla status
   z oboma progami.
4. Wysokość, szerokość i głębokość pobrane z tego samego obrazu wykonują OCR
   tylko raz w ramach jednego przeliczenia.
5. Pusty slot, brak liczby, niezgodna konfiguracja i niedostępny silnik OCR są
   izolowane do tego źródła; pozostałe mapowania nadal się renderują.
6. Wszystkie istniejące szablony bez `image_dimension` dają identyczne wyniki
   jak przed zmianą.
