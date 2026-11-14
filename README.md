# UniFi Protect Watermark

[![GitHub release](https://img.shields.io/github/v/release/KB1RMA/ha-protect-watermark)](https://github.com/KB1RMA/ha-protect-watermark/releases/latest)
[![Marketplace: custom repository](https://img.shields.io/badge/Marketplace-custom_repository-41BDF5)](#installation)
[![Home Assistant 2026.10+](https://img.shields.io/badge/Home_Assistant-2026.10%2B-41BDF5?logo=homeassistant&logoColor=white)](https://www.home-assistant.io/)
[![CI](https://github.com/KB1RMA/ha-protect-watermark/actions/workflows/ci.yml/badge.svg)](https://github.com/KB1RMA/ha-protect-watermark/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/github/license/KB1RMA/ha-protect-watermark)](LICENSE)

[![Open your Home Assistant instance and open this repository in the Marketplace.](https://my.home-assistant.io/badges/marketplace_repository.svg)](https://my.home-assistant.io/redirect/marketplace_repository/?owner=KB1RMA&repository=ha-protect-watermark&category=integration)

A Home Assistant custom integration that sets the text of UniFi Protect's **visible watermark** on your
cameras. Use it to burn live data, such as the outdoor temperature, into live view, recordings and exports.

[UniFi Protect 7.2.98](https://community.ui.com/releases/UniFi-Protect-Application-7-2-98/3b090596-55f5-4c27-824b-44951c2d4a25),
released on 3 August 2026, added Evidence Trust and visible watermarks. Each camera's watermark can include a
**Custom String** (Settings → Evidence Trust → Visible Watermark). This integration adds a text entity for each
corner of that watermark to your existing UniFi Protect camera devices. Set the entity from an automation, and
the text appears on the camera.

![The top-right corner of a G6 Bullet's picture, with the outdoor temperature, 45°F, in the watermark](https://raw.githubusercontent.com/KB1RMA/ha-protect-watermark/main/docs/images/watermark-top-right.jpg)

Protect's UI calls this the *visible watermark*, and its API calls it the *overlay*. Both names mean the same
thing here.

> [!IMPORTANT]
> Your UniFi Protect integration must be signed in with a **local username and password**. An API-key-only
> setup can't change the watermark: adding this integration stops with a message saying so, and an existing
> setup shows a repair under **Settings → Repairs**. See [Requirements](#requirements).

## How it works

- **No sign-in of its own.** It reuses the signed-in client of Home Assistant's built-in
  [UniFi Protect integration](https://www.home-assistant.io/integrations/unifiprotect/). There are no
  credentials to enter and nothing extra to secure.
- **Entities go on your existing cameras.** They're added to the device UniFi Protect already created, as
  configuration entities.
- **Changes only what you set.** Each change sends just that setting to Protect, and it's saved, not shown as
  a temporary preview. Protect is read first, so a value it already has isn't sent again.
- **Reads changes made in Protect.** Settings are polled every minute, so edits made in the Protect UI, such
  as moving text to another corner, show up in Home Assistant.

## Entities

Each camera that supports the visible watermark gets:

| Entity | Type | Protect setting | Enabled by default |
|---|---|---|---|
| **Watermark** | switch | Shows or hides the whole watermark (`enable`) | Yes |
| **Watermark top left**, **top right**, **bottom left**, **bottom right** | text | The text in each corner | Yes |
| **Watermark date format** | text | The `strftime` format of `{Datetime}`, such as `%Y-%m-%d %r` | No |
| **Watermark area** | sensor (diagnostic) | How much of the picture the watermark covers, in percent (`overlayAreaPercent`). Protect works it out from the text, up to a limit of 20% on current cameras. | No |

Top left normally holds Protect's own `{Datetime} {CameraName}`. An empty value clears a corner.

These Protect placeholders are passed through, so you can mix them with your own text: `{Datetime}`,
`{CameraName}`, `{Resolution}`, `{Width}`, `{Height}`, `{Codec}`, `{Bitrate}`, `{BitrateFull}`, `{ULogo}` and
`{CustomLogo}`.

The custom logo image itself can only be uploaded in Protect.

## Requirements

- Home Assistant 2026.10 or newer.
- UniFi Protect 7.2.98 or newer, the first 7.2 release
  ([release notes](https://community.ui.com/releases/UniFi-Protect-Application-7-2-98/3b090596-55f5-4c27-824b-44951c2d4a25)).
- Cameras on firmware 5.4 or newer that support the visible watermark. Protect's release notes list firmware 5.4
  as the requirement for visible watermarks. G6-series cameras support it. Older models (G4 cameras and the G4
  Doorbell, for example) only have the legacy name, date and logo toggles, and get no entities.
- The UniFi Protect integration, set up with a **local username and password** (not only an API key). The
  watermark is only on Protect's private API, so a public-API-only setup can't change it. That user needs
  permission to edit camera settings. Without this, adding the integration stops with "Set up the UniFi
  Protect integration first", or an existing setup shows the repair "UniFi Protect has no private API
  access".

If no camera qualifies, the integration still loads, and a repair under **Settings → Repairs** lists each
camera's model and firmware against these minimums.

## Installation

### Marketplace (Home Assistant 2026.11 and newer)

[![Open your Home Assistant instance and open this repository in the Marketplace.](https://my.home-assistant.io/badges/marketplace_repository.svg)](https://my.home-assistant.io/redirect/marketplace_repository/?owner=KB1RMA&repository=ha-protect-watermark&category=integration)

1. Select the button above, or go to **Settings → Marketplace → Add from link** and enter
   `KB1RMA/ha-protect-watermark`.
2. Install **UniFi Protect Watermark** and restart Home Assistant.

### HACS (Home Assistant 2026.10)

[![Open your Home Assistant instance and open this repository in HACS.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=KB1RMA&repository=ha-protect-watermark&category=integration)

1. Select the button above, or in HACS open the menu → **Custom repositories** and add this repository as an
   **Integration**.
2. Install **UniFi Protect Watermark** and restart Home Assistant.

### Manual

Copy `custom_components/protect_watermark` into your Home Assistant `config/custom_components/` folder and
restart Home Assistant.

## Setup

**Settings → Devices & services → Add integration → UniFi Protect Watermark.** With one UniFi Protect console,
there's nothing to fill in. With more than one, pick the console.

Cameras added to Protect later get their entities after you reload the integration.

## Quick start: outdoor temperature in the top-right corner

This automation writes the temperature to one camera whenever it changes. Replace the two entity IDs with
yours.

```yaml
alias: Camera watermark temperature
triggers:
  - trigger: state
    entity_id: sensor.outdoor_temperature
    to: null
conditions:
  - condition: numeric_state
    entity_id: sensor.outdoor_temperature
    above: -100
actions:
  - action: text.set_value
    target:
      entity_id: text.driveway_watermark_top_right
    data:
      value: "{{ states('sensor.outdoor_temperature') | float | round(0) | int }}°F"
```

The `numeric_state` condition skips `unavailable` and `unknown`, so those never reach the video. For
Celsius, change `°F` to `°C`. You can test the entity without an automation: open it in Home Assistant, type
some text and check the camera's live view.

## Full example: several cameras, with stale-reading handling

The quick start keeps showing the last temperature if the sensor stops reporting. Because the watermark is
burned into recordings, you may prefer to show `--°F` instead. This version does that, and updates every
camera at once.

First, add a `camera_watermark` label to each **Watermark top right** entity you want updated (open the
entity → settings → **Labels**). The automation targets that label rather than individual entities.

```yaml
alias: Camera watermark temperature
mode: queued
max: 2
max_exceeded: silent
triggers:
  - trigger: state
    entity_id: sensor.outdoor_temperature
    to: null
    id: reading
  - trigger: template
    value_template: >-
      {% set s = states.sensor.outdoor_temperature %}
      {{ s is none or now() - s.last_reported > timedelta(minutes=30) }}
    id: stale
  - trigger: template
    value_template: >-
      {% set s = states.sensor.outdoor_temperature %}
      {{ s is not none and now() - s.last_reported <= timedelta(minutes=30) }}
    id: recovered
actions:
  - choose:
      - conditions:
          - condition: trigger
            id: stale
        sequence:
          - action: text.set_value
            target:
              label_id: camera_watermark
            data:
              value: "--°F"
      - conditions:
          - condition: numeric_state
            entity_id: sensor.outdoor_temperature
            above: -100
        sequence:
          - action: text.set_value
            target:
              label_id: camera_watermark
            data:
              value: "{{ states('sensor.outdoor_temperature') | float | round(0) | int }}°F"
```

How it works:

- **Readings.** `to: null` fires on state changes only, not attribute updates. The `numeric_state` condition
  skips `unavailable`, `unknown` and other non-numeric states.
- **Stale readings.** The watermark is burned into recordings, so an old temperature shouldn't stay on them. If
  the sensor hasn't reported for 30 minutes, the corner shows `--°F`. This uses `last_reported`, which moves on
  every report even when the value is unchanged, so it catches a sensor that went `unavailable` and one that
  froze on its last value, as cloud weather stations can. A state trigger with `for:` wouldn't work: it
  restarts only when the value changes, so a steady temperature would look stale.
- **Recovery.** `recovered` fires when reports resume, so a sensor that comes back with the same value it froze
  on still replaces `--°F`.
- **Queueing.** `queued` with `max: 2` lets one write finish while keeping only the latest reading waiting. Home
  Assistant doesn't accept `max: 1` for queued mode.
- **Writes.** Rounding to a whole degree, plus the integration skipping writes that change nothing, means
  Protect is only written when the displayed value changes.
- **Units.** For Celsius, change `°F` to `°C` in both values.

The `°` sign renders on G6 cameras. Check other special characters on your cameras before relying on them.

## Limits and risks

- **Private API.** The overlay isn't in Protect's public Integration API (as of 7.2), so this uses the private
  API through the UniFi Protect integration's client. A Protect update could change it.
- **Home Assistant's direction.** The UniFi Protect integration is phasing out the private API. If a future
  release stops using a username and password, this integration shows a repair issue and stops loading. If
  Ubiquiti adds the overlay to the public API, the feature belongs upstream, and this integration can retire.
- **It relies on UniFi Protect's internals.** It reads the client from that integration's config entry, which
  isn't a public Home Assistant interface. Each release is tested against the current Home Assistant.

## Development

Development uses [uv](https://docs.astral.sh/uv/). `uv sync` creates `.venv` from `uv.lock`, including a
Python that matches Home Assistant's minimum if you don't have one.

```bash
uv sync
uv run ruff check . && uv run ruff format --check .
uv run pyright
uv run pytest
```

The `uiprotect` pin in `pyproject.toml` must match the version Home Assistant's UniFi Protect integration pins.

CI runs Ruff, Pyright in strict mode, the tests (100% coverage required), hassfest and HACS validation.

## Licence

MIT
