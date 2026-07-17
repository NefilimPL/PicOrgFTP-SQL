# Panel webowy w LAN

Repozytorium zawiera lokalny panel webowy dla użytkowników w tej samej sieci LAN. Panel nie zastępuje aplikacji desktopowej; zapisuje pliki do tej samej struktury `_ZDJECIA PRZEROBIONE_` i korzysta z tych samych ustawień roboczych.

## Zakres

Panel pozwala użytkownikom w przeglądarce:

- logować się i wgrywać zdjęcia do skonfigurowanych slotów,
- wyszukiwać i wczytywać wpisy po EAN,
- dopasowywać produkt po nazwie, typie i modelu,
- oglądać miniatury slotów i podglądy lokalne albo cache'owane FTP,
- przeciągać pliki między slotami,
- czyścić pojedyncze sloty,
- widzieć status LOCAL/FTP/SQL,
- wysyłać zdjęcia na FTP po przetworzeniu,
- zapisywać nowe i istniejące wpisy Excel,
- korzystać z historii webowej grupowanej po EAN,
- edytować listy, ustawienia, sloty i mapowanie SQL,
- wykonywać testy folderów lokalnych, FTP i SQL,
- zarządzać użytkownikami oraz hasłami.

Logowanie jest domyślnie włączone. Pierwsze konto to `admin` / `admin`. Hasło należy zmienić w **Ustawienia -> Użytkownicy** przed używaniem panelu poza zaufanym testem.

## Instalacja zależności

```powershell
python -m pip install -r requirements-web.txt
```

## Uruchomienie

Na Windows można użyć skryptów:

- `START_WEB.bat` - uruchamia panel, doinstalowuje brakujące zależności webowe, otwiera przeglądarkę i pokazuje adres LAN.
- `STOP_WEB.bat` - zatrzymuje panel uruchomiony na skonfigurowanym porcie.

Ręczne uruchomienie backendu:

```powershell
python -m uvicorn picorgftp_sql.web.app:app --host 0.0.0.0 --port 8000
```

Z innego komputera w tej samej sieci otwórz:

```text
http://IP_SERWERA:8000
```

Ustawienia są widoczne tylko dla użytkowników webowych z rolą `admin`.

## Historia i obserwowalność administratora

Widok **Historia** pokazuje przebieg operacji produktu. Przycisk **Zmiany** otwiera bezpieczny podgląd wartości przed i po operacji, zmian plików, czasu wykonania oraz identyfikatora powiązanego zadania.

Administrator ma także widok **Logi** z kartami **Na żywo**, **Krytyczne**, **Błędy**, **Ostrzeżenia** i **Zadania**. Strumień na żywo obejmuje zdarzenia z ostatnich 24 godzin. Powiązane zdarzenia są grupowane w incydenty i zadania, a nieprzeczytane wpisy są sygnalizowane według najwyższego priorytetu: krytyczne, błędy, a następnie ostrzeżenia.

## Stan backendu w nagłówku

Obok nazwy aplikacji widoczny jest tekstowy stan backendu z kropką i medianą czasu odpowiedzi z pięciu ostatnich udanych pomiarów. Szczegóły po najechaniu, ustawieniu fokusu lub kliknięciu pokazują stan backendu, SQLite, procesora zadań oraz ostatni znany stan FTP, SQL, profili SQL i Pimcore. Panel pokazuje wyłącznie znormalizowane stany, bez ścieżek, sekretów i treści wyjątków.

- **Online**: lokalne komponenty odpowiadają prawidłowo, mediana jest poniżej 300 ms i brak stanu ograniczonego.
- **Wolno**: mediana wynosi co najmniej 300 ms albo któryś komponent ma stan ograniczony.
- **Krytyczny**: backend lub SQLite zgłasza problem albo mediana przekracza 1000 ms.
- **Offline**: trzy kolejne próby pobrania stanu zakończyły się błędem.

Pomiar jest wykonywany co pięć sekund. Przeglądarka wstrzymuje go w ukrytej karcie i odświeża stan natychmiast po powrocie.

## Bezpieczeństwo LAN

Panel jest przeznaczony do zaufanej sieci LAN albo VPN. Nie wystawiaj tego panelu bezpośrednio do publicznego internetu bez dodatkowej warstwy zabezpieczeń, aktualizacji haseł, kontroli dostępu i przeglądu konfiguracji serwera.

## Zrzuty ekranu

<img width="1912" height="922" alt="Panel webowy" src="https://github.com/user-attachments/assets/1cdeae0d-db34-488f-9565-ad791805cf83" />

<img width="1912" height="922" alt="Panel webowy" src="https://github.com/user-attachments/assets/6f66ecca-6e23-40c5-a46e-63693d1eea40" />

<img width="1283" height="631" alt="Panel webowy" src="https://github.com/user-attachments/assets/e7a44084-5694-4968-a632-6465818b65f2" />

<img width="1275" height="864" alt="Panel webowy" src="https://github.com/user-attachments/assets/613d7141-305a-436c-a7fd-32f72fbdd50e" />

<img width="1272" height="307" alt="Panel webowy" src="https://github.com/user-attachments/assets/24eabef8-57e5-431a-9945-52e14d0eb63b" />

<img width="1249" height="362" alt="Panel webowy" src="https://github.com/user-attachments/assets/16118148-3323-4868-8038-75825fbfa1ca" />
