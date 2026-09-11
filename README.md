# Salus iT500 Integration for Home Assistant

Custom integration for controlling Salus iT500 thermostats in Home Assistant. This integration provides full control over your heating system including temperature control, heating modes, and hot water (if supported by your system).

## Features

- **Full Heating Control**
  - Set temperature
  - Multiple HVAC modes (Heat, Off)
  - Preset modes (Auto, Manual, Temp Hold)
  - Real-time temperature monitoring
  - Relay status (heating/idle)
  - Support for multi-zone systems (CH1, CH2)

- **Hot Water Control** (if supported)
  - Auto mode (follows schedule)
  - Boost mode (one-time heating)
  - Manual on/off
  - Status monitoring

- **Modern Architecture**
  - Async implementation using pyit500 library
  - Uses official Salus API (Arrayent backend)
  - Config flow for easy setup via UI
  - Update coordinator for efficient polling
  - No more IP blocking issues (unlike web scraping method)

## Installation

### HACS (Recommended)

1. Add this repository to HACS as a custom repository
2. Search for "Salus iT500" in HACS
3. Click Install
4. Restart Home Assistant

### Manual Installation

1. Copy the `custom_components/salusfy` folder to your Home Assistant `config/custom_components/` directory
2. Restart Home Assistant

## Configuration

### UI Configuration (Recommended)

1. Go to **Settings** → **Devices & Services**
2. Click **+ Add Integration**
3. Search for **Salus iT500**
4. Enter your Salus account credentials:
   - **Email**: Your Salus account email
   - **Password**: Your Salus account password
5. Click **Submit**

The integration will automatically discover your device and create appropriate entities.

### YAML Configuration (Legacy - Not Recommended)

While this integration now uses config entries, you can still add it via YAML if needed:

```yaml
# Note: This is deprecated. Please use UI configuration instead.
```

## Entities Created

### Climate Entities

For each heating zone in your system:

- **climate.salus_it500_heating_zone_1** (always created)
- **climate.salus_it500_heating_zone_2** (only if you have a 2-zone system)

Each climate entity provides:
- Current temperature
- Target temperature (5-34.5°C)
- HVAC modes: Heat, Off
- Preset modes:
  - **Auto**: Follow scheduled program
  - **Manual**: Manual temperature control
  - **Temp Hold**: Temporary temperature override
- Additional attributes:
  - Frost protection status
  - Schedule type

### Water Heater Entity

If your system supports hot water:

- **water_heater.salus_it500_hot_water**

Provides:
- Operation modes:
  - **Auto**: Follow scheduled program
  - **Boost**: One-time heating cycle
  - **On**: Always on
  - **Off**: Always off
- Current status (on/off)
- Additional attributes:
  - Schedule type
  - Running mode
  - Boost remaining hours (when in boost mode)

## Usage Examples

### Automations

#### Morning Heating Boost

```yaml
automation:
  - alias: "Morning Heating Boost"
    trigger:
      - platform: time
        at: "06:00:00"
    action:
      - service: climate.set_preset_mode
        target:
          entity_id: climate.salus_it500_heating_zone_1
        data:
          preset_mode: "manual"
      - service: climate.set_temperature
        target:
          entity_id: climate.salus_it500_heating_zone_1
        data:
          temperature: 22
```

#### Hot Water Boost

```yaml
automation:
  - alias: "Hot Water Boost"
    trigger:
      - platform: time
        at: "18:00:00"
    action:
      - service: water_heater.set_operation_mode
        target:
          entity_id: water_heater.salus_it500_hot_water
        data:
          operation_mode: "boost"
```

#### Return to Schedule

```yaml
automation:
  - alias: "Return to Schedule at Night"
    trigger:
      - platform: time
        at: "22:00:00"
    action:
      - service: climate.set_preset_mode
        target:
          entity_id: climate.salus_it500_heating_zone_1
        data:
          preset_mode: "auto"
```

## Troubleshooting

### Authentication Failed

- Verify your email and password are correct
- Try logging into https://salus-it500.com to confirm credentials
- Check if you can log into the Salus mobile app

### No Devices Found

- Ensure you have at least one Salus iT500 device registered to your account
- Check that your device is online and connected to the internet
- Try restarting your thermostat

### Integration Not Loading

- Check Home Assistant logs for errors
- Ensure all dependencies are installed (aiohttp, xmltodict)
- Try removing and re-adding the integration

## Supported Devices

This integration supports Salus iT500 thermostats including:
- RT301i
- RT300
- RT500
- Other models compatible with the Salus iT500 cloud service

## Differences from Old Version

The new version (1.0.0) has significant improvements over the old version (0.0.x):

| Feature | Old Version | New Version |
|---------|-------------|-------------|
| Configuration | YAML with device ID | UI with auto-discovery |
| API Method | Web scraping | Official API |
| Implementation | Synchronous | Async |
| Preset Modes | No | Yes (Auto/Manual/Temp Hold) |
| Hot Water | No | Yes |
| Multi-Zone | No | Yes |
| IP Blocking Issues | Yes | No |
| Update Method | Polling with requests | Coordinator with aiohttp |

## Credits

- Based on the [pyit500](https://github.com/) library
- Original salusfy component by @floringhimie
- Updated to v1.0.0 with full pyit500 integration