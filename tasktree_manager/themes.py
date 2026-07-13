"""Textual themes for tasktree-manager.

Palettes come from the "TaskTree-Manager design system" Claude Design
project (tokens/colors.css + tokens/themes.css): the Tokyo Night shape —
panels darker than the screen ground, accent focus border, selection bar,
keycap footer chips — carrying six palettes. The default "tasktree" theme
is the lazygit-classic ANSI palette; the other five override Textual's
built-in themes of the same name so the design's exact layering and
selection colors apply.

Token contract (design token → Textual token):
    --tt-bg → $background · --tt-panel → $panel (panel body, darker)
    --tt-surface → $surface (inputs, lists, chips)
    --tt-border → $border-blurred · --tt-border-focus → $border/$accent
    --tt-sel-* → $block-cursor-* · footer chips → $footer-*

All app styling references these tokens only, so every registered theme
(and any remaining Textual built-in) re-skins the whole UI.
"""

from textual.theme import Theme

# Order the `t` binding cycles through (design ui_kit: lazygit-classic first,
# then the popular palettes; the extra catppuccin flavors are Textual built-ins)
THEME_CYCLE = [
    "tasktree",
    "tokyo-night",
    "catppuccin-mocha",
    "catppuccin-macchiato",
    "catppuccin-frappe",
    "catppuccin-latte",
    "gruvbox",
    "dracula",
    "nord",
]


def _design_theme(
    name: str,
    *,
    bg: str,
    panel: str,
    surface: str,
    border: str,
    focus: str,
    text: str,
    dim: str,
    red: str,
    green: str,
    yellow: str,
    blue: str,
    cyan: str,
    sel_bg: str,
    sel_fg: str,
    sel_blurred: str,
) -> Theme:
    """Build a Theme from the design system's token set."""
    return Theme(
        name=name,
        primary=focus,  # identity color: primary buttons, palette highlights
        secondary=blue,
        accent=focus,
        warning=yellow,
        error=red,
        success=green,
        foreground=text,
        background=bg,
        surface=surface,
        panel=panel,
        dark=True,
        variables={
            # Focused panels take the accent border; blurred ones stay dim
            "border": focus,
            "border-blurred": border,
            # Selection bar: themed block when focused, faint when not
            "block-cursor-background": sel_bg,
            "block-cursor-foreground": sel_fg,
            "block-cursor-text-style": "bold",
            "block-cursor-blurred-background": sel_blurred,
            "block-cursor-blurred-foreground": text,
            # Keycap footer chips: cyan key letter on a surface chip
            "footer-background": panel,
            "footer-key-foreground": cyan,
            "footer-key-background": surface,
            "footer-description-foreground": dim,
            # Dark label text on accent-filled primary buttons
            "button-color-foreground": panel,
        },
    )


TASKTREE_THEME = _design_theme(
    "tasktree",  # lazygit-classic ANSI palette (design default)
    bg="#131313",
    panel="#0c0c0c",
    surface="#1c1c1c",
    border="#3f3f3f",
    focus="#87d787",
    text="#c8c8c8",
    dim="#585858",
    red="#d75f5f",
    green="#87d787",
    yellow="#d7af5f",
    blue="#5f87d7",
    cyan="#5fd7d7",
    sel_bg="#1c2c44",
    sel_fg="#ffffff",
    sel_blurred="#161616",
)

ALL_THEMES = [
    TASKTREE_THEME,
    _design_theme(
        "tokyo-night",
        bg="#1a1b26",
        panel="#16161e",
        surface="#1f2335",
        border="#3b4261",
        focus="#7aa2f7",
        text="#c0caf5",
        dim="#565f89",
        red="#f7768e",
        green="#9ece6a",
        yellow="#e0af68",
        blue="#7aa2f7",
        cyan="#7dcfff",
        sel_bg="#283457",
        sel_fg="#c0caf5",
        sel_blurred="#20223a",
    ),
    _design_theme(
        "catppuccin-mocha",
        bg="#1e1e2e",
        panel="#181825",
        surface="#313244",
        border="#45475a",
        focus="#cba6f7",
        text="#cdd6f4",
        dim="#6c7086",
        red="#f38ba8",
        green="#a6e3a1",
        yellow="#f9e2af",
        blue="#89b4fa",
        cyan="#94e2d5",
        sel_bg="#313244",
        sel_fg="#cdd6f4",
        sel_blurred="#24243a",
    ),
    _design_theme(
        "gruvbox",
        bg="#282828",
        panel="#1d2021",
        surface="#3c3836",
        border="#504945",
        focus="#fe8019",
        text="#ebdbb2",
        dim="#928374",
        red="#fb4934",
        green="#b8bb26",
        yellow="#fabd2f",
        blue="#83a598",
        cyan="#8ec07c",
        sel_bg="#3c3836",
        sel_fg="#fbf1c7",
        sel_blurred="#32302f",
    ),
    _design_theme(
        "dracula",
        bg="#282a36",
        panel="#21222c",
        surface="#343746",
        border="#44475a",
        focus="#bd93f9",
        text="#f8f8f2",
        dim="#6272a4",
        red="#ff5555",
        green="#50fa7b",
        yellow="#f1fa8c",
        blue="#8be9fd",
        cyan="#8be9fd",
        sel_bg="#44475a",
        sel_fg="#f8f8f2",
        sel_blurred="#2e3040",
    ),
    _design_theme(
        "nord",
        bg="#2e3440",
        panel="#272c36",
        surface="#3b4252",
        border="#4c566a",
        focus="#88c0d0",
        text="#d8dee9",
        dim="#616e88",
        red="#bf616a",
        green="#a3be8c",
        yellow="#ebcb8b",
        blue="#81a1c1",
        cyan="#88c0d0",
        sel_bg="#3b4252",
        sel_fg="#eceff4",
        sel_blurred="#333947",
    ),
]
