"""Data and feature pipelines for the LaLiga AI Predictor project."""

from .features import run_phase2
from .pipeline import run_phase1
from .eda import run_phase3
from .modeling import run_phase4
from .goal_modeling import run_phase5
from .advanced_modeling import run_phase6

__all__ = [
    "run_phase1",
    "run_phase2",
    "run_phase3",
    "run_phase4",
    "run_phase5",
    "run_phase6",
]
