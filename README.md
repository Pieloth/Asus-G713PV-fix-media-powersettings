# Asus Modern Standby Fix (`fix_media_powersettings`)

Automated background utility to fix Modern Standby (S0 Low Power Idle) system freezes and crashes on Asus laptops caused by audio driver power management subkeys.

---

## 🚨 The Problem

On several Asus laptops (such as the ROG Strix G713PV series and related models), an ACPI/BIOS implementation bug causes system freezes, black screens, or hard crashes during Modern Standby (S0) sleep transitions.

This instability is triggered by `PowerSettings` subkeys created in the Windows Registry by high-definition audio drivers. Even if deleted manually, Windows or driver updates periodically restore these keys, causing sleep crashes to return.

## 💡 The Solution

`fix_media_powersettings` is an autonomous, lightweight tool that:
1. **Scans** `HKLM\SYSTEM\CurrentControlSet\Control\Class` for affected audio drivers.
2. **Deletes** the problematic `PowerSettings` registry subkeys.
3. **Registers Windows Scheduled Tasks** (running under `SYSTEM`) to automatically maintain a clean state in the background without user intervention.

---

## ✨ Key Features

- **100% Autonomous:** Automatically cleans registry keys as soon as Windows or GPU/Audio installers recreate them.
- **Smart Event-Driven Triggers:**
  - **System Boot:** Ensures a clean state on startup.
  - **Kernel-PnP (Event 410):** Triggers instantly when a driver INF file is bound or updated.
  - **System Wake (Event 1):** Post-wake cleanup safeguard before the next standby transition.
  - **Application Wake (Event 1002):** In case of a Winlogon.exe application crash, restart nVidia services
- **Idempotent & Fast:** Safe to run repeatedly. Checks complete in milliseconds with zero persistent RAM/CPU usage.
- **Self-Elevating:** Automatically requests Administrator UAC elevation when launched manually.
- **Self-Rotating Logs:** Keeps an execution history (`.log` / `.bak`) capped at 512 KB.
- **Self-Update Location:** Automatically updates its path if moved to another folder.

---

## 🚀 Quick Start

### Option 1: Executable (`.exe`)
1. Download the latest `fix_media_powersettings.exe` from the [Releases](../../releases) page and place it in some folder.
2. Right-click and **Run as Administrator** (or accept the UAC prompt).
3. The script applies the fix immediately and configures the automated Task Scheduler entries. 

> [!NOTE]
> The Task Scheduler entry updates the .exe location automatically. Just rerun the .exe if moved to another folder.

### Option 2: Python Script (`.py`) - For interactive test usage
**Requirements:** Python 3.8+ and `pywin32`.

```bash
pip install pywin32
python fix_media_powersettings.py /v
```

> [!NOTE]
> The optional `/v` flag opens a native Windows summary popup upon execution.\
> Task created in Task Scheduler will point to .exe file, not .py

**Compile and build:** .py to .exe

```bash
pyinstaller --onefile fix_media_powersettings.py
```

---

## ⚙️ Target Drivers & Registry Paths

The script inspects driver subkeys located under:
`HKLM\SYSTEM\CurrentControlSet\Control\Class\{4d36e96c-e325-11ce-bfc1-08002be10318}\<DeviceID>\PowerSettings`

**Targeted Audio Drivers (Case-Insensitive):**
- `nVidia High Definition Audio`
- `AMD Streaming Audio Device`
- `Realtek High Definition Audio`

---

## ⚠️ Disclaimer

This tool modifies specific driver power management registry keys to prevent hardware freezes. Tested and verified on Asus ROG hardware. Use at your own risk.

---
