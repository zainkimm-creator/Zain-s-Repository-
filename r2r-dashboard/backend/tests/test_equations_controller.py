from math import isfinite

from backend.models.controller import CascadePIController, ControllerConfig
from backend.models.equations import R2RParameters, derivatives, equation_summary, nominal_state, velocities


def test_equation_summary_exposes_required_vectors_and_units():
    summary = equation_summary()
    assert summary["state_vector"] == "x = [T1, T2, T3, omega_UW, omega_Nip, omega_RW]"
    assert summary["input_vector"] == "u = [u_UW, u_Nip, u_RW]"
    assert "EA" in summary["sysid_parameters"]
    assert summary["units"]["kt"] == "1/kg (paper R^2/J ratio)"
    assert len(summary["backend_equations"]) >= 10
    assert len(summary["paper_equations"]) >= 9
    assert len(summary["equation_register"]) == len(summary["paper_equations"]) + len(summary["backend_equations"])
    assert len(summary["theory_summary"]) >= 5
    assert summary["paper_equations"][0]["number"] == "U-0"
    paper_numbers = {item["number"] for item in summary["paper_equations"]}
    assert {"(1)", "(9)", "U-8", "U-10"}.issubset(paper_numbers)
    paper_text = " ".join(item["equation"] for item in summary["paper_equations"])
    assert "J_multi" in paper_text
    assert "tau_min/Tlog >= 5" in paper_text
    assert any("RK4" in step for step in summary["derivation_steps"])


def test_derivatives_are_finite_for_nominal_state():
    params = R2RParameters()
    state = nominal_state(params)
    dx = derivatives(state, [0.0, 0.0, 0.0], params)
    assert len(dx) == 6
    assert all(isfinite(value) for value in dx)
    assert velocities(state, params) == (1.0, 1.0, 1.0)


def test_controller_returns_three_inputs_and_feedforward_terms():
    params = R2RParameters()
    controller = CascadePIController(ControllerConfig(target_tension_N=params.tension_ref_N))
    action = controller.update(nominal_state(params), 0.010, params)
    assert len(action.inputs_V) == 3
    assert len(action.velocity_ref_rad_s) == 3
    assert any(abs(value) > 0 for value in action.feedforward_torque_Nm)
