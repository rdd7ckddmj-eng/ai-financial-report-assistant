"""Small helpers for the device-aware product layout.

The browser remains the source of truth for viewport detection.  User-agent
inference is only a first-render fallback while the browser component starts.
"""

from __future__ import annotations


DEVICE_PREFERENCES = ("auto", "mobile", "desktop")
DEVICE_LABELS = {
    "auto": "自动识别",
    "mobile": "手机",
    "desktop": "电脑",
}


def normalise_device_preference(raw: object) -> str:
    """Return one supported device preference, defaulting safely to auto."""
    value = str(raw or "").strip().lower()
    return value if value in DEVICE_PREFERENCES else "auto"


def infer_device_from_user_agent(raw: object) -> str:
    """Infer a conservative first-render mode from an HTTP user-agent."""
    user_agent = str(raw or "").lower()
    mobile_markers = (
        "android",
        "iphone",
        "ipod",
        "mobile",
        "windows phone",
    )
    # iPadOS can advertise itself as Macintosh.  Explicit iPad remains useful
    # for older versions and embedded browsers, while wider tablets will be
    # corrected by the live viewport check in the browser component.
    if "ipad" in user_agent or any(
        marker in user_agent for marker in mobile_markers
    ):
        return "mobile"
    return "desktop"


def effective_device_mode(preference: object, detected: object) -> str:
    """Resolve a manual preference over the browser-detected layout."""
    clean_preference = normalise_device_preference(preference)
    clean_detected = str(detected or "").strip().lower()
    if clean_detected not in {"mobile", "desktop"}:
        clean_detected = "desktop"
    if clean_preference == "auto":
        return clean_detected
    return clean_preference

