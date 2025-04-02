# CSS styles for the Streamlit UI

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

# Add more styles here as needed 