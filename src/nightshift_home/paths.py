"""An explicit application-only home override for demos and isolated tests."""
import os
from pathlib import Path


def user_home():
    return Path(os.environ.get('NIGHTSHIFT_HOME', str(Path.home()))).expanduser().resolve()


def desktop_quote(value):
    value = str(value).replace('\\', '\\\\\\\\').replace('"', '\\\\"')
    value = value.replace('`', '\\\\`').replace('$', '\\\\$').replace('%', '%%')
    return '"' + value + '"'
