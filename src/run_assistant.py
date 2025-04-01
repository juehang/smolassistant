from smolassistant.__main__ import main as smolassistant_main
from smolassistant.config import ConfigManager


def main():
    """Entry point for the CLI command"""
    config = ConfigManager()
    smolassistant_main(config)


if __name__ == "__main__":
    main()