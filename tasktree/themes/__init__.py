"""Theme system for tasktree."""

from dataclasses import dataclass


@dataclass
class Theme:
    """Color theme definition."""

    name: str

    # Base colors
    background: str
    background_alt: str
    foreground: str
    foreground_muted: str

    # Border colors
    border: str
    border_focused: str

    # Selection/highlight colors
    highlight_unfocused: str
    highlight_focused: str

    # Accent colors
    accent: str
    accent_alt: str

    # Status colors
    success: str
    warning: str
    error: str

    # Text on highlight
    highlight_text: str


# Default theme (lazygit-inspired)
DEFAULT = Theme(
    name="default",
    background="#111111",
    background_alt="#1c1c1c",
    foreground="#ffffff",
    foreground_muted="#808080",
    border="#444444",
    border_focused="#00d700",
    highlight_unfocused="#303030",
    highlight_focused="#005faf",
    accent="#5fafff",
    accent_alt="#0087ff",
    success="#00d700",
    warning="#ffaf00",
    error="#ff5f5f",
    highlight_text="#ffffff",
)

# VS Code Dark theme
VSCODE_DARK = Theme(
    name="vscode-dark",
    background="#1e1e1e",
    background_alt="#252526",
    foreground="#d4d4d4",
    foreground_muted="#808080",
    border="#3c3c3c",
    border_focused="#007acc",
    highlight_unfocused="#37373d",
    highlight_focused="#094771",
    accent="#007acc",
    accent_alt="#0e639c",
    success="#4ec9b0",
    warning="#dcdcaa",
    error="#f44747",
    highlight_text="#ffffff",
)

# VS Code Light theme
VSCODE_LIGHT = Theme(
    name="vscode-light",
    background="#ffffff",
    background_alt="#f3f3f3",
    foreground="#333333",
    foreground_muted="#6e6e6e",
    border="#e0e0e0",
    border_focused="#007acc",
    highlight_unfocused="#e4e6f1",
    highlight_focused="#007acc",
    accent="#007acc",
    accent_alt="#0066b8",
    success="#008000",
    warning="#795e26",
    error="#d32f2f",
    highlight_text="#ffffff",
)

# Catppuccin Mocha theme
CATPPUCCIN = Theme(
    name="catppuccin",
    background="#1e1e2e",
    background_alt="#313244",
    foreground="#cdd6f4",
    foreground_muted="#6c7086",
    border="#45475a",
    border_focused="#89b4fa",
    highlight_unfocused="#45475a",
    highlight_focused="#89b4fa",
    accent="#89b4fa",
    accent_alt="#74c7ec",
    success="#a6e3a1",
    warning="#f9e2af",
    error="#f38ba8",
    highlight_text="#1e1e2e",
)

# All available themes
THEMES: dict[str, Theme] = {
    "default": DEFAULT,
    "vscode-dark": VSCODE_DARK,
    "vscode-light": VSCODE_LIGHT,
    "catppuccin": CATPPUCCIN,
}

# Theme order for cycling
THEME_ORDER = ["default", "vscode-dark", "vscode-light", "catppuccin"]


def get_theme(name: str) -> Theme:
    """Get a theme by name."""
    return THEMES.get(name, DEFAULT)


def get_next_theme(current: str) -> Theme:
    """Get the next theme in the cycle."""
    try:
        idx = THEME_ORDER.index(current)
        next_idx = (idx + 1) % len(THEME_ORDER)
    except ValueError:
        next_idx = 0
    return THEMES[THEME_ORDER[next_idx]]


def generate_css(theme: Theme) -> str:
    """Generate CSS for a theme."""
    return f"""
/* Theme: {theme.name} */

Screen {{
    background: {theme.background};
}}

#main-container {{
    height: 100%;
    width: 100%;
    background: {theme.background};
}}

#top-panels {{
    height: 1fr;
    min-height: 10;
}}

/* Task panel */
#task-panel {{
    width: 30%;
    min-width: 20;
    border: round {theme.border};
    background: {theme.background};
    padding: 0;
}}

#task-panel:focus-within {{
    border: round {theme.border_focused};
}}

/* Worktree panel */
#worktree-panel {{
    width: 70%;
    border: round {theme.border};
    background: {theme.background};
    padding: 0;
}}

#worktree-panel:focus-within {{
    border: round {theme.border_focused};
}}

/* Status panel */
#status-panel {{
    height: auto;
    min-height: 6;
    max-height: 12;
    border: round {theme.border};
    background: {theme.background};
    padding: 0;
}}

/* Panel titles */
.panel-title {{
    text-style: bold;
    color: {theme.foreground};
    background: transparent;
    text-align: left;
    width: 100%;
    padding: 0 1;
}}

/* Task list */
#task-list {{
    height: 1fr;
    background: {theme.background};
    scrollbar-gutter: stable;
    padding: 0;
}}

#task-list > ListItem {{
    padding: 0 1;
    height: 1;
    background: {theme.background};
    color: {theme.foreground};
}}

#task-list > ListItem.--highlight {{
    background: {theme.highlight_unfocused};
}}

#task-list > ListItem.--highlight .task-item-text {{
    background: {theme.highlight_unfocused};
}}

#task-list:focus > ListItem.--highlight {{
    background: {theme.highlight_focused};
}}

#task-list:focus > ListItem.--highlight .task-item-text {{
    background: {theme.highlight_focused};
}}

.task-item-text {{
    width: 100%;
    background: transparent;
}}

/* Worktree list */
#worktree-list {{
    height: 1fr;
    background: {theme.background};
    scrollbar-gutter: stable;
    padding: 0;
}}

#worktree-list > ListItem {{
    padding: 0 1;
    height: 1;
    background: {theme.background};
    color: {theme.foreground};
}}

#worktree-list > ListItem.--highlight {{
    background: {theme.highlight_unfocused};
}}

#worktree-list > ListItem.--highlight .worktree-item-text {{
    background: {theme.highlight_unfocused};
}}

#worktree-list:focus > ListItem.--highlight {{
    background: {theme.highlight_focused};
}}

#worktree-list:focus > ListItem.--highlight .worktree-item-text {{
    background: {theme.highlight_focused};
}}

.worktree-item-text {{
    width: 100%;
    background: transparent;
}}

/* Status panel styling */
#status-display {{
    height: 100%;
    padding: 0 1;
    background: {theme.background};
    color: {theme.foreground};
}}

/* Header */
Header {{
    background: {theme.background};
    color: {theme.accent};
    text-style: bold;
    dock: top;
    height: 1;
}}

/* Footer */
Footer {{
    background: {theme.background_alt};
}}

FooterKey {{
    background: {theme.background_alt};
    color: {theme.foreground_muted};
}}

FooterKey > .footer-key--key {{
    background: {theme.border};
    color: {theme.accent};
}}

FooterKey > .footer-key--description {{
    color: {theme.foreground_muted};
}}

/* Scrollbar */
Scrollbar {{
    background: {theme.background};
}}

ScrollBar > .scrollbar--bar {{
    background: {theme.border};
}}

ScrollBar > .scrollbar--bar:hover {{
    background: {theme.foreground_muted};
}}

ListItem {{
    height: 1;
}}
"""


def generate_modal_css(theme: Theme) -> str:
    """Generate modal CSS for a theme."""
    return f"""
/* Modal base */
.modal-title {{
    text-align: center;
    text-style: bold;
    color: {theme.foreground};
    margin-bottom: 1;
}}

.modal-container {{
    border: round {theme.border};
    background: {theme.background_alt};
    padding: 1 2;
}}

.section-label {{
    color: {theme.foreground_muted};
    margin-top: 1;
    margin-bottom: 0;
}}

.help-text {{
    color: {theme.foreground};
    margin-bottom: 1;
}}

.modal-message {{
    text-align: center;
    color: {theme.foreground};
    margin-bottom: 1;
}}

.button-row {{
    align: center middle;
    margin-top: 1;
}}

Input {{
    background: {theme.background};
    border: round {theme.border};
    margin-bottom: 1;
}}

SelectionList {{
    height: 12;
    margin-bottom: 1;
    background: {theme.background};
    border: round {theme.border};
}}

Button {{
    margin: 0 1;
    background: {theme.border};
    color: {theme.foreground};
    border: none;
}}

Button:hover {{
    background: {theme.highlight_unfocused};
}}

Button.-primary {{
    background: {theme.accent};
    color: {theme.highlight_text};
}}

Button.-primary:hover {{
    background: {theme.accent_alt};
}}

Button.-error {{
    background: {theme.error};
    color: {theme.highlight_text};
}}
"""
