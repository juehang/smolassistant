from xdg_base_dirs import xdg_config_home
import tomli
import tomli_w
import os

config_dir = os.path.join(xdg_config_home(), "smolassistant")
config_file = os.path.join(config_dir, "config.toml")

DEFAULTS = {
    "provider": "anthropic",
    "model": "claude-3-5-haiku-latest",
    "max_context_length": 99999,
    "api_key": "",
    "reminders": {
        "db_path": "reminders.sqlite"
    }
}


class ConfigManager:
    """
    Manages the configuration of the smolassistant.
    """
    def __init__(self):
        if not os.path.exists(config_file):
            os.makedirs(config_dir, exist_ok=True)
            with open(config_file, "wb") as f:
                tomli_w.dump(DEFAULTS, f)
        with open(config_file, "rb") as f:
            self.config = tomli.load(f)

    def reload(self):
        with open(config_file, "rb") as f:
            self.config = tomli.load(f)
    
    def save(self):
        with open(config_file, "w") as f:
            tomli_w.dump(self.config, f)
