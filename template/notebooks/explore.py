"""marimo notebook for exploratory analysis.

Open with:
    uv run --extra experiment marimo edit notebooks/explore.py
or:
    task marimo
"""

import marimo

__generated_with = "0.12.3"
app = marimo.App(width="full")


@app.cell
def _():
    from pathlib import Path

    import polars as pl

    # data/raw is the canonical landing zone for untouched inputs
    # (see data/DEIDENTIFICATION.md before adding anything sensitive).
    raw_dir = Path("data") / "raw"

    return raw_dir, pl


@app.cell
def _(raw_dir, pl):
    csvs = sorted(raw_dir.glob("*.csv"))
    df = pl.read_csv(csvs[0]) if csvs else pl.DataFrame({"x": [1, 2, 3]})
    df.head()
    return csvs, df


@app.cell
def _(df):
    df.describe()


if __name__ == "__main__":
    app.run()
