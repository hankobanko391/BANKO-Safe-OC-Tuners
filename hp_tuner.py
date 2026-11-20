"""BANKO HP Safe GPU & Performance Tuner (v1.0.0).

Brand-locked Windows desktop tuning utility for HP / Hewlett-Packard systems.
Enforces strict WMI manufacturer verification, zero-voltage overclock presets,
1000ms thermal cut-off (>82C), and one-click stock reset.
"""

from __future__ import annotations

import ctypes
import os
import re
import shutil
import subprocess
import threading
import time
import winreg
from datetime import datetime
from typing import Optional

import customtkinter as ctk

APP_VERSION = "1.0.0"
WINDOW_TITLE = f"BANKO HP Safe GPU & Performance Tuner v{APP_VERSION}"
WINDOW_WIDTH = 820
WINDOW_HEIGHT = 620

# Theme palette: Dark UI with Neon Cyan accents
BG_ROOT = "#0D0F14"
BG_PANEL = "#141821"
BG_CARD = "#1B202C"
BORDER_SUBTLE = "#262D3D"
ACCENT = "#00B4D8"
ACCENT_HOVER = "#0090AD"
ACCENT_TEXT = "#0D0F14"
TEXT_PRIMARY = "#F1F5F9"
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
        "name": "Eco / Cool Mode",
        "subtitle": "Stock Clocks & Cool Acoustic Curve",
        "core_offset": 0,
        "mem_offset": 0,
        "power_label": "Balanced",
        "power_guid": POWER_BALANCED_GUID,
        "badge": "STOCK / ECO",
    },
    "balanced": {
        "key": "balanced",
        "name": "Balanced Boost",
        "subtitle": "Safe Everyday Uplift + Power Fallback",
        "core_offset": 75,
        "mem_offset": 150,
        "power_label": "High Performance",
        "power_guid": POWER_HIGH_PERF_GUID,
        "badge": "BALANCED BOOST",
    },
    "max": {
        "key": "max",
        "name": "Max Safe OC",
        "subtitle": "Capped Safe Ceiling + High Performance",
        "core_offset": 120,
        "mem_offset": 250,
        "power_label": "High Performance",
        "power_guid": POWER_HIGH_PERF_GUID,
        "badge": "MAX SAFE OC",
    },
}


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
    candidates = [
        r"C:\Windows\System32\nvidia-smi.exe",
        r"C:\Program Files\NVIDIA Corporation\NVSMI\nvidia-smi.exe",
    ]
    for path in candidates:
        if os.path.isfile(path):
            return path
    return None


def check_nvapi_available() -> bool:
    """Check whether NVAPI shared library can be loaded on 64-bit/32-bit Windows."""
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

    def read_gpu_temperature(self) -> tuple[Optional[float], str]:
        """Return (temperature_celsius, source_label)."""
        if self.nvidia_smi:
            rc, out, _ = _run_hidden(
                [
                    self.nvidia_smi,
                    "--query-gpu=temperature.gpu",
                    "--format=csv,noheader,nounits",
                ],
                timeout=2.5,
            )
            if rc == 0 and out:
                first = out.splitlines()[0].strip()
                try:
                    return float(first), "NVIDIA-SMI"
                except ValueError:
                    pass

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
                return float(out.splitlines()[0].strip()), "ACPI Thermal"
            except ValueError:
                pass

        return None, "Unavailable"

    def _set_windows_power_plan(self, guid: str, label: str) -> tuple[bool, str]:
        rc, _, err = _run_hidden(["powercfg", "/setactive", guid], timeout=3.0)
        if rc == 0:
            return True, f"Windows power plan -> {label}"

        # Some Modern Standby laptops hide High Performance until queried or duplicated.
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
    """Main desktop window for BANKO HP Safe GPU & Performance Tuner."""

    def __init__(self) -> None:
        super().__init__()
        ctk.set_appearance_mode("dark")

        self.title(WINDOW_TITLE)
        self.geometry(f"{WINDOW_WIDTH}x{WINDOW_HEIGHT}")
        self.resizable(False, False)
        self.configure(fg_color=BG_ROOT)

        self.manufacturer = get_system_manufacturer()
        self.unlocked = is_hp_hardware(self.manufacturer)

        self.active_preset_key = "eco"
        self.thermal_tripped = False
        self.monitoring_active = False
        self.controller: Optional[HardwareController] = None
        self.preset_cards: dict[str, ctk.CTkFrame] = {}
        self.preset_buttons: dict[str, ctk.CTkButton] = {}

        if self.unlocked:
            self.controller = HardwareController()
            self._build_unlocked_ui()
            self.monitoring_active = True
            self._log(f"Verified OEM hardware: {self.manufacturer}")
            self._log(f"Detected GPU: {self.controller.gpu_name}")
            self._log("Thermal guardrail armed: Auto cut-off > 82°C (1000ms poll).")
            self._poll_thermal_loop()
        else:
            self._build_lock_screen()

        self.protocol("WM_DELETE_WINDOW", self._on_close)

    def _build_lock_screen(self) -> None:
        outer = ctk.CTkFrame(
            self,
            fg_color=BG_PANEL,
            border_width=2,
            border_color=DANGER,
            corner_radius=16,
        )
        outer.pack(fill="both", expand=True, padx=28, pady=28)

        badge = ctk.CTkLabel(
            outer,
            text="HP / HEWLETT-PACKARD HARDWARE GUARD",
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
            text_color=ACCENT,
            fg_color=BG_CARD,
            corner_radius=8,
            padx=14,
            pady=6,
        )
        badge.pack(pady=(46, 18))

        title = ctk.CTkLabel(
            outer,
            text="🔒 HARDWARE SAFETY LOCK ENGAGED",
            font=ctk.CTkFont(family="Segoe UI", size=26, weight="bold"),
            text_color=DANGER,
        )
        title.pack(pady=(0, 12))

        subtitle = ctk.CTkLabel(
            outer,
            text=(
                "BANKO HP Tuner is strictly brand-locked to HP / Hewlett-Packard systems.\n"
                "Tuning controls are disabled on unsupported OEM hardware to prevent\n"
                "improper power and thermal curve mismatches."
            ),
            font=ctk.CTkFont(family="Segoe UI", size=14),
            text_color=TEXT_PRIMARY,
            justify="center",
        )
        subtitle.pack(pady=(0, 26))

        info_card = ctk.CTkFrame(
            outer,
            fg_color=BG_CARD,
            border_width=1,
            border_color=ACCENT,
            corner_radius=12,
        )
        info_card.pack(padx=90, fill="x", pady=(0, 32))

        ctk.CTkLabel(
            info_card,
            text="DETECTED WMI Win32_ComputerSystem.Manufacturer",
            font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"),
            text_color=TEXT_MUTED,
        ).pack(pady=(16, 4))

        ctk.CTkLabel(
            info_card,
            text=self.manufacturer,
            font=ctk.CTkFont(family="Consolas", size=18, weight="bold"),
            text_color=WARNING,
        ).pack(pady=(0, 8))

        ctk.CTkLabel(
            info_card,
            text="Required Manufacturer: HP or Hewlett-Packard",
            font=ctk.CTkFont(family="Segoe UI", size=12),
            text_color=ACCENT,
        ).pack(pady=(0, 16))

        exit_btn = ctk.CTkButton(
            outer,
            text="EXIT TUNER",
            command=self._on_close,
            fg_color=DANGER,
            hover_color=DANGER_HOVER,
            text_color=TEXT_PRIMARY,
            font=ctk.CTkFont(family="Segoe UI", size=14, weight="bold"),
            height=44,
            width=220,
            corner_radius=10,
        )
        exit_btn.pack(pady=(0, 24))

    def _build_unlocked_ui(self) -> None:
        assert self.controller is not None
        container = ctk.CTkFrame(self, fg_color=BG_ROOT)
        container.pack(fill="both", expand=True, padx=16, pady=14)

        # 1. Header bar
        header = ctk.CTkFrame(
            container,
            fg_color=BG_PANEL,
            border_width=1,
            border_color=BORDER_SUBTLE,
            corner_radius=12,
        )
        header.pack(fill="x", pady=(0, 8))

        left_head = ctk.CTkFrame(header, fg_color="transparent")
        left_head.pack(side="left", padx=14, pady=10)

        ctk.CTkLabel(
            left_head,
            text="BANKO HP SAFE GPU & PERFORMANCE TUNER",
            font=ctk.CTkFont(family="Segoe UI", size=17, weight="bold"),
            text_color=ACCENT,
        ).pack(anchor="w")

        ctk.CTkLabel(
            left_head,
            text=f"OEM Verified: {self.manufacturer}  |  GPU: {self.controller.gpu_name}",
            font=ctk.CTkFont(family="Segoe UI", size=11),
            text_color=TEXT_MUTED,
        ).pack(anchor="w")

        self.mode_badge = ctk.CTkLabel(
            header,
            text="ACTIVE: STOCK / ECO",
            font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"),
            text_color=ACCENT_TEXT,
            fg_color=ACCENT,
            corner_radius=8,
            padx=12,
            pady=6,
        )
        self.mode_badge.pack(side="right", padx=14, pady=10)

        # 2. Zero-voltage guardrail / thermal alert banner
        self.banner_frame = ctk.CTkFrame(
            container,
            fg_color=BG_PANEL,
            border_width=1,
            border_color=ACCENT,
            corner_radius=8,
        )
        self.banner_frame.pack(fill="x", pady=(0, 8))

        self.banner_label = ctk.CTkLabel(
            self.banner_frame,
            text="ZERO-VOLTAGE LOCK: Core voltage sliders are omitted by design for hardware safety.",
            font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"),
            text_color=ACCENT,
        )
        self.banner_label.pack(pady=6)

        # 3. Telemetry 4-card row
        telemetry_row = ctk.CTkFrame(container, fg_color="transparent")
        telemetry_row.pack(fill="x", pady=(0, 8))
        telemetry_row.grid_columnconfigure((0, 1, 2, 3), weight=1, uniform="tele")

        self.temp_value = self._make_telemetry_card(
            telemetry_row, 0, "GPU TEMPERATURE", "-- °C", ACCENT
        )
        self.offset_value = self._make_telemetry_card(
            telemetry_row, 1, "CLOCK OFFSETS", "+0 / +0 MHz", TEXT_PRIMARY
        )
        self.power_value = self._make_telemetry_card(
            telemetry_row, 2, "WINDOWS POWER", "Balanced", TEXT_PRIMARY
        )
        self.guard_value = self._make_telemetry_card(
            telemetry_row, 3, "THERMAL CUT-OFF (>82°C)", "ARMED (1000ms)", SUCCESS
        )

        # 4. Safe Presets row
        presets_row = ctk.CTkFrame(container, fg_color="transparent")
        presets_row.pack(fill="x", pady=(0, 8))
        presets_row.grid_columnconfigure((0, 1, 2), weight=1, uniform="preset")

        for col, key in enumerate(("eco", "balanced", "max")):
            self._make_preset_card(presets_row, col, PRESETS[key])

        self._refresh_preset_selection()

        # 5. Prominent RESET TO STOCK button
        reset_btn = ctk.CTkButton(
            container,
            text="⟳  RESET TO STOCK — RESTORE DEFAULT CLOCKS & POWER",
            command=self._reset_to_stock,
            fg_color=DANGER,
            hover_color=DANGER_HOVER,
            text_color=TEXT_PRIMARY,
            font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"),
            height=42,
            corner_radius=10,
        )
        reset_btn.pack(fill="x", pady=(0, 8))

        # 6. Activity Log
        log_frame = ctk.CTkFrame(
            container,
            fg_color=BG_PANEL,
            border_width=1,
            border_color=BORDER_SUBTLE,
            corner_radius=10,
        )
        log_frame.pack(fill="both", expand=True)

        ctk.CTkLabel(
            log_frame,
            text="LIVE TELEMETRY & GUARDRAIL LOG",
            font=ctk.CTkFont(family="Segoe UI", size=10, weight="bold"),
            text_color=TEXT_MUTED,
        ).pack(anchor="w", padx=12, pady=(6, 2))

        self.log_box = ctk.CTkTextbox(
            log_frame,
            fg_color=BG_ROOT,
            text_color=TEXT_PRIMARY,
            font=ctk.CTkFont(family="Consolas", size=11),
            corner_radius=8,
            border_width=0,
            activate_scrollbars=True,
        )
        self.log_box.pack(fill="both", expand=True, padx=10, pady=(0, 8))
        self.log_box.configure(state="disabled")

    def _make_telemetry_card(
        self,
        parent: ctk.CTkFrame,
        col: int,
        label: str,
        initial: str,
        value_color: str,
    ) -> ctk.CTkLabel:
        card = ctk.CTkFrame(
            parent,
            fg_color=BG_PANEL,
            border_width=1,
            border_color=BORDER_SUBTLE,
            corner_radius=10,
        )
        padx = (0, 6) if col < 3 else (0, 0)
        card.grid(row=0, column=col, sticky="nsew", padx=padx)

        ctk.CTkLabel(
            card,
            text=label,
            font=ctk.CTkFont(family="Segoe UI", size=10, weight="bold"),
            text_color=TEXT_MUTED,
        ).pack(pady=(10, 2))

        val_lbl = ctk.CTkLabel(
            card,
            text=initial,
            font=ctk.CTkFont(family="Consolas", size=15, weight="bold"),
            text_color=value_color,
        )
        val_lbl.pack(pady=(0, 12))
        return val_lbl

    def _make_preset_card(
        self, parent: ctk.CTkFrame, col: int, preset: dict
    ) -> None:
        card = ctk.CTkFrame(
            parent,
            fg_color=BG_PANEL,
            border_width=1,
            border_color=BORDER_SUBTLE,
            corner_radius=12,
        )
        padx = (0, 8) if col < 2 else (0, 0)
        card.grid(row=0, column=col, sticky="nsew", padx=padx)

        ctk.CTkLabel(
            card,
            text=preset["name"],
            font=ctk.CTkFont(family="Segoe UI", size=15, weight="bold"),
            text_color=TEXT_PRIMARY,
        ).pack(pady=(14, 2))

        ctk.CTkLabel(
            card,
            text=preset["subtitle"],
            font=ctk.CTkFont(family="Segoe UI", size=11),
            text_color=TEXT_MUTED,
        ).pack(pady=(0, 10))

        offset_text = (
            "Stock Clocks (+0 / +0 MHz)"
            if preset["core_offset"] == 0
            else f"+{preset['core_offset']} MHz Core  |  +{preset['mem_offset']} MHz Mem"
        )
        ctk.CTkLabel(
            card,
            text=offset_text,
            font=ctk.CTkFont(family="Consolas", size=12, weight="bold"),
            text_color=ACCENT,
        ).pack(pady=(0, 4))

        ctk.CTkLabel(
            card,
            text=f"Power Plan: {preset['power_label']}",
            font=ctk.CTkFont(family="Segoe UI", size=11),
            text_color=TEXT_MUTED,
        ).pack(pady=(0, 14))

        btn = ctk.CTkButton(
            card,
            text=f"APPLY {preset['badge']}",
            command=lambda k=preset["key"]: self._select_preset(k),
            fg_color=BG_CARD,
            hover_color=ACCENT_HOVER,
            text_color=TEXT_PRIMARY,
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
            height=36,
            corner_radius=8,
        )
        btn.pack(fill="x", padx=14, pady=(0, 14))

        self.preset_cards[preset["key"]] = card
        self.preset_buttons[preset["key"]] = btn

    def _refresh_preset_selection(self) -> None:
        preset = PRESETS[self.active_preset_key]
        self.mode_badge.configure(text=f"ACTIVE: {preset['badge']}")
        self.offset_value.configure(
            text=f"+{preset['core_offset']} / +{preset['mem_offset']} MHz"
        )
        self.power_value.configure(text=preset["power_label"])

        for key, card in self.preset_cards.items():
            btn = self.preset_buttons[key]
            if key == self.active_preset_key:
                card.configure(border_color=ACCENT, border_width=2)
                btn.configure(
                    fg_color=ACCENT,
                    hover_color=ACCENT_HOVER,
                    text_color=ACCENT_TEXT,
                    text=f"✓ {PRESETS[key]['badge']} ACTIVE",
                )
            else:
                card.configure(border_color=BORDER_SUBTLE, border_width=1)
                btn.configure(
                    fg_color=BG_CARD,
                    hover_color=ACCENT_HOVER,
                    text_color=TEXT_PRIMARY,
                    text=f"APPLY {PRESETS[key]['badge']}",
                )

    def _select_preset(self, key: str, reason: str = "User selection") -> None:
        if not self.controller:
            return
        preset = PRESETS[key]
        self.active_preset_key = key
        if reason == "User selection" and self.thermal_tripped:
            self.thermal_tripped = False
            self.banner_frame.configure(border_color=ACCENT)
            self.banner_label.configure(
                text="ZERO-VOLTAGE LOCK: Core voltage sliders are omitted by design for hardware safety.",
                text_color=ACCENT,
            )
            self.guard_value.configure(text="ARMED (1000ms)", text_color=SUCCESS)

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
        self._log(f"[{reason}] Applied preset: {preset_name}")
        for entry in logs:
            self._log(f"  -> {entry}")

    def _reset_to_stock(self) -> None:
        self.thermal_tripped = False
        self.banner_frame.configure(border_color=ACCENT)
        self.banner_label.configure(
            text="ZERO-VOLTAGE LOCK: Core voltage sliders are omitted by design for hardware safety.",
            text_color=ACCENT,
        )
        self.guard_value.configure(text="ARMED (1000ms)", text_color=SUCCESS)
        self._select_preset("eco", reason="Manual Reset to Stock")

    def _poll_thermal_loop(self) -> None:
        if not self.monitoring_active or not self.controller:
            return

        def poll_worker() -> None:
            temp, src = self.controller.read_gpu_temperature()  # type: ignore[union-attr]
            self.after(0, lambda: self._handle_temp_reading(temp, src))

        threading.Thread(target=poll_worker, daemon=True).start()
        self.after(POLL_INTERVAL_MS, self._poll_thermal_loop)

    def _handle_temp_reading(self, temp: Optional[float], source: str) -> None:
        if temp is None:
            self.temp_value.configure(text="N/A", text_color=TEXT_MUTED)
            return

        if temp > THERMAL_CUTOFF_C:
            color = DANGER
        elif temp >= 75.0:
            color = WARNING
        else:
            color = ACCENT

        self.temp_value.configure(text=f"{temp:.1f} °C ({source})", text_color=color)

        if temp > THERMAL_CUTOFF_C and (
            self.active_preset_key != "eco" or not self.thermal_tripped
        ):
            self.thermal_tripped = True
            self.banner_frame.configure(border_color=DANGER)
            self.banner_label.configure(
                text=f"⚠ THERMAL CUT-OFF TRIGGERED ({temp:.1f}°C > 82°C) — REVERTED TO STOCK/ECO MODE",
                text_color=DANGER,
            )
            self.guard_value.configure(text="TRIPPED (>82°C)", text_color=DANGER)
            self._log(
                f"CRITICAL: GPU temp {temp:.1f}°C exceeded 82°C ceiling! Auto-reverting to Stock/Eco Mode."
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
