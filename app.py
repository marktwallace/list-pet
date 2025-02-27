import streamlit as st
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import (
    SystemMessagePromptTemplate,
    HumanMessagePromptTemplate,
    AIMessagePromptTemplate,
    ChatPromptTemplate
)
from langchain_openai import ChatOpenAI
import os
from parse import parse_markup
openai_api_key = os.getenv("OPENAI_API_KEY")

st.title("🐇 List Pet")
st.caption("📋 An AI Data Assistant (instead of a spreadsheet!)")

# Sidebar configuration
with st.sidebar:
    st.header("⚙️ Configuration")
    selected_model = st.selectbox(
        "Choose a model",
        ["gpt-4o-mini"],
        index=0
    )
    show_internal = st.checkbox("Show internal messages", value=False)
    
# Initiate the chat engine
llm_engine = ChatOpenAI(
    model=selected_model,
    temperature=0.0
)

# System prompt configuration
with open('prompts/system.txt', 'r') as f:
    system_template = f.read()
system_prompt = SystemMessagePromptTemplate.from_template(system_template)

# Session state management
if "message_log" not in st.session_state:
    with open('prompts/first.txt', 'r') as f:
        first_message = f.read()
    st.session_state.dataframes = {}
    st.session_state.tables = {}
    st.session_state.message_log = []
    parsed_first_message = parse_markup(first_message).get("display", [])
    rendered_first_message = "\n".join(item['text'] for item in parsed_first_message)
    st.session_state.message_log.append({
        "internal": {"role": "ai", "content": first_message},
        "display": {"role": "ai", "content": rendered_first_message}
    })

# Chat container
chat_container = st.container()

# Display chat messages
with chat_container:
    for message in st.session_state.message_log:
        if message["display"]["role"] == "ai":
            if show_internal:
                with st.chat_message("internal"):
                    st.markdown(message["internal"]["content"])
            with st.chat_message(message["display"]["role"]):
                st.markdown(message["display"]["content"])
        else:
            with st.chat_message(message["display"]["role"]):
                st.markdown(message["display"]["content"])

# Chat input and processing
user_query = st.chat_input("Type your coding question here...")

def generate_ai_response_stream(prompt_chain):
    """Streams AI response token by token"""
    processing_pipeline = prompt_chain | llm_engine | StrOutputParser()
    return processing_pipeline.stream({})

def build_prompt_chain():
    prompt_sequence = [system_prompt]
    for msg in st.session_state.message_log:
        if msg["internal"]["role"] == "user":
            prompt_sequence.append(HumanMessagePromptTemplate.from_template(msg["internal"]["content"]))
        elif msg["internal"]["role"] == "ai":
            prompt_sequence.append(AIMessagePromptTemplate.from_template(msg["internal"]["content"]))
    return ChatPromptTemplate.from_messages(prompt_sequence)

if user_query:
    # Save the new query in session_state so it shows immediately
    st.session_state.pending_query = user_query
    st.session_state.message_log.append({
        "internal": {"role": "user", "content": user_query},
        "display": {"role": "user", "content": user_query}
    })
    st.rerun()

if "pending_query" in st.session_state:
    with st.chat_message("ai"):
        response_container = st.empty()  # Placeholder for streaming response
        full_response = ""

        with st.spinner("🧠 Processing..."):
            prompt_chain = build_prompt_chain()
            for chunk in generate_ai_response_stream(prompt_chain):
                full_response += chunk
                response_container.markdown(full_response)  # Update message live

        # Store final AI response
        parsed_response = parse_markup(full_response).get("display", [])
        rendered_response = "\n".join(item['text'] for item in parsed_response)
        st.session_state.message_log.append({
            "internal": {"role": "ai", "content": full_response},
            "display": {"role": "ai", "content": rendered_response}
        })
    
    # Clear the pending flag
    del st.session_state.pending_query
    st.rerun()
