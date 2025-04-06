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