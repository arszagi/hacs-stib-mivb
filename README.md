# STIB/MIVB — Home Assistant Integration

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://github.com/hacs/integration)

Monitor real-time waiting times for the **Brussels public transport network (STIB/MIVB)** directly in Home Assistant — buses, trams and metro.

---

## Features

- **One sensor per line per stop** — shows minutes until the next arrival
- **Grouped stops** — all physical platforms of the same stop name are handled as one
- **Bilingual** — French or Dutch display language
- **Official STIB line colours** — loaded from the GTFS feed at install time
- **Vehicle type detection** — bus / tram / metro per line
- **Service messages** — "Ne pas embarquer", "Ligne déviée", "Temps théorique"
- **Optimised API usage** — only your monitored stops are fetched (~2 KB per refresh instead of ~1 MB)
- **Configurable polling interval** (default 30 s, min 10 s)
- **Add stops at any time** via the integration options
- **Refresh line data** manually to get updated GTFS colours and types

---

## Prerequisites — API Key

1. Go to **[api-management-opendata-production.developer.azure-api.net](https://api-management-opendata-production.developer.azure-api.net/)**
2. Log in or create a free account
3. Go to your **Profile** page
4. Subscribe to the **"Standard"** product
5. Copy your **primary or secondary key** — you will need it during setup

---

## Installation via HACS

1. Open **HACS → Integrations → ⋮ → Custom repositories**
2. Paste `https://github.com/arszagi/hacs-stib-mivb` and select category **Integration**
3. Click **Download**
4. Restart Home Assistant

---

## Setup

1. Go to **Settings → Devices & Services → Add integration → STIB/MIVB**
2. Choose your **display language** (French or Dutch) and enter your **API key**
3. The integration validates the key and downloads the full stop catalogue (~2 400 stops) — this takes a few seconds
4. **Search** for a stop by typing part of its name (e.g. `forest`, `midi`, `schuman`)
5. **Select** the stop from the results — all platforms are grouped automatically
6. Repeat to add more stops, then click **Finish**

At first launch the integration also downloads the STIB GTFS feed to get official line colours and vehicle types. This is a one-time download; subsequent restarts use the cached data.

---

## Sensors

Each sensor is named **`sensor.line_<LINE>_<STOP>_<DESTINATION>`** and belongs to a **device** named after the stop.

| State | Meaning |
|---|---|
| `3` | 3 minutes until the next vehicle |
| `0` | Vehicle at the stop |
| `unavailable` | API unreachable or coordinator refresh failed |

### Attributes

| Attribute | Type | Description |
|---|---|---|
| `current_passage` | ISO timestamp | Expected arrival time of the next vehicle |
| `next_passage` | ISO timestamp | Expected arrival time of the vehicle after next |
| `next_passage_minutes` | int | Minutes until the vehicle after next |
| `destination` | string | Real-time destination (in your chosen language) |
| `message` | string | Service message from STIB (see below) |
| `is_boarding` | bool | `false` when the vehicle will not stop for passengers |
| `line_id` | string | Line number e.g. `"25"` |
| `line_type` | string | `"bus"`, `"tram"` or `"metro"` |
| `line_type_label` | string | `"B"`, `"T"` or `"M"` |
| `line_color` | string | Official STIB hex colour e.g. `"#A12944"` |
| `line_text_color` | string | Contrasting text colour e.g. `"#FFFFFF"` |
| `stop_name_fr` | string | Stop name in French |
| `stop_name_nl` | string | Stop name in Dutch |
| `latitude` / `longitude` | float | Stop GPS coordinates |
| `point_ids` | list | Physical platform IDs grouped under this stop |

### Service messages

The `message` attribute carries official STIB service messages when present.

| `message` value | `is_boarding` | Meaning |
|---|---|---|
| *(empty)* | `true` | Normal operation |
| `Ne pas embarquer` | `false` | Vehicle will **not stop** for passengers (going to depot) |
| `Ligne déviée` | `true` | Line is **detoured** — different route than usual |
| `Temps théorique` | `true` | **No real-time data** — showing scheduled time only |

---

## Options

Go to **Settings → Devices & Services → STIB/MIVB → Configure** to:

| Option | Description |
|---|---|
| **Update interval** | Polling frequency in seconds (10–3600, default 30) |
| **Add another stop** | Search and add a new stop group |
| **Refresh line colours & types** | Re-download the GTFS feed to get updated line colours and vehicle types |

---

## Lovelace examples

### Basic entity card

```yaml
type: entity
entity: sensor.line_25_uccle_boondael_gare
name: "Line 25 → Boondael"
icon: mdi:tram
```

### Mushroom template card — with message fallback, no image needed

```yaml
type: custom:mushroom-template-card
entity: sensor.line_25_uccle_boondael_gare
icon: >-
  {% set t = state_attr('sensor.line_25_uccle_boondael_gare', 'line_type') %}
  {{ 'mdi:subway' if t == 'metro' else 'mdi:tram' if t == 'tram' else 'mdi:bus' }}
icon_color: "{{ state_attr('sensor.line_25_uccle_boondael_gare', 'line_color') }}"
badge_text: "{{ state_attr('sensor.line_25_uccle_boondael_gare', 'line_type_label') }}"
badge_color: "{{ state_attr('sensor.line_25_uccle_boondael_gare', 'line_color') }}"
primary: "25 – {{ state_attr('sensor.line_25_uccle_boondael_gare', 'destination') }}"
secondary: >-
  {% set msg = state_attr('sensor.line_25_uccle_boondael_gare', 'message') %}
  {% if msg %}
    {{ msg }}
  {% else %}
    {{ states('sensor.line_25_uccle_boondael_gare') }} min
    ( {{ state_attr('sensor.line_25_uccle_boondael_gare', 'next_passage_minutes') }} min )
  {% endif %}
color: "{{ state_attr('sensor.line_25_uccle_boondael_gare', 'line_color') }}"
vertical: true
```

### Grid of stops — multiple lines at the same stop

```yaml
type: grid
columns: 3
square: true
cards:
  - type: custom:mushroom-template-card
    entity: sensor.line_21_michel_ange_maes
    icon: mdi:bus
    icon_color: "{{ state_attr('sensor.line_21_michel_ange_maes', 'line_color') }}"
    badge_text: "{{ state_attr('sensor.line_21_michel_ange_maes', 'line_type_label') }}"
    badge_color: "{{ state_attr('sensor.line_21_michel_ange_maes', 'line_color') }}"
    primary: "21 – {{ state_attr('sensor.line_21_michel_ange_maes', 'destination') }}"
    secondary: >-
      {% set msg = state_attr('sensor.line_21_michel_ange_maes', 'message') %}
      {% if msg %}{{ msg }}{% else %}
      {{ states('sensor.line_21_michel_ange_maes') }} min
      ( {{ state_attr('sensor.line_21_michel_ange_maes', 'next_passage_minutes') }} min )
      {% endif %}
    vertical: true

  - type: custom:mushroom-template-card
    entity: sensor.line_63_michel_ange_cimetiere_de_bruxelles
    icon: mdi:bus
    icon_color: "{{ state_attr('sensor.line_63_michel_ange_cimetiere_de_bruxelles', 'line_color') }}"
    badge_text: "{{ state_attr('sensor.line_63_michel_ange_cimetiere_de_bruxelles', 'line_type_label') }}"
    badge_color: "{{ state_attr('sensor.line_63_michel_ange_cimetiere_de_bruxelles', 'line_color') }}"
    primary: "63 – {{ state_attr('sensor.line_63_michel_ange_cimetiere_de_bruxelles', 'destination') }}"
    secondary: >-
      {% set msg = state_attr('sensor.line_63_michel_ange_cimetiere_de_bruxelles', 'message') %}
      {% if msg %}{{ msg }}{% else %}
      {{ states('sensor.line_63_michel_ange_cimetiere_de_bruxelles') }} min
      ( {{ state_attr('sensor.line_63_michel_ange_cimetiere_de_bruxelles', 'next_passage_minutes') }} min )
      {% endif %}
    vertical: true
```

### Automation — alert when bus is about to arrive and boarding

```yaml
automation:
  alias: "Alert: Bus 25 arriving in less than 3 min"
  trigger:
    - platform: numeric_state
      entity_id: sensor.line_25_uccle_boondael_gare
      below: 3
  condition:
    - condition: template
      value_template: >
        {{ state_attr('sensor.line_25_uccle_boondael_gare', 'is_boarding') == true }}
  action:
    - service: notify.mobile_app
      data:
        message: "Bus 25 arrives in {{ states('sensor.line_25_uccle_boondael_gare') }} min!"
```

### Template sensor — display next passage time in human-readable format

```yaml
template:
  - sensor:
      - name: "Line 25 next passage"
        state: >
          {% set ts = state_attr('sensor.line_25_uccle_boondael_gare', 'next_passage') %}
          {% if ts %}{{ as_timestamp(ts) | timestamp_custom('%H:%M') }}{% else %}—{% endif %}
```

---

## Data sources

| Source | Endpoint | Used for |
|---|---|---|
| STIB Open Data | `rt/WaitingTimes` | Real-time arrivals (filtered by stop) |
| STIB Open Data | `static/stopsByLine` | Line directions and canonical destinations |
| STIB Open Data | `static/StopDetails` | Stop catalogue (names, coordinates) |
| STIB GTFS | `routes.txt` | Official line colours and vehicle types |

All endpoints require the `bmc-partner-key` header with your API key.

---

## License

MIT
