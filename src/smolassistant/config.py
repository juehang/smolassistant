import os

import tomli
import tomli_w
from xdg_base_dirs import xdg_config_home

config_dir = os.path.join(xdg_config_home(), "smolassistant")
config_file = os.path.join(config_dir, "config.toml")

DEFAULTS = {
    "model": "anthropic/claude-3-7-sonnet-latest",
    "api_key": "",
    "additional_instructions": (
        "\nPlease use HTML to format your final answer. "
        "Only the following HTML tags are supported: "
        "<b>bold</b>, <i>italic</i>, <code>code</code>, "
        '<pre language="python">code</pre>, <s>strike</s>, <u>underline</u>'
        "Do not use any other HTML tags, such as <br>, <ul>, etc.\n"
        "Be sure to escape any HTML characters in your response, "
        "such as &, <, and >.\n\n"
        "If given a natural language processing problem, "
        "such as summarization or translation, please rely on your own "
        "capabilities or the text processing tool, and do not use coding "
        "except for basic tasks such as counting words.\n"
        "For tools that support summarization "
        "(email tools and webpage visits), summarization is enabled by "
        "default. Use it to make long content more digestible.\n"
        "Before submitting your final answer, please review it for any "
        "mistakes, and ensure that it is correct, complete, and "
        "follows the instructions given.\n"
    ),
    "additional_system_prompt": (
        "\nPlease ensure that your responses via the final answer function "
        "are friendly and helpful, and greet the user when appropriate!\n"
        "If you are unsure about your answer, please include your "
        "confidence.\nYou do not know the current date or time; "
        "if you need this information, "
        "please use your coding capabilities to find it.\n"
        "If you require additional context about earlier conversations, "
        "please use the message history tool to retrieve it.\n"
    ),  # Custom text to add to the system prompt
    "reminders": {"db_path": "reminders.sqlite"},
    "gmail": {"credentials_path": "credentials.json", "accounts": []},
    "telegram": {
        "enabled": False,
        "token": "",
        # ID of first user to interact with bot
        "authorized_user_id": None,
    },
    "message_history": {"max_size": 20},
    "text_processor": {
        "model": "anthropic/claude-3-haiku-20240307",
        "summary_prompt": (
            "Summarize the following text. Preserve key information "
            "while being concise. For emails, include sender, subject, and "
            "main points. For webpages, include main topics and key details. "
            "For attachments, mention types but not full filenames."
        ),
    },
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

        # Ensure all default values are present
        self.ensure_defaults()

    def reload(self):
        with open(config_file, "rb") as f:
            self.config = tomli.load(f)

    def save(self):
        with open(config_file, "wb") as f:
            tomli_w.dump(self.config, f)

    def ensure_defaults(self):
        """
        Ensure that all default configuration values are present in the current
        configuration. If any are missing, add them, print to console, and save
        the configuration.
        """
        changed = False

        def update_recursively(config, defaults, path=""):
            nonlocal changed

            for key, default_value in defaults.items():
                current_path = f"{path}.{key}" if path else key

                # If the key doesn't exist in the config, add it
                if key not in config:
                    config[key] = default_value
                    print(f"Added missing configuration entry: {current_path}")
                    changed = True
                # If the value is a dictionary, recursively update it
                elif isinstance(default_value, dict) and isinstance(
                    config[key], dict,
                ):
                    update_recursively(
                        config[key], default_value, current_path,
                    )

        update_recursively(self.config, DEFAULTS)

        if changed:
            self.save()
            print("Configuration file updated with new default values")
