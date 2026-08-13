# Sesje oparte na identyfikatorze użytkownika

## Cel

Usunąć nazwę użytkownika z payloadu cookie sesyjnego, zachowując podpis HMAC, wersjonowanie sesji, czas wydania, maksymalny czas życia i losowy nonce.

## Zakres

- Każdy rekord użytkownika ma trwałe pole `id`, będące UUID4 wygenerowanym po stronie serwera.
- Pierwszy odczyt istniejących rekordów z brakującym lub nieprawidłowym `id` generuje UUID4 i od razu utrwala znormalizowane rekordy, aby identyfikator nie zmienił się między żądaniami.
- Nowe konta dostają `id` podczas tworzenia.
- Zostanie dodane wyszukiwanie użytkownika po `id`, zwracające ten sam publiczny model użytkownika co wyszukiwanie po nazwie.
- Format nowych tokenów to `session-v2|<user-id>|<session-version>|<issued-at>|<nonce>` wraz z istniejącym podpisem i kodowaniem Base64 URL-safe.
- Odczyt tokenu przyjmuje tylko `session-v2`, wyszukuje użytkownika po `id`, sprawdza stan konta i wersję sesji, po czym zwraca kanoniczną nazwę użytkownika.

## Kompatybilność i bezpieczeństwo

- Poprzednie formaty tokenów sesyjnych są odrzucane. Wdrożenie wymusza ponowne logowanie.
- Token nadal zawiera wyłącznie dane potrzebne do walidacji, podpisane kluczem serwera. Nie zawiera nazwy użytkownika ani wartości otrzymanej bezpośrednio z żądania.
- Zmiana nie dotyczy tokenu rozszerzenia przeglądarkowego, który nie jest cookie sesyjnym wskazanym w alercie.

## Testy

- Pierwszy odczyt istniejącego użytkownika tworzy UUID4 i zapisuje go; kolejny odczyt zwraca ten sam UUID4.
- Nowy użytkownik ma UUID4.
- Token sesji `session-v2` nie zawiera loginu, jest odczytywany jako właściwa nazwa użytkownika i pozostaje ważny dla aktywnego konta.
- Token jest odrzucany po zmianie `session_version` oraz gdy zawiera poprzedni format.
- Istniejące testy logowania, CSRF i unieważniania sesji nadal przechodzą.
