from src.device_experience import (
    effective_device_mode,
    infer_device_from_user_agent,
    normalise_device_preference,
)


def test_device_preference_defaults_to_auto() -> None:
    assert normalise_device_preference(None) == "auto"
    assert normalise_device_preference("projector") == "auto"
    assert normalise_device_preference(" MOBILE ") == "mobile"


def test_user_agent_inference_handles_phone_and_desktop() -> None:
    assert infer_device_from_user_agent("Mozilla/5.0 (iPhone; Mobile)") == (
        "mobile"
    )
    assert infer_device_from_user_agent("Mozilla/5.0 (Linux; Android 15)") == (
        "mobile"
    )
    assert infer_device_from_user_agent("Mozilla/5.0 (Macintosh; Intel Mac)") == (
        "desktop"
    )


def test_manual_preference_overrides_detected_mode() -> None:
    assert effective_device_mode("auto", "mobile") == "mobile"
    assert effective_device_mode("desktop", "mobile") == "desktop"
    assert effective_device_mode("mobile", "desktop") == "mobile"

