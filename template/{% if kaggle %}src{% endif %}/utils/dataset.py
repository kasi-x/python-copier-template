"""Build the dataset: read raw inputs and write processed features.

Usage:
    python -m utils.dataset
"""

from __future__ import annotations

import typer

from utils.config import DATA_DIR
from utils.config import INPUT_DIR
from utils.config import logger

app = typer.Typer()


@app.command()
def main(
    input_path: str = "train.csv",
    output_path: str = "dataset.parquet",
) -> None:
    """Read raw input and write a cleaned dataset.

    Args:
        input_path: Relative to ``src/input``.
        output_path: Relative to ``src/data``.
    """
    src = INPUT_DIR / input_path
    dst = DATA_DIR / output_path
    if not src.exists():
        msg = f"input not found: {src}"
        raise typer.BadParameter(msg)
    logger.info("building_dataset", src=str(src), dst=str(dst))
    # TODO: replace with real preprocessing
    dst.write_bytes(src.read_bytes())
    logger.success("dataset_built", dst=str(dst))


if __name__ == "__main__":
    app()
