# PicOrgFTP-SQL

Organizator zdjęć produktowych dla pracy lokalnej, FTP, SQL oraz panelu webowego w zaufanej sieci LAN.

[![Build Windows EXE](https://github.com/NefilimPL/PicOrgFTP-SQL/actions/workflows/build-exe.yml/badge.svg?branch=main)](https://github.com/NefilimPL/PicOrgFTP-SQL/actions/workflows/build-exe.yml)
[![CI](https://github.com/NefilimPL/PicOrgFTP-SQL/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/NefilimPL/PicOrgFTP-SQL/actions/workflows/ci.yml)

<img width="1920" height="1040" alt="PicOrgFTP-SQL desktop" src="https://github.com/user-attachments/assets/8d2f9c31-1103-4368-bea2-7b6899d92761" />

## Co robi aplikacja

- Układa zdjęcia produktów w strukturze katalogów opartej o nazwę, typ, model, kolory, dodatek i EAN.
- Optymalizuje, skaluje, kompresuje i opcjonalnie konwertuje zdjęcia.
- Obsługuje sloty zdjęć, miniatury, statusy LOCAL/FTP/SQL oraz wczytywanie istniejących zdjęć.
- Może wysyłać pliki na FTP i aktualizować ścieżki zdjęć w MS SQL albo MySQL.
- Ma aplikację desktopową oraz osobny panel webowy do pracy w lokalnej sieci.
- Integruje się z Pimcore 6.6 REST do wyszukiwania i tworzenia obiektów produktów.

## Szybki start

Aplikacja desktopowa:

```powershell
python PicOrgFTP-SQL.pyw
```

Panel webowy w LAN:

```powershell
python -m pip install -r requirements-web.txt
python -m uvicorn picorgftp_sql.web.app:app --host 0.0.0.0 --port 8000
```

Na Windows możesz też użyć `START_WEB.bat` i `STOP_WEB.bat`.

## Dokumentacja

| Temat | Plik |
| --- | --- |
| Praca lokalna i aplikacja desktopowa | [docs/local-desktop.md](docs/local-desktop.md) |
| Panel webowy w LAN | [docs/web-panel.md](docs/web-panel.md) |
| Konfiguracja Pimcore REST | [docs/pimcore.md](docs/pimcore.md) |
| Budowanie EXE i GitHub Actions | [docs/building-exe.md](docs/building-exe.md) |
| Plan rozwoju | [PLAN_ROZWOJU.md](PLAN_ROZWOJU.md) |
| Wkład w projekt | [CONTRIBUTING.md](CONTRIBUTING.md) |
| Bezpieczeństwo | [SECURITY.md](SECURITY.md) |
| Zasady zachowania | [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md) |

## English Summary

PicOrgFTP-SQL is a Python product photo organiser with desktop and LAN web workflows. It can process images, organise them into product folders, upload to FTP, update SQL image paths and integrate with Pimcore 6.6 REST.

## Licencja

Projekt jest udostępniany na licencji [Apache License 2.0](LICENSE).
