# CSS styles for the Streamlit UI

# Icons
TRAIN_ICON = "🚃"

# Style for text wrapping in code blocks
CODE_WRAP_STYLE = """
<style>
/* Handle pre elements */
.stMarkdown pre,
.element-container pre,
div[data-testid="stMarkdownContainer"] pre {
    white-space: pre-wrap !important;
    word-wrap: break-word !important;
    overflow-wrap: break-word !important;
}

/* Handle code containers */
.stCode,
div[data-testid="stMarkdownContainer"] .stCode {
    overflow-x: visible !important;
    white-space: pre-wrap !important;
}

/* Handle the code element itself */
.stCode code,
div[data-testid="stMarkdownContainer"] code {
    white-space: pre-wrap !important;
    word-wrap: break-word !important;
}
</style>
"""

# Style for conversation buttons in sidebar
CONVERSATION_BUTTON_STYLE = """
<style>
/* Left align text in all conversation buttons by default */
.stButton button div[data-testid="stMarkdownContainer"] {
    text-align: left !important;
    width: 100% !important;
}

/* Ensure consistent padding in buttons */
.stButton button {
    padding: 0.5rem !important;
    width: 100% !important;
}

/* Style for new conversation button */
.element-container.st-key-new-conversation-button button {
    background-color: #00cc66 !important;
    border-color: #00cc66 !important;
    color: white !important;
    text-align: center !important;
}

/* Hover state for all buttons */
.stButton button:hover {
    background-color: #00b359 !important;
    border-color: #00b359 !important;
    color: white !important;
}

/* Active conversation button style */
.stButton button[kind="primary"] {
    background-color: #00cc66 !important;
    border-color: #00cc66 !important;
    color: white !important;
}

/* Center text ONLY in new conversation button */
.element-container.st-key-new-conversation-button button div[data-testid="stMarkdownContainer"] {
    text-align: center !important;
    width: 100% !important;
    display: block !important;
}

/* Override any other text alignment for this specific button */
.element-container.st-key-new-conversation-button button div[data-testid="stMarkdownContainer"] p,
.element-container.st-key-new-conversation-button button div[data-testid="stMarkdownContainer"] * {
    text-align: center !important;
}

/* Chat message avatar size */
.stChatMessage img {
    width: 48px !important;
    height: 48px !important;
}

/* Message background consistency */
[data-testid="stChatMessageContent"] {
    background-color: transparent !important;
}

/* Target the specific message containers */
.stChatMessage {
    background-color: transparent !important;
}

/* Target the user message container specifically */
.stChatMessage[data-testid="user-message"] {
    background-color: transparent !important;
}

/* Target any potential wrapper divs */
.stChatMessage > div,
.stChatMessage [data-testid="stChatMessageContent"] > div {
    background-color: transparent !important;
}

/* Ensure chat message containers have dark background */
.stChatMessage [data-testid="chatAvatarIcon-user"],
.stChatMessage [data-testid="chatAvatarIcon-assistant"] {
    background-color: transparent !important;
}

/* Trim button styling */
button[data-testid="baseButton-secondary"]:has(div:contains("✂️")) {
    background-color: #ff4444 !important;
    border-color: #ff4444 !important;
    color: white !important;
    width: 80px !important;  /* Fixed width */
    min-width: unset !important;
    padding: 0.5rem 0.25rem !important;
}

button[data-testid="baseButton-secondary"]:has(div:contains("✂️")):hover {
    background-color: #cc0000 !important;
    border-color: #cc0000 !important;
}

/* Center text in trim button */
button[data-testid="baseButton-secondary"]:has(div:contains("✂️")) div[data-testid="stMarkdownContainer"] {
    text-align: center !important;
    width: 100% !important;
}
</style>
"""

# Add more styles here as needed 

# Style for message action buttons (copy, thumbs up, thumbs down, edit)
MESSAGE_ACTION_BUTTONS_STYLE = """
<style>
/* Targeting the Streamlit button's container */
div[data-testid="stButton"] > button {
    /* Making the button more compact */
    padding: 0.1rem 0.5rem;
    font-size: 0.9rem;
}

/* Specifically target the action buttons via their titles */
div[data-testid="stButton"] > button[title="Copy message content"],
div[data-testid="stButton"] > button[title="Thumbs up"],
div[data-testid="stButton"] > button[title="Thumbs down"],
div[data-testid="stButton"] > button[title="Edit message"] {
    font-size: 1.1rem; /* Increase emoji size */
    padding: 0.1rem 0.2rem; /* Tighter padding for emojis */
}
</style>
"""

FEEDBACK_BUTTON_STYLE = """
    <style>
        /* --- Feedback Button Styling --- */

        /* General transition for a smoother feel */
        div[data-testid="stButton"] > button[title="Thumbs up"],
        div[data-testid="stButton"] > button[title="Thumbs down"] {
            transition: all 0.2s ease-in-out;
            border-radius: 8px;
        }

        /* UNSELECTED (Secondary) state */
        div[data-testid="stButton"] > button[data-testid="baseButton-secondary"][title="Thumbs up"],
        div[data-testid="stButton"] > button[data-testid="baseButton-secondary"][title="Thumbs down"] {
            background-color: transparent;
            opacity: 0.5; /* Make them faded */
        }

        /* HOVER on UNSELECTED */
        div[data-testid="stButton"] > button[data-testid="baseButton-secondary"][title="Thumbs up"]:hover,
        div[data-testid="stButton"] > button[data-testid="baseButton-secondary"][title="Thumbs down"]:hover {
            opacity: 1;
            transform: scale(1.1);
        }

        /* SELECTED (Primary) state - Override Streamlit's default green */
        div[data-testid="stButton"] > button[data-testid="baseButton-primary"][title="Thumbs up"],
        div[data-testid="stButton"] > button[data-testid="baseButton-primary"][title="Thumbs down"] {
            background-color: transparent !important;
            border: 1px solid #4A90E2 !important; /* Blue border */
            transform: scale(1.1);
            opacity: 1;
            box-shadow: 0 0 8px rgba(74, 144, 226, 0.5); /* Blue glow */
        }
    </style>
"""

CONTINUE_AI_PLAN_BUTTON_STYLE = """
<style>
/* Styling for the action buttons */
button[key="continue_ai_plan_button"],
button[key="fix_error_button"] {
    background-color: #00cc66 !important;
    border-color: #00cc66 !important;
    color: white !important;
}

/* Hover effect for both buttons */
button[key="continue_ai_plan_button"]:hover,
button[key="fix_error_button"]:hover {
    background-color: #00b359 !important;
    border-color: #00b359 !important;
    color: white !important;
}

/* Additional selectors for better specificity */
div.stButton button[data-testid="baseButton-primary"][key="continue_ai_plan_button"],
div.stButton button[data-testid="baseButton-primary"][key="fix_error_button"] {
    background-color: #00cc66 !important;
    border-color: #00cc66 !important;
}

div.stButton button[data-testid="baseButton-primary"][key="continue_ai_plan_button"]:hover,
div.stButton button[data-testid="baseButton-primary"][key="fix_error_button"]:hover {
    background-color: #00b359 !important;
    border-color: #00b359 !important;
}
</style>
"""

# IMPROVED: Custom HTML button styles with high specificity
ACTION_BUTTON_STYLES = """
<style>
/* --- DEBUG: Very obvious test styles --- */
.action-button {
    background-color: red !important; /* DEBUG: Should be very obvious if working */
    border: 3px solid yellow !important;
    color: white !important;
    font-size: 1.1rem !important;
    padding: 0.4rem !important;
    border-radius: 0.5rem !important;
    transition: all 0.2s ease-in-out !important;
    width: 2.5em !important;
    height: 2.5em !important;
    display: inline-flex !important;
    justify-content: center !important;
    align-items: center !important;
    cursor: pointer !important;
    margin: 0 2px !important;
    box-sizing: border-box !important;
    font-family: "Source Sans Pro", sans-serif !important;
}

.action-button:hover {
    color: rgba(250, 250, 250, 1); /* Full opacity on hover */
    border-color: rgb(70, 75, 95); /* Lighter border on hover */
    transform: scale(1.05);
    background-color: rgb(49, 51, 63); /* Slightly lighter background on hover */
}

.action-button.selected {
    background-color: #4A90E2;
    border-color: #4A90E2;
    color: white;
    opacity: 1;
    transform: scale(1.05);
    box-shadow: 0 0 10px rgba(74, 144, 226, 0.4);
    animation: buttonSelect 0.3s ease-out;
}

.action-button.selected:hover {
    background-color: #3A7BC8;
    border-color: #3A7BC8;
    transform: scale(1.08);
}

/* Animation for selected state */
@keyframes buttonSelect {
    0% { transform: scale(1); }
    50% { transform: scale(1.1); }
    100% { transform: scale(1.05); }
}

/* Copy button styling (keeping this separate from action buttons) */
.copy-button {
    background-color: blue !important; /* DEBUG: Should be very obvious */
    border: 3px solid orange !important;
    color: white !important;
    cursor: pointer !important;
    font-size: 1.1rem !important;
    padding: 0.4rem !important;
    border-radius: 0.5rem !important;
    line-height: 1 !important;
    transition: all 0.2s ease-in-out !important;
    width: 2.5em !important;
    height: 2.5em !important;
    display: inline-flex !important;
    justify-content: center !important;
    align-items: center !important;
    margin: 0 2px !important;
    box-sizing: border-box !important;
    font-family: "Source Sans Pro", sans-serif !important;
}

.copy-button:hover {
    color: rgba(250, 250, 250, 1); /* Full opacity on hover */
    border-color: rgb(70, 75, 95);
    transform: scale(1.05);
    background-color: rgb(49, 51, 63);
}
</style>
"""

# Subtle appearance for in-message action buttons (▲ ▼ ✎)
SUBTLE_ACTION_BUTTON_STYLE = """
<style>
/* Force square buttons with very high specificity */
.main .block-container div[data-testid='stButton'] button[title="Thumbs up"],
.main .block-container div[data-testid='stButton'] button[title="Thumbs down"],
.main .block-container div[data-testid='stButton'] button[title="Edit message"],
div[data-testid='stVerticalBlock'] div[data-testid='stButton'] button[title="Thumbs up"],
div[data-testid='stVerticalBlock'] div[data-testid='stButton'] button[title="Thumbs down"],
div[data-testid='stVerticalBlock'] div[data-testid='stButton'] button[title="Edit message"],
.stChatMessage div[data-testid='stButton'] button[title="Thumbs up"],
.stChatMessage div[data-testid='stButton'] button[title="Thumbs down"],
.stChatMessage div[data-testid='stButton'] button[title="Edit message"] {
    background: transparent !important;
    border: none !important;
    font-size: 0.9rem !important;
    opacity: 0.35 !important;
    padding: 0 !important;
    margin: 0 !important;
    line-height: 1 !important;
    transition: opacity 0.2s ease, transform 0.2s ease !important;
    width: 2rem !important;
    height: 2rem !important;
    min-width: 2rem !important;
    max-width: 2rem !important;
    min-height: 2rem !important;
    max-height: 2rem !important;
    display: inline-flex !important;
    justify-content: center !important;
    align-items: center !important;
    box-sizing: border-box !important;
    border-radius: 4px !important;
}

/* Force square buttons for selected state */
.main .block-container div[data-testid='stButton'] button[data-testid='baseButton-primary'][title="Thumbs up"],
.main .block-container div[data-testid='stButton'] button[data-testid='baseButton-primary'][title="Thumbs down"],
div[data-testid='stVerticalBlock'] div[data-testid='stButton'] button[data-testid='baseButton-primary'][title="Thumbs up"],
div[data-testid='stVerticalBlock'] div[data-testid='stButton'] button[data-testid='baseButton-primary'][title="Thumbs down"],
.stChatMessage div[data-testid='stButton'] button[data-testid='baseButton-primary'][title="Thumbs up"],
.stChatMessage div[data-testid='stButton'] button[data-testid='baseButton-primary'][title="Thumbs down"] {
    background-color: #2f8df9 !important;
    border: none !important;
    color: white !important;
    opacity: 1 !important;
    width: 2rem !important;
    height: 2rem !important;
    min-width: 2rem !important;
    max-width: 2rem !important;
    min-height: 2rem !important;
    max-height: 2rem !important;
    display: inline-flex !important;
    justify-content: center !important;
    align-items: center !important;
    box-sizing: border-box !important;
    border-radius: 4px !important;
}

/* Hover effects with high specificity */
.main .block-container div[data-testid='stButton'] button[title="Thumbs up"]:hover,
.main .block-container div[data-testid='stButton'] button[title="Thumbs down"]:hover,
.main .block-container div[data-testid='stButton'] button[title="Edit message"]:hover,
div[data-testid='stVerticalBlock'] div[data-testid='stButton'] button[title="Thumbs up"]:hover,
div[data-testid='stVerticalBlock'] div[data-testid='stButton'] button[title="Thumbs down"]:hover,
div[data-testid='stVerticalBlock'] div[data-testid='stButton'] button[title="Edit message"]:hover,
.stChatMessage div[data-testid='stButton'] button[title="Thumbs up"]:hover,
.stChatMessage div[data-testid='stButton'] button[title="Thumbs down"]:hover,
.stChatMessage div[data-testid='stButton'] button[title="Edit message"]:hover {
    opacity: 0.9 !important;
    transform: scale(1.1) !important;
}
</style>
"""

