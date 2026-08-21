"""PyInstaller runtime hook used only by the web build without OCR."""

import os


os.environ["PICORGFTP_SQL_OCR_ENABLED"] = "0"
