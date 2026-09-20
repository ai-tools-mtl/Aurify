"""Optional settings from ``$DSH_HOME/patent-services.yaml``, env-overridable.

The plugin's knobs (the experiment command policy, the docker images, the
native draw.io CLI path, the HTML figure browser) are user preferences, not
launch decisions — they belong in a file the user and the agent can read and
edit (``~/.dsh/patent-services.yaml``), not in ``setx`` environment variables
that need a re-login and hide their value from every tool. An environment
variable still wins when set, keeping scripted deployments and the documented
opt-in rows working unchanged; the file is for people.
"""

from __future__ import annotations

import os
from pathlib import Path

import yaml

#: The config file's name inside $DSH_HOME (default ~/.dsh).
CONFIG_NAME = "patent-services.yaml"

#: The enabling keys this module serves: env name → file key.
OPTION_KEYS = {
    "DSH_EXPERIMENT_ALLOW_ANY_COMMAND": "experiment_allow_any_command",
    "DSH_PATENT_EXPERIMENT_IMAGE": "experiment_image",
    "DSH_DRAWIO_BIN": "drawio_bin",
    "DSH_DRAWIO_DOCKER_IMAGE": "drawio_docker_image",
    "DSH_HTML_BROWSER": "html_browser",
}


def config_path() -> Path:
    """Where the optional-settings file lives for this machine."""
    home = os.environ.get("DSH_HOME")
    return Path(home) if home else Path.home() / ".dsh"


def config_file() -> Path:
    """The settings file's full path."""
    return config_path() / CONFIG_NAME


def load_options() -> dict:
    """Read the settings file; missing or broken yields an empty mapping.

    A broken file is a preference problem, never a crash: every option has a
    code default, and the setup check reports the breakage instead.
    """
    path = config_file()
    if not path.is_file():
        return {}
    try:
        loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError:
        return {}
    return loaded if isinstance(loaded, dict) else {}


def config_value(env_name: str) -> str | None:
    """Resolve one option: environment variable first, then the file.

    YAML booleans normalize to ``"1"``/``""`` so ``experiment_allow_any_command:
    true`` behaves like the env form ``DSH_EXPERIMENT_ALLOW_ANY_COMMAND=1``.

    Args:
        env_name: the option's environment variable name; the file key is its
            lowercased snake form (``DSH_DRAWIO_BIN`` ↔ ``drawio_bin``).

    Returns:
        The resolved string value, or None when neither source sets it.
    """
    ambient = os.environ.get(env_name)
    if ambient is not None and ambient != "":
        return ambient
    file_key = OPTION_KEYS.get(env_name, env_name.removeprefix("DSH_").lower())
    value = load_options().get(file_key)
    if value is False:
        return None
    if isinstance(value, bool):
        return "1"
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, str) and value != "":
        return value
    return None
