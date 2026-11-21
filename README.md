# BANKO Safe GPU & Performance Tuners (`v2.0.0`)

Two brand-locked Windows desktop GPU & power tuning applications styled with a modern **Steam / Epic Games launcher** interface and custom metallic/neon circular `.ico` desktop emblems.

## Live Download Page & Releases

- **Download Portal (GitHub Pages):** https://hankobanko391.github.io/BANKO-Safe-OC-Tuners/
- **Release v2.0.0:** https://github.com/hankobanko391/BANKO-Safe-OC-Tuners/releases/tag/v2.0.0
  - `BANKO_HP_Tuner.exe` — HP / Hewlett-Packard Edition (`#0D0F14` + Electric Cyan `#00B4D8`, custom `hp_icon.ico`)
  - `BANKO_Dell_Tuner.exe` — Dell Edition (`#0D0F14` + Neon Emerald `#00FF66`, custom `dell_icon.ico`)

## What's New in v2.0.0

- **Custom Brand Desktop Icons**: Generated multi-size circular emblem `.ico` icons (`hp_icon.ico` & `dell_icon.ico`) via `generate_icons.py` (`Pillow`).
- **Steam / Epic Launcher Layout**:
  - **Left Sidebar Navigation (`#12151E`)**: Brand emblem, **TUNING PROFILES**, **LIVE TELEMETRY**, and **SAFETY & SPECS** tabs, plus bottom **HARDWARE LOCK STATUS** badge (`VERIFIED: HP` / `VERIFIED: DELL`).
  - **Top Hero Banner**: Displays detected Laptop Model, GPU, and live GPU temperature & core/memory clock speeds.
  - **Interactive Game-Launcher Profile Cards**: Side-by-side **ECO / COOL MODE**, **BALANCED BOOST**, and **MAX SAFE OC** cards with hover glow borders and **APPLIED** / **ACTIVATE** pill buttons.
  - **Sleek Bottom Status Bar**: Live **Auto Thermal Guard (`82°C` cutoff)** indicator + bold **RESET TO STOCK** button.

## Building from Source

```powershell
pip install -r requirements.txt
python generate_icons.py
python -m PyInstaller --noconfirm --clean --onefile --noconsole --collect-all customtkinter --icon=hp_icon.ico --add-data "hp_icon.ico;." --name BANKO_HP_Tuner hp_tuner.py
python -m PyInstaller --noconfirm --clean --onefile --noconsole --collect-all customtkinter --icon=dell_icon.ico --add-data "dell_icon.ico;." --name BANKO_Dell_Tuner dell_tuner.py
```

---

## Author & Related Projects by Yassin Haitham (`hankobanko391`)

- **Author:** **Yassin Haitham** ([@hankobanko391](https://github.com/hankobanko391))
- **Portfolio Hub:** https://hankobanko391.github.io/
- **Public Windows Hardware Utilities Ecosystem:**
  - [**HANKO Thermal Suite**](https://github.com/hankobanko391/HANKO-Thermal-Suite) ([Live Site](https://hankobanko391.github.io/HANKO-Thermal-Suite/)) — Industrial Windows hardware telemetry, `powercfg` processor policy engine, and multi-core thermal load verification utility.
  - [**BANKO Performance Monitor**](https://github.com/hankobanko391/BANKO-Performance-Monitor) ([Live Site](https://hankobanko391.github.io/BANKO-Performance-Monitor/)) — Universal Windows 10/11 GPU, CPU, and RAM performance monitor, mini gaming overlay, DWM FPS counter, and one-click Boost System.
  - [**BANKO Safe OC Tuners (BANKO Tuner)**](https://github.com/hankobanko391/BANKO-Safe-OC-Tuners) ([Live Site](https://hankobanko391.github.io/BANKO-Safe-OC-Tuners/)) — Brand-locked HP and Dell laptop GPU & performance tuners with an 82°C automatic thermal cutoff and zero-voltage safety lock.
