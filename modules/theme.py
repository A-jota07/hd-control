DARK_CSS = """
window, dialog, .main-window {
    background-color: #09090b;
    color: #fafafa;
    font-family: "Inter", "Cantarell", "Noto Sans", sans-serif;
}

.sidebar {
    background-color: #111114;
    border-right: 1px solid #27272a;
}

.topbar {
    background-color: #111114;
    border-bottom: 1px solid #27272a;
    padding: 12px 20px;
}

.card {
    background-color: #141418;
    border: 1px solid #27272a;
    border-radius: 8px;
    padding: 10px 14px;
}

.card-highlight {
    background-color: #18181c;
    border: 1px solid #e4e4e7;
    border-radius: 8px;
    padding: 10px 14px;
}

.stat-value {
    font-size: 20px;
    font-weight: 800;
    color: #ffffff;
}

.stat-label {
    font-size: 10px;
    font-weight: 600;
    color: #a1a1aa;
    letter-spacing: 0.5px;
}

notebook {
    background-color: transparent;
    border: none;
}

notebook tab {
    padding: 6px 14px;
    background-color: #18181c;
    color: #a1a1aa;
    font-weight: 600;
    border: 1px solid #27272a;
    border-bottom: none;
    border-top-left-radius: 6px;
    border-top-right-radius: 6px;
}

notebook tab:checked {
    background-color: #ffffff;
    color: #09090b;
    font-weight: 700;
    border-color: #ffffff;
}

.section-title {
    font-size: 16px;
    font-weight: 700;
    color: #ffffff;
}

.subtitle {
    font-size: 12px;
    color: #a1a1aa;
}

.mono {
    font-family: "IBM Plex Mono", "JetBrains Mono", "Monospace", monospace;
    font-size: 12px;
}

button {
    background-image: none;
    background-color: #1c1c21;
    color: #f4f4f5;
    border: 1px solid #3f3f46;
    border-radius: 6px;
    padding: 7px 14px;
    font-weight: 600;
    box-shadow: none;
    text-shadow: none;
}

button:hover {
    background-color: #27272a;
    border-color: #71717a;
}

button:active {
    background-color: #3f3f46;
}

button.primary-btn {
    background-color: #ffffff;
    color: #09090b;
    border: 1px solid #ffffff;
    font-weight: 700;
}

button.primary-btn:hover {
    background-color: #e4e4e7;
    border-color: #e4e4e7;
}

button.danger-btn {
    background-color: #18181b;
    color: #fafafa;
    border: 1px dashed #71717a;
}

button.danger-btn:hover {
    background-color: #ffffff;
    color: #000000;
    border: 1px solid #ffffff;
}

button.nav-btn {
    background-color: transparent;
    color: #a1a1aa;
    border: 1px solid transparent;
    border-radius: 6px;
    padding: 10px 14px;
    font-weight: 600;
}

button.nav-btn:hover {
    background-color: #18181c;
    color: #ffffff;
}

button.nav-btn-active {
    background-color: #ffffff;
    color: #09090b;
    border: 1px solid #ffffff;
    border-radius: 6px;
    padding: 10px 14px;
    font-weight: 700;
}

entry, combobox button, spinbutton, textview, textview text {
    background-image: none;
    background-color: #09090b;
    color: #fafafa;
    border: 1px solid #3f3f46;
    border-radius: 6px;
    padding: 6px 10px;
}

entry:focus, textview:focus {
    border-color: #ffffff;
}

treeview.view {
    background-color: #111114;
    color: #f4f4f5;
}

treeview.view:selected {
    background-color: #ffffff;
    color: #09090b;
}

treeview.view header button {
    background-color: #18181c;
    color: #a1a1aa;
    font-weight: 700;
    border: none;
    border-bottom: 1px solid #27272a;
    border-right: 1px solid #27272a;
    padding: 8px 10px;
}

.badge-dark {
    background-color: #ffffff;
    color: #09090b;
    border-radius: 4px;
    padding: 2px 8px;
    font-size: 11px;
    font-weight: 700;
}

.badge-outline {
    background-color: #18181c;
    color: #e4e4e7;
    border: 1px solid #52525b;
    border-radius: 4px;
    padding: 2px 8px;
    font-size: 11px;
    font-weight: 600;
}

.status-bar {
    background-color: #111114;
    border-top: 1px solid #27272a;
    padding: 8px 18px;
    font-size: 12px;
    color: #a1a1aa;
}
"""

LIGHT_CSS = """
window, dialog, .main-window {
    background-color: #fafafa;
    color: #09090b;
    font-family: "Inter", "Cantarell", "Noto Sans", sans-serif;
}

.sidebar {
    background-color: #f4f4f5;
    border-right: 1px solid #d4d4d8;
}

.topbar {
    background-color: #ffffff;
    border-bottom: 1px solid #d4d4d8;
    padding: 12px 20px;
}

.card {
    background-color: #ffffff;
    border: 1px solid #d4d4d8;
    border-radius: 8px;
    padding: 10px 14px;
}

.card-highlight {
    background-color: #ffffff;
    border: 2px solid #09090b;
    border-radius: 8px;
    padding: 10px 14px;
}

.stat-value {
    font-size: 20px;
    font-weight: 800;
    color: #09090b;
}

.stat-label {
    font-size: 10px;
    font-weight: 600;
    color: #52525b;
    letter-spacing: 0.5px;
}

notebook {
    background-color: transparent;
    border: none;
}

notebook tab {
    padding: 6px 14px;
    background-color: #e4e4e7;
    color: #52525b;
    font-weight: 600;
    border: 1px solid #d4d4d8;
    border-bottom: none;
    border-top-left-radius: 6px;
    border-top-right-radius: 6px;
}

notebook tab:checked {
    background-color: #09090b;
    color: #ffffff;
    font-weight: 700;
    border-color: #09090b;
}

.section-title {
    font-size: 16px;
    font-weight: 700;
    color: #09090b;
}

.subtitle {
    font-size: 12px;
    color: #52525b;
}

.mono {
    font-family: "IBM Plex Mono", "JetBrains Mono", "Monospace", monospace;
    font-size: 12px;
}

button {
    background-image: none;
    background-color: #ffffff;
    color: #09090b;
    border: 1px solid #a1a1aa;
    border-radius: 6px;
    padding: 7px 14px;
    font-weight: 600;
    box-shadow: none;
    text-shadow: none;
}

button:hover {
    background-color: #f4f4f5;
    border-color: #09090b;
}

button:active {
    background-color: #e4e4e7;
}

button.primary-btn {
    background-color: #09090b;
    color: #ffffff;
    border: 1px solid #09090b;
    font-weight: 700;
}

button.primary-btn:hover {
    background-color: #27272a;
    border-color: #27272a;
}

button.danger-btn {
    background-color: #ffffff;
    color: #09090b;
    border: 1px dashed #52525b;
}

button.danger-btn:hover {
    background-color: #09090b;
    color: #ffffff;
    border: 1px solid #09090b;
}

button.nav-btn {
    background-color: transparent;
    color: #52525b;
    border: 1px solid transparent;
    border-radius: 6px;
    padding: 10px 14px;
    font-weight: 600;
}

button.nav-btn:hover {
    background-color: #e4e4e7;
    color: #09090b;
}

button.nav-btn-active {
    background-color: #09090b;
    color: #ffffff;
    border: 1px solid #09090b;
    border-radius: 6px;
    padding: 10px 14px;
    font-weight: 700;
}

entry, combobox button, spinbutton, textview, textview text {
    background-image: none;
    background-color: #ffffff;
    color: #09090b;
    border: 1px solid #a1a1aa;
    border-radius: 6px;
    padding: 6px 10px;
}

entry:focus, textview:focus {
    border-color: #09090b;
}

treeview.view {
    background-color: #ffffff;
    color: #09090b;
}

treeview.view:selected {
    background-color: #09090b;
    color: #ffffff;
}

treeview.view header button {
    background-color: #f4f4f5;
    color: #27272a;
    font-weight: 700;
    border: none;
    border-bottom: 1px solid #d4d4d8;
    border-right: 1px solid #d4d4d8;
    padding: 8px 10px;
}

.badge-dark {
    background-color: #09090b;
    color: #ffffff;
    border-radius: 4px;
    padding: 2px 8px;
    font-size: 11px;
    font-weight: 700;
}

.badge-outline {
    background-color: #f4f4f5;
    color: #09090b;
    border: 1px solid #71717a;
    border-radius: 4px;
    padding: 2px 8px;
    font-size: 11px;
    font-weight: 600;
}

.status-bar {
    background-color: #f4f4f5;
    border-top: 1px solid #d4d4d8;
    padding: 8px 18px;
    font-size: 12px;
    color: #52525b;
}
"""
