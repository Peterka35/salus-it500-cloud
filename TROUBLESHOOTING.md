# Troubleshooting - Salus iT500 Integration

## Chyba: "Invalid handler specified"

Tato chyba znamená, že Home Assistant nemůže najít nebo načíst config flow handler. Zde jsou kroky k řešení:

### 1. Zkontrolujte strukturu souborů

Ujistěte se, že máte všechny tyto soubory:

```
custom_components/salusfy/
├── __init__.py
├── config_flow.py          ← DŮLEŽITÉ!
├── const.py                ← DŮLEŽITÉ!
├── manifest.json           ← DŮLEŽITÉ!
├── climate.py
├── coordinator.py
├── entity.py
├── water_heater.py
├── strings.json
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

### 2. Kontrola klíčových souborů

#### manifest.json
Musí obsahovat:
```json
{
  "domain": "salusfy",
  "name": "Salus iT500",
  "config_flow": true,
  ...
}
```

#### const.py
Musí obsahovat:
```python
DOMAIN = "salusfy"
```

#### config_flow.py
Musí obsahovat třídu `ConfigFlow` (PŘESNĚ tento název!):
```python
class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Salus iT500."""
    VERSION = 1
    ...
```

### 3. Vyčištění cache a restart

```bash
# V Home Assistant konfigurační složce
cd custom_components/salusfy
# Smažte všechny __pycache__ složky
find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null

# Nebo na Windows v PowerShell:
# Get-ChildItem -Path . -Recurse -Directory -Filter __pycache__ | Remove-Item -Recurse -Force
```

Poté:
1. Plně restartujte Home Assistant (ne pouze "Reload")
2. Počkejte 30 sekund
3. Zkuste přidat integraci znovu

### 4. Kontrola logů

Zapněte debug logging:

V `configuration.yaml`:
```yaml
logger:
  default: warning
  logs:
    custom_components.salusfy: debug
    homeassistant.config_entries: debug
```

Restart HA a podívejte se do logů (Settings → System → Logs)

Hledejte:
- `Error loading custom_components.salusfy`
- `Invalid config_flow`
- Python syntax errors
- Import errors

### 5. Kontrola Python syntaxe

Ujistěte se, že žádný soubor neobsahuje syntaktické chyby:
- Žádné chybějící uvozovky
- Správné odsazení
- Žádné chybějící dvojtečky
- Správně uzavřené závorky

### 6. Kontrola verzí

Minimální požadavky:
- Home Assistant: 2025.2.0+

Zkontrolujte verzi v:
Settings → System → Repairs → Three dots menu → System Information

### 7. Ruční kontrola importů

Zkuste spustit Python import test (pokud máte přístup k HA Python):

```python
# Toto spusťte v HA Python prostředí
import sys
sys.path.append('/config/custom_components')

try:
    from salusfy.const import DOMAIN
    print(f"DOMAIN = {DOMAIN}")
    from salusfy import config_flow
    print(f"ConfigFlow = {config_flow.ConfigFlow}")
    print("✓ Importy OK!")
except Exception as e:
    print(f"✗ Chyba importu: {e}")
```

## Další Časté Chyby

### "Cannot connect" / "Failed to connect"

**Příčiny:**
- Problém s internetovým připojením
- Salus API je nedostupné nebo vrací chyby

**Řešení:**
1. Zkuste se přihlásit do mobilní aplikace Salus
2. Zkontrolujte internetové připojení HA
3. Zkuste to znovu později – již nastavená integrace se při nedostupném API načte automaticky, jakmile API odpoví

### Výzva k novému přihlášení

Salus odmítl uložené heslo (např. po jeho změně). Otevřete oznámení v **Nastavení → Opravy** nebo u integrace a zadejte aktuální heslo.

### "Příkaz pro Salus iT500 selhal"

Salus příkaz nepřijal nebo neodpověděl. Stav v Home Assistantu zůstává podle skutečného stavu termostatu; příkaz zopakujte. Při opakování zapněte debug logování (viz níže).

### "No devices found"

**Příčiny:**
- Nemáte žádné zařízení na účtu
- Zařízení není online
- Zařízení není správně registrované

**Řešení:**
1. Přihlaste se na https://salus-it500.com
2. Zkontrolujte, že vidíte své zařízení
3. Zkontrolujte, že zařízení je online (zelená tečka)
4. Zkuste restartovat termostat

### Entity se nezobrazují po instalaci

**Řešení:**
1. Přejděte na Settings → Devices & Services
2. Klikněte na "Salus iT500"
3. Měli byste vidět device s entitami
4. Pokud ne, zkuste:
   - Remove integration
   - Restart HA
   - Add integration znovu

### Integrace zmizela po restartu

**Příčiny:**
- Soubory byly smazány nebo poškozeny
- Chyba při načítání

**Řešení:**
1. Zkontrolujte, že složka custom_components/salusfy stále existuje
2. Zkontrolujte logy pro chyby
3. Možná budete muset reinstalovat

## Debug Checklist

Před nahlášením problému projděte tento checklist:

- [ ] Všechny soubory jsou na správném místě
- [ ] Home Assistant byl plně restartován (ne reload)
- [ ] Cache byla vyčištěna (__pycache__ složky smazány)
- [ ] manifest.json obsahuje `"config_flow": true`
- [ ] const.py obsahuje `DOMAIN = "salusfy"`
- [ ] config_flow.py obsahuje třídu `ConfigFlow`
- [ ] Verze HA je 2025.2.0+
- [ ] Logy byly zkontrolovány
- [ ] Debug logging je zapnut
- [ ] Přihlašovací údaje jsou správné
- [ ] Účet má alespoň jedno zařízení

## Získání Pomoci

Pokud problém přetrvává:

1. Zapněte debug logging (viz výše)
2. Zkuste přidat integraci
3. Zkopírujte relevantní část logů
4. Vytvořte issue na GitHub s:
   - Verzí Home Assistant
   - Kompletním chybovým hlášením z logů
   - Kroky k reprodukci problému
   - Seznam souborů v custom_components/salusfy

## Známé Problémy

### Windows: Problém s právy

Na Windows může být problém s právy k souborům. Ujistěte se, že:
- Home Assistant má právo číst složku custom_components
- Soubory nejsou "Read-only"

### Docker: Problém s mountováním

Pokud používáte Docker, ujistěte se, že:
- Složka custom_components je správně mountovaná
- Kontejner má přístup ke složce

### HAOS/Supervised: Addon file editor

Pokud používáte File Editor addon:
- Můžete potřebovat restartovat i addon
- Zkontrolujte, že editor neukazuje staré soubory

## Quick Fix - Reinstalace

Pokud nic nepomáhá, zkuste čistou reinstalaci:

1. Odstraňte integraci: Settings → Devices & Services → Salus iT500 → Remove
2. Smažte složku: `custom_components/salusfy`
3. Smažte `home-assistant_v2.db-shm` a `home-assistant_v2.db-wal` (volitelné, NEBEZPEČNÉ!)
4. Restart HA
5. Zkopírujte čerstvé soubory do `custom_components/salusfy`
6. Restart HA
7. Přidejte integraci znovu
