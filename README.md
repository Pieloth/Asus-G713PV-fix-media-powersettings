# Asus Modern Standby Fix (`fix_media_powersettings`)

Automated background utility to fix Modern Standby (S0 Low Power Idle) system freezes, black screens, and crashes on Asus laptops caused by audio driver power management settings and GPU TDR timeout limits.

---

## 🚨 The Problem

On several Asus laptops (such as the ROG Strix G713PV series and related models), an ACPI/BIOS implementation bug causes system freezes, black screens, or hard crashes during Modern Standby (S0) sleep transitions.

This instability is triggered by default `PowerSettings` subkeys created in the Windows Registry by high-definition audio drivers (or internal driver fallback defaults when those keys are absent), leading to ACPI driver state mismatches. Additionally, strict default GPU TDR (Timeout Detection and Recovery) delays can trigger display driver resets during power state transitions.

## 💡 The Solution

`fix_media_powersettings` is an autonomous, lightweight tool that:
1. **Scans** `HKLM\SYSTEM\CurrentControlSet\Control\Class` for target audio drivers and configures optimal `REG_BINARY` values for `ConservationIdleTime`, `IdlePowerState`, and `PerformanceIdleTime`.
2. **Configures** `TdrDelay` and `TdrDdiDelay` under `HKLM\SYSTEM\CurrentControlSet\Control\GraphicsDrivers` to prevent false-positive GPU timeouts during standby state shifts.
3. **Registers Windows Scheduled Tasks** (running under `SYSTEM`) to automatically maintain these optimal settings in the background without user intervention.

---

## ✨ Key Features

- **Optimal Registry Values:** Overrides problematic driver defaults with stable binary idle timeouts instead of deleting keys, ensuring compatibility with the latest driver releases (e.g., NVIDIA HD Audio 1.4.5.7+ or 1.4.6.3+).
- **GPU TDR Hardening:** Automatically creates and enforces `TdrDelay = 8` and `TdrDdiDelay = 8` (DWORD) to prevent display driver timeouts during power state transitions.
- **100% Autonomous:** Automatically restores optimal registry values as soon as Windows Update or GPU/Audio installers reset them.
- **Smart Event-Driven Triggers:**
  - **System Boot:** Ensures a clean state on startup.
  - **Kernel-PnP (Event 410):** Triggers instantly when a driver INF file is bound or updated.
  - **System Wake (Event 1):** Post-wake cleanup safeguard before the next standby transition.
  - **Application Winlogon (Event 1002):** Automatically restarts NVIDIA services in case of a `winlogon.exe` application crash.
- **Robust Task Execution:** Task 1 always targets the executable (`.exe`) file path (even when initialized via `.py`), avoiding file-association issues under the `SYSTEM` account.
- **Idempotent & Fast:** Safe to run repeatedly. Checks complete in milliseconds with zero persistent RAM/CPU usage.
- **Self-Elevating:** Automatically requests Administrator UAC elevation when launched manually.
- **Self-Rotating Logs:** Keeps an execution history (`.log` / `.bak`) capped at 512 KB.
- **Self-Update Location:** Automatically updates task paths if moved to another directory.

---

## 🚀 Quick Start

### Option 1: Executable (`.exe`)
1. Download the latest `fix_media_powersettings.exe` from the Releases page and place it in a permanent folder.
2. Right-click and **Run as Administrator** (or accept the UAC prompt).
3. The utility applies the registry fixes immediately and configures the automated Task Scheduler entries. 

> [!NOTE]
> The Task Scheduler entry updates the `.exe` location automatically if you move the file. Just rerun the executable from the new path.

### Option 2: Python Script (`.py`) - Interactive & Development Usage
Requirements: Python 3.8+ and `pywin32`.

`pip install pywin32` \
`python fix_media_powersettings.py /v`

> [!NOTE]
> - The optional `/v` flag opens a native Windows summary popup upon execution.\
> - Tasks created in Task Scheduler will explicitly point to the `.exe` binary path located in the same directory to ensure execution under the `SYSTEM` account.

Compile to Standalone Binary (`.exe`):

`pyinstaller --onefile fix_media_powersettings.py`

---

## ⚙️ Registry Configurations Applied

### 1. Media Audio PowerSettings
Target path: `HKLM\SYSTEM\CurrentControlSet\Control\Class\{4d36e96c-e325-11ce-bfc1-08002be10318}\<DeviceID>\PowerSettings`

Targeted Audio Drivers (Case-Insensitive):
- `nVidia High Definition Audio`
- `AMD Streaming Audio Device`
- `Realtek High Definition Audio`

Applied Binary Values (`REG_BINARY`):
- `ConservationIdleTime`: `3C 00 00 00` (60 seconds idle time)
- `IdlePowerState`: `03 00 00 00` (D3 Power State)
- `PerformanceIdleTime`: `00 40 00 00` (Several hours on AC power)

### 2. GraphicsDrivers TDR Delays
Target path: `HKLM\SYSTEM\CurrentControlSet\Control\GraphicsDrivers`

Applied DWORD Values (`REG_DWORD`):
- `TdrDelay`: `8` (Timeout delay in seconds before TDR triggers)
- `TdrDdiDelay`: `8` (Timeout delay for OS thread execution)

---

## ⚠️ Disclaimer

This tool modifies specific driver power management and graphics recovery registry keys to prevent hardware freezes. Tested and verified on Asus ROG hardware. Use at your own risk.
