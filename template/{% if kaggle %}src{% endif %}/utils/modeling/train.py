"""Train a model.

Usage:
    python -m utils.modeling.train                    # default config
    python -m utils.modeling.train params.lr=1e-3     # hydra override
"""

from __future__ import annotations

from pathlib import Path

import hydra
import optuna
import typer
from omegaconf import DictConfig

from utils.config import FEATURES_DIR
from utils.config import MODELS_DIR
from utils.config import logger

app = typer.Typer()


def objective(trial: optuna.Trial, _cfg: DictConfig) -> float:
    """Optuna objective: tune hyperparameters, return a metric to maximize."""
    lr = trial.suggest_float("lr", 1e-4, 1e-2, log=True)
    n_estimators = trial.suggest_int("n_estimators", 50, 500, step=50)
    # TODO: replace with real training; higher is better
    logger.info("trial", lr=lr, n_estimators=n_estimators)
    return float(lr * n_estimators)


@hydra.main(version_base=None, config_path="../../configs", config_name="train")
def train(cfg: DictConfig) -> None:
    """Run training (or a single Optuna trial) using Hydra config."""
    logger.info("config", cfg=cfg)
    if cfg.optuna.trials > 0:
        study = optuna.create_study(direction="maximize")
        study.optimize(lambda trial: objective(trial, cfg), n_trials=cfg.optuna.trials)
        logger.success("best_trial", value=study.best_value, params=study.best_params)
    else:
        value = objective(optuna.trial.FixedTrial(cfg.params), cfg)
        logger.success("training_done", value=value)


@app.command()
def main(
    input_path: str = "features.parquet",
    output_path: str = "model.pkl",
) -> None:
    """Simple typer entrypoint: read features, write a model."""
    src = FEATURES_DIR / input_path
    dst = MODELS_DIR / output_path
    if not src.exists():
        msg = f"input not found: {src}"
        raise typer.BadParameter(msg)
    logger.info("training", src=str(src), dst=str(dst))
    # TODO: replace with real training
    Path(dst).write_bytes(b"")
    logger.success("model_saved", dst=str(dst))


if __name__ == "__main__":
    train()
