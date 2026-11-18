"""Constants of Stampa remota."""
DOMAIN = "stampa_remota"
VERSION = "1.0.0"

CONF_URI = "printer_uri"
CONF_PAPER = "paper"
CONF_MONO = "monochrome_default"
CONF_ADMIN_ONLY = "admin_only"

PAPERS = ["A4", "A5", "Letter", "Legal"]

PANEL_URL = "stampa"
STATIC_URL = "/stampa_remota_static"
EVENT = "stampa_remota_evento"
MAX_UPLOAD = 60 * 1024 * 1024
