"""Mathematical model, controller, and simulation primitives."""

from .controller import CascadePIController, ControllerConfig
from .equations import (
    INPUT_NAMES,
    PARAMETER_NAMES,
    STATE_NAMES,
    R2RParameters,
    derivatives,
    equation_summary,
    velocities,
)
from .simulation import SimulationConfig, SimulationResult, simulate

__all__ = [
    "CascadePIController",
    "ControllerConfig",
    "INPUT_NAMES",
    "PARAMETER_NAMES",
    "STATE_NAMES",
    "R2RParameters",
    "SimulationConfig",
    "SimulationResult",
    "derivatives",
    "equation_summary",
    "simulate",
    "velocities",
]
