# Deduplikacja EAN w eksporcie Pimcore

## Cel

Eksport CSV i XLSX przeznaczony do importu w Pimcore ma zawierać co najwyżej jeden wiersz dla każdego niepustego EAN-u, bez usuwania pełnej historii operacji z SQLite.

## Zasada wyboru

Rekordy są już odczytywane od najnowszego do najstarszego według `created_at` i `rowid`.

- Dla każdego niepustego EAN-u eksport wybiera najnowszy rekord o statusie `completed`.
- Jeżeli dla EAN-u nie istnieje rekord `completed`, eksport wybiera najnowszy rekord dowolnego statusu.
- Rekordy bez EAN-u pozostają w eksporcie osobno, aby nie scalać niepowiązanych operacji.
- Status `duplicate` nie jest traktowany jako sukces: wskazuje, że utworzenie produktu nie utworzyło nowego obiektu.

## Zakres techniczny

Dodana zostanie czysta funkcja pomocnicza w `web_data.py`, wykonująca wybór rekordów przed mapowaniem ich na układ `export_columns`. `export_pimcore_submissions()` wykorzysta jej wynik dla CSV i XLSX (oraz odpowiedzi JSON tego samego endpointu), a tabela `pimcore_submissions` i endpoint historii nie będą modyfikowane.

## Zachowanie brzegowe

- Kolejność wybranych wierszy pozostaje zgodna z obecną kolejnością historii: od najnowszego do najstarszego.
- Nowsza nieudana próba nie zastępuje starszego wpisu `completed`.
- Jeśli wszystkie próby EAN-u są nieudane, wybrana zostaje najnowsza z nich.
- Limit bazy pozostaje aktualnym limitem endpointu; deduplikacja działa na rekordach pobranych przez ten limit.

## Testy

Testy jednostkowe pokryją: wybór najnowszego sukcesu mimo nowszej porażki, fallback do najnowszego wpisu bez sukcesu, zachowanie rekordów bez EAN-u oraz zachowanie kolejności. Dotychczasowe testy CSV/XLSX potwierdzą, że mapowanie kolumn nie ulega zmianie.
