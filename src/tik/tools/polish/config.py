from tik.shared.user_settings import SettingsManager

FACTORY_DEFAULTS = {
    "additional_library_paths": [],
}

settings = SettingsManager("tik_polish_settings", FACTORY_DEFAULTS)