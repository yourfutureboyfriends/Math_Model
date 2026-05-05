"""
Theme Configuration Module

Handles theme persistence, system detection, and session management.
"""

import json
import platform
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Literal, Optional

import streamlit as st

# Config file location
CONFIG_DIR = Path.home()
CONFIG_FILE = CONFIG_DIR / ".macro_research_theme.json"


def get_system_theme() -> Literal["dark", "light"]:
    """Detect system theme preference."""
    system = platform.system()

    try:
        if system == "Darwin":  # macOS
            result = subprocess.run(
                ["defaults", "read", "-g", "AppleInterfaceStyle"],
                capture_output=True,
                text=True,
                timeout=2
            )
            return "dark" if "Dark" in result.stdout else "light"
        elif system == "Windows":
            import winreg
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                               r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize") as key:
                value, _ = winreg.QueryValueEx(key, "AppsUseLightTheme")
                return "light" if value == 1 else "dark"
        else:  # Linux
            result = subprocess.run(
                ["gsettings", "get", "org.gnome.desktop.interface", "gtk-theme"],
                capture_output=True,
                text=True,
                timeout=2
            )
            return "dark" if "dark" in result.stdout.lower() else "light"
    except Exception:
        return "dark"  # Default fallback


def load_theme() -> dict:
    """Load theme configuration from file."""
    default_config = {
        "theme": "dark",
        "auto_detect": True,
        "last_updated": datetime.now().isoformat()
    }

    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE) as f:
                config = json.load(f)
                # Validate required fields
                if "theme" not in config:
                    config["theme"] = default_config["theme"]
                if "auto_detect" not in config:
                    config["auto_detect"] = default_config["auto_detect"]
                return config
        except (json.JSONDecodeError, IOError):
            pass

    return default_config


def save_theme(theme: Literal["dark", "light"], auto_detect: bool = False) -> None:
    """Save theme configuration to file."""
    config = {
        "theme": theme,
        "auto_detect": auto_detect,
        "last_updated": datetime.now().isoformat()
    }

    try:
        with open(CONFIG_FILE, "w") as f:
            json.dump(config, f, indent=2)
    except IOError as e:
        st.warning(f"Could not save theme preference: {e}")


def init_theme() -> Literal["dark", "light"]:
    """Initialize theme from config or system preference.

    Returns the active theme ("dark" or "light").
    """
    # Check if already initialized in session state
    if "theme_initialized" in st.session_state:
        return st.session_state.get("theme", "dark")

    # Load from config file
    config = load_theme()

    # Determine theme
    if config.get("auto_detect", True):
        theme = get_system_theme()
    else:
        theme = config.get("theme", "dark")

    # Store in session state
    st.session_state["theme"] = theme
    st.session_state["theme_initialized"] = True
    st.session_state["auto_detect_theme"] = config.get("auto_detect", True)

    return theme


def get_current_theme_name() -> Literal["dark", "light"]:
    """Get current theme from session state."""
    if "theme" not in st.session_state:
        return init_theme()
    return st.session_state.get("theme", "dark")


def toggle_theme() -> Literal["dark", "light"]:
    """Toggle between dark and light themes.

    Returns the new theme.
    """
    current = get_current_theme_name()
    new_theme = "light" if current == "dark" else "dark"

    # Update session state
    st.session_state["theme"] = new_theme
    st.session_state["auto_detect_theme"] = False

    # Save to config
    save_theme(new_theme, auto_detect=False)

    return new_theme


def set_theme(theme: Literal["dark", "light"], auto_detect: bool = False) -> None:
    """Set theme explicitly.

    Args:
        theme: "dark" or "light"
        auto_detect: Whether to use system preference
    """
    if auto_detect:
        theme = get_system_theme()

    st.session_state["theme"] = theme
    st.session_state["auto_detect_theme"] = auto_detect
    save_theme(theme, auto_detect)


def get_theme_toggle_button_html(current_theme: str) -> str:
    """Generate HTML for theme toggle button.

    Args:
        current_theme: Current theme name ("dark" or "light")

    Returns:
        HTML string for the toggle button
    """
    is_dark = current_theme == "dark"
    icon = "🌙" if is_dark else "☀️"
    label = "Dark" if is_dark else "Light"
    bg_color = "#1F2937" if is_dark else "#F1F5F9"
    text_color = "#E5E7EB" if is_dark else "#0F172A"
    border_color = "#374151" if is_dark else "#E2E8F0"

    return f"""
    <div style="
        display: inline-flex;
        align-items: center;
        gap: 8px;
        background: {bg_color};
        border: 1px solid {border_color};
        border-radius: 6px;
        padding: 6px 12px;
        font-size: 13px;
        font-weight: 500;
        color: {text_color};
        cursor: pointer;
        transition: all 0.2s ease;
    ">
        <span style="font-size: 14px;">{icon}</span>
        <span>{label}</span>
    </div>
    """
