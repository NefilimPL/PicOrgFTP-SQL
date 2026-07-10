# Security Policy

## Zakres

Projekt obsługuje dane konfiguracyjne dla FTP, SQL, MySQL i Pimcore. Traktuj `config.json`, `local_settings.json`, logi, zrzuty ekranu i eksporty konfiguracji jako potencjalnie wrażliwe, jeżeli pochodzą z prawdziwego środowiska.

Panel webowy jest przeznaczony do zaufanej sieci LAN albo VPN. Nie wystawiaj go bezpośrednio do publicznego internetu bez dodatkowej warstwy zabezpieczeń i przeglądu konfiguracji.

## Zgłaszanie podatności

Nie publikuj podatności, tokenów, haseł, kluczy API ani danych klientów w publicznym issue.

Jeżeli w repozytorium jest dostępna opcja GitHub **Report a vulnerability**, użyj jej. W przeciwnym razie skontaktuj się z właścicielem repozytorium prywatnym kanałem, zanim opiszesz problem publicznie.

W zgłoszeniu podaj:

- wersję albo commit,
- obszar problemu: desktop, web, FTP, SQL, Pimcore, build EXE albo workflow,
- minimalne kroki odtworzenia,
- wpływ problemu,
- czy w zgłoszeniu znajdują się dane wrażliwe.

## Sekrety

- Klucze API Pimcore są przechowywane w postaci zaszyfrowanej.
- Standardowe endpointy ustawień i logi operacji Pimcore nie powinny zwracać klucza API.
- `APP_SECRET` powinien być unikalny dla środowiska.
- Token `ACTIONS_RUNNER_READ_TOKEN` powinien mieć minimalny zakres: tylko to repozytorium i **Administration: Read-only**.

Jeżeli sekret trafił do publicznego issue, logu albo historii repozytorium, potraktuj go jako ujawniony i natychmiast go unieważnij.
