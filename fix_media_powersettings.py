import os
import sys
import ctypes
import argparse
import winreg
from datetime import datetime

# Version Identifier
VERSION = "1.16.0"

# Maximum Log File Size in Bytes (512 KB)
MAX_LOG_SIZE_BYTES = 512 * 1024

# Requires: pip install pywin32
try:
    import win32com.client
except ImportError:
    win32com = None

# Target drivers for PowerSettings adjustment (Case-Insensitive)
TARGET_DRIVERS = [
    "nVidia High Definition Audio",
    "AMD Streaming Audio Device",
    "Realtek High Definition Audio"
]

# PowerSettings Target Binary Values (REG_BINARY - 4 Bytes)
# ConservationIdleTime : 0x3C = 60 seconds
# IdlePowerState        : 0x03 = D3 Power State
# PerformanceIdleTime   : 0x00 = Disabled under AC Power
TARGET_CONSERVATION_IDLE_TIME = b'\x3C\x00\x00\x00'
TARGET_IDLE_POWER_STATE = b'\x03\x00\x00\x00'
TARGET_PERFORMANCE_IDLE_TIME = b'\x00\x00\x00\x00'

# GraphicsDrivers TDR Configuration (REG_DWORD)
GRAPHICS_DRIVERS_KEY_PATH = "SYSTEM\\CurrentControlSet\\Control\\GraphicsDrivers"
TARGET_TDR_DELAY = 8
TARGET_TDR_DDI_DELAY = 8

# Task 1 Configuration (Media PowerSettings & TDR Optimization)
TASK1_NAME = "fix_media_powersettings"
TASK1_DESCRIPTION = (
    "Compiled Python script to adjust Media class PowerSettings subkeys and "
    "configure TDR registry keys to prevent Modern Standby system freezes "
    "due to ACPI BIOS bugs on Asus laptops. "
    "Triggers on boot, Kernel-PnP driver binding (Event 410), and system wake (Event 1)."
)

# Task 2 Configuration (Winlogon Crash / NVIDIA Services Restarter)
TASK2_NAME = "fix_winlogon_crash"
TASK2_DESCRIPTION = "Fix the Winlogon crash with black logon screen issue by restarting nVidia services when it happens"

# Base Registry Path for Media Devices
CLASS_KEY_PATH = "SYSTEM\\CurrentControlSet\\Control\\Class"


class TeeLogger:
    """
    Redirects stdout/stderr to both the terminal console and a log file.
    Rotates the log file into a .bak file if its size exceeds max_bytes.
    """
    def __init__(self, log_path, max_bytes=MAX_LOG_SIZE_BYTES):
        self.terminal = sys.stdout
        self._rotate_log_if_needed(log_path, max_bytes)
        self.log_file = open(log_path, "a", encoding="utf-8")

    def _rotate_log_if_needed(self, log_path, max_bytes):
        """Rotates log file to log_path.bak if it exceeds max_bytes."""
        if os.path.exists(log_path):
            try:
                if os.path.getsize(log_path) >= max_bytes:
                    backup_path = log_path + ".bak"
                    if os.path.exists(backup_path):
                        os.remove(backup_path)
                    os.rename(log_path, backup_path)
            except Exception:
                pass

    def write(self, message):
        self.terminal.write(message)
        self.log_file.write(message)
        self.log_file.flush()

    def flush(self):
        self.terminal.flush()
        self.log_file.flush()


def is_admin():
    """Checks if the script is running with administrator privileges."""
    try:
        return ctypes.windll.shell32.IsUserAnAdmin() != 0
    except:
        return False


def elevate_privileges():
    """
    Relaunches the current script or executable with Administrator privileges (UAC prompt).
    """
    if getattr(sys, 'frozen', False):
        executable = sys.executable
        params = " ".join([f'"{arg}"' for arg in sys.argv[1:]])
    else:
        executable = sys.executable
        script = os.path.abspath(sys.argv[0])
        params = f'"{script}" ' + " ".join([f'"{arg}"' for arg in sys.argv[1:]])

    ret = ctypes.windll.shell32.ShellExecuteW(None, "runas", executable, params, None, 1)
    
    if ret > 32:
        sys.exit(0)
    else:
        print("[!] Elevation request was denied by the user or failed.")
        sys.exit(1)


def show_popup(title, message):
    """Displays a native Windows information popup dialog."""
    ctypes.windll.user32.MessageBoxW(0, message, title, 0x40)


def get_current_executable_path():
    """
    Returns the absolute path to the current running executable/script.
    Handles both standalone compiled .exe (PyInstaller) and standard .py execution.
    """
    if getattr(sys, 'frozen', False):
        return os.path.abspath(sys.executable)
    else:
        return os.path.abspath(sys.argv[0])


def get_target_executable_path():
    """
    Returns the absolute path for Task Scheduler targeting.
    Forces the extension to '.exe' even if executed from a '.py' script.
    """
    current_path = get_current_executable_path()
    base_path, ext = os.path.splitext(current_path)
    if ext.lower() in ['.py', '.pyw']:
        return base_path + ".exe"
    return current_path


def bytes_to_hex_str(data):
    """Converts a bytes object or integer to a formatted hex string (e.g., 3C 00 00 00)."""
    if data is None:
        return "Absent"
    if isinstance(data, int):
        return f"0x{data:08X} (DWORD)"
    return " ".join(f"{b:02X}" for b in data)


def create_or_update_scheduled_task1_com():
    """
    Creates or updates Task 1 (fix_media_powersettings) using pywin32 COM API.
    Always targets the .exe file path to avoid file-association issues under SYSTEM account.
    Configures triggers for Boot, Kernel-PnP Driver Binding (Event 410), and System Wake (Event 1).
    """
    if win32com is None:
        return "Error: 'pywin32' library is not installed (run 'pip install pywin32')."

    target_exe = get_target_executable_path()

    TASK_TRIGGER_EVENT = 0
    TASK_TRIGGER_BOOT = 8
    TASK_ACTION_EXEC = 0
    TASK_CREATE_OR_UPDATE = 6
    TASK_LOGON_SERVICE_ACCOUNT = 5
    TASK_RUNLEVEL_HIGHEST = 1

    EVENT_SUBSCRIPTION_XML = (
        '<QueryList>'
        '  <Query Id="0" Path="Microsoft-Windows-Kernel-PnP/Configuration">'
        '    <Select Path="Microsoft-Windows-Kernel-PnP/Configuration">* [System[EventID=410]]</Select>'
        '  </Query>'
        '  <Query Id="1" Path="System">'
        '    <Select Path="System">*[System[Provider[@Name=\'Microsoft-Windows-Power-Troubleshooter\'] and EventID=1]]</Select>'
        '  </Query>'
        '</QueryList>'
    )

    try:
        scheduler = win32com.client.Dispatch("Schedule.Service")
        scheduler.Connect()
        root_folder = scheduler.GetFolder("\\")

        existing_command = None
        try:
            existing_task = root_folder.GetTask(TASK1_NAME)
            task_def = existing_task.Definition
            for action in task_def.Actions:
                if action.Type == TASK_ACTION_EXEC:
                    existing_command = action.Path
                    break
        except Exception:
            pass

        if existing_command:
            if os.path.normpath(existing_command).lower() == os.path.normpath(target_exe).lower():
                action_status = f"Task exists and points to target executable path ({target_exe})."
            else:
                action_status = f"Updated task path from '{existing_command}' to '{target_exe}'."
        else:
            action_status = f"Task created successfully pointing to '{target_exe}'."

        task_def = scheduler.NewTask(0)
        task_def.RegistrationInfo.Description = TASK1_DESCRIPTION

        settings = task_def.Settings
        settings.Enabled = True
        settings.StartWhenAvailable = False
        settings.DisallowStartIfOnBatteries = False
        settings.StopIfGoingOnBatteries = False
        settings.AllowHardTerminate = True
        settings.ExecutionTimeLimit = "PT72H"
        settings.Priority = 7

        boot_trigger = task_def.Triggers.Create(TASK_TRIGGER_BOOT)
        boot_trigger.Enabled = True

        event_trigger = task_def.Triggers.Create(TASK_TRIGGER_EVENT)
        event_trigger.Enabled = True
        event_trigger.Subscription = EVENT_SUBSCRIPTION_XML

        action = task_def.Actions.Create(TASK_ACTION_EXEC)
        action.Path = target_exe

        principal = task_def.Principal
        principal.UserId = "S-1-5-18"  # Local SYSTEM account
        principal.RunLevel = TASK_RUNLEVEL_HIGHEST

        root_folder.RegisterTaskDefinition(
            TASK1_NAME,
            task_def,
            TASK_CREATE_OR_UPDATE,
            None,
            None,
            TASK_LOGON_SERVICE_ACCOUNT
        )

        return action_status

    except Exception as e:
        return f"Failed to configure task via COM API: {str(e)}"


def create_or_update_scheduled_task2_com():
    """
    Creates or updates Task 2 (fix_winlogon_crash) using pywin32 COM API.
    Triggers on Winlogon crash (Application Event 1002) to restart NVIDIA services.
    """
    if win32com is None:
        return "Error: 'pywin32' library is not installed."

    TASK_TRIGGER_EVENT = 0
    TASK_ACTION_EXEC = 0
    TASK_CREATE_OR_UPDATE = 6
    TASK_LOGON_SERVICE_ACCOUNT = 5
    TASK_RUNLEVEL_HIGHEST = 1

    EVENT_SUBSCRIPTION_XML = (
        '<QueryList>'
        '  <Query Id="0" Path="Application">'
        '    <Select Path="Application">'
        '      *[System[Provider[@Name=\'Microsoft-Windows-Winlogon\'] and EventID=1002]]'
        '    </Select>'
        '  </Query>'
        '</QueryList>'
    )

    CMD_ARGUMENTS = (
        '/c "sc stop NVDisplay.ContainerLocalSystem & '
        'sc stop NvContainerLocalSystem & '
        'timeout /nobreak 5 & '
        'sc start NVDisplay.ContainerLocalSystem & '
        'sc start NvContainerLocalSystem"'
    )

    try:
        scheduler = win32com.client.Dispatch("Schedule.Service")
        scheduler.Connect()
        root_folder = scheduler.GetFolder("\\")

        task_exists = False
        try:
            root_folder.GetTask(TASK2_NAME)
            task_exists = True
        except Exception:
            pass

        task_def = scheduler.NewTask(0)
        task_def.RegistrationInfo.Description = TASK2_DESCRIPTION

        settings = task_def.Settings
        settings.Enabled = True
        settings.StartWhenAvailable = False
        settings.DisallowStartIfOnBatteries = False
        settings.StopIfGoingOnBatteries = False
        settings.AllowHardTerminate = True
        settings.ExecutionTimeLimit = "PT72H"
        settings.Priority = 7

        event_trigger = task_def.Triggers.Create(TASK_TRIGGER_EVENT)
        event_trigger.Enabled = True
        event_trigger.Subscription = EVENT_SUBSCRIPTION_XML

        action = task_def.Actions.Create(TASK_ACTION_EXEC)
        action.Path = "c:\\windows\\system32\\cmd.exe"
        action.Arguments = CMD_ARGUMENTS

        principal = task_def.Principal
        principal.UserId = "S-1-5-18"  # Local SYSTEM account
        principal.RunLevel = TASK_RUNLEVEL_HIGHEST

        root_folder.RegisterTaskDefinition(
            TASK2_NAME,
            task_def,
            TASK_CREATE_OR_UPDATE,
            None,
            None,
            TASK_LOGON_SERVICE_ACCOUNT
        )

        if task_exists:
            return "Task exists and was updated (Winlogon Event 1002 -> NVIDIA services restart)."
        else:
            return "Task created successfully (Winlogon Event 1002 -> NVIDIA services restart)."

    except Exception as e:
        return f"Failed to configure fix_winlogon_crash task: {str(e)}"


def find_all_power_settings_paths():
    r"""
    Iterates through the subkeys of HKLM\SYSTEM\CurrentControlSet\Control\Class.
    Maps matches to the lowercase version of the drivers listed in TARGET_DRIVERS.
    Returns a dictionary of {driver_name: power_settings_registry_path_or_None}.
    """
    results = {driver.lower(): None for driver in TARGET_DRIVERS}
    drivers_to_find = [d.lower() for d in TARGET_DRIVERS]

    try:
        class_key = winreg.OpenKey(
            winreg.HKEY_LOCAL_MACHINE, 
            CLASS_KEY_PATH, 
            0, 
            winreg.KEY_READ | winreg.KEY_WOW64_64KEY
        )
    except OSError as e:
        print(f"[-] Unable to open the Class key: {e}")
        return {}

    i = 0
    while True:
        try:
            sub_key_name = winreg.EnumKey(class_key, i)
            sub_key_path = f"{CLASS_KEY_PATH}\\{sub_key_name}"
            
            sub_key = winreg.OpenKey(
                winreg.HKEY_LOCAL_MACHINE, 
                sub_key_path, 
                0, 
                winreg.KEY_READ | winreg.KEY_WOW64_64KEY
            )
            j = 0
            while True:
                try:
                    driver_index_name = winreg.EnumKey(sub_key, j)
                    driver_path = f"{sub_key_path}\\{driver_index_name}"
                    
                    try:
                        driver_key = winreg.OpenKey(
                            winreg.HKEY_LOCAL_MACHINE, 
                            driver_path, 
                            0, 
                            winreg.KEY_READ | winreg.KEY_WOW64_64KEY
                        )
                        driver_desc, _ = winreg.QueryValueEx(driver_key, "DriverDesc")
                        driver_key.Close()
                        
                        desc_lower = str(driver_desc).lower()
                        if desc_lower in drivers_to_find:
                            power_settings_path = f"{driver_path}\\PowerSettings"
                            try:
                                ps_key = winreg.OpenKey(
                                    winreg.HKEY_LOCAL_MACHINE, 
                                    power_settings_path, 
                                    0, 
                                    winreg.KEY_READ | winreg.KEY_WOW64_64KEY
                                )
                                ps_key.Close()
                                results[desc_lower] = power_settings_path
                            except OSError:
                                pass
                    except OSError:
                        pass
                    j += 1
                except OSError:
                    break
            
            sub_key.Close()
            i += 1
        except OSError:
            break

    class_key.Close()
    return results


def process_power_settings_keys(power_settings_path):
    """
    Checks and updates the 3 PowerSettings registry keys to target REG_BINARY values.
    Returns a list of human-readable changes made.
    """
    keys_to_update = {
        "ConservationIdleTime": TARGET_CONSERVATION_IDLE_TIME,
        "IdlePowerState": TARGET_IDLE_POWER_STATE,
        "PerformanceIdleTime": TARGET_PERFORMANCE_IDLE_TIME
    }
    
    changes_made = []
    
    try:
        reg_key = winreg.OpenKey(
            winreg.HKEY_LOCAL_MACHINE, 
            power_settings_path, 
            0, 
            winreg.KEY_ALL_ACCESS | winreg.KEY_WOW64_64KEY
        )
    except OSError as e:
        msg = f"Failed to open key HKLM\\{power_settings_path}: {e}"
        print(f"[-] {msg}")
        return [msg]

    for key_name, target_value in keys_to_update.items():
        try:
            current_value, value_type = winreg.QueryValueEx(reg_key, key_name)
        except OSError:
            current_value = None
            value_type = winreg.REG_BINARY

        if current_value != target_value or value_type != winreg.REG_BINARY:
            winreg.SetValueEx(reg_key, key_name, 0, winreg.REG_BINARY, target_value)
            
            old_val_str = bytes_to_hex_str(current_value)
            new_val_str = bytes_to_hex_str(target_value)
            
            change_str = f"{key_name}: {old_val_str} -> {new_val_str}"
            changes_made.append(change_str)
            print(f"[+] Updated: {change_str}")
        else:
            print(f"[-] Unchanged: {key_name} is already set to target binary value ({bytes_to_hex_str(target_value)})")

    reg_key.Close()
    return changes_made


def process_tdr_registry_keys():
    """
    Ensures TdrDelay and TdrDdiDelay exist under HKLM\SYSTEM\CurrentControlSet\Control\Class\GraphicsDrivers
    and are configured to at least the target threshold values (REG_DWORD).
    """
    tdr_targets = {
        "TdrDelay": TARGET_TDR_DELAY,
        "TdrDdiDelay": TARGET_TDR_DDI_DELAY
    }
    
    changes_made = []

    try:
        gfx_key = winreg.CreateKeyEx(
            winreg.HKEY_LOCAL_MACHINE,
            GRAPHICS_DRIVERS_KEY_PATH,
            0,
            winreg.KEY_ALL_ACCESS | winreg.KEY_WOW64_64KEY
        )
    except OSError as e:
        msg = f"Failed to open/create GraphicsDrivers key: {e}"
        print(f"[-] {msg}")
        return [msg]

    for key_name, target_val in tdr_targets.items():
        try:
            current_value, value_type = winreg.QueryValueEx(gfx_key, key_name)
        except OSError:
            current_value = None
            value_type = winreg.REG_DWORD

        # Modify if absent, wrong type, or lower than target threshold
        if current_value is None or value_type != winreg.REG_DWORD or current_value < target_val:
            winreg.SetValueEx(gfx_key, key_name, 0, winreg.REG_DWORD, target_val)
            
            old_str = f"{current_value}" if current_value is not None else "Absent"
            change_str = f"{key_name}: {old_str} -> {target_val}"
            changes_made.append(change_str)
            print(f"[+] Updated TDR key: {change_str}")
        else:
            print(f"[-] Unchanged TDR key: {key_name} is already set to {current_value} (>= {target_val})")

    gfx_key.Close()
    return changes_made


def main():
    parser = argparse.ArgumentParser(
        description=f"Configure audio driver PowerSettings and GPU TDR delays to fix Modern Standby freeze issues (v{VERSION}).",
        prefix_chars='/-'
    )
    parser.add_argument('/v', action='store_true', help="Display a summary popup notification after processing.")
    args = parser.parse_args()

    if not is_admin():
        print("[*] Administrator privileges required. Requesting UAC elevation...")
        elevate_privileges()

    current_exe = get_current_executable_path()
    log_path = os.path.splitext(current_exe)[0] + ".log"
    
    try:
        logger = TeeLogger(log_path, max_bytes=MAX_LOG_SIZE_BYTES)
        sys.stdout = logger
        sys.stderr = logger
    except Exception as e:
        print(f"[!] Warning: Could not initialize log file '{log_path}': {e}")

    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print("=" * 60)
    print(f"Execution Date & Time: {now_str}")
    print(f"=== Modern Standby Registry Fixer v{VERSION} ===")
    print(f"[*] Logging output to: {log_path} (Max size: {MAX_LOG_SIZE_BYTES // 1024} KB)")

    popup_messages = []

    # --- PART 1: Task Scheduler Management ---
    print("[*] Checking Windows Task Scheduler configurations via COM API...")
    
    task1_status = create_or_update_scheduled_task1_com()
    print(f"[+] Task 1 ({TASK1_NAME}): {task1_status}")
    popup_messages.append(f"• Task 1 ({TASK1_NAME}):\n  {task1_status}")

    task2_status = create_or_update_scheduled_task2_com()
    print(f"[+] Task 2 ({TASK2_NAME}): {task2_status}")
    popup_messages.append(f"• Task 2 ({TASK2_NAME}):\n  {task2_status}")

    # --- PART 2: Media Audio PowerSettings Processing ---
    print("-" * 60)
    print("[*] Scanning Registry Class configurations for targeted audio drivers...")
    found_paths = find_all_power_settings_paths()

    for driver in TARGET_DRIVERS:
        driver_lower = driver.lower()
        path = found_paths.get(driver_lower)

        print(f"[*] Processing Audio Driver: {driver}")
        
        if not path:
            msg = "PowerSettings key not found in registry."
            print(f"[-] {msg}")
            popup_messages.append(f"• {driver}:\n  {msg}")
        else:
            print(f"[+] Key location: HKLM\\{path}")
            changes = process_power_settings_keys(path)
            if changes:
                msg_details = "\n  ".join(changes)
                popup_messages.append(f"• {driver} (Updated):\n  {msg_details}")
            else:
                popup_messages.append(f"• {driver}:\n  All PowerSettings values are already optimal.")
        print("-" * 60)

    # --- PART 3: GraphicsDrivers TDR Keys Processing ---
    print("[*] Processing GraphicsDrivers TDR registry configuration...")
    tdr_changes = process_tdr_registry_keys()
    if tdr_changes:
        msg_details = "\n  ".join(tdr_changes)
        popup_messages.append(f"• Graphics Drivers TDR (Updated):\n  {msg_details}")
    else:
        popup_messages.append("• Graphics Drivers TDR:\n  TdrDelay and TdrDdiDelay are already optimal.")
    print("-" * 60)

    # --- PART 4: Summary Popup Display ---
    if args.v:
        summary_message = f"Execution Status Report (v{VERSION}):\n\n" + "\n\n".join(popup_messages)
        show_popup(f"Modern Standby Registry Fixer v{VERSION}", summary_message)


if __name__ == "__main__":
    main()