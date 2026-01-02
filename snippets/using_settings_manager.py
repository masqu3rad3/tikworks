"""
Example usage of the generic SettingsManager from tik.shared.user_settings.

To use this as a singleton in your application:
1. Create a `config.py` (or `settings.py`) module in your tool's package.
2. Instantiate `SettingsManager` at the module level.
3. Import this instance wherever you need access to settings.
"""

from typing import List
import logging

# Assuming 'src' is in your PYTHONPATH
from tik.shared.user_settings import SettingsManager

# --- 1. Define Defaults ---
# Define the default values for your application's settings.
MY_TOOL_DEFAULTS = {
    "window_size": [800, 600],
    "theme": "dark",
    "max_recent_files": 5,
    "recent_files": [],
    "debug_mode": False,
    "auto_save_interval": 15
}

# --- 2. Instantiate Singleton ---
# This instance will be shared across your application.
# The app_name determines the filename: "my_tool_settings.json"
settings = SettingsManager(settings_file_name="my_tool", defaults=MY_TOOL_DEFAULTS)


# --- 3. Usage Examples ---

def update_theme(new_theme: str):
    """Example function modifying a setting."""
    print(f"Changing theme from '{settings.get('theme')}' to '{new_theme}'")
    settings.set("theme", new_theme)


def add_recent_file(file_path: str):
    """Example of complex logic using the settings manager."""
    # Get current list (returns a copy or reference depending on implementation,
    # but it's safe to modify and set back)
    recent = settings.get("recent_files", [])
    max_files = settings.get("max_recent_files", 10)

    if file_path in recent:
        recent.remove(file_path)

    recent.insert(0, file_path)

    # Trim to max length
    if len(recent) > max_files:
        recent = recent[:max_files]

    settings.set("recent_files", recent)
    print(f"Added '{file_path}' to recent files.")


def main():
    # Configure logging for demo
    logging.basicConfig(level=logging.INFO)

    print(f"Settings file location: {settings._user_settings._file_path}")
    print(f"Current Settings: {settings.get_all_settings()}")

    # Modify settings
    update_theme("light")
    add_recent_file("D:/projects/shot_01.ma")
    add_recent_file("D:/projects/shot_02.ma")

    # Check for changes
    if settings.is_changed():
        print("Settings have changed.")

        # Save to disk
        success = settings.save()
        if success:
            print("Settings saved successfully.")
        else:
            print("Failed to save settings.")
    else:
        print("No changes to save.")

if __name__ == "__main__":
    main()

