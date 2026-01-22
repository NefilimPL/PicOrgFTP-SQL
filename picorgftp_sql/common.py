"""Shared constants, imports and helper utilities for PicOrgFTP-SQL."""

################################ Aktualne ustawienia startowe aplikacji ################################
# --- Konfigurowalne ustawienia ---
# Katalog roboczy aplikacji jest odczytywany z pliku `local_settings.json`.
# Poniższa wartość służy jedynie do wstępnego uzupełnienia pliku przy pierwszym
# uruchomieniu (wpis w `local_settings.json` zawsze ma pierwszeństwo).
BASE_DIR_OVERRIDE = r""
# Nazwa lokalnego pliku konfiguracyjnego z ustawieniami katalogu bazowego.
BASE_DIR_SETTINGS_FILE = "local_settings.json"
# Klucz przechowujący preferowany język interfejsu użytkownika.
LANGUAGE_PREF_KEY = "language"
# Wartość domyślna dla ustawień językowych (automatyczny wybór).
LANGUAGE_PREF_DEFAULT = "auto"
# Domyślna struktura wspomnianego pliku.
BASE_DIR_SETTINGS_TEMPLATE = {
    "base_dir_override": BASE_DIR_OVERRIDE,
    LANGUAGE_PREF_KEY: LANGUAGE_PREF_DEFAULT,
}

# Klucz używany do prostego szyfrowania danych konfiguracyjnych.
APP_SECRET = "secret_v1"

# Domyślny port serwera FTP.
PORT = 21

# Zapytanie SQL aktualizujące ścieżkę do obrazu.
SQL_UPDATE_TEMPLATE = (
    "UPDATE object_query_1 SET {col} = 'https://xml.wipmebgroup.pl/img/{filename}' "
    "WHERE EAN = '{ean}' OR Towar_powiazany_z_SKU = '{ean}'"
)

# Domyślne dane konfiguracyjne wykorzystywane przy pierwszym uruchomieniu.
DEFAULT_CONFIG = {
    "ftp": {
        "host": r"",
        "port": PORT,
        "user": r"",
        "pass": r"",
        "path": r"/PHOTOS/",
    },
    "sql": {
        "server": r"",
        "database": r"",
        "user": r"",
        "pass": r"",
    },
    "mysql": {
        "server": r"",
        "database": r"",
        "user": r"",
        "pass": r"",
    },
    "db_type": r"mysql",
    "sql_query": SQL_UPDATE_TEMPLATE,
    "enable_ftp_update": True,
    "enable_sql_update": True,
}
# --- Koniec konfiguracji ---

# Komunikaty dla użytkownika
PROCESSING_MSG = "Trwa przetwarzanie. Poczekaj na zakończenie bieżącej operacji."
OPERATION_TITLE = "Operacja w toku"

# Podstawowe ustawienia
A_ = "1.0"
Az = "normal"
Ay = False
Ax = range
Al = True
Ak = "disabled"
Aj = getattr
AQ = None

# Komunikaty o błędach
NETWORK_ERROR_MSG = "Błąd sieciowy lub brak internetu"
PATH_NOT_FOUND_MSG = "Nie znaleziono ścieżki na serwerze"
NO_SUCH_FILE_MSG = "No such file"
LOGIN_DATA_ERROR_MSG = "Błędne dane logowania"
LOGIN_INCORRECT_MSG = "Login incorrect"
NO_DATA_MSG = "Brak danych"
MISSING_FIELDS_MSG = "Uzupełnij wszystkie wymagane pola przed dodaniem pliku."
INCOMPLETE_DATA_MSG = "Niekompletne dane"

BASE_DIR_PROMPT_TITLE = "Wybierz katalog roboczy"
BASE_DIR_PROMPT_REQUIRED_MSG = (
    "Nie wskazano katalogu roboczego. Aplikacja zostanie zamknięta."
)
BASE_DIR_INVALID_SELECTION_MSG = (
    "Nie udało się uzyskać dostępu do wskazanego katalogu. Wybierz inną lokalizację."
)
BASE_DIR_PROMPT_REASON_MSG = (
    "W pliku \"local_settings.json\" nie zapisano katalogu bazowego lub wskazana "
    "ścieżka jest niedostępna. Wskaż folder, w którym mają być zapisywane i "
    "odczytywane dane."
)
BASE_DIR_OVERRIDE_INVALID_MSG = (
    "Nie można uzyskać dostępu do katalogu wskazanego w pliku \"local_settings.json\":\n"
    "{path}\n\n"
    "{reason}"
)
CONFIG_DIR_PROMPT_TITLE = "Wskaż folder z plikiem konfiguracyjnym"
EXCEL_LOCKED_TITLE = "Plik zablokowany"
EXCEL_LOCK_OTHER_PROCESS = "przez inny proces"
EXCEL_LOCKED_BY_USER = "przez użytkownika '{user}'"

# Oznaczenia interfejsu
CANCEL_LABEL = "Anuluj"
SETTINGS_LABEL = "Ustawienia"
EDIT_LISTS_LABEL = "Edytuj listy"
LIST_TAB_NAMES_LABEL = "Nazwy"
LIST_TAB_TYPES_LABEL = "Typy"
LIST_TAB_MODELS_LABEL = "Modele"
LIST_TAB_COLORS_LABEL = "Kolory"
LIST_TAB_EXTRAS_LABEL = "Dodatki"
LIST_ADD_BUTTON_LABEL = "Dodaj"
LIST_REMOVE_BUTTON_LABEL = "Usuń"
LIST_ADD_DIALOG_TITLE = "Dodaj"
LIST_REMOVE_DIALOG_TITLE = "Usuń"
LIST_ADD_PROMPT_MSG = "Nowa wartość do listy {list}:"
LIST_REMOVE_PROMPT_MSG = "Czy usunąć '{value}' z listy {list}?"
LIGHT_GREEN = "lightgreen"
OPEN_FURNITURE = "open_furniture"
NON_PIC = "non_pic"
ELEMENT_PIC = "element_pic"
DEFAULT_SLOT_DEFS = [
    {"prefix": "01", "label": "Assembly_instruction"},
    {"prefix": "02", "label": "Assembly_instruction1"},
    {"prefix": "03", "label": "DETAIL_pic"},
    {"prefix": "04", "label": "DETAIL_pic1"},
    {"prefix": "05", "label": "element_pic1"},
    {"prefix": "06", "label": ELEMENT_PIC},
    {"prefix": "07", "label": "LED_Assembly_instruction"},
    {"prefix": "08", "label": "MOOD_pic"},
    {"prefix": "09", "label": "MOOD_pic1"},
    {"prefix": "10", "label": "MOOD_pic2"},
    {"prefix": "11", "label": "MOOD_pic3"},
    {"prefix": "12", "label": "MOOD_pic4"},
    {"prefix": "13", "label": "MOOD_pic5"},
    {"prefix": "14", "label": NON_PIC},
    {"prefix": "15", "label": OPEN_FURNITURE},
    {"prefix": "16", "label": "open_furniture1"},
    {"prefix": "17", "label": "open_furniture2"},
    {"prefix": "18", "label": "NO_EAN"},
    {"prefix": "19", "label": "Technical_drawing"},
    {"prefix": "20", "label": "Technical_drawing1"},
    {"prefix": "21", "label": "Technical_drawing2"},
    {"prefix": "22", "label": "WB_pic"},
    {"prefix": "23", "label": "WB_pic1"},
    {"prefix": "24", "label": "WB_pic2"},
    {"prefix": "25", "label": "WB_pic3"},
    {"prefix": "26", "label": "WB_pic4"},
]

# Klasy wyjątków
timeout_error = TimeoutError
connection_refused_error = ConnectionRefusedError
TIMEOUT_ERROR = timeout_error
CONNECTION_REFUSED_ERROR = connection_refused_error
As = "550"
Am = "left"
An = "vertical"
At = "PNG"
Ao = "Plik zablokowany"
Ap = "przez inny proces"
Aq = isinstance
Au = OSError
AR = "blue"
AS = "frame"
Aa = "prefix"
Ab = "red"
AT = "white"
NO_FILE_FALLBACK = "Brak pliku"
AV = "right"
Ac = "Błąd zapisu"
AW = "KOLOR3"
AX = "KOLOR2"
AY = "KOLOR1"
AZ = "MODEL"
Ad = "TYP"
Ae = "NAZWA"
AI = ", "
AJ = "Brak na liście"
AK = "Błąd"
A6 = "%Y-%m-%d %H:%M:%S"
A7 = "x_lbl"
A8 = "#aaa"
A4 = "green"
A2 = "<<ComboboxSelected>>"
y = "img_lbl"
z = "both"
A0 = enumerate
x = open
ft = "enable_ftp_update"
u = "enable_sql_update"
v = "host"
w = "sql_query"
SLOT_DEFS_KEY = "slot_definitions"
SQL_COLUMN_MAP_KEY = "sql_column_map"
SQL_AVAILABLE_COLUMNS_KEY = "sql_available_columns"
p = "db_type"
q = "BRAK-EAN"
r = "port"
s = "MODELE"
t = "TYPY"
m = "path"
k = "utf-8"
n = "NAZWY"
j = "TCombobox"
f = "filepath"
B0 = "mark"
g = "-"
a = "_"
h = Ay
b = "database"
c = "server"
d = "DODATKI"
Z = "Existing.TCombobox"
Y = "KOLORY"
W = "ENTRIES"
R = "e"
T = "w"
S = "values"
V = Ak
Q = len
P = "sql"
X = Az
M = "pass"
N = "user"
L = "NO-LED"
K = "mysql"
J = Al
I = AQ
H = "ftp"
E = Exception
G = str
B = ""

DEFAULT_CONFIG.setdefault(SLOT_DEFS_KEY, DEFAULT_SLOT_DEFS)
DEFAULT_CONFIG.setdefault(
    SQL_COLUMN_MAP_KEY,
    {slot["prefix"]: slot["label"] for slot in DEFAULT_SLOT_DEFS},
)
DEFAULT_CONFIG.setdefault(SQL_AVAILABLE_COLUMNS_KEY, [])

import sys
import os as A
import subprocess as BH
import shutil as Af
import getpass
import platform as BR
import locale as BO
from datetime import datetime as A9
import time as Ag
import tempfile
import uuid
from tkinter import scrolledtext as BS
import threading
import urllib.request as BN
import urllib.parse as BP

AO = getpass.getuser()
AF = BR.node()
OLD_HOST_KEY = (AF or B) + "secret_OLD"


def ensure_package(pkg_name, import_name=I):
    """Ensure that a dependency is installed."""
    try:
        __import__(import_name or pkg_name)
    except ImportError:
        BH.check_call([sys.executable, "-m", "pip", "install", pkg_name])


ensure_package("tkinterdnd2")
ensure_package("Pillow", "PIL")
ensure_package("openpyxl")
ensure_package("pyodbc")
ensure_package("mysql-connector-python", "mysql.connector")

import tkinter as F
from tkinter import ttk as C, filedialog as BT, messagebox as O, simpledialog as BI
from tkinterdnd2 import TkinterDnD as BU, DND_ALL, DND_FILES as BJ, DND_TEXT
from PIL import Image as AA, ImageTk
from openpyxl import Workbook as BV, load_workbook as Ah
import ftplib as AB
import socket as BK
import pyodbc
import mysql.connector
import ctypes
import json as Ar
import base64 as BL

Ai = OLD_HOST_KEY
