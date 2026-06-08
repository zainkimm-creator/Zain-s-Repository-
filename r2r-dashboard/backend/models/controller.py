"""Cascade PI plus feedforward controller for the R2R model."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Sequence

from .equations import R2RParameters, validate_vector, web_torques


def _clamp(value: float, lower: float, upper: float) -> float:
    return max(lower, min(upper, value))


@dataclass(frozen=True)
class ControllerConfig:
    """Controller gains and setpoints with explicit units."""

    target_tension_N: tuple[float, float, float] = (42.0, 44.0, 43.0)
    line_speed_m_s: float = 1.0
    Kp_star_m_s_per_N: float = 0.000010
    TI_s: float = 2.00
    velocity_Kp_Nm_per_rad_s: float = 0.200
    velocity_TI_s: float = 0.20
    max_voltage_V: float = 24.0
    feedforward_enabled: bool = True

    def __post_init__(self) -> None:
        if len(self.target_tension_N) != 3:
            raise ValueError("target_tension_N must contain exactly 3 values")
        if self.TI_s <= 0 or self.velocity_TI_s <= 0:
            raise ValueError("PI integral times must be positive")
        if self.max_voltage_V <= 0:
            raise ValueError("max_voltage_V must be positive")


@dataclass
class ControlAction:
    """Controller output and diagnostics for one sample."""

    inputs_V: tuple[float, float, float]
    velocity_ref_rad_s: tuple[float, float, float]
    tension_error_N: tuple[float, float, float]
    velocity_error_rad_s: tuple[float, float, float]
    feedforward_torque_Nm: tuple[float, float, float]

    def to_dict(self) -> dict[str, object]:
        return {
            "inputs_V": list(self.inputs_V),
            "velocity_ref_rad_s": list(self.velocity_ref_rad_s),
            "tension_error_N": list(self.tension_error_N),
            "velocity_error_rad_s": list(self.velocity_error_rad_s),
            "feedforward_torque_Nm": list(self.feedforward_torque_Nm),
        }


@dataclass
class CascadePIController:
    """Cascade PI controller with outer tension loop and inner velocity loop."""

    config: ControllerConfig = field(default_factory=ControllerConfig)
    tension_integral_N_s: list[float] = field(default_factory=lambda: [0.0, 0.0, 0.0])
    velocity_integral_rad: list[float] = field(default_factory=lambda: [0.0, 0.0, 0.0])

    def reset(self) -> None:
        self.tension_integral_N_s = [0.0, 0.0, 0.0]
        self.velocity_integral_rad = [0.0, 0.0, 0.0]

    def update(
        self,
        state: Sequence[float],
        dt_s: float,
        params: R2RParameters | None = None,
    ) -> ControlAction:
        """Compute held motor-voltage inputs for the next controller interval."""

        active_params = params or R2RParameters()
        x = validate_vector(state, 6, "state")
        measured_tension = x[:3]
        measured_omega = x[3:]
        tension_error = tuple(
            self.config.target_tension_N[i] - measured_tension[i] for i in range(3)
        )
        for i in range(3):
            self.tension_integral_N_s[i] += tension_error[i] * dt_s

        integral_gain = self.config.Kp_star_m_s_per_N / self.config.TI_s
        correction = tuple(
            self.config.Kp_star_m_s_per_N * tension_error[i]
            + integral_gain * self.tension_integral_N_s[i]
            for i in range(3)
        )

        c1, c2, c3 = correction
        v_ref_m_s = (
            self.config.line_speed_m_s - c1 - 0.5 * c3,
            self.config.line_speed_m_s + c1 - c2 - 0.5 * c3,
            self.config.line_speed_m_s + c2 + c3,
        )
        velocity_ref = tuple(
            v_ref_m_s[i] / active_params.roller_radius_m[i] for i in range(3)
        )
        velocity_error = tuple(velocity_ref[i] - measured_omega[i] for i in range(3))
        for i in range(3):
            self.velocity_integral_rad[i] += velocity_error[i] * dt_s

        velocity_integral_gain = self.config.velocity_Kp_Nm_per_rad_s / self.config.velocity_TI_s
        tau_web = web_torques(x, active_params)
        feedforward_torque = tuple(
            active_params.kf[i] * velocity_ref[i] - tau_web[i]
            if self.config.feedforward_enabled
            else 0.0
            for i in range(3)
        )
        torque_cmd = tuple(
            self.config.velocity_Kp_Nm_per_rad_s * velocity_error[i]
            + velocity_integral_gain * self.velocity_integral_rad[i]
            + feedforward_torque[i]
            for i in range(3)
        )
        inputs = tuple(
            _clamp(torque_cmd[i] / active_params.kt[i], -self.config.max_voltage_V, self.config.max_voltage_V)
            for i in range(3)
        )
        return ControlAction(
            inputs_V=inputs,
            velocity_ref_rad_s=velocity_ref,
            tension_error_N=tension_error,
            velocity_error_rad_s=velocity_error,
            feedforward_torque_Nm=feedforward_torque,
        )
