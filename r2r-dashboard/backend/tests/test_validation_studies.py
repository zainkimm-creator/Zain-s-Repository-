from pathlib import Path

from backend.validation.studies import drift_study, excitation_study, logging_rate_study, retuning_study


def test_logging_rate_study_generates_plot_and_noisy_window_check():
    result = logging_rate_study([1, 10, 20])
    assert Path(result["plot_path"]).exists()
    assert result["metrics"]["supports_noisy_optimum_near_10_20ms"] is True


def test_excitation_study_identifies_multi_channel_profile_under_noise():
    result = excitation_study()
    assert Path(result["plot_path"]).exists()
    assert result["metrics"]["supports_multi_channel_or_toggle_under_noise"] is True


def test_drift_study_identifies_j_drift_as_dominant():
    result = drift_study()
    assert Path(result["plot_path"]).exists()
    assert result["metrics"]["supports_J_drift_dominance"] is True


def test_retuning_study_reports_hgs_bo5_with_fewer_real_evaluations():
    result = retuning_study()
    assert Path(result["plot_path"]).exists()
    assert result["metrics"]["supports_HGS_BO5_fewer_real_evaluations_than_CS_BO30"] is True
