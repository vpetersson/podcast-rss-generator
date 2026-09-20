"""Reading the YAML configuration file."""

from typing import Any

import yaml


def read_podcast_config(yaml_file_path: str) -> Any:
    with open(yaml_file_path, encoding="utf-8") as file:
        return yaml.safe_load(file)
