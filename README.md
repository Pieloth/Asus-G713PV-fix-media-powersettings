# Asus Modern Standby Fix (`fix_media_powersettings`)

Automated background utility to fix Modern Standby (S0 Low Power Idle) system freezes, black screens, and crashes on Asus laptops caused by audio driver power management settings, GPU TDR timeout limits, and Winlogon process instability.

[![Watch a one-minute video tour of asus-g713pv-fix-media-powersettings](https://gitdiagram.com/video-badge.svg)](https://gitdiagram.com/pieloth/asus-g713pv-fix-media-powersettings/video)

---

## 🚨 The Problem

On several Asus laptops (such as the ROG Strix G713PV series and related models), an ACPI/BIOS implementation bug causes system freezes, black screens, or hard crashes during Modern Standby (S0) sleep transitions.

This instability is triggered by default `PowerSettings` subkeys created in the Windows Registry by high-definition audio drivers (or internal driver fallback defaults when those keys are absent), leading to ACPI driver state mismatches. Additionally:
- Strict default GPU TDR (Timeout Detection and Recovery) delays trigger display driver resets during power state shifts.
- Intermittent `winlogon.exe` / `userinit.exe` application crashes cause black screens upon logon or sleep exit.
- Background services like `GameInputRedistService` or inadequate hibernation file sizing (`hiberfile.sys`) contribute to sleep resume freezes.

## 💡 The Solution

`fix_media_powersettings` is an autonomous, lightweight tool that:
1. **Scans** `HKLM\SYSTEM\CurrentControlSet\Control\Class` for target audio drivers and enforces optimal `REG_BINARY` values for `ConservationIdleTime`, `IdlePowerState`, and `PerformanceIdleTime`.
2. **Configures** `TdrDelay` and `TdrDdiDelay` under `HKLM\SYSTEM\CurrentControlSet\Control\GraphicsDrivers` to prevent false-positive GPU timeouts during standby state shifts.
3. **Hardens Winlogon & WER Diagnostics** by setting `UserenvDebugLevel` (DWORD `0x30002`) and configuring WER `LocalDumps` for `winlogon.exe` (`DumpCount = 5`, `DumpType = 2`).
4. **Mitigates Background Interference** by disabling `GameInputRedistService` and tuning hibernation file size to `70%` (`full` type via `powercfg`).
5. **Registers Windows Scheduled Tasks** (running under `SYSTEM`) to automatically maintain these optimal settings in the background and recover NVIDIA services upon Winlogon crashes.

---

## ✨ Key Features

- **Optimal Registry Values:** Overrides problematic audio driver defaults with stable binary idle timeouts instead of deleting keys, ensuring compatibility with modern driver releases (e.g., NVIDIA HD Audio 1.4.6.3+).
- **GPU TDR Hardening:** Automatically creates and enforces `TdrDelay = 8` and `TdrDdiDelay = 8` (DWORD) to prevent display driver timeouts during power state transitions.
- **Winlogon Crash Mitigation & WER Dumps:** Enables verbose `Userenv` debug logs and sets up Windows Error Reporting crash dumps for `winlogon.exe`.
- **GameInput Service Neutralization:** Automatically disables and stops `GameInputRedistService` via system commands.
- **Hibernation Sizing:** Adjusts `hiberfile.sys` to `70%` of RAM size (`powercfg /h /type full` & `/size 70`) to prevent memory constraint freezes on resume.
- **100% Autonomous:** Automatically restores optimal registry values whenever Windows Update or installer scripts reset them.
- **Smart Event-Driven Triggers:**
  - **System Boot:** Ensures a clean state on startup.
  - **Kernel-PnP (Event 410):** Triggers instantly when a driver INF file is bound or updated.
  - **System Wake (Event 1):** Post-wake cleanup safeguard before the next standby transition.
  - **Application Winlogon (Event 1002):** Automatically restarts NVIDIA container services with an extended 10-second delay in case of a `winlogon.exe` crash.
- **Robust Task Execution:** Task 1 always targets the executable (`.exe`) file path (even when initialized via `.py`), avoiding file-association issues under the `SYSTEM` account.
- **Self-Rotating Logs:** Keeps execution logs (`.log` / `.bak` and `gpsvc.log`) capped at 512 KB.
- **Self-Elevating:** Requests Administrator UAC elevation automatically.

---

## 🚀 Quick Start

### Option 1: Executable (`.exe`)
1. Download the latest `fix_media_powersettings.exe` from the [Releases](../../releases) page and place it in a permanent folder.
2. Right-click and **Run as Administrator** (or accept the UAC prompt).
3. The utility applies the registry and system fixes immediately and configures the automated Task Scheduler entries. 

> [!NOTE]
> A system reboot is recommended after the initial run for `powercfg` hibernation changes to take full effect.

### Option 2: Python Script (`.py`) - Interactive & Development Usage
**Requirements:** Python 3.8+ and `pywin32`.

```bash
pip install pywin32
python fix_media_powersettings.py /v
```

> [!NOTE]
> - The optional `/v` flag opens a native Windows summary popup upon execution.
> - Tasks created in Task Scheduler will explicitly point to the `.exe` binary path located in the same directory.

**Compile to Standalone Binary (`.exe`):**

```bash
pyinstaller --onefile fix_media_powersettings.py
```

---

## ⚙️ Registry & System Configurations Applied

### 1. Media Audio PowerSettings
Target path: `HKLM\SYSTEM\CurrentControlSet\Control\Class\{4d36e96c-e325-11ce-bfc1-08002be10318}\<DeviceID>\PowerSettings`

**Targeted Audio Drivers (Case-Insensitive):**
- `nVidia High Definition Audio`
- `AMD Streaming Audio Device`
- `Realtek High Definition Audio`

**Applied Binary Values (`REG_BINARY`):**
- `ConservationIdleTime`: `3C 00 00 00` (60 seconds idle time)
- `IdlePowerState`: `03 00 00 00` (D3 Power State)
- `PerformanceIdleTime`: `00 50 00 00` (~5h45 idle timeout on AC)

### 2. GraphicsDrivers TDR Delays
Target path: `HKLM\SYSTEM\CurrentControlSet\Control\GraphicsDrivers`

**Applied DWORD Values (`REG_DWORD`):**
- `TdrDelay`: `8`
- `TdrDdiDelay`: `8`

### 3. Winlogon Debugging & WER LocalDumps
- `HKLM\SOFTWARE\Microsoft\Windows NT\CurrentVersion\Winlogon`:
  - Subkey `GPExtensions` (created if absent)
  - `UserenvDebugLevel`: `0x00030002` (`REG_DWORD`)
- `HKLM\SOFTWARE\Microsoft\Windows\Windows Error Reporting\LocalDumps\winlogon.exe`:
  - `DumpCount`: `5` (`REG_DWORD`)
  - `DumpType`: `2` (`REG_DWORD`)

### 4. System Services & Power Settings
- `GameInputRedistService`: Configured to `disabled` and stopped.
- Hibernation File (`hiberfile.sys`): Set to `full` type and `70%` RAM size via `powercfg`.

---

## ⚠️ Disclaimer

This tool modifies specific driver power management, graphics recovery, and system service configurations to prevent hardware freezes. Tested and verified on Asus ROG hardware. Use at your own risk.

---

## 🎉 Happy Modern Standby 😊

<img width="640" height="360" alt="ezgif-608d3a39ba95bd6d" src="https://github.com/user-attachments/assets/aef21ee0-cdff-4318-8f4d-a6ea4dc3d287" />
