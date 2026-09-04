"""Plotting helpers and figures.

Usage:
    python -m utils.plots
"""

from __future__ import annotations

import typer

from utils.config import FEATURES_DIR
from utils.config import OUTPUT_DIR
from utils.config import logger

app = typer.Typer()


@app.command()
def main(
    input_path: str = "features.parquet",
    output_path: str = "eda.png",
) -> None:
    """Generate exploratory plots from features.

    Args:
        input_path: Relative to ``src/features``.
        output_path: Relative to ``src/output``.
    """
    src = FEATURES_DIR / input_path
    dst = OUTPUT_DIR / output_path
    if not src.exists():
        msg = f"input not found: {src}"
        raise typer.BadParameter(msg)
    logger.info("plotting", src=str(src), dst=str(dst))
    # TODO: replace with real plotting
    dst.write_bytes(b"")
    logger.success("plots_written", dst=str(dst))


if __name__ == "__main__":
    app()
