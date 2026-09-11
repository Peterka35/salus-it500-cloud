# Instalační Návod - Salus iT500 Integration

## Rychlá Instalace

### Krok 1: Zkopírování souborů

Zkopírujte celou složku `custom_components/salusfy` do vaší Home Assistant konfigurace:

```
<homeassistant_config>/
  └── custom_components/
      └── salusfy/
          ├── __init__.py
          ├── climate.py
          ├── config_flow.py
          ├── const.py
          ├── coordinator.py
          ├── entity.py
          ├── manifest.json
          ├── strings.json
          ├── water_heater.py
          ├── translations/
          │   ├── cs.json
          │   └── en.json
          └── pyit500/
              ├── __init__.py
              ├── LICENSE
              ├── auth.py
              ├── device.py
              ├── devicelistitem.py
              ├── enumfriendly.py
              ├── exceptions.py
              ├── heatingzone.py
              ├── hotwaterzone.py
              ├── parsing.py
              ├── pyit500.py
              ├── user.py
              └── zone.py
```

### Krok 2: Restart Home Assistant

Po zkopírování souborů restartujte Home Assistant.

### Krok 3: Přidání Integrace

1. Přejděte do **Nastavení** → **Zařízení a Služby**
2. Klikněte na **+ Přidat Integraci** (pravý dolní roh)
3. Vyhledejte **"Salus iT500"** nebo **"salusfy"**
4. Zadejte své přihlašovací údaje:
   - **Email**: Váš Salus účet (email)
   - **Password**: Vaše heslo

5. Klikněte na **Odeslat**

Integrace automaticky najde vaše zařízení a vytvoří příslušné entity.

## Řešení Problémů

### Chyba: "Invalid handler specified"

Tato chyba může nastat, pokud:

1. **Soubory nejsou správně zkopírovány**
   - Zkontrolujte, že všechny soubory jsou na správném místě
   - Zejména zkontrolujte `config_flow.py` a `const.py`

2. **Home Assistant nebyl restartován**
   - Restartujte Home Assistant a zkuste znovu

3. **Stará verze integrace je stále načtena**
   - Plně restartujte Home Assistant (ne pouze reload)
   - Případně smažte `__pycache__` složky v custom_components

### Chyba: "Authentication failed"

1. Zkontrolujte své přihlašovací údaje
2. Zkuste se přihlásit na https://salus-it500.com
3. Zkontrolujte, že máte aktivní účet

Pokud Salus odmítne heslo u již nastavené integrace, Home Assistant zobrazí výzvu k novému přihlášení. Stačí v ní zadat aktuální heslo.

### Chyba: "No devices found"

1. Ujistěte se, že máte alespoň jeden Salus iT500 termostat registrovaný na vašem účtu
2. Zkontrolujte, že je termostat online
3. Zkuste restartovat termostat

### Integrace se nezobrazuje v seznamu

1. Smažte cache:
   ```bash
   cd <homeassistant_config>
   find custom_components/salusfy -name "__pycache__" -type d -exec rm -rf {} +
   ```

2. Zkontrolujte logy Home Assistant:
   ```
   Settings → System → Logs
   ```

   Hledejte chyby související s "salusfy"

3. Zkontrolujte, že `manifest.json` má správný formát a obsahuje `"config_flow": true`

## Upgrade ze Staré Verze (0.0.x)

### 1. Odstranění staré konfigurace z configuration.yaml

Smažte nebo zakomentujte starou konfiguraci:

```yaml
# climate:
#   - platform: salusfy
#     username: "EMAIL"
#     password: "PASSWORD"
#     id: "DEVICEID"
```

### 2. Odstranění staré integrace (volitelné)

Pokud jste měli nainstalovanou starou verzi, můžete ji nejprve odstranit:

1. Smažte starou složku `custom_components/salusfy`
2. Restartujte Home Assistant
3. Nainstalujte novou verzi podle návodu výše

### 3. Vytvoření nové entity

Po instalaci nové verze:

1. Přidejte integraci přes UI (viz Krok 3 výše)
2. Starý climate entity bude nahrazen novým
3. **DŮLEŽITÉ**: Entity ID se může změnit, aktualizujte své automatizace!

   Staré: `climate.salus_thermostat`
   Nové: `climate.<název_zařízení>_heating_zone_1`

## Kontrola Instalace

### Kontrolní seznam:

- [ ] Složka `custom_components/salusfy` existuje v konfiguraci
- [ ] Všechny soubory jsou přítomny (viz Krok 1)
- [ ] Home Assistant byl plně restartován
- [ ] V Settings → Devices & Services lze najít "Add Integration"
- [ ] V seznamu integrací je "Salus iT500" nebo "salusfy"
- [ ] Přihlašovací údaje jsou správné
- [ ] V logu nejsou chyby související s "salusfy"

### Kontrola v Developer Tools

Po úspěšné instalaci byste měli vidět:

1. **Settings → Devices & Services → Salus iT500**
2. **Developer Tools → States:**
   - `climate.<název_zařízení>_heating_zone_1` (vždy)
   - `climate.<název_zařízení>_heating_zone_2` (pokud máte 2 zóny)
   - `water_heater.<název_zařízení>_tepla_voda` (pokud máte ohřev vody)

   Název zařízení je popis termostatu v aplikaci Salus.

## Získání Podpory

Pokud problém přetrvává:

1. Zapněte debug logging pro integraci:

   Do `configuration.yaml` přidejte:
   ```yaml
   logger:
     default: info
     logs:
       custom_components.salusfy: debug
   ```

2. Restartujte Home Assistant

3. Zkuste přidat integraci znovu

4. Zkopírujte logy a vytvořte issue na GitHub

## Minimum Požadavky

- Home Assistant 2025.2.0 nebo novější
- Salus iT500 účet s alespoň jedním zařízením
- Internetové připojení
