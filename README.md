# UniFi Protect Watermark

A Home Assistant custom integration that sets the text of UniFi Protect's **visible watermark** on your
cameras. Use it to burn live data, such as the outdoor temperature, into live view, recordings and exports.

Protect 7.2 added a **Custom String** to each camera's watermark (Settings → Evidence Trust → Visible
Watermark). This integration adds a text entity for each corner of that watermark to your existing UniFi Protect
camera devices. Set the entity from an automation, and the text appears on the camera.

## How it works

- **No sign-in of its own.** It reuses the signed-in client of Home Assistant's built-in
  [UniFi Protect integration](https://www.home-assistant.io/integrations/unifiprotect/). There are no
  credentials to enter and nothing extra to secure.
- **Entities go on your existing cameras.** Each overlay-capable camera gets up to four `text` entities, one
  per corner, on the device UniFi Protect already created. Only **Watermark top right** is enabled by default.
  Top left normally holds Protect's own `{Datetime} {CameraName}`.
- **Changes only what you set.** Setting a corner sends just that corner to Protect, and it's saved, not shown
  as a temporary preview. Setting the same text again sends nothing.
- **Reads changes made in Protect.** The current text is polled every 5 minutes, so edits made in the Protect
  UI show up in Home Assistant.

Protect placeholders such as `{Datetime}`, `{CameraName}`, `{Resolution}` and `{Bitrate}` are passed through,
so you can mix them with your own text. An empty value clears the corner.

## Requirements

- Home Assistant 2026.10 or newer.
- UniFi Protect 7.2 or newer, and cameras that support the new overlay. G6-series cameras do. Older models
  (G4 cameras and the G4 Doorbell, for example) only have the legacy name, date and logo toggles, and get no
  entities.
- The UniFi Protect integration, set up with a **local username and password** (not only an API key). The
  watermark is only on Protect's private API, so a public-API-only setup can't change it. That user needs
  permission to edit camera settings.

## Installation

### HACS

1. In HACS, open the menu → **Custom repositories**, and add this repository as an **Integration**.
2. Install **UniFi Protect Watermark** and restart Home Assistant.

### Manual

Copy `custom_components/protect_watermark` into your Home Assistant `config/custom_components/` folder and
restart Home Assistant.

## Setup

**Settings → Devices & services → Add integration → UniFi Protect Watermark.** With one UniFi Protect console,
there's nothing to fill in. With more than one, pick the console.

Cameras added to Protect later get their entities after you reload the integration.

## Example: outdoor temperature in the top-right corner

```yaml
alias: Camera watermark temperature
mode: queued
max: 1
triggers:
  - trigger: state
    entity_id: sensor.outdoor_temperature
conditions:
  - condition: not
    conditions:
      - condition: state
        entity_id: sensor.outdoor_temperature
        state: [unavailable, unknown]
actions:
  - action: text.set_value
    target:
      label_id: camera_watermark
    data:
      value: "{{ states('sensor.outdoor_temperature') | float | round(0) | int }}F"
```

Add the `camera_watermark` label to each **Watermark top right** entity you want updated. Rounding means Protect
is only written to when the whole-degree value changes.

Check how your cameras render special characters, such as `°`, before relying on them.

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
