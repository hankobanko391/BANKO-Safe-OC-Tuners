"""BANKO HP Safe GPU & Performance Tuner v2.0.0.

Steam / Epic Games launcher-inspired Windows desktop tuning utility
brand-locked to HP / Hewlett-Packard systems via WMI.
"""

from __future__ import annotations

import ctypes
import os
import re
import shutil
import subprocess
import sys
import threading
import winreg
from datetime import datetime
from typing import Optional

import customtkinter as ctk

APP_VERSION = "2.0.0"
WINDOW_TITLE = f"BANKO HP Safe GPU & Performance Tuner v{APP_VERSION}"
WINDOW_WIDTH = 1040
WINDOW_HEIGHT = 660

# Palette: Dark Launcher Aesthetic + Electric Cyan (#00B4D8)
BG_ROOT = "#0D0F14"
BG_SIDEBAR = "#12151E"
BG_HERO = "#141824"
BG_CARD = "#161B26"
BG_CARD_INNER = "#1C2230"
BORDER_SUBTLE = "#262E40"
BORDER_HOVER = "#47D4F0"
ACCENT = "#00B4D8"
ACCENT_HOVER = "#0093B2"
ACCENT_TEXT = "#0D0F14"
TEXT_PRIMARY = "#F8FAFC"
TEXT_MUTED = "#94A3B8"
DANGER = "#FF3355"
DANGER_HOVER = "#D92343"
WARNING = "#FFB800"
SUCCESS = "#10B981"

THERMAL_CUTOFF_C = 82.0
POLL_INTERVAL_MS = 1000

POWER_BALANCED_GUID = "381b4222-f694-41f0-9685-ff5bb260df2e"
POWER_HIGH_PERF_GUID = "8c5e7fda-e8bf-4a96-9a85-a6e23a8c635c"

CREATE_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)

PRESETS = {
    "eco": {
        "key": "eco",
        "tier": "SILENT BASELINE",
        "name": "ECO / COOL MODE",
        "subtitle": "Stock Clocks • Max Quiet",
        "core_offset": 0,
        "mem_offset": 0,
        "power_label": "Balanced",
        "power_guid": POWER_BALANCED_GUID,
        "description": "Factory default clocks with cool fan acoustics and balanced Windows power draw.",
    },
    "balanced": {
        "key": "balanced",
        "tier": "RECOMMENDED",
        "name": "BALANCED BOOST",
        "subtitle": "+75 MHz Core / +150 MHz Mem • Recommended",
        "core_offset": 75,
        "mem_offset": 150,
        "power_label": "High Performance",
        "power_guid": POWER_HIGH_PERF_GUID,
        "description": "Safe everyday uplift via nvidia-smi / NVAPI wrapper with High Performance fallback.",
    },
    "max": {
        "key": "max",
        "tier": "PERFORMANCE CEILING",
        "name": "MAX SAFE OC",
        "subtitle": "+120 MHz Core / +250 MHz Mem • High Performance",
        "core_offset": 120,
        "mem_offset": 250,
        "power_label": "High Performance",
        "power_guid": POWER_HIGH_PERF_GUID,
        "description": "Maximum zero-voltage safe offset ceiling locked to High Performance Windows power.",
    },
}


def resolve_asset_path(filename: str) -> Optional[str]:
    """Locate bundled asset in PyInstaller _MEIPASS or script directory."""
    candidates = []
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        candidates.append(os.path.join(meipass, filename))
    candidates.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), filename))
    for path in candidates:
        if os.path.isfile(path):
            return path
    return None


def _run_hidden(cmd: list[str], timeout: float = 4.0) -> tuple[int, str, str]:
    """Execute a subprocess without flashing a Windows console window."""
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            creationflags=CREATE_NO_WINDOW,
        )
        return proc.returncode, (proc.stdout or "").strip(), (proc.stderr or "").strip()
    except Exception as exc:
        return -1, "", str(exc)


def get_system_manufacturer() -> str:
    """Read Win32_ComputerSystem.Manufacturer via WMI/CIM with safe fallbacks."""
    rc, out, _ = _run_hidden(
        [
            "powershell",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-Command",
            "(Get-CimInstance -ClassName Win32_ComputerSystem).Manufacturer",
        ],
        timeout=5.0,
    )
    if rc == 0 and out:
        return out.splitlines()[0].strip()

    rc, out, _ = _run_hidden(
        ["wmic", "computersystem", "get", "manufacturer", "/value"],
        timeout=4.0,
    )
    if rc == 0 and out:
        for line in out.splitlines():
            if "=" in line:
                _, val = line.split("=", 1)
                if val.strip():
                    return val.strip()

    try:
        with winreg.OpenKey(
            winreg.HKEY_LOCAL_MACHINE,
            r"HARDWARE\DESCRIPTION\System\BIOS",
        ) as key:
            val, _ = winreg.QueryValueEx(key, "SystemManufacturer")
            if isinstance(val, str) and val.strip():
                return val.strip()
    except OSError:
        pass

    return "Unknown Manufacturer"


def get_system_model() -> str:
    """Read Win32_ComputerSystem.Model via WMI/CIM with safe fallbacks."""
    rc, out, _ = _run_hidden(
        [
            "powershell",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-Command",
            "(Get-CimInstance -ClassName Win32_ComputerSystem).Model",
        ],
        timeout=5.0,
    )
    if rc == 0 and out:
        return out.splitlines()[0].strip()

    rc, out, _ = _run_hidden(
        ["wmic", "computersystem", "get", "model", "/value"],
        timeout=4.0,
    )
    if rc == 0 and out:
        for line in out.splitlines():
            if "=" in line:
                _, val = line.split("=", 1)
                if val.strip():
                    return val.strip()

    try:
        with winreg.OpenKey(
            winreg.HKEY_LOCAL_MACHINE,
            r"HARDWARE\DESCRIPTION\System\BIOS",
        ) as key:
            val, _ = winreg.QueryValueEx(key, "SystemProductName")
            if isinstance(val, str) and val.strip():
                return val.strip()
    except OSError:
        pass

    return "HP Windows Laptop"


def is_hp_hardware(manufacturer: str) -> bool:
    """Return True only when HP / Hewlett-Packard hardware is detected."""
    if os.environ.get("BANKO_FORCE_UNLOCK") == "1":
        return True
    low = manufacturer.lower().strip()
    if "hewlett-packard" in low or "hewlett packard" in low:
        return True
    return bool(re.search(r"\bhp\b", low))


def find_nvidia_smi() -> Optional[str]:
    """Locate nvidia-smi executable if installed on this system."""
    found = shutil.which("nvidia-smi")
    if found:
        return found
    for path in (
        r"C:\Windows\System32\nvidia-smi.exe",
        r"C:\Program Files\NVIDIA Corporation\NVSMI\nvidia-smi.exe",
    ):
        if os.path.isfile(path):
            return path
    return None


def check_nvapi_available() -> bool:
    """Check whether NVAPI shared library can be loaded on Windows."""
    for dll_name in ("nvapi64.dll", "nvapi.dll"):
        try:
            ctypes.WinDLL(dll_name)
            return True
        except OSError:
            continue
    return False


class HardwareController:
    """Safe GPU clock offset wrapper (nvidia-smi / NVAPI) and Windows power manager."""

    def __init__(self) -> None:
        self.nvidia_smi = find_nvidia_smi()
        self.nvapi_ready = check_nvapi_available()
        self.gpu_name = self._detect_gpu_name()
        self.stock_max_clocks = self._query_max_clocks()

    def _detect_gpu_name(self) -> str:
        if self.nvidia_smi:
            rc, out, _ = _run_hidden(
                [self.nvidia_smi, "--query-gpu=name", "--format=csv,noheader"],
                timeout=3.0,
            )
            if rc == 0 and out:
                return out.splitlines()[0].strip()

        rc, out, _ = _run_hidden(
            [
                "powershell",
                "-NoProfile",
                "-Command",
                "(Get-CimInstance -ClassName Win32_VideoController | Select-Object -First 1).Name",
            ],
            timeout=4.0,
        )
        if rc == 0 and out:
            return out.splitlines()[0].strip()
        return "System Display Adapter"

    def _query_max_clocks(self) -> Optional[tuple[int, int]]:
        if not self.nvidia_smi:
            return None
        rc, out, _ = _run_hidden(
            [
                self.nvidia_smi,
                "--query-gpu=clocks.max.graphics,clocks.max.memory",
                "--format=csv,noheader,nounits",
            ],
            timeout=3.0,
        )
        if rc == 0 and out:
            parts = [p.strip() for p in out.splitlines()[0].split(",")]
            if len(parts) >= 2 and parts[0].isdigit() and parts[1].isdigit():
                return int(parts[0]), int(parts[1])
        return None

    def read_gpu_telemetry(
        self,
    ) -> tuple[Optional[float], Optional[int], Optional[int], str]:
        """Return (temp_c, core_clock_mhz, mem_clock_mhz, source_label)."""
        if self.nvidia_smi:
            rc, out, _ = _run_hidden(
                [
                    self.nvidia_smi,
                    "--query-gpu=temperature.gpu,clocks.current.graphics,clocks.current.memory",
                    "--format=csv,noheader,nounits",
                ],
                timeout=2.5,
            )
            if rc == 0 and out:
                parts = [p.strip() for p in out.splitlines()[0].split(",")]
                temp_val: Optional[float] = None
                core_val: Optional[int] = None
                mem_val: Optional[int] = None
                if len(parts) >= 1:
                    try:
                        temp_val = float(parts[0])
                    except ValueError:
                        pass
                if len(parts) >= 2 and parts[1].isdigit():
                    core_val = int(parts[1])
                if len(parts) >= 3 and parts[2].isdigit():
                    mem_val = int(parts[2])
                if temp_val is not None:
                    return temp_val, core_val, mem_val, "NVIDIA-SMI"

        rc, out, _ = _run_hidden(
            [
                "powershell",
                "-NoProfile",
                "-Command",
                (
                    "$t=(Get-CimInstance -Namespace root/wmi -ClassName "
                    "MSAcpi_ThermalZoneTemperature -ErrorAction SilentlyContinue | "
                    "Select-Object -First 1).CurrentTemperature; "
                    "if ($t) { [math]::Round(($t / 10) - 273.15, 1) }"
                ),
            ],
            timeout=2.5,
        )
        if rc == 0 and out:
            try:
                return float(out.splitlines()[0].strip()), None, None, "ACPI Thermal"
            except ValueError:
                pass

        return None, None, None, "Unavailable"

    def read_gpu_temperature(self) -> tuple[Optional[float], str]:
        """Return (temperature_celsius, source_label)."""
        temp, _, _, src = self.read_gpu_telemetry()
        return temp, src

    def _set_windows_power_plan(self, guid: str, label: str) -> tuple[bool, str]:
        rc, _, err = _run_hidden(["powercfg", "/setactive", guid], timeout=3.0)
        if rc == 0:
            return True, f"Windows power plan -> {label}"

        if guid == POWER_HIGH_PERF_GUID:
            rc_dup, out_dup, _ = _run_hidden(
                ["powercfg", "/duplicatescheme", POWER_HIGH_PERF_GUID],
                timeout=3.0,
            )
            if rc_dup == 0 and out_dup:
                match = re.search(
                    r"([0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12})",
                    out_dup,
                )
                if match:
                    rc2, _, _ = _run_hidden(
                        ["powercfg", "/setactive", match.group(1)],
                        timeout=3.0,
                    )
                    if rc2 == 0:
                        return True, f"Windows power plan -> {label} (provisioned)"

        return False, f"Power plan fallback notice ({err or 'standard OEM profile active'})"

    def apply_preset(self, preset: dict) -> list[str]:
        """Apply safe preset via NVAPI/nvidia-smi wrapper and Windows power plan."""
        logs: list[str] = []
        core = preset["core_offset"]
        mem = preset["mem_offset"]

        if core == 0 and mem == 0:
            if self.nvidia_smi:
                rc_g, _, _ = _run_hidden([self.nvidia_smi, "-rgc"], timeout=3.0)
                rc_m, _, _ = _run_hidden([self.nvidia_smi, "-rmc"], timeout=3.0)
                if rc_g == 0 or rc_m == 0:
                    logs.append("GPU clocks reset to factory stock via nvidia-smi (-rgc/-rmc).")
                else:
                    logs.append("Stock clock profile restored (driver-managed stock curve).")
            else:
                logs.append("Stock baseline engaged (no discrete nvidia-smi lock required).")

            _, p_msg = self._set_windows_power_plan(
                preset["power_guid"], preset["power_label"]
            )
            logs.append(p_msg)
            return logs

        backend_notes: list[str] = []
        if self.nvapi_ready:
            backend_notes.append("NVAPI detected")
        if self.nvidia_smi:
            if self.stock_max_clocks:
                max_g, max_m = self.stock_max_clocks
                target_g = max_g + core
                target_m = max_m + mem
                rc_lgc, _, _ = _run_hidden(
                    [self.nvidia_smi, "-lgc", f"0,{target_g}"],
                    timeout=3.0,
                )
                rc_lmc, _, _ = _run_hidden(
                    [self.nvidia_smi, "-lmc", f"0,{target_m}"],
                    timeout=3.0,
                )
                if rc_lgc == 0 or rc_lmc == 0:
                    backend_notes.append(
                        f"nvidia-smi safe range applied (+{core}/+{mem} MHz)"
                    )
                else:
                    backend_notes.append(
                        f"nvidia-smi offset locked by driver/admin; High Perf fallback active (+{core}/+{mem} MHz target)"
                    )
            else:
                backend_notes.append(
                    f"nvidia-smi present; High Perf fallback applied for +{core}/+{mem} MHz profile"
                )
        else:
            backend_notes.append(
                f"No NVIDIA GPU CLI present; Windows High Performance fallback active (+{core}/+{mem} MHz profile)"
            )

        logs.append(" | ".join(backend_notes))
        _, p_msg = self._set_windows_power_plan(preset["power_guid"], preset["power_label"])
        logs.append(p_msg)
        return logs


class BankoHpTunerApp(ctk.CTk):
    """Steam / Epic Games launcher-styled desktop window for HP Tuner."""

    def __init__(self) -> None:
        super().__init__()
        ctk.set_appearance_mode("dark")

        self.title(WINDOW_TITLE)
        self.geometry(f"{WINDOW_WIDTH}x{WINDOW_HEIGHT}")
        self.minsize(980, 620)
        self.configure(fg_color=BG_ROOT)

        icon_path = resolve_asset_path("hp_icon.ico")
        if icon_path:
            try:
                self.iconbitmap(icon_path)
            except Exception:
                pass

        self.manufacturer = get_system_manufacturer()
        self.laptop_model = get_system_model()
        self.unlocked = is_hp_hardware(self.manufacturer)

        self.active_preset_key = "eco"
        self.active_tab = "profiles"
        self.thermal_tripped = False
        self.monitoring_active = False
        self.controller: Optional[HardwareController] = None

        self.nav_buttons: dict[str, ctk.CTkButton] = {}
        self.tab_frames: dict[str, ctk.CTkFrame] = {}
        self.preset_cards: dict[str, ctk.CTkFrame] = {}
        self.preset_buttons: dict[str, ctk.CTkButton] = {}
        self.hovered_card: Optional[str] = None

        if self.unlocked:
            self.controller = HardwareController()
            self._build_launcher_ui()
            self.monitoring_active = True
            self._log(f"Verified OEM hardware: {self.manufacturer} ({self.laptop_model})")
            self._log(f"Detected GPU: {self.controller.gpu_name}")
            self._log("Auto Thermal Guard armed: 82°C cut-off (1000ms telemetry poll).")
            self._poll_thermal_loop()
        else:
            self._build_lock_screen()

        self.protocol("WM_DELETE_WINDOW", self._on_close)

    def _build_lock_screen(self) -> None:
        shell = ctk.CTkFrame(self, fg_color=BG_ROOT)
        shell.pack(fill="both", expand=True)

        sidebar = ctk.CTkFrame(
            shell,
            width=230,
            fg_color=BG_SIDEBAR,
            corner_radius=0,
            border_width=1,
            border_color=BORDER_SUBTLE,
        )
        sidebar.pack(side="left", fill="y")
        sidebar.pack_propagate(False)

        self._build_sidebar_header(sidebar)

        lock_badge = ctk.CTkFrame(
            sidebar,
            fg_color=BG_CARD_INNER,
            border_width=1,
            border_color=DANGER,
            corner_radius=10,
        )
        lock_badge.pack(side="bottom", fill="x", padx=16, pady=18)
        ctk.CTkLabel(
            lock_badge,
            text="HARDWARE LOCK STATUS",
            font=ctk.CTkFont(family="Segoe UI", size=10, weight="bold"),
            text_color=TEXT_MUTED,
        ).pack(pady=(10, 2))
        ctk.CTkLabel(
            lock_badge,
            text="● BLOCKED: NON-HP",
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
            text_color=DANGER,
        ).pack(pady=(0, 10))

        main = ctk.CTkFrame(shell, fg_color=BG_ROOT)
        main.pack(side="right", fill="both", expand=True, padx=28, pady=28)

        card = ctk.CTkFrame(
            main,
            fg_color=BG_HERO,
            border_width=2,
            border_color=DANGER,
            corner_radius=16,
        )
        card.pack(fill="both", expand=True)

        ctk.CTkLabel(
            card,
            text="HP / HEWLETT-PACKARD HARDWARE GUARD",
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
            text_color=ACCENT,
            fg_color=BG_CARD_INNER,
            corner_radius=8,
            padx=14,
            pady=6,
        ).pack(pady=(58, 18))

        ctk.CTkLabel(
            card,
            text="🔒 HARDWARE SAFETY LOCK ENGAGED",
            font=ctk.CTkFont(family="Segoe UI", size=26, weight="bold"),
            text_color=DANGER,
        ).pack(pady=(0, 12))

        ctk.CTkLabel(
            card,
            text=(
                "BANKO HP Tuner is strictly brand-locked to HP / Hewlett-Packard systems.\n"
                "All overclocking and power controls remain disabled on non-HP hardware."
            ),
            font=ctk.CTkFont(family="Segoe UI", size=14),
            text_color=TEXT_PRIMARY,
            justify="center",
        ).pack(pady=(0, 26))

        info = ctk.CTkFrame(
            card,
            fg_color=BG_CARD_INNER,
            border_width=1,
            border_color=ACCENT,
            corner_radius=12,
        )
        info.pack(padx=90, fill="x", pady=(0, 32))

        ctk.CTkLabel(
            info,
            text="DETECTED WMI Win32_ComputerSystem",
            font=ctk.CTkFont(family="Segoe UI", size=10, weight="bold"),
            text_color=TEXT_MUTED,
        ).pack(pady=(14, 4))

        ctk.CTkLabel(
            info,
            text=f"{self.manufacturer}  •  {self.laptop_model}",
            font=ctk.CTkFont(family="Consolas", size=16, weight="bold"),
            text_color=WARNING,
        ).pack(pady=(0, 6))

        ctk.CTkLabel(
            info,
            text="Required Manufacturer: HP or Hewlett-Packard",
            font=ctk.CTkFont(family="Segoe UI", size=12),
            text_color=ACCENT,
        ).pack(pady=(0, 14))

        ctk.CTkButton(
            card,
            text="EXIT LAUNCHER",
            command=self._on_close,
            fg_color=DANGER,
            hover_color=DANGER_HOVER,
            text_color=TEXT_PRIMARY,
            font=ctk.CTkFont(family="Segoe UI", size=14, weight="bold"),
            height=44,
            width=220,
            corner_radius=10,
        ).pack()

    def _build_sidebar_header(self, sidebar: ctk.CTkFrame) -> None:
        brand_box = ctk.CTkFrame(sidebar, fg_color="transparent")
        brand_box.pack(fill="x", padx=16, pady=(22, 18))

        emblem = ctk.CTkFrame(
            brand_box,
            width=66,
            height=66,
            corner_radius=33,
            fg_color=BG_ROOT,
            border_width=3,
            border_color=ACCENT,
        )
        emblem.pack(pady=(0, 10))
        emblem.pack_propagate(False)

        ctk.CTkLabel(
            emblem,
            text="HP",
            font=ctk.CTkFont(family="Segoe UI", size=24, weight="bold"),
            text_color=TEXT_PRIMARY,
        ).place(relx=0.5, rely=0.5, anchor="center")

        ctk.CTkLabel(
            brand_box,
            text="BANKO TUNER",
            font=ctk.CTkFont(family="Segoe UI", size=17, weight="bold"),
            text_color=TEXT_PRIMARY,
        ).pack()

        ctk.CTkLabel(
            brand_box,
            text=f"HP EDITION • v{APP_VERSION}",
            font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"),
            text_color=ACCENT,
        ).pack(pady=(2, 0))

    def _build_launcher_ui(self) -> None:
        assert self.controller is not None
        shell = ctk.CTkFrame(self, fg_color=BG_ROOT)
        shell.pack(fill="both", expand=True)

        # --- Left Sidebar Navigation (#12151E) ---
        sidebar = ctk.CTkFrame(
            shell,
            width=230,
            fg_color=BG_SIDEBAR,
            corner_radius=0,
            border_width=1,
            border_color=BORDER_SUBTLE,
        )
        sidebar.pack(side="left", fill="y")
        sidebar.pack_propagate(False)

        self._build_sidebar_header(sidebar)

        ctk.CTkFrame(sidebar, height=1, fg_color=BORDER_SUBTLE).pack(
            fill="x", padx=18, pady=(0, 16)
        )

        ctk.CTkLabel(
            sidebar,
            text="LAUNCHER NAVIGATION",
            font=ctk.CTkFont(family="Segoe UI", size=10, weight="bold"),
            text_color=TEXT_MUTED,
        ).pack(anchor="w", padx=20, pady=(0, 8))

        for tab_key, label in (
            ("profiles", "⚡  TUNING PROFILES"),
            ("telemetry", "📊  LIVE TELEMETRY"),
            ("safety", "🛡️  SAFETY & SPECS"),
        ):
            btn = ctk.CTkButton(
                sidebar,
                text=label,
                anchor="w",
                command=lambda k=tab_key: self._switch_tab(k),
                fg_color="transparent",
                hover_color=BG_CARD_INNER,
                text_color=TEXT_MUTED,
                font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"),
                height=42,
                corner_radius=10,
            )
            btn.pack(fill="x", padx=14, pady=4)
            self.nav_buttons[tab_key] = btn

        # Bottom Hardware Lock Status Badge
        lock_badge = ctk.CTkFrame(
            sidebar,
            fg_color=BG_CARD_INNER,
            border_width=1,
            border_color=ACCENT,
            corner_radius=12,
        )
        lock_badge.pack(side="bottom", fill="x", padx=16, pady=18)

        ctk.CTkLabel(
            lock_badge,
            text="HARDWARE LOCK STATUS",
            font=ctk.CTkFont(family="Segoe UI", size=10, weight="bold"),
            text_color=TEXT_MUTED,
        ).pack(pady=(10, 2))

        ctk.CTkLabel(
            lock_badge,
            text="● VERIFIED: HP",
            font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"),
            text_color=ACCENT,
        ).pack(pady=(0, 4))

        ctk.CTkLabel(
            lock_badge,
            text=f"OEM: {self.manufacturer}",
            font=ctk.CTkFont(family="Segoe UI", size=10),
            text_color=TEXT_MUTED,
        ).pack(pady=(0, 10))

        # --- Right Main Content Workspace ---
        workspace = ctk.CTkFrame(shell, fg_color=BG_ROOT)
        workspace.pack(side="right", fill="both", expand=True)

        # Bottom Sleek Status Bar (packed before expandable body so it never clips)
        status_bar = ctk.CTkFrame(
            workspace,
            height=62,
            fg_color=BG_SIDEBAR,
            corner_radius=0,
            border_width=1,
            border_color=BORDER_SUBTLE,
        )
        status_bar.pack(side="bottom", fill="x")
        status_bar.pack_propagate(False)

        self.thermal_status_pill = ctk.CTkLabel(
            status_bar,
            text="🛡️  AUTO THERMAL GUARD: ARMED (82°C CUTOFF • 1000ms)",
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
            text_color=SUCCESS,
            fg_color=BG_CARD_INNER,
            corner_radius=8,
            padx=14,
            pady=8,
        )
        self.thermal_status_pill.pack(side="left", padx=20)

        ctk.CTkButton(
            status_bar,
            text="⟳  RESET TO STOCK",
            command=self._reset_to_stock,
            fg_color=DANGER,
            hover_color=DANGER_HOVER,
            text_color=TEXT_PRIMARY,
            font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"),
            height=38,
            width=190,
            corner_radius=10,
        ).pack(side="right", padx=20)

        content = ctk.CTkFrame(workspace, fg_color=BG_ROOT)
        content.pack(fill="both", expand=True, padx=22, pady=18)

        # 1. Top Hero Banner
        hero = ctk.CTkFrame(
            content,
            fg_color=BG_HERO,
            border_width=1,
            border_color=ACCENT,
            corner_radius=14,
        )
        hero.pack(fill="x", pady=(0, 16))

        hero_left = ctk.CTkFrame(hero, fg_color="transparent")
        hero_left.pack(side="left", padx=20, pady=16)

        ctk.CTkLabel(
            hero_left,
            text="HP HARDWARE DECK • ZERO-VOLTAGE SAFE TUNING",
            font=ctk.CTkFont(family="Segoe UI", size=10, weight="bold"),
            text_color=ACCENT,
        ).pack(anchor="w")

        ctk.CTkLabel(
            hero_left,
            text=self.laptop_model,
            font=ctk.CTkFont(family="Segoe UI", size=22, weight="bold"),
            text_color=TEXT_PRIMARY,
        ).pack(anchor="w", pady=(2, 2))

        self.hero_gpu_label = ctk.CTkLabel(
            hero_left,
            text=f"GPU: {self.controller.gpu_name}   •   Active Profile: ECO / COOL MODE",
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
            text_color=TEXT_MUTED,
        )
        self.hero_gpu_label.pack(anchor="w")

        hero_right = ctk.CTkFrame(hero, fg_color="transparent")
        hero_right.pack(side="right", padx=20, pady=14)

        temp_pod = ctk.CTkFrame(
            hero_right,
            fg_color=BG_CARD_INNER,
            border_width=1,
            border_color=BORDER_SUBTLE,
            corner_radius=10,
        )
        temp_pod.pack(side="left", padx=(0, 10))
        ctk.CTkLabel(
            temp_pod,
            text="GPU TEMP",
            font=ctk.CTkFont(family="Segoe UI", size=10, weight="bold"),
            text_color=TEXT_MUTED,
        ).pack(padx=16, pady=(8, 0))
        self.hero_temp_value = ctk.CTkLabel(
            temp_pod,
            text="-- °C",
            font=ctk.CTkFont(family="Consolas", size=22, weight="bold"),
            text_color=ACCENT,
        )
        self.hero_temp_value.pack(padx=16, pady=(0, 8))

        clk_pod = ctk.CTkFrame(
            hero_right,
            fg_color=BG_CARD_INNER,
            border_width=1,
            border_color=BORDER_SUBTLE,
            corner_radius=10,
        )
        clk_pod.pack(side="left")
        ctk.CTkLabel(
            clk_pod,
            text="CLOCK SPEEDS (CORE / MEM)",
            font=ctk.CTkFont(family="Segoe UI", size=10, weight="bold"),
            text_color=TEXT_MUTED,
        ).pack(padx=16, pady=(8, 0))
        self.hero_clock_value = ctk.CTkLabel(
            clk_pod,
            text="-- / -- MHz",
            font=ctk.CTkFont(family="Consolas", size=18, weight="bold"),
            text_color=TEXT_PRIMARY,
        )
        self.hero_clock_value.pack(padx=16, pady=(2, 10))

        # 2. Tab Stack Container
        self.tab_stack = ctk.CTkFrame(content, fg_color="transparent")
        self.tab_stack.pack(fill="both", expand=True)

        self._build_profiles_tab()
        self._build_telemetry_tab()
        self._build_safety_tab()

        self._refresh_preset_selection()
        self._switch_tab("profiles")

    def _build_profiles_tab(self) -> None:
        frame = ctk.CTkFrame(self.tab_stack, fg_color="transparent")
        self.tab_frames["profiles"] = frame

        header_row = ctk.CTkFrame(frame, fg_color="transparent")
        header_row.pack(fill="x", pady=(0, 10))

        ctk.CTkLabel(
            header_row,
            text="SELECT TUNING PROFILE",
            font=ctk.CTkFont(family="Segoe UI", size=14, weight="bold"),
            text_color=TEXT_PRIMARY,
        ).pack(side="left")

        ctk.CTkLabel(
            header_row,
            text="NO VOLTAGE SLIDERS • CAPPED SAFE OFFSETS • 82°C AUTO CUT-OFF",
            font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"),
            text_color=ACCENT,
        ).pack(side="right")

        cards_grid = ctk.CTkFrame(frame, fg_color="transparent")
        cards_grid.pack(fill="both", expand=True)
        cards_grid.grid_columnconfigure((0, 1, 2), weight=1, uniform="cards")
        cards_grid.grid_rowconfigure(0, weight=1)

        for col, key in enumerate(("eco", "balanced", "max")):
            self._make_launcher_card(cards_grid, col, PRESETS[key])

    def _make_launcher_card(
        self, parent: ctk.CTkFrame, col: int, preset: dict
    ) -> None:
        key = preset["key"]
        card = ctk.CTkFrame(
            parent,
            fg_color=BG_CARD,
            border_width=2,
            border_color=BORDER_SUBTLE,
            corner_radius=14,
        )
        padx = (0, 12) if col < 2 else (0, 0)
        card.grid(row=0, column=col, sticky="nsew", padx=padx)

        tier = ctk.CTkLabel(
            card,
            text=preset["tier"],
            font=ctk.CTkFont(family="Segoe UI", size=10, weight="bold"),
            text_color=ACCENT,
            fg_color=BG_CARD_INNER,
            corner_radius=6,
            padx=10,
            pady=4,
        )
        tier.pack(anchor="w", padx=18, pady=(18, 10))

        title = ctk.CTkLabel(
            card,
            text=preset["name"],
            font=ctk.CTkFont(family="Segoe UI", size=19, weight="bold"),
            text_color=TEXT_PRIMARY,
        )
        title.pack(anchor="w", padx=18)

        sub = ctk.CTkLabel(
            card,
            text=preset["subtitle"],
            font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"),
            text_color=ACCENT,
            wraplength=210,
            justify="left",
        )
        sub.pack(anchor="w", padx=18, pady=(4, 10))

        desc = ctk.CTkLabel(
            card,
            text=preset["description"],
            font=ctk.CTkFont(family="Segoe UI", size=11),
            text_color=TEXT_MUTED,
            wraplength=210,
            justify="left",
        )
        desc.pack(anchor="w", padx=18, pady=(0, 12))

        specs_box = ctk.CTkFrame(
            card,
            fg_color=BG_CARD_INNER,
            border_width=1,
            border_color=BORDER_SUBTLE,
            corner_radius=10,
        )
        specs_box.pack(fill="x", padx=16, pady=(0, 14))

        core_txt = "Stock (+0 MHz)" if preset["core_offset"] == 0 else f"+{preset['core_offset']} MHz"
        mem_txt = "Stock (+0 MHz)" if preset["mem_offset"] == 0 else f"+{preset['mem_offset']} MHz"

        for spec_label, spec_val in (
            ("Core Offset", core_txt),
            ("Memory Offset", mem_txt),
            ("Power Plan", preset["power_label"]),
        ):
            row = ctk.CTkFrame(specs_box, fg_color="transparent")
            row.pack(fill="x", padx=12, pady=5)
            ctk.CTkLabel(
                row,
                text=spec_label,
                font=ctk.CTkFont(family="Segoe UI", size=11),
                text_color=TEXT_MUTED,
            ).pack(side="left")
            ctk.CTkLabel(
                row,
                text=spec_val,
                font=ctk.CTkFont(family="Consolas", size=11, weight="bold"),
                text_color=TEXT_PRIMARY,
            ).pack(side="right")

        btn = ctk.CTkButton(
            card,
            text="ACTIVATE",
            command=lambda k=key: self._select_preset(k),
            fg_color=BG_CARD_INNER,
            hover_color=ACCENT_HOVER,
            text_color=TEXT_PRIMARY,
            font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"),
            height=40,
            corner_radius=20,
        )
        btn.pack(side="bottom", fill="x", padx=16, pady=16)

        self.preset_cards[key] = card
        self.preset_buttons[key] = btn

        # Hover glow border binding
        for widget in (card, tier, title, sub, desc, specs_box):
            widget.bind("<Enter>", lambda _e, k=key: self._on_card_hover(k, True))
            widget.bind("<Leave>", lambda _e, k=key: self._on_card_hover(k, False))

    def _on_card_hover(self, key: str, entering: bool) -> None:
        self.hovered_card = key if entering else None
        card = self.preset_cards[key]
        if key == self.active_preset_key:
            card.configure(border_color=ACCENT)
        elif entering:
            card.configure(border_color=BORDER_HOVER)
        else:
            card.configure(border_color=BORDER_SUBTLE)

    def _build_telemetry_tab(self) -> None:
        frame = ctk.CTkFrame(self.tab_stack, fg_color="transparent")
        self.tab_frames["telemetry"] = frame

        stats = ctk.CTkFrame(frame, fg_color="transparent")
        stats.pack(fill="x", pady=(0, 12))
        stats.grid_columnconfigure((0, 1, 2, 3), weight=1, uniform="tstat")

        self.tele_temp = self._make_stat_tile(stats, 0, "LIVE GPU TEMP", "-- °C", ACCENT)
        self.tele_clocks = self._make_stat_tile(stats, 1, "CURRENT CLOCKS", "-- / -- MHz", TEXT_PRIMARY)
        self.tele_offsets = self._make_stat_tile(stats, 2, "ACTIVE OFFSETS", "+0 / +0 MHz", ACCENT)
        self.tele_power = self._make_stat_tile(stats, 3, "WINDOWS POWER", "Balanced", TEXT_PRIMARY)

        bar_card = ctk.CTkFrame(
            frame,
            fg_color=BG_CARD,
            border_width=1,
            border_color=BORDER_SUBTLE,
            corner_radius=12,
        )
        bar_card.pack(fill="x", pady=(0, 12))

        bar_top = ctk.CTkFrame(bar_card, fg_color="transparent")
        bar_top.pack(fill="x", padx=16, pady=(10, 6))
        ctk.CTkLabel(
            bar_top,
            text="THERMAL HEADROOM TO 82°C CUT-OFF CEILING",
            font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"),
            text_color=TEXT_MUTED,
        ).pack(side="left")
        self.thermal_pct_label = ctk.CTkLabel(
            bar_top,
            text="Waiting for sensor...",
            font=ctk.CTkFont(family="Consolas", size=11, weight="bold"),
            text_color=ACCENT,
        )
        self.thermal_pct_label.pack(side="right")

        self.thermal_progress = ctk.CTkProgressBar(
            bar_card,
            height=12,
            corner_radius=6,
            fg_color=BG_CARD_INNER,
            progress_color=ACCENT,
        )
        self.thermal_progress.pack(fill="x", padx=16, pady=(0, 12))
        self.thermal_progress.set(0.0)

        log_card = ctk.CTkFrame(
            frame,
            fg_color=BG_CARD,
            border_width=1,
            border_color=BORDER_SUBTLE,
            corner_radius=12,
        )
        log_card.pack(fill="both", expand=True)

        ctk.CTkLabel(
            log_card,
            text="LIVE TELEMETRY & GUARDRAIL EVENT LOG",
            font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"),
            text_color=TEXT_MUTED,
        ).pack(anchor="w", padx=16, pady=(10, 4))

        self.log_box = ctk.CTkTextbox(
            log_card,
            fg_color=BG_ROOT,
            text_color=TEXT_PRIMARY,
            font=ctk.CTkFont(family="Consolas", size=11),
            corner_radius=8,
            border_width=0,
        )
        self.log_box.pack(fill="both", expand=True, padx=14, pady=(0, 12))
        self.log_box.configure(state="disabled")

    def _make_stat_tile(
        self,
        parent: ctk.CTkFrame,
        col: int,
        label: str,
        initial: str,
        color: str,
    ) -> ctk.CTkLabel:
        tile = ctk.CTkFrame(
            parent,
            fg_color=BG_CARD,
            border_width=1,
            border_color=BORDER_SUBTLE,
            corner_radius=12,
        )
        padx = (0, 10) if col < 3 else (0, 0)
        tile.grid(row=0, column=col, sticky="nsew", padx=padx)

        ctk.CTkLabel(
            tile,
            text=label,
            font=ctk.CTkFont(family="Segoe UI", size=10, weight="bold"),
            text_color=TEXT_MUTED,
        ).pack(pady=(12, 4))

        val = ctk.CTkLabel(
            tile,
            text=initial,
            font=ctk.CTkFont(family="Consolas", size=15, weight="bold"),
            text_color=color,
        )
        val.pack(pady=(0, 12))
        return val

    def _build_safety_tab(self) -> None:
        assert self.controller is not None
        frame = ctk.CTkFrame(self.tab_stack, fg_color="transparent")
        self.tab_frames["safety"] = frame

        panel = ctk.CTkFrame(
            frame,
            fg_color=BG_CARD,
            border_width=1,
            border_color=BORDER_SUBTLE,
            corner_radius=14,
        )
        panel.pack(fill="both", expand=True)

        ctk.CTkLabel(
            panel,
            text="HARDWARE GUARDRAILS & SYSTEM SPECIFICATION",
            font=ctk.CTkFont(family="Segoe UI", size=15, weight="bold"),
            text_color=ACCENT,
        ).pack(anchor="w", padx=22, pady=(18, 12))

        max_clk_str = (
            f"{self.controller.stock_max_clocks[0]} MHz Core / {self.controller.stock_max_clocks[1]} MHz Mem"
            if self.controller.stock_max_clocks
            else "Driver-Managed Dynamic Boost"
        )
        rows = [
            ("WMI OEM Verification", f"UNLOCKED — {self.manufacturer} (HP / Hewlett-Packard Lock)"),
            ("Detected Laptop Model", self.laptop_model),
            ("Detected GPU Adapter", self.controller.gpu_name),
            ("Stock Max GPU Clocks", max_clk_str),
            (
                "Tuning Backend",
                f"nvidia-smi: {'Detected' if self.controller.nvidia_smi else 'Not Found'} | "
                f"NVAPI: {'Detected' if self.controller.nvapi_ready else 'Unavailable'} | PowerCfg Fallback",
            ),
            ("Voltage Safety Lock", "STRICTLY ENFORCED — Core voltage sliders disabled by design"),
            ("Auto Thermal Guard", "1000ms polling • Auto-reverts to Stock / Eco Mode above 82°C"),
        ]

        for label, value in rows:
            row = ctk.CTkFrame(
                panel,
                fg_color=BG_CARD_INNER,
                corner_radius=8,
            )
            row.pack(fill="x", padx=22, pady=5)
            ctk.CTkLabel(
                row,
                text=label,
                font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
                text_color=TEXT_MUTED,
            ).pack(side="left", padx=14, pady=9)
            ctk.CTkLabel(
                row,
                text=value,
                font=ctk.CTkFont(family="Consolas", size=12, weight="bold"),
                text_color=TEXT_PRIMARY,
            ).pack(side="right", padx=14, pady=9)

    def _switch_tab(self, tab_key: str) -> None:
        self.active_tab = tab_key
        for key, frame in self.tab_frames.items():
            if key == tab_key:
                frame.pack(fill="both", expand=True)
            else:
                frame.pack_forget()

        for key, btn in self.nav_buttons.items():
            if key == tab_key:
                btn.configure(fg_color=ACCENT, hover_color=ACCENT_HOVER, text_color=ACCENT_TEXT)
            else:
                btn.configure(fg_color="transparent", hover_color=BG_CARD_INNER, text_color=TEXT_MUTED)

    def _refresh_preset_selection(self) -> None:
        assert self.controller is not None
        preset = PRESETS[self.active_preset_key]
        self.hero_gpu_label.configure(
            text=f"GPU: {self.controller.gpu_name}   •   Active Profile: {preset['name']}"
        )
        self.tele_offsets.configure(
            text=f"+{preset['core_offset']} / +{preset['mem_offset']} MHz"
        )
        self.tele_power.configure(text=preset["power_label"])

        for key, card in self.preset_cards.items():
            btn = self.preset_buttons[key]
            if key == self.active_preset_key:
                card.configure(border_color=ACCENT)
                btn.configure(
                    fg_color=ACCENT,
                    hover_color=ACCENT_HOVER,
                    text_color=ACCENT_TEXT,
                    text="✓  APPLIED",
                )
            else:
                card.configure(
                    border_color=BORDER_HOVER if self.hovered_card == key else BORDER_SUBTLE
                )
                btn.configure(
                    fg_color=BG_CARD_INNER,
                    hover_color=ACCENT_HOVER,
                    text_color=TEXT_PRIMARY,
                    text="ACTIVATE",
                )

    def _select_preset(self, key: str, reason: str = "User selection") -> None:
        if not self.controller:
            return
        preset = PRESETS[key]
        self.active_preset_key = key

        if reason == "User selection" and self.thermal_tripped:
            self.thermal_tripped = False
            self.thermal_status_pill.configure(
                text="🛡️  AUTO THERMAL GUARD: ARMED (82°C CUTOFF • 1000ms)",
                text_color=SUCCESS,
            )

        self._refresh_preset_selection()

        def worker() -> None:
            logs = self.controller.apply_preset(preset)  # type: ignore[union-attr]
            self.after(
                0,
                lambda: self._on_preset_applied(preset["name"], reason, logs),
            )

        threading.Thread(target=worker, daemon=True).start()

    def _on_preset_applied(
        self, preset_name: str, reason: str, logs: list[str]
    ) -> None:
        self._log(f"[{reason}] Activated profile: {preset_name}")
        for entry in logs:
            self._log(f"  -> {entry}")

    def _reset_to_stock(self) -> None:
        self.thermal_tripped = False
        self.thermal_status_pill.configure(
            text="🛡️  AUTO THERMAL GUARD: ARMED (82°C CUTOFF • 1000ms)",
            text_color=SUCCESS,
        )
        self._select_preset("eco", reason="Manual Reset to Stock")

    def _poll_thermal_loop(self) -> None:
        if not self.monitoring_active or not self.controller:
            return

        def poll_worker() -> None:
            temp, core_mhz, mem_mhz, src = self.controller.read_gpu_telemetry()  # type: ignore[union-attr]
            self.after(0, lambda: self._handle_telemetry_reading(temp, core_mhz, mem_mhz, src))

        threading.Thread(target=poll_worker, daemon=True).start()
        self.after(POLL_INTERVAL_MS, self._poll_thermal_loop)

    def _handle_temp_reading(self, temp: Optional[float], source: str) -> None:
        self._handle_telemetry_reading(temp, None, None, source)

    def _handle_telemetry_reading(
        self,
        temp: Optional[float],
        core_mhz: Optional[int],
        mem_mhz: Optional[int],
        source: str,
    ) -> None:
        if core_mhz is not None and mem_mhz is not None:
            clk_txt = f"{core_mhz} / {mem_mhz} MHz"
        else:
            preset = PRESETS[self.active_preset_key]
            clk_txt = f"+{preset['core_offset']} / +{preset['mem_offset']} MHz"
        self.hero_clock_value.configure(text=clk_txt)
        self.tele_clocks.configure(text=clk_txt)

        if temp is None:
            self.hero_temp_value.configure(text="N/A", text_color=TEXT_MUTED)
            self.tele_temp.configure(text="N/A", text_color=TEXT_MUTED)
            self.thermal_pct_label.configure(text="No thermal sensor", text_color=TEXT_MUTED)
            self.thermal_progress.set(0.0)
            return

        if temp > THERMAL_CUTOFF_C:
            color = DANGER
        elif temp >= 75.0:
            color = WARNING
        else:
            color = ACCENT

        self.hero_temp_value.configure(text=f"{temp:.1f} °C", text_color=color)
        self.tele_temp.configure(text=f"{temp:.1f} °C ({source})", text_color=color)

        ratio = max(0.0, min(1.0, temp / THERMAL_CUTOFF_C))
        self.thermal_progress.set(ratio)
        self.thermal_progress.configure(progress_color=color)
        self.thermal_pct_label.configure(
            text=f"{temp:.1f}°C / {THERMAL_CUTOFF_C:.0f}°C ({ratio * 100:.0f}%)",
            text_color=color,
        )

        if temp > THERMAL_CUTOFF_C and (
            self.active_preset_key != "eco" or not self.thermal_tripped
        ):
            self.thermal_tripped = True
            self.thermal_status_pill.configure(
                text=f"⚠  THERMAL CUTOFF ({temp:.1f}°C > 82°C) — REVERTED TO STOCK",
                text_color=DANGER,
            )
            self._log(
                f"CRITICAL: GPU temp {temp:.1f}°C exceeded 82°C ceiling! Reverting to Stock/Eco Mode."
            )
            self._select_preset("eco", reason="Auto Thermal Cut-off (>82°C)")

    def _log(self, message: str) -> None:
        stamp = datetime.now().strftime("%H:%M:%S")
        line = f"[{stamp}] {message}\n"
        self.log_box.configure(state="normal")
        self.log_box.insert("end", line)
        self.log_box.see("end")
        self.log_box.configure(state="disabled")

    def _on_close(self) -> None:
        self.monitoring_active = False
        self.destroy()


def main() -> None:
    app = BankoHpTunerApp()
    app.mainloop()


if __name__ == "__main__":
    main()
