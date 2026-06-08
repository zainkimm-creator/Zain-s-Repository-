"""R2R governing equations with explicit state, input, parameter, and unit names.

State vector:
    x = [T1, T2, T3, omega_UW, omega_Nip, omega_RW]

Input vector:
    u = [u_UW, u_Nip, u_RW]

Units:
    Tension T_i: N
    Angular velocity omega_i: rad/s
    Roller command input u_i: V in the dashboard API, converted to motor torque
    Web speed v_i = R_i * omega_i: m/s
    Elastic modulus-area product EA: N
    SysID ratio kt_i = R_i^2/J_i: 1/kg
    SysID ratio kf_i = f_i/J_i: 1/s
    Internal motor gain: N*m/V
    Viscous friction f_i: N*m*s/rad
    Roller inertia J_i: kg*m^2
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from math import isfinite
from typing import Iterable, Mapping, Sequence

STATE_NAMES = ("T1", "T2", "T3", "omega_UW", "omega_Nip", "omega_RW")
INPUT_NAMES = ("u_UW", "u_Nip", "u_RW")
PARAMETER_NAMES = ("kt_UW", "kt_Nip", "kt_RW", "kf_UW", "kf_Nip", "kf_RW", "EA")
ROLLER_NAMES = ("UW", "Nip", "RW")


def _tuple3(values: Sequence[float], name: str) -> tuple[float, float, float]:
    if len(values) != 3:
        raise ValueError(f"{name} must contain exactly 3 values")
    result = tuple(float(v) for v in values)
    if not all(isfinite(v) for v in result):
        raise ValueError(f"{name} must contain finite values")
    return result


@dataclass(frozen=True)
class R2RParameters:
    """Physical parameters for the paper-based R2R validation model."""

    span_length_m: tuple[float, float, float] = (0.80, 0.80, 1.60)
    roller_radius_m: tuple[float, float, float] = (0.050, 0.050, 0.050)
    inertia_kg_m2: tuple[float, float, float] = (0.075, 0.055, 0.090)
    tension_ref_N: tuple[float, float, float] = (42.0, 44.0, 43.0)
    tension_relaxation_hz: float = 0.05
    process_noise_b: float = 0.0
    kt_UW: float = 0.085
    kt_Nip: float = 0.105
    kt_RW: float = 0.090
    kf_UW: float = 0.010
    kf_Nip: float = 0.012
    kf_RW: float = 0.011
    EA: float = 4200.0
    feeder_velocity_m_s: float = 1.0

    def __post_init__(self) -> None:
        object.__setattr__(self, "span_length_m", _tuple3(self.span_length_m, "span_length_m"))
        object.__setattr__(self, "roller_radius_m", _tuple3(self.roller_radius_m, "roller_radius_m"))
        object.__setattr__(self, "inertia_kg_m2", _tuple3(self.inertia_kg_m2, "inertia_kg_m2"))
        object.__setattr__(self, "tension_ref_N", _tuple3(self.tension_ref_N, "tension_ref_N"))
        positive_fields = {
            "span_length_m": self.span_length_m,
            "roller_radius_m": self.roller_radius_m,
            "inertia_kg_m2": self.inertia_kg_m2,
            "kt_UW": (self.kt_UW,),
            "kt_Nip": (self.kt_Nip,),
            "kt_RW": (self.kt_RW,),
            "kf_UW": (self.kf_UW,),
            "kf_Nip": (self.kf_Nip,),
            "kf_RW": (self.kf_RW,),
            "EA": (self.EA,),
            "feeder_velocity_m_s": (self.feeder_velocity_m_s,),
        }
        for field_name, values in positive_fields.items():
            if any(v <= 0 or not isfinite(v) for v in values):
                raise ValueError(f"{field_name} values must be finite and positive")
        if self.tension_relaxation_hz < 0 or not isfinite(self.tension_relaxation_hz):
            raise ValueError("tension_relaxation_hz must be finite and non-negative")
        if self.process_noise_b < 0 or not isfinite(self.process_noise_b):
            raise ValueError("process_noise_b must be finite and non-negative")

    @property
    def kt(self) -> tuple[float, float, float]:
        return (self.kt_UW, self.kt_Nip, self.kt_RW)

    @property
    def kf(self) -> tuple[float, float, float]:
        return (self.kf_UW, self.kf_Nip, self.kf_RW)

    @property
    def paper_kt(self) -> tuple[float, float, float]:
        """Paper Eq. (6) ratio parameters `k_t,i = R_i^2/J_i`."""

        return tuple(
            radius * radius / inertia
            for radius, inertia in zip(self.roller_radius_m, self.inertia_kg_m2, strict=True)
        )

    @property
    def paper_kf(self) -> tuple[float, float, float]:
        """Paper Eq. (6) ratio parameters `k_f,i = f_i/J_i`."""

        return tuple(
            friction / inertia for friction, inertia in zip(self.kf, self.inertia_kg_m2, strict=True)
        )

    def sysid_values(self) -> dict[str, float]:
        kt_values = self.paper_kt
        kf_values = self.paper_kf
        return {
            "kt_UW": kt_values[0],
            "kt_Nip": kt_values[1],
            "kt_RW": kt_values[2],
            "kf_UW": kf_values[0],
            "kf_Nip": kf_values[1],
            "kf_RW": kf_values[2],
            "EA": float(self.EA),
        }

    def with_sysid_values(self, values: Mapping[str, float]) -> "R2RParameters":
        allowed = {name: float(value) for name, value in values.items() if name in PARAMETER_NAMES}
        return replace(self, **allowed)

    def with_drift(
        self,
        *,
        EA_scale: float = 1.0,
        friction_scale: float = 1.0,
        inertia_scale: float = 1.0,
    ) -> "R2RParameters":
        return replace(
            self,
            EA=self.EA * EA_scale,
            kf_UW=self.kf_UW * friction_scale,
            kf_Nip=self.kf_Nip * friction_scale,
            kf_RW=self.kf_RW * friction_scale,
            inertia_kg_m2=tuple(j * inertia_scale for j in self.inertia_kg_m2),
        )

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def validate_vector(values: Sequence[float], expected: int, name: str) -> tuple[float, ...]:
    if len(values) != expected:
        raise ValueError(f"{name} must contain {expected} values")
    result = tuple(float(v) for v in values)
    if not all(isfinite(v) for v in result):
        raise ValueError(f"{name} must contain only finite values")
    return result


def velocities(state: Sequence[float], params: R2RParameters) -> tuple[float, float, float]:
    """Return roller surface velocities `(v_UW, v_Nip, v_RW)` in m/s."""

    x = validate_vector(state, 6, "state")
    _, _, _, omega_uw, omega_nip, omega_rw = x
    return (
        params.roller_radius_m[0] * omega_uw,
        params.roller_radius_m[1] * omega_nip,
        params.roller_radius_m[2] * omega_rw,
    )


def tension_state_pairs(state: Sequence[float]) -> tuple[tuple[float, float], ...]:
    """Return `(T_{i-1}, T_i)` pairs for Eq. (1), with `T0 = 0`."""

    t1, t2, t3, *_ = validate_vector(state, 6, "state")
    return ((0.0, t1), (t1, t2), (t2, t3))


def span_velocity_pairs(
    state: Sequence[float], params: R2RParameters
) -> tuple[tuple[float, float], ...]:
    """Return `(v_{i-1}, v_i)` pairs for Eq. (1)."""

    v_uw, v_nip, v_rw = velocities(state, params)
    return ((params.feeder_velocity_m_s, v_uw), (v_uw, v_nip), (v_nip, v_rw))


def roller_tension_differences(state: Sequence[float]) -> tuple[float, float, float]:
    """Return `T_{i+1} - T_i` for Eq. (2), with downstream `T4 = 0`."""

    t1, t2, t3, *_ = validate_vector(state, 6, "state")
    return (t2 - t1, t3 - t2, -t3)


def tension_derivatives(state: Sequence[float], params: R2RParameters) -> tuple[float, float, float]:
    """Return `[dT1/dt, dT2/dt, dT3/dt]` in N/s using paper Eq. (1).

    Eq. (1):
        dT_i/dt = (EA/L_i)(v_i - v_{i-1})
                  + (1/L_i)(T_{i-1}v_{i-1} - T_i v_i)

    The upstream boundary uses `T0 = 0`; the upstream velocity is the fixed
    feeder boundary speed.
    """

    x = validate_vector(state, 6, "state")
    derivatives_t: list[float] = []
    for length, tensions, speed_pair in zip(
        params.span_length_m,
        tension_state_pairs(x),
        span_velocity_pairs(x, params),
        strict=True,
    ):
        t_prev, t_i = tensions
        v_prev, v_i = speed_pair
        elastic = (params.EA / length) * (v_i - v_prev)
        convective = (t_prev * v_prev - t_i * v_i) / length
        derivatives_t.append(elastic + convective)
    return tuple(derivatives_t)  # type: ignore[return-value]


def web_torques(state: Sequence[float], params: R2RParameters) -> tuple[float, float, float]:
    """Return the Eq. (2) web-tension torque term `R_i(T_{i+1}-T_i)`."""

    return tuple(
        radius * tension_delta
        for radius, tension_delta in zip(
            params.roller_radius_m, roller_tension_differences(state), strict=True
        )
    )


def roller_velocity_derivatives(
    state: Sequence[float],
    inputs: Sequence[float],
    params: R2RParameters,
) -> tuple[float, float, float]:
    """Return `[domega_UW/dt, domega_Nip/dt, domega_RW/dt]` via paper Eq. (2).

    Eq. (2) is written for surface speed:
        dv_i/dt = (R_i^2/J_i)(T_{i+1}-T_i)
                  - (f_i/J_i)v_i + (R_i/J_i)u_i

    The dashboard API still sends voltage-like commands, so the internal
    actuator gain `Kmotor_i*u_i` is the motor torque input used in the paper
    equation.
    """

    x = validate_vector(state, 6, "state")
    u = validate_vector(inputs, 3, "inputs")
    _, _, _, omega_uw, omega_nip, omega_rw = x
    omega = (omega_uw, omega_nip, omega_rw)
    derivatives_w: list[float] = []
    for i, delta_tension in enumerate(roller_tension_differences(x)):
        radius = params.roller_radius_m[i]
        inertia = params.inertia_kg_m2[i]
        surface_speed = radius * omega[i]
        motor_torque = params.kt[i] * u[i]
        dv_dt = ((radius * radius) / inertia) * delta_tension
        dv_dt -= (params.kf[i] / inertia) * surface_speed
        dv_dt += (radius / inertia) * motor_torque
        derivatives_w.append(dv_dt / radius)
    return tuple(derivatives_w)  # type: ignore[return-value]


def derivatives(
    state: Sequence[float],
    inputs: Sequence[float],
    params: R2RParameters | None = None,
) -> tuple[float, float, float, float, float, float]:
    """Return the complete state derivative `dx/dt` in state-vector order."""

    active_params = params or R2RParameters()
    return tension_derivatives(state, active_params) + roller_velocity_derivatives(
        state, inputs, active_params
    )


def rk4_step(
    state: Sequence[float],
    inputs: Sequence[float],
    dt_s: float,
    params: R2RParameters | None = None,
) -> tuple[float, ...]:
    """Advance the R2R state by one RK4 step."""

    active_params = params or R2RParameters()
    x = validate_vector(state, 6, "state")
    u = validate_vector(inputs, 3, "inputs")

    def add_scaled(base: Sequence[float], slope: Sequence[float], scale: float) -> tuple[float, ...]:
        return tuple(base[i] + scale * slope[i] for i in range(6))

    k1 = derivatives(x, u, active_params)
    k2 = derivatives(add_scaled(x, k1, 0.5 * dt_s), u, active_params)
    k3 = derivatives(add_scaled(x, k2, 0.5 * dt_s), u, active_params)
    k4 = derivatives(add_scaled(x, k3, dt_s), u, active_params)
    return tuple(x[i] + (dt_s / 6.0) * (k1[i] + 2.0 * k2[i] + 2.0 * k3[i] + k4[i]) for i in range(6))


def nominal_state(params: R2RParameters | None = None, line_speed_m_s: float = 1.0) -> tuple[float, ...]:
    """Return a nominal state at target tensions and uniform line speed."""

    active_params = params or R2RParameters()
    omegas = tuple(line_speed_m_s / radius for radius in active_params.roller_radius_m)
    return active_params.tension_ref_N + omegas


def equation_summary() -> dict[str, object]:
    """Return display-ready equations and units for API/UI inspection."""

    summary = {
        "state_vector": "x = [T1, T2, T3, omega_UW, omega_Nip, omega_RW]",
        "input_vector": "u = [u_UW, u_Nip, u_RW]",
        "output_vector": "y = [T1, T2, T3]",
        "paper_source": {
            "title": "Equation Identifier for Practical system identification for roll-to-roll web tension control",
            "file_name": "paper1_isa_v2_equation_identifier.pdf",
            "scope": "Equations, definitions, decision rules, and examples extracted only from the supplied PDF.",
            "page_count": 4,
            "typography": "Times-style body text with Cambria Math/TeX-like math extraction; dominant extracted size is about 9-10 pt.",
        },
        "section2_note": (
            "Paper-facing equations are taken from the supplied PDF "
            "paper1_isa_v2_equation_identifier.pdf. The PDF contains numbered equations (1)-(9) plus "
            "important unnumbered definitions labeled U-*. Tokens such as CS-BO(30), WS-BO(30), "
            "HGS+BO(5), and HGS+BO(10) are method labels or evaluation budgets, not equation numbers. "
            "System equations show the runnable backend equations now aligned with the supplied PDF dynamics."
        ),
        "theory_summary": [
            {
                "title": "Plant model",
                "detail": "The paper models a three-span R2R line with three span tensions and three roller speeds. Tension is the measured output, while motor torque or voltage commands drive the rollers.",
            },
            {
                "title": "Tension physics",
                "detail": "Velocity mismatch stretches or relaxes the web through EA/L. The paper equation also includes convective transport of tension into and out of each span.",
            },
            {
                "title": "Roller physics",
                "detail": "Roller motion is shaped by tension difference, inertia J, viscous friction f, radius R, and motor input. This is why J drift changes several dynamic paths at once.",
            },
            {
                "title": "Cascade controller",
                "detail": "The outer PI loop turns tension error into a speed correction, while the inner loop tracks speed and adds feedforward torque. The normalized gain Kp_star controls how informative the transient data is.",
            },
            {
                "title": "SysID objective",
                "detail": "System identification minimizes one-step tension prediction error. Multiple excitation conditions add independent constraints and improve robustness under noise.",
            },
            {
                "title": "Deployment rules",
                "detail": "The PDF links the equations to practical rules: noise-free logging needs tau_min/Tlog >= 5, sensor-noise logging prefers 10-20 ms with LPF >= 50 Hz, and Kp_star is set near 100-200 for SysID mode.",
            },
        ],
        "paper_equations": [
            {
                "number": "U-0",
                "title": "Plant variables and physical setup",
                "equation": "x = [T1, T2, T3, omega_UW, omega_Nip, omega_RW]^T in R^6; u = [u_UW, u_Nip, u_RW]^T; y = [T1, T2, T3]^T; EA = E*h*w; v_i = omega_i*R_i; J_reel proportional R^4",
                "variables": "x contains three span tensions and three roller angular velocities; u is the paper motor-torque input; y is measured tension; EA is axial web stiffness.",
                "paper_use": "The PDF uses these definitions to set the three-span R2R plant and to motivate the seven-parameter SysID vector.",
                "dashboard_note": "The backend uses the same state and output order. Its input vector is a held motor-voltage command that is converted through backend motor gains.",
            },
            {
                "number": "(1)",
                "title": "Web tension dynamics",
                "equation": "dT_i/dt = (EA/L_i)(v_i - v_{i-1}) + (1/L_i)(T_{i-1}v_{i-1} - T_i v_i),  i = 1,2,3",
                "variables": "T_i: span tension, EA: axial web stiffness, L_i: span length, v_i: roller surface velocity.",
                "paper_use": "The PDF states the boundary condition T_0 = T_4 = 0 and links this tension equation to RK4 integration, one-step residuals, and the logging-rate result.",
                "dashboard_note": "The backend now uses this equation directly, with T0 = 0 and a fixed feeder boundary speed for v0.",
            },
            {
                "number": "(2)",
                "title": "Roller velocity dynamics",
                "equation": "dv_i/dt = (R_i^2/J_i)(T_{i+1} - T_i) - (f_i/J_i)v_i + (R_i/J_i)u_i",
                "variables": "R_i: roller radius, J_i: moment of inertia, f_i: viscous friction, u_i: motor torque input.",
                "paper_use": "The PDF uses this roller equation to explain why J drift is dominant: J appears in the tension-coupling, friction, and torque coefficients.",
                "dashboard_note": "The backend state uses omega_i, so the runnable model represents this balance as domega_i/dt with web torque, friction, inertia, and voltage-to-torque gain.",
            },
            {
                "number": "(3)",
                "title": "Outer-loop tension PI velocity correction",
                "equation": "v_corr,i = (L_i/EA)Kp_star [sigma_i e_i + (1/TI) integral_0^t sigma_i e_i(tau) d tau]; omega_ref,i = omega_ss,i + v_corr,i/R_i",
                "variables": "e_i = T_ref,i - T_meas,i; sigma_i in {-1,+1,+1}; Kp_star = Kp*EA/L is the normalized proportional gain.",
                "paper_use": "The PDF emphasizes that L/EA in this controller cancels EA/L in equation (1), making Kp_star the practical information-content knob.",
                "dashboard_note": "The backend controller uses the same tension-error-to-velocity-correction concept before the inner velocity loop computes motor commands.",
            },
            {
                "number": "(4)",
                "title": "Inner-loop velocity P plus feedforward torque",
                "equation": "u_i = K_vel,i(omega_ref,i - omega_i) + u_ff,i; K_vel,i = alpha*J_i*omega_n,i; omega_n,i = sqrt(EA*R_i^2/(J_i*L_i)); alpha = 1.4",
                "variables": "omega_ref,i is the target from equation (3); omega_i is measured roller speed; u_ff,i is the feedforward torque.",
                "paper_use": "The PDF links this cascade loop to the loss of predictive value in zeta_CL,min and the practical use of Kp_star instead.",
                "dashboard_note": "The backend uses a velocity PI plus feedforward torque, then converts torque to a clamped voltage command.",
            },
            {
                "number": "(5)",
                "title": "Measurement-based feedforward",
                "equation": "u_ff,i = +/- T_meas*R_i + f_i*omega_i; u_ff = [T0*R0, (T2 - T1)R1, -T2*R2]^T + f o omega",
                "variables": "The sign depends on roller/span direction; f o omega denotes elementwise friction compensation.",
                "paper_use": "The PDF states that measurement-based feedforward compensates measured tension load and friction and can absorb some EA drift.",
                "dashboard_note": "The backend feedforward uses the current web-torque balance and friction term to reduce the burden on the feedback loops.",
            },
            {
                "number": "(6)",
                "title": "Ratio-parameter SysID formulation",
                "equation": "k_t,i = R_i^2/J_i; k_f,i = f_i/J_i; k_u,i = R_i/J_i; theta = [kt_UW, kt_Nip, kt_RW, kf_UW, kf_Nip, kf_RW, EA] in R^7",
                "variables": "R_i and L_i are treated as known measurable constants; ku_i can be derived rather than estimated independently.",
                "paper_use": "The PDF uses these ratio parameters because they are the combinations that appear in equation (2).",
                "dashboard_note": "The backend estimates the same seven displayed parameter names as paper ratios. A separate internal motor gain converts the dashboard voltage-like command into the torque input used by Eq. (2).",
            },
            {
                "number": "(7)",
                "title": "One-step prediction-error cost",
                "equation": "J(theta) = sum_{k=1}^N || y_k - y_hat_k(theta) ||^2",
                "variables": "y_k is the measured tension vector at the logging instant; yhat_k(theta) is the model prediction.",
                "paper_use": "The PDF identifies this as the central SysID objective and uses it to explain the sensitivity to logging period and filtering.",
                "dashboard_note": "The dashboard reports parameter-estimation error tables and RMSE_theta from the resulting estimates.",
            },
            {
                "number": "(8)",
                "title": "Multi-condition prediction-error cost",
                "equation": "J_multi(theta) = sum_{c=1}^C sum_{k=1}^{N_c} || y_k^(c) - y_hat_k^(c)(theta) ||^2",
                "variables": "c indexes distinct excitation or operating conditions.",
                "paper_use": "The PDF states that multi-condition residuals add independent constraints and reduce shallow or ambiguous cost landscapes.",
                "dashboard_note": "The excitation validation tab compares which excitation profiles produce better SysID information.",
            },
            {
                "number": "U-8",
                "title": "Initial guesses and SysID accuracy metrics",
                "equation": "theta_init = alpha*theta_true, alpha in {1.5, 2, 5, 10, 50}; error_j = |theta_est,j - theta_true,j|/theta_true,j*100; RMSE_theta = n^-1 sum_i |(theta_hat_i - theta_i)/theta_i|*100; RMSE_y = n^-1 sum_i RMSE_i",
                "variables": "alpha scales the initial guess; error_j is per-parameter relative error; RMSE_theta and RMSE_y aggregate SysID and tracking errors.",
                "paper_use": "The PDF uses these metrics to compare convergence basins, data designs, and validation step responses.",
                "dashboard_note": "The backend reports RMSE_theta as a root-mean-square relative error, so the dashboard labels it as the implementation aggregate.",
            },
            {
                "number": "(9)",
                "title": "Channel-weighted retuning score",
                "equation": "S = sum_{i=1}^n w_i (RMSE_i/1 + OS_i/100 + t90_i/15 + U_total,i/200); w_i = |Delta T_ref,i|/sum_j |Delta T_ref,j|; RMSE_i = sqrt(N^-1 sum_k (T_i(t_k) - T_ref,i)^2); OS_i = max(0, (T_i,peak - T_ref,i,new)/|Delta T_ref,i|)*100; U_total,i = integral_0^Tsim u_i^2(t) dt",
                "variables": "S combines tracking error, overshoot, rise time to 90%, and total squared control effort.",
                "paper_use": "The PDF links this score to Table 3/Figure 10 and the HGS+BO(5) result: median cost 0.342 with five real evaluations versus CS-BO(30) at 0.407.",
                "dashboard_note": "The dashboard retuning study uses a related cost combining RMSE, overshoot, t90, and control effort.",
            },
            {
                "number": "U-10",
                "title": "Deployment rules derived from the equations",
                "equation": "tau_min = 1/max_i(|Re(lambda_i)|); NF: tau_min/Tlog >= 5; SN: Tlog = 10-20 ms and LPF fc >= 50 Hz; Kp_star = 100 default, Kp_star = 200 under high noise; validate RMSE_y < epsilon and S < C_target",
                "variables": "NF: noise-free; SN: sensor-noise case; LPF: low-pass filter; Kp_star controls transient information content.",
                "paper_use": "The PDF describes these as decision rules derived from the model, SysID objective, and retuning score, not new governing equations.",
                "dashboard_note": "Validation tabs expose the logging, excitation, SysID, and retuning checks that correspond to these rules.",
            },
        ],
        "backend_equations": [
            {
                "title": "Web transport kinematics",
                "equation": "v_i = R_i * omega_i",
                "variables": "R_i: roller radius, omega_i: angular velocity, v_i: surface speed.",
                "backend_use": "Used in simulation logging, tension derivatives, and SysID EA regression.",
            },
            {
                "title": "Paper web tension dynamics",
                "equation": "dT_i/dt = (EA/L_i)(v_i - v_{i-1}) + (T_{i-1}v_{i-1} - T_i v_i)/L_i,  i = 1,2,3",
                "variables": "EA: web stiffness, L_i: span length, T0 = 0, and v0 is the fixed feeder boundary speed.",
                "backend_use": "Used by tension_derivatives(), derivatives(), rk4_step(), simulation rows, and the Calculation tab derivative example.",
            },
            {
                "title": "Web torque balance on rollers",
                "equation": "tau_web,i = R_i(T_{i+1} - T_i), with T4 = 0",
                "variables": "T_i: span tensions, R_i: roller radii.",
                "backend_use": "Used by roller dynamics and by the cascade PI feedforward torque.",
            },
            {
                "title": "Roller velocity dynamics",
                "equation": "dv_i/dt = (R_i^2/J_i)(T_{i+1} - T_i) - (f_i/J_i)v_i + (R_i/J_i)(Kmotor_i*u_i); domega_i/dt = (dv_i/dt)/R_i",
                "variables": "J_i: inertia, Kmotor_i*u_i: motor torque sent into paper Eq. (2), f_i: viscous friction.",
                "backend_use": "Used by roller_velocity_derivatives(), derivatives(), rk4_step(), and SysID kt/kf regression.",
            },
            {
                "title": "Outer tension PI correction",
                "equation": "c_i = Kp_star*e_i + (Kp_star/TI)*integral(e_i dt),  e_i = T_ref,i - T_i",
                "variables": "c_i: tension-loop velocity correction, e_i: tension error, TI: integral time.",
                "backend_use": "Used by CascadePIController.update() to build roller speed references.",
            },
            {
                "title": "Velocity reference coupling",
                "equation": "v_ref,UW = v_line - c1 - 0.5c3; v_ref,Nip = v_line + c1 - c2 - 0.5c3; v_ref,RW = v_line + c2 + c3; omega_ref,i = v_ref,i/R_i",
                "variables": "v_line: target line speed, c_i: tension-loop corrections.",
                "backend_use": "Used by the PI controller to convert tension error into roller angular-speed references.",
            },
            {
                "title": "Inner velocity PI plus feedforward",
                "equation": "tau_cmd,i = Kvel*e_omega,i + (Kvel/TI_vel)*integral(e_omega,i dt) + tau_ff,i; tau_ff,i = f_i*omega_ref,i - tau_web,i; u_i = clamp(tau_cmd,i/Kmotor_i)",
                "variables": "e_omega,i = omega_ref,i - omega_i; tau_ff,i is friction and web-torque feedforward.",
                "backend_use": "Used by CascadePIController.update() to produce the held motor-voltage input u.",
            },
            {
                "title": "RK4 state update",
                "equation": "x_next = x + (dt/6)(k1 + 2k2 + 2k3 + k4)",
                "variables": "k1...k4 are derivatives evaluated by the backend model while u is held constant over the integration step.",
                "backend_use": "Used by rk4_step() for every 1 ms physics update in simulation.",
            },
            {
                "title": "Simulation tension RMSE",
                "equation": "tension_rmse_N = sqrt(sum((T_i - T_ref,i)^2) / (3N))",
                "variables": "N: logged row count, i: T1/T2/T3.",
                "backend_use": "Used by compute_metrics() and displayed in Simulation, Drift, and Retuning results.",
            },
            {
                "title": "Control effort RMS",
                "equation": "control_effort_rms_V = sqrt(sum(u_UW^2 + u_Nip^2 + u_RW^2) / (3N))",
                "variables": "N: logged row count.",
                "backend_use": "Used by compute_metrics() and displayed in Simulation, Drift, and Retuning results.",
            },
            {
                "title": "SysID roller regression",
                "equation": "dv_i/dt = kt_i*(T_{i+1}-T_i + Kmotor_i*u_i/R_i) - kf_i*v_i",
                "variables": "Finite differences from logged rows provide dv_i/dt; kt_i = R_i^2/J_i and kf_i = f_i/J_i.",
                "backend_use": "Used by estimate_parameters() to solve kt_UW, kt_Nip, kt_RW, kf_UW, kf_Nip, and kf_RW.",
            },
            {
                "title": "SysID EA regression",
                "equation": "dT_i/dt - (T_{i-1}v_{i-1} - T_i v_i)/L_i = EA*(v_i - v_{i-1})/L_i",
                "variables": "Finite differences from logged rows provide dT_i/dt; the convective term is subtracted before fitting EA.",
                "backend_use": "Used by estimate_parameters() to solve EA from logged simulation rows.",
            },
            {
                "title": "SysID parameter RMSE",
                "equation": "RMSE_theta = sqrt(mean(relative_error_i^2))",
                "variables": "relative_error_i = (estimate_i - truth_i) / truth_i.",
                "backend_use": "Used by estimate_parameters() and all SysID validation result tables.",
            },
        ],
        "derivation_steps": [
            "Step 1: Compute surface speeds from roller kinematics: v_i = R_i * omega_i.",
            "Step 2: Use Eq. (1) to combine elastic stretch, (EA/L_i)(v_i - v_{i-1}), with convective transport, (T_{i-1}v_{i-1} - T_i v_i)/L_i.",
            "Step 3: Use Eq. (2) to compute surface-speed acceleration from tension difference, friction, inertia, radius, and motor torque.",
            "Step 4: Convert surface-speed acceleration to angular acceleration through domega_i/dt = (dv_i/dt)/R_i.",
            "Step 5: Use Kmotor_i*u_i as the motor torque input supplied to Eq. (2) by the dashboard controller.",
            "Step 6: Concatenate all derivatives in state-vector order and advance the state with RK4.",
            "Step 7: During SysID, rearrange the same one-step equations into least-squares form for the seven estimated parameters.",
        ],
        "tension_dynamics": [
            "dT1/dt = (EA/L1)(v_UW - v0) + (T0*v0 - T1*v_UW)/L1,  T0 = 0",
            "dT2/dt = (EA/L2)(v_Nip - v_UW) + (T1*v_UW - T2*v_Nip)/L2",
            "dT3/dt = (EA/L3)(v_RW - v_Nip) + (T2*v_Nip - T3*v_RW)/L3",
        ],
        "roller_velocity_dynamics": [
            "dv_UW/dt = (R_UW^2/J_UW)(T2 - T1) - (f_UW/J_UW)v_UW + (R_UW/J_UW)(Kmotor_UW*u_UW)",
            "dv_Nip/dt = (R_Nip^2/J_Nip)(T3 - T2) - (f_Nip/J_Nip)v_Nip + (R_Nip/J_Nip)(Kmotor_Nip*u_Nip)",
            "dv_RW/dt = (R_RW^2/J_RW)(T4 - T3) - (f_RW/J_RW)v_RW + (R_RW/J_RW)(Kmotor_RW*u_RW),  T4 = 0",
        ],
        "sysid_parameters": list(PARAMETER_NAMES),
        "units": {
            "T": "N",
            "omega": "rad/s",
            "u": "V",
            "R": "m",
            "L": "m",
            "J": "kg*m^2",
            "kt": "1/kg (paper R^2/J ratio)",
            "kf": "1/s (paper f/J ratio)",
            "Kmotor": "N*m/V",
            "EA": "N",
            "b": "dimensionless process-noise scale",
        },
    }

    summary["equation_register"] = [
        {
            "source": "Paper",
            "number": item["number"],
            "title": item["title"],
            "equation": item["equation"],
            "variables": item["variables"],
            "usage": item["paper_use"],
            "dashboard_note": item["dashboard_note"],
        }
        for item in summary["paper_equations"]
    ] + [
        {
            "source": "System",
            "number": "backend",
            "title": item["title"],
            "equation": item["equation"],
            "variables": item["variables"],
            "usage": item["backend_use"],
            "dashboard_note": "This is a runnable backend equation used by the current dashboard model.",
        }
        for item in summary["backend_equations"]
    ]
    return summary


def as_named_dict(values: Iterable[float], names: Sequence[str]) -> dict[str, float]:
    return {name: float(value) for name, value in zip(names, values)}
