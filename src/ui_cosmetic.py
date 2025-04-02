import streamlit as st

def _inject_styles():
    if "_styled_ui_css" not in st.session_state:
        st.markdown("""
        <style>
        .styled-neutral {
            background-color: #f0f2f6 !important;
            color: #222 !important;
            border: 1px solid #ccc !important;
            border-radius: 6px !important;
        }
        .styled-neutral:hover {
            background-color: #e0e0e0 !important;
        }

        .styled-active {
            background-color: #28a745 !important;
            color: white !important;
            border: none !important;
            border-radius: 6px !important;
        }
        .styled-active:hover {
            background-color: #218838 !important;
        }

        .styled-warn {
            background-color: #ffc107 !important;
            color: black !important;
            border: none !important;
            border-radius: 6px !important;
        }
        .styled-warn:hover {
            background-color: #e0a800 !important;
        }

        .styled-danger {
            background-color: #dc3545 !important;
            color: white !important;
            border: none !important;
            border-radius: 6px !important;
        }
        .styled-danger:hover {
            background-color: #c82333 !important;
        }

        .styled-ghost {
            background-color: transparent !important;
            color: #444 !important;
            border: 1px dashed #aaa !important;
            border-radius: 6px !important;
        }
        .styled-ghost:hover {
            background-color: #f5f5f5 !important;
        }

        /* For toggle styling */
        div[data-testid="stToggle"] > label[data-testid="stWidgetLabel"] > div {
            background-color: #28a745 !important;
        }
        </style>
        """, unsafe_allow_html=True)
        st.session_state._styled_ui_css = True

def styled_button(label: str, key: str = None, style: str = "neutral", use_container_width=False) -> bool:
    """
    A styled button with visual options.
    
    style: one of ["neutral", "active", "warn", "danger", "ghost"]
    """
    _inject_styles()
    clicked = st.button(label, key=key, use_container_width=use_container_width)
    st.markdown(f"""
    <script>
    const buttons = window.parent.document.querySelectorAll('button');
    for (const btn of buttons) {{
        if (btn.innerText === `{label}`) {{
            btn.classList.add('styled-{style}');
        }}
    }}
    </script>
    """, unsafe_allow_html=True)
    return clicked

def styled_toggle(label: str, key: str, value: bool = False) -> bool:
    """
    A visually consistent toggle that avoids red background when 'on'.
    """
    _inject_styles()
    if key not in st.session_state:
        st.session_state[key] = value
    st.session_state[key] = st.toggle(label, value=st.session_state[key], key=key)
    return st.session_state[key]
