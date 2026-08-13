# Widoczny przycisk otwierania slotu

## Cel

Przycisk `Otwórz` ma być stale widoczny przy każdym slocie, niezależnie od
tego, czy aktywne źródło to LOCAL, FTP czy SQL. Nie może zniknąć po
przełączeniu źródła ani wymagać ponownego wyszukania EAN.

## Projekt interfejsu

- Kontrolka `Otwórz` jest tworzona dla każdej karty slotu i pozostaje w DOM.
- Jest umieszczona pod obszarem podglądu, nie jako nakładka na obraz.
- Przycisk ma pełny, nieucięty tekst `Otwórz`; szerokość i reguły układu nie
  mogą zastępować tekstu wielokropkiem.
- W stanie niegotowym przycisk jest widoczny, ale wyłączony. Jego podpowiedź
  wyjaśnia, czy trwa pobieranie źródła, czy dane źródło nie jest otwieralne.
- Gdy dane aktywnego źródła są gotowe, ten sam przycisk jest odblokowywany bez
  odtwarzania całej karty i bez akcji użytkownika.

## Gotowość źródeł

- LOCAL jest gotowy, gdy istnieje token lokalnego pliku.
- FTP jest gotowy, gdy istnieje adres lub token cache; przed pobraniem pozostaje
  widoczny, wyłączony i automatycznie odblokowuje się po zakończeniu pobierania
  podglądu FTP.
- SQL jest gotowy wyłącznie dla poprawnego adresu HTTP lub HTTPS. Inna wartość
  SQL pozostawia przycisk wyłączony z wyjaśnieniem.

## Przepływ danych

Pierwszy render tworzy przycisk niezależnie od bieżącej gotowości źródła.
`updateSlotPreview` ponownie wylicza stan, etykietę i podpowiedź po zmianie
źródła, odebraniu podglądu FTP oraz zmianie danych slotu. Nie opiera się na
warunkowym dodawaniu/usuwaniu elementu.

## Testy regresji

- Przycisk istnieje po pierwszym renderze karty, także gdy FTP nie ma jeszcze
  cache URL.
- Przełączenie między LOCAL, FTP i SQL zmienia jego stan bez ponownego
  wyszukania EAN.
- Ukończenie pobierania FTP odblokowuje istniejący przycisk.
- Reguły CSS umieszczają kontrolkę poza podglądem i zachowują pełną etykietę.
