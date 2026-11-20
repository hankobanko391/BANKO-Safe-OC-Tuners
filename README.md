# BANKO Safe GPU & Performance Tuners (`v1.0.0`)

Two brand-locked Windows desktop GPU & power tuning utilities built with Python and `customtkinter`, engineered with strict OEM WMI locking, zero-voltage overclock ceilings, `1000ms` thermal monitoring (`>82°C` automatic cut-off), and one-click stock reset.

## Live Download Page & Releases

- **Download Portal (GitHub Pages):** https://hankobanko391.github.io/BANKO-Safe-OC-Tuners/
- **Release v1.0.0:** https://github.com/hankobanko391/BANKO-Safe-OC-Tuners/releases/tag/v1.0.0
  - `BANKO_HP_Tuner.exe` — HP / Hewlett-Packard Edition (`#0D0F14` Dark + `#00B4D8` Neon Cyan)
  - `BANKO_Dell_Tuner.exe` — Dell Edition (`#0D0F14` Dark + `#00FF66` Neon Green)

## Safety Guardrails

1. **Strict WMI Brand Lock**: Checks `Win32_ComputerSystem.Manufacturer` on startup.
   - `hp_tuner.py` unlocks **only** on `HP` / `Hewlett-Packard` systems.
   - `dell_tuner.py` unlocks **only** on `Dell` systems.
   - Non-matching OEM hardware displays a Hardware Safety Lock screen with tuning controls disabled.
2. **Zero Voltage Sliders**: Voltage controls are omitted by design.
3. **Three Safe Presets**:
   - **Eco / Cool Mode**: Stock clocks (`+0 / +0 MHz`) + Windows Balanced power plan.
   - **Balanced Boost**: `+75 MHz` Core / `+150 MHz` Memory safe offset via `nvidia-smi` / NVAPI wrapper with Windows High Performance power fallback.
   - **Max Safe OC**: `+120 MHz` Core / `+250 MHz` Memory ceiling + Windows High Performance power plan.
4. **Auto Thermal Cut-off (`1000ms`)**: Polls GPU temperature every second; if temperature exceeds `82°C`, automatically reverts to Stock / Eco Mode.
5. **RESET TO STOCK**: High-visibility reset control restoring stock GPU clocks (`-rgc` / `-rmc`) and Balanced power plan.

## Building from Source

```powershell
pip install -r requirements.txt
pyinstaller --noconfirm --clean --onefile --noconsole --collect-all customtkinter --name BANKO_HP_Tuner hp_tuner.py
pyinstaller --noconfirm --clean --onefile --noconsole --collect-all customtkinter --name BANKO_Dell_Tuner dell_tuner.py
```
