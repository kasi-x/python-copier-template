"""Config: path constants and logging setup for the Kaggle project.

Paths are relative to the ``src/`` directory, e.g.::

    from utils.config import INPUT_DIR, OUTPUT_DIR, MODELS_DIR, LOGS_DIR
"""

from __future__ import annotations

from pathlib import Path

import structlog

########## SETUP ###############

structlog.configure(
    processors=[
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.JSONRenderer(),
    ],
    wrapper_class=structlog.make_filtering_bound_logger(__import__("logging").INFO),
)

logger = structlog.get_logger()

########## PATHS ###############

# src/ is one level below the project root; paths below are relative to it.
SRC_DIR = Path(__file__).resolve().parent
PROJ_ROOT = SRC_DIR.parent

CONFIG_DIR = SRC_DIR / "configs"
DATA_DIR = SRC_DIR / "data"
INPUT_DIR = SRC_DIR / "input"
OUTPUT_DIR = SRC_DIR / "output"
FEATURES_DIR = SRC_DIR / "features"
LOGS_DIR = SRC_DIR / "logs"
MODELS_DIR = SRC_DIR / "models"
NOTEBOOK_DIR = SRC_DIR / "notebook"
SCRIPTS_DIR = SRC_DIR / "scripts"

# Create the directories on import so paths always exist.
for _dir in (
    CONFIG_DIR,
    DATA_DIR,
    INPUT_DIR,
    OUTPUT_DIR,
    FEATURES_DIR,
    LOGS_DIR,
    MODELS_DIR,
    NOTEBOOK_DIR,
    SCRIPTS_DIR,
):
    _dir.mkdir(parents=True, exist_ok=True)
