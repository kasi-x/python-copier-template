"""Predict with a trained model.

Usage:
    python -m utils.modeling.predict
"""

from __future__ import annotations

import typer

from utils.config import INPUT_DIR
from utils.config import MODELS_DIR
from utils.config import OUTPUT_DIR
from utils.config import logger

app = typer.Typer()


@app.command()
def main(
    model_path: str = "model.pkl",
    input_path: str = "test.csv",
    output_path: str = "submission.csv",
) -> None:
    """Run inference and write predictions.

    Args:
        model_path: Relative to ``src/models``.
        input_path: Relative to ``src/input``.
        output_path: Relative to ``src/output``.
    """
    model = MODELS_DIR / model_path
    src = INPUT_DIR / input_path
    dst = OUTPUT_DIR / output_path
    if not model.exists():
        msg = f"model not found: {model}"
        raise typer.BadParameter(msg)
    if not src.exists():
        msg = f"input not found: {src}"
        raise typer.BadParameter(msg)
    logger.info("predicting", model=str(model), src=str(src), dst=str(dst))
    # TODO: replace with real inference
    dst.write_bytes(b"")
    logger.success("predictions_written", dst=str(dst))


if __name__ == "__main__":
    app()
