""""""
from textual.theme import BUILTIN_THEMES, Theme


__all__ = ("BUILTIN_THEMES", "GALAXY_THEME")

GALAXY_THEME = Theme(
    name="galaxy",
    primary="#C45AFF",
    secondary="#A684E8",
    warning="#FFD700",
    error="#FF4500",
    success="#00FA9A",
    accent="#FF69B4",
    background="#0F0F1F",
    surface="#1E1E3F",
    panel="#2D2B55",
    dark=True,
    variables={
        "input-cursor-background": "#C45AFF",
        "footer-background": "transparent",
    },
)
