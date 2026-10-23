# Salus iT500 Integration for Home Assistant

Custom integration for Salus iT500 thermostats (RT301i, RT300, RT500 and other devices of the Salus iT500 cloud service). It controls heating zones and hot water through the Salus iT500 cloud API (Arrayent backend).

## Features

- **Heating control**
  - Target temperature in 0.5 °C steps (5–34.5 °C)
  - HVAC modes Heat / Off, `climate.turn_on` / `climate.turn_off`
  - Preset modes Auto (schedule), Manual, Temporary hold
  - Room temperature and relay (heating / idle) status
  - Two heating zones on CH1 + CH2 systems
- **Hot water control** (CH1 + hot water systems)
  - Auto (schedule), Boost (one-time heating), Always on, Off
- **Responsive control**
  - The commanded state is shown immediately. Salus API reports changes after 10–30 seconds, so the state is confirmed 5 and 20 seconds after a command.
  - Commands rejected by Salus are reported as errors in Home Assistant.
  - Temporary Salus API failures (HTTP 5xx, timeouts) are retried; the last known state is kept during API outages of up to 10 minutes.
- **Setup**
  - Configuration in the UI, re-authentication when the password is rejected
  - Setup is retried automatically while Salus API is unavailable
  - Passwords with special characters silently removed by Salus are handled

## Requirements

- Home Assistant 2025.2 or newer
- Salus iT500 account with at least one device

## Installation

### HACS

1. HACS → ⋮ → **Custom repositories** → add `https://github.com/Peterka35/salus-it500-cloud` as **Integration**
2. Install **Salus iT500**
3. Restart Home Assistant

### Manual installation

1. Copy the `custom_components/salusfy` folder to `config/custom_components/`
2. Restart Home Assistant

## Configuration

1. **Settings** → **Devices & Services** → **Add Integration**
2. Search for **Salus iT500**
3. Enter the e-mail and password of your Salus account

Each entry controls one thermostat. When the account has several thermostats (for example one per house), the setup asks which one to add; add the integration again for each of the others. Thermostats under separate Salus accounts are added the same way, one entry per account.

Entries made before 1.4.0 keep the first thermostat of their account.

## Entities

Each thermostat is a device named after its description in the Salus app.

| Platform | Name | Created |
|---|---|---|
| climate | `<device> Heating Zone 1` | always |
| climate | `<device> Heating Zone 2` | CH1 + CH2 systems |
| water_heater | `<device> Teplá voda` | CH1 + hot water systems |

- Climate attributes: `frost_active`, `schedule_type`
- Water heater attributes: `schedule_type`, `running_mode`, `boost_remaining_hours` (in boost mode)
- `climate.set_hvac_mode` with `heat` switches the thermostat to Auto (schedule). `climate.turn_on` does the same for a turned off thermostat; a thermostat already heating keeps its mode.

## Automation examples

### Manual temperature in the morning

```yaml
automation:
  - alias: "Morning heating"
    triggers:
      - trigger: time
        at: "06:00:00"
    actions:
      - action: climate.set_preset_mode
        target:
          entity_id: climate.my_home_heating_zone_1
        data:
          preset_mode: manual
      - action: climate.set_temperature
        target:
          entity_id: climate.my_home_heating_zone_1
        data:
          temperature: 22
```

### Hot water boost

```yaml
automation:
  - alias: "Hot water boost"
    triggers:
      - trigger: time
        at: "18:00:00"
    actions:
      - action: water_heater.set_operation_mode
        target:
          entity_id: water_heater.my_home_tepla_voda
        data:
          operation_mode: boost
```

### Return to schedule at night

```yaml
automation:
  - alias: "Return to schedule"
    triggers:
      - trigger: time
        at: "22:00:00"
    actions:
      - action: climate.set_preset_mode
        target:
          entity_id: climate.my_home_heating_zone_1
        data:
          preset_mode: auto
```

## Troubleshooting

- **Re-authentication requested** – Salus rejected the saved password. Check that you can log in to the Salus app and enter the current password in the repair notification.
- **Integration keeps retrying setup** – Salus API is not available; the setup continues automatically when it responds again.
- **Command failed** – Salus did not accept the command or did not respond; the error is shown in Home Assistant.

Debug logging:

```yaml
logger:
  logs:
    custom_components.salusfy: debug
```

Logs do not contain the account e-mail, password hashes or server responses. More details (in Czech) are in [TROUBLESHOOTING.md](TROUBLESHOOTING.md).

## Development

```bash
pip install homeassistant pytest pytest-asyncio xmltodict ruff
pytest
ruff check && ruff format --check
```

Ruff and pytest settings are in `pyproject.toml`.

## Credits and license

- The API client in `custom_components/salusfy/pyit500` is based on the **pyit500** library by Richard Archer, MIT license – see [its license](custom_components/salusfy/pyit500/LICENSE).
- The integration domain `salusfy` comes from the original [salusfy](https://github.com/floringhimie/salusfy) component by @floringhimie; this implementation is a rewrite on top of pyit500.
- MIT License – see [LICENSE](LICENSE).
