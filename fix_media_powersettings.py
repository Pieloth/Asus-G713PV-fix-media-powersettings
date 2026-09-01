import os
import sys
import ctypes
import argparse
import winreg
from datetime import datetime

# Version Identifier
VERSION = "1.15.0"

# Maximum Log File Size in Bytes (512 KB)
MAX_LOG_SIZE_BYTES = 512 * 1024

# Requires: pip install pywin32
try:
    import win32com.client
except ImportError:
    win32com = None

# Configuration: Add any target drivers to this list (Case-Insensitive)
TARGET_DRIVERS = [
    "nVidia High Definition Audio",
    "AMD Streaming Audio Device",
    "Realtek High Definition Audio"
]

# Task 1 Configuration (Media PowerSettings Cleanup)
TASK1_NAME = "fix_media_powersettings"
TASK1_DESCRIPTION = (
    "Compiled Python script to remove Media class PowerSettings subkeys in "
    "registry for nVidia, AMD, and Realtek drivers, due to ACPI malfunction in "
    "Asus BIOS leading to PC freeze in Modern Standby. "
    "Triggers on boot, Kernel-PnP driver binding (Event 410), and system wake (Event 1)."
)

# Task 2 Configuration (Winlogon Crash / NVIDIA Services Restarter)
TASK2_NAME = "fix_winlogon_crash"
TASK2_DESCRIPTION = "Fix the Winlogon crash with black logon screen issue by restarting nVidia services when it happens"

# Base Search Path (Double backslashes prevent syntax warnings)
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
                # Fallback if rotation fails (e.g. file lock issue)
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
        # Executable compiled (PyInstaller / cx_Freeze)
        executable = sys.executable
        params = " ".join([f'"{arg}"' for arg in sys.argv[1:]])
    else:
        # Standard Python script (.py)
        executable = sys.executable
        script = os.path.abspath(sys.argv[0])
        params = f'"{script}" ' + " ".join([f'"{arg}"' for arg in sys.argv[1:]])

    # 1 = SW_SHOWNORMAL | "runas" triggers the Windows UAC elevation prompt
    ret = ctypes.windll.shell32.ShellExecuteW(None, "runas", executable, params, None, 1)
    
    # HINSTANCE > 32 indicates successful process creation
    if ret > 32:
        sys.exit(0)
    else:
        print("[!] Elevation request was denied by the user or failed.")
        sys.exit(1)

def show_popup(title, message):
    """Displays a native Windows information popup dialog."""
    # 0x40 = MB_OK | MB_ICONINFORMATION
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

def delete_power_settings(power_settings_path):
    """
    Safely deletes the target PowerSettings registry key.
    """
    try:
        parent_path, key_to_delete = power_settings_path.rsplit('\\', 1)
        
        parent_key = winreg.OpenKey(
            winreg.HKEY_LOCAL_MACHINE, 
            parent_path, 
            0, 
            winreg.KEY_WRITE | winreg.KEY_WOW64_64KEY
        )
        
        winreg.DeleteKey(parent_key, key_to_delete)
        parent_key.Close()
        return True
    except OSError as e:
        print(f"[-] Error occurred while deleting the key: {e}")
        return False

def main():
    parser = argparse.ArgumentParser(
        description=f"Disable targeted audio device power restrictions to fix Modern Standby bugs & setup winlogon crash fix (v{VERSION}).",
        prefix_chars='/-'
    )
    parser.add_argument('/v', action='store_true', help="Display a summary popup notification after processing.")
    args = parser.parse_args()

    # Request UAC elevation if not already running as Administrator
    if not is_admin():
        print("[*] Administrator privileges required. Requesting UAC elevation...")
        elevate_privileges()

    # Setup Logging to file (<script_name>.log) and console with size limit
    current_exe = get_current_executable_path()
    log_path = os.path.splitext(current_exe)[0] + ".log"
    
    try:
        logger = TeeLogger(log_path, max_bytes=MAX_LOG_SIZE_BYTES)
        sys.stdout = logger
        sys.stderr = logger
    except Exception as e:
        print(f"[!] Warning: Could not initialize log file '{log_path}': {e}")

    # Display execution timestamp and version banner
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print("=" * 60)
    print(f"Execution Date & Time: {now_str}")
    print(f"=== Modern Standby Registry Fixer v{VERSION} ===")
    print(f"[*] Logging output to: {log_path} (Max size: {MAX_LOG_SIZE_BYTES // 1024} KB)")

    popup_messages = []

    # --- PART 1: Task Scheduler Management (via pywin32 COM) ---
    print("[*] Checking Windows Task Scheduler configurations via COM API...")
    
    # Task 1: fix_media_powersettings
    task1_status = create_or_update_scheduled_task1_com()
    print(f"[+] Task 1 ({TASK1_NAME}): {task1_status}")
    popup_messages.append(f"• Task 1 ({TASK1_NAME}):\n  {task1_status}")

    # Task 2: fix_winlogon_crash
    task2_status = create_or_update_scheduled_task2_com()
    print(f"[+] Task 2 ({TASK2_NAME}): {task2_status}")
    popup_messages.append(f"• Task 2 ({TASK2_NAME}):\n  {task2_status}")

    # --- PART 2: Registry Processing ---
    print("-" * 60)
    print("[*] Scanning Registry Class configurations for matching target drivers...")
    found_paths = find_all_power_settings_paths()

    for driver in TARGET_DRIVERS:
        driver_lower = driver.lower()
        path = found_paths.get(driver_lower)

        print(f"[*] Processing: {driver}")
        
        if not path:
            msg = "No 'PowerSettings' key found (already deleted or absent)."
            print(f"[-] {msg}")
            popup_messages.append(f"• {driver}:\n  {msg}")
        else:
            print(f"[+] Key detected: HKLM\\{path}")
            success = delete_power_settings(path)
            if success:
                msg = "The 'PowerSettings' directory was successfully deleted."
                print(f"[+] {msg}")
                popup_messages.append(f"• {driver}:\n  {msg}")
            else:
                msg = "Failed to delete the registry key."
                print(f"[-] {msg}")
                popup_messages.append(f"• {driver}:\n  {msg}")
        print("-" * 60)

    # --- PART 3: Summary Display ---
    if args.v:
        summary_message = f"Execution Status Report (v{VERSION}):\n\n" + "\n\n".join(popup_messages)
        show_popup(f"Modern Standby Registry Fixer v{VERSION}", summary_message)

if __name__ == "__main__":
    main()