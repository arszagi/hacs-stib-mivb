"""Constants for the STIB/MIVB integration."""

DOMAIN = "stib_mivb"
DEFAULT_SCAN_INTERVAL = 30  # seconds

CONF_LANGUAGE = "language"
CONF_API_KEY = "api_key"
CONF_STOP_SEARCH = "stop_search"
CONF_STOP_NAME = "stop_name"
CONF_STOP_GROUPS = "stop_groups"  # list of grouped stop entries
CONF_SCAN_INTERVAL = "scan_interval"

LANGUAGE_FRENCH = "fr"
LANGUAGE_DUTCH = "nl"

# Authenticated endpoint (requires bmc-partner-key header)
API_BASE = "https://api-management-opendata-production.azure-api.net/api/datasets/stibmivb"
API_STOPS_BY_LINE = f"{API_BASE}/static/stopsByLine"
API_STOP_DETAILS = f"{API_BASE}/static/StopDetails"
API_WAITING_TIMES = f"{API_BASE}/rt/WaitingTimes"

API_KEY_HEADER = "bmc-partner-key"

ATTR_NEXT_PASSAGE = "next_passage"
ATTR_LATITUDE = "latitude"
ATTR_LONGITUDE = "longitude"
ATTR_STOP_NAME_FR = "stop_name_fr"
ATTR_STOP_NAME_NL = "stop_name_nl"
ATTR_DIRECTION = "direction"
ATTR_DESTINATION = "destination"
ATTR_LINE_ID = "line_id"
ATTR_POINT_IDS = "point_ids"
ATTR_MESSAGE = "message"
ATTR_IS_BOARDING = "is_boarding"

# Line info: type label per type
STIB_TYPE_LABEL: dict[str, str] = {"metro": "M", "tram": "T", "bus": "B"}

# Source: STIB/MIVB GTFS routes.txt (May 2026)
# URL: https://api-management-opendata-production.azure-api.net/api/gtfs/feed/stibmivb/static/
# route_type: 0=tram  1=metro  3=bus
STIB_LINE_INFO: dict[str, dict] = {
    "1":   {"color": "#B5378C", "text_color": "#FFFFFF", "type": "metro"},
    "2":   {"color": "#ED6C23", "text_color": "#FFFFFF", "type": "metro"},
    "4":   {"color": "#EA4F80", "text_color": "#000000", "type": "tram"},
    "5":   {"color": "#F6A90B", "text_color": "#FFFFFF", "type": "metro"},
    "6":   {"color": "#0066A3", "text_color": "#FFFFFF", "type": "metro"},
    "7":   {"color": "#EFE048", "text_color": "#000000", "type": "tram"},
    "8":   {"color": "#169FDB", "text_color": "#FFFFFF", "type": "tram"},
    "9":   {"color": "#C44F97", "text_color": "#FFFFFF", "type": "tram"},
    "10":  {"color": "#8F4199", "text_color": "#FFFFFF", "type": "tram"},
    "12":  {"color": "#4C8B33", "text_color": "#FFFFFF", "type": "bus"},
    "13":  {"color": "#91BEE7", "text_color": "#000000", "type": "bus"},
    "14":  {"color": "#F29DC3", "text_color": "#000000", "type": "bus"},
    "17":  {"color": "#E43C2E", "text_color": "#FFFFFF", "type": "bus"},
    "18":  {"color": "#91BEE7", "text_color": "#000000", "type": "tram"},
    "19":  {"color": "#E43C2E", "text_color": "#FFFFFF", "type": "tram"},
    "20":  {"color": "#F3C300", "text_color": "#000000", "type": "bus"},
    "21":  {"color": "#FFDC01", "text_color": "#000000", "type": "bus"},
    "25":  {"color": "#A12944", "text_color": "#FFFFFF", "type": "tram"},
    "28":  {"color": "#E43C2E", "text_color": "#FFFFFF", "type": "bus"},
    "29":  {"color": "#ED7807", "text_color": "#FFFFFF", "type": "bus"},
    "34":  {"color": "#F3C300", "text_color": "#000000", "type": "bus"},
    "35":  {"color": "#336195", "text_color": "#FFFFFF", "type": "tram"},
    "36":  {"color": "#91BEE7", "text_color": "#000000", "type": "bus"},
    "37":  {"color": "#306196", "text_color": "#FFFFFF", "type": "bus"},
    "38":  {"color": "#A67CB0", "text_color": "#FFFFFF", "type": "bus"},
    "39":  {"color": "#E43C2E", "text_color": "#FFFFFF", "type": "tram"},
    "41":  {"color": "#91BEE7", "text_color": "#000000", "type": "bus"},
    "42":  {"color": "#4C8B33", "text_color": "#FFFFFF", "type": "bus"},
    "43":  {"color": "#9B6018", "text_color": "#FFFFFF", "type": "bus"},
    "44":  {"color": "#F3C300", "text_color": "#000000", "type": "tram"},
    "45":  {"color": "#A67CB0", "text_color": "#FFFFFF", "type": "bus"},
    "46":  {"color": "#E43C2E", "text_color": "#FFFFFF", "type": "bus"},
    "47":  {"color": "#E43C2E", "text_color": "#FFFFFF", "type": "bus"},
    "48":  {"color": "#ED7807", "text_color": "#FFFFFF", "type": "bus"},
    "49":  {"color": "#306196", "text_color": "#FFFFFF", "type": "bus"},
    "50":  {"color": "#B4BD10", "text_color": "#000000", "type": "bus"},
    "51":  {"color": "#F3C300", "text_color": "#000000", "type": "tram"},
    "53":  {"color": "#4C8B33", "text_color": "#FFFFFF", "type": "bus"},
    "54":  {"color": "#E43C2E", "text_color": "#FFFFFF", "type": "bus"},
    "55":  {"color": "#F3C300", "text_color": "#000000", "type": "tram"},
    "56":  {"color": "#ED7807", "text_color": "#FFFFFF", "type": "bus"},
    "58":  {"color": "#4C8B33", "text_color": "#FFFFFF", "type": "bus"},
    "59":  {"color": "#9B6018", "text_color": "#FFFFFF", "type": "bus"},
    "60":  {"color": "#F29DC3", "text_color": "#000000", "type": "bus"},
    "61":  {"color": "#FFDC01", "text_color": "#000000", "type": "bus"},
    "62":  {"color": "#F29DC3", "text_color": "#000000", "type": "tram"},
    "63":  {"color": "#91BEE7", "text_color": "#000000", "type": "bus"},
    "64":  {"color": "#E43C2E", "text_color": "#FFFFFF", "type": "bus"},
    "65":  {"color": "#F3C300", "text_color": "#000000", "type": "bus"},
    "66":  {"color": "#306196", "text_color": "#FFFFFF", "type": "bus"},
    "69":  {"color": "#ED7807", "text_color": "#FFFFFF", "type": "bus"},
    "71":  {"color": "#4C8B33", "text_color": "#FFFFFF", "type": "bus"},
    "72":  {"color": "#F29DC3", "text_color": "#000000", "type": "bus"},
    "73":  {"color": "#F29DC3", "text_color": "#000000", "type": "bus"},
    "74":  {"color": "#A67CB0", "text_color": "#FFFFFF", "type": "bus"},
    "75":  {"color": "#FFDC01", "text_color": "#000000", "type": "bus"},
    "76":  {"color": "#FFDC01", "text_color": "#000000", "type": "bus"},
    "77":  {"color": "#4C8B33", "text_color": "#FFFFFF", "type": "bus"},
    "78":  {"color": "#A67CB0", "text_color": "#FFFFFF", "type": "bus"},
    "79":  {"color": "#306196", "text_color": "#FFFFFF", "type": "bus"},
    "80":  {"color": "#4C8B33", "text_color": "#FFFFFF", "type": "bus"},
    "81":  {"color": "#4C8B33", "text_color": "#FFFFFF", "type": "tram"},
    "82":  {"color": "#91BEE7", "text_color": "#000000", "type": "tram"},
    "83":  {"color": "#B4BD10", "text_color": "#000000", "type": "bus"},
    "86":  {"color": "#306196", "text_color": "#FFFFFF", "type": "bus"},
    "87":  {"color": "#4C8B33", "text_color": "#FFFFFF", "type": "bus"},
    "88":  {"color": "#A12944", "text_color": "#FFFFFF", "type": "bus"},
    "89":  {"color": "#B4BD10", "text_color": "#000000", "type": "bus"},
    "92":  {"color": "#E43C2E", "text_color": "#FFFFFF", "type": "tram"},
    "93":  {"color": "#ED7807", "text_color": "#FFFFFF", "type": "tram"},
    "95":  {"color": "#306196", "text_color": "#FFFFFF", "type": "bus"},
    "96":  {"color": "#A12944", "text_color": "#FFFFFF", "type": "bus"},
    # Night buses
    "N04": {"color": "#C44F97", "text_color": "#FFFFFF", "type": "bus"},
    "N05": {"color": "#A67CB0", "text_color": "#FFFFFF", "type": "bus"},
    "N06": {"color": "#169FDB", "text_color": "#FFFFFF", "type": "bus"},
    "N08": {"color": "#91BEE7", "text_color": "#000000", "type": "bus"},
    "N09": {"color": "#C44F97", "text_color": "#FFFFFF", "type": "bus"},
    "N10": {"color": "#C1D66B", "text_color": "#000000", "type": "bus"},
    "N11": {"color": "#9B6018", "text_color": "#FFFFFF", "type": "bus"},
    "N12": {"color": "#ED7807", "text_color": "#FFFFFF", "type": "bus"},
    "N13": {"color": "#A12944", "text_color": "#FFFFFF", "type": "bus"},
    "N16": {"color": "#74C095", "text_color": "#FFFFFF", "type": "bus"},
    "N18": {"color": "#23A845", "text_color": "#FFFFFF", "type": "bus"},
    "NAV": {"color": "#F3C300", "text_color": "#000000", "type": "bus"},
}
