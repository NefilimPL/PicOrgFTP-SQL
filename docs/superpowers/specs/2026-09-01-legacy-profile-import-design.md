# Import pełnego profilu sprzed rebrandingu

## Cel

Jednorazowo przenieść kompletną konfigurację PicOrgFTP-SQL do nowego pliku
SQLite PicSyncra bez utraty kont, haseł, ustawień, list, historii, indeksu ani
sekretów. Import nie może wymagać drugiego importu ani restartu.

## Przyczyna przebudowy

Dotychczasowy importer niezależnie wyszukuje bazę SQLite oraz pliki JSON/XLSX
w kilku katalogach. Może przez to skopiować pustą bazę bez `web_users.json`.
Pierwsze odczytanie tworzy wtedy domyślnego administratora i maskuje utratę
starego konta.

## Profil źródłowy

`LegacyProfile` oznacza dokładnie jeden wybrany katalog. Rozpoznaje wyłącznie
jego bezpośrednie pliki: `picorgftp_sql.sqlite` z sidecarami, `config.json`,
`lists.xlsx`, `web_users.json`, `web_history.json`, `file_index.json` oraz
`local_settings.json`. Nigdy nie miesza katalogu EXE, katalogu zdjęć i
baza aktywnej aplikacji. Automatyczne wykrycie jest dozwolone tylko dla jednego
kandydata; wiele kandydatów wymaga wskazania źródłowego katalogu.

## Transakcja

1. Skaner tworzy manifest źródeł i publiczne liczniki, bez sekretów i hashy.
2. Import tworzy nową roboczą SQLite, kopiuje starą SQLite przez SQLite backup
   i nakłada pliki JSON/XLSX z tego samego profilu. JSON ma pierwszeństwo dla
   konta o tym samym loginie.
3. Walidacja porównuje konfigurację, listy, historię, indeks oraz każde konto:
   login, rolę, aktywność i hash hasła. Brak konta jest błędem transakcji.
4. Przed publikacją tworzone jest pełne archiwum w
   `BACKUP/legacy-import/<czas>-<id>/` wraz z raportem importu. Dopiero potem
   nowa SQLite jest aktywowana i ustawienia wskazują ją atomowo.
5. Dokładne pliki profilu są przenoszone do archiwum. Gdy Windows blokuje plik,
   retry pozostaje wyłącznie w `BACKUP`; po zwolnieniu sprząta źródło automatycznie.

Przy błędzie przed publikacją nie zmienia się aktywna baza, ustawienia ani
źródło. Z `local_settings.json` przenoszone są tylko `language`, `app_secret`
i `sqlite_backup`; lokalizacja katalogu i baza pozostają nowymi wartościami.

## Interfejs

```python
discover_legacy_profiles(candidate_roots: Iterable[Path]) -> tuple[LegacyProfile, ...]
adopt_legacy_profile(
    *, source_root: Path, database_path: Path, backup_root: Path,
    finalize: Callable[[Path, dict[str, object]], Callable[[], None] | None] | None = None,
    replace_existing_target: bool = False,
) -> MigrationResult
```

`adopt_legacy_data` pozostaje jedynie adapterem zgodności i nie implementuje
własnego wykrywania ani importu. Automatyczne `migrate_legacy_data` jest
wycofane i niczego nie kopiuje; import uruchamia wyłącznie ręczna akcja w
ustawieniach.

Finalizator aktywacji zwraca opcjonalną funkcję cofającą. Gdy późniejszy etap
transakcji nie powiedzie się, importer wywołuje ją zanim usunie opublikowany
plik roboczy.

## Kryteria akceptacji

- Pusta stara SQLite oraz administrator w JSON zachowują konto, rolę i stare hasło.
- Żaden plik z drugiego katalogu nie może trafić do importu.
- Błąd walidacji nie przełącza bazy i nie przenosi źródeł.
- Udany import archiwizuje wszystkie pliki profilu i czyści katalog źródłowy.
- Nowe konto działa po przełączeniu bez restartu i bez drugiego importu.
