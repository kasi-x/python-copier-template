"""Feature engineering: read processed data and write features.

Usage:
    python -m utils.features
"""

from __future__ import annotations

import typer

from utils.config import DATA_DIR
from utils.config import FEATURES_DIR
from utils.config import logger

app = typer.Typer()


@app.command()
def main(
    input_path: str = "dataset.parquet",
    output_path: str = "features.parquet",
) -> None:
    """Build features from the processed dataset.

    Args:
        input_path: Relative to ``src/data``.
        output_path: Relative to ``src/features``.
    """
    src = DATA_DIR / input_path
    dst = FEATURES_DIR / output_path
    if not src.exists():
        msg = f"input not found: {src}"
        raise typer.BadParameter(msg)
    logger.info("building_features", src=str(src), dst=str(dst))
    # TODO: replace with real feature engineering
    dst.write_bytes(src.read_bytes())
    logger.success("features_built", dst=str(dst))


if __name__ == "__main__":
    app()
