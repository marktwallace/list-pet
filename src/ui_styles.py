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
/* Very aggressive targeting - multiple selector approaches */

/* Target by exact key matches */
button[key="copy_1"], button[key="copy_2"], button[key="copy_3"], button[key="copy_4"], button[key="copy_5"],
button[key="copy_6"], button[key="copy_7"], button[key="copy_8"], button[key="copy_9"], button[key="copy_10"],
button[key^="copy_"], button[key^="thumbs_up_"], button[key^="thumbs_down_"], button[key^="edit_"],
.stButton button[key^="copy_"], .stButton button[key^="thumbs_up_"], 
.stButton button[key^="thumbs_down_"], .stButton button[key^="edit_"] {
    background-color: transparent !important;
    background: none !important;
    border: 1px solid transparent !important;
    box-shadow: none !important;
    color: #666 !important;
    padding: 4px 8px !important;
    font-size: 14px !important;
    min-height: 32px !important;
    height: 32px !important;
    width: 40px !important;
    min-width: 40px !important;
    border-radius: 6px !important;
    transition: all 0.2s ease !important;
    margin: 1px !important;
    opacity: 0.5 !important;
}

/* Hover states */
button[key^="copy_"]:hover, button[key^="thumbs_up_"]:hover, 
button[key^="thumbs_down_"]:hover, button[key^="edit_"]:hover,
.stButton button[key^="copy_"]:hover, .stButton button[key^="thumbs_up_"]:hover,
.stButton button[key^="thumbs_down_"]:hover, .stButton button[key^="edit_"]:hover {
    background-color: rgba(100, 100, 100, 0.15) !important;
    background: rgba(100, 100, 100, 0.15) !important;
    color: #aaa !important;
    border: 1px solid transparent !important;
    box-shadow: none !important;
    opacity: 1 !important;
}

/* Focus states */
button[key^="copy_"]:focus, button[key^="thumbs_up_"]:focus,
button[key^="thumbs_down_"]:focus, button[key^="edit_"]:focus {
    border: 1px solid transparent !important;
    box-shadow: none !important;
    outline: none !important;
}

/* Target secondary buttons more generally */
button[data-testid="baseButton-secondary"] {
    background-color: transparent !important;
    border: 1px solid transparent !important;
    box-shadow: none !important;
    opacity: 0.5 !important;
}

button[data-testid="baseButton-secondary"]:hover {
    background-color: rgba(100, 100, 100, 0.15) !important;
    border: 1px solid transparent !important;
    box-shadow: none !important;
    opacity: 1 !important;
}

/* Style button containers to reduce spacing */
.stButton {
    margin: 0 !important;
    padding: 0 !important;
}

/* Target button content */
.stButton button div[data-testid="stMarkdownContainer"] {
    text-align: center !important;
    margin: 0 !important;
    padding: 0 !important;
}

.stButton button div[data-testid="stMarkdownContainer"] p {
    margin: 0 !important;
    padding: 0 !important;
    font-size: 14px !important;
}

/* Alternative approach - target all buttons in chat message areas */
.stChatMessage .stButton button {
    background-color: transparent !important;
    border: 1px solid transparent !important;
    box-shadow: none !important;
    opacity: 0.5 !important;
}

.stChatMessage .stButton button:hover {
    background-color: rgba(100, 100, 100, 0.15) !important;
    opacity: 1 !important;
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