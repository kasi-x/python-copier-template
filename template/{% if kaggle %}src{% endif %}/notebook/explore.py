"""marimo notebook for exploratory analysis.

Open with:
    uv run --extra experiment marimo edit src/notebook/explore.py
or:
    task marimo
"""

import marimo

__generated_with = "0.12.3"
app = marimo.App(width="full")


@app.cell
def _():
    import matplotlib.pyplot as plt
    import polars as pl
    import seaborn as sns

    # NOTE: override with real data paths; INPUT_DIR points at src/input
    from utils.config import INPUT_DIR

    return INPUT_DIR, pl, plt, sns


@app.cell
def _(INPUT_DIR, pl):
    path = INPUT_DIR / "train.csv"
    df = pl.read_csv(path) if path.exists() else pl.DataFrame({"x": [1, 2, 3]})
    df.head()
    return df, path


@app.cell
def _(df):
    df.describe()


if __name__ == "__main__":
    app.run()
