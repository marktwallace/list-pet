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
import duckdb

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
    #print("system.txt:", system_template)
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

# Ensure db directory exists
os.makedirs("db", exist_ok=True)

# Create/connect to database in db directory
if 'duckdb_connection' not in st.session_state:
    st.session_state.duckdb_connection = duckdb.connect('db/list_pet.db')

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

def generate_ai_response_stream(prompt_chain, variables):
    """Streams AI response token by token"""
    processing_pipeline = prompt_chain | llm_engine | StrOutputParser()
    return processing_pipeline.stream(variables)

def build_prompt_chain():
    prompt_sequence = [system_prompt]
    # Create a variables dict for the template
    variables = {}
    
    # Add any dataframes from previous queries
    if hasattr(st.session_state, 'dataframes'):
        variables.update(st.session_state.dataframes)
    
    for msg in st.session_state.message_log:
        if msg["internal"]["role"] == "user":
            prompt_sequence.append(HumanMessagePromptTemplate.from_template(msg["internal"]["content"]))
        elif msg["internal"]["role"] == "ai":
            prompt_sequence.append(AIMessagePromptTemplate.from_template(msg["internal"]["content"]))
    
    template = ChatPromptTemplate.from_messages(prompt_sequence)
    return template, variables  # Return both template and variables

if user_query:
    # Save the new query in session_state so it shows immediately
    st.session_state.pending_query = user_query
    st.session_state.message_log.append({
        "internal": {"role": "user", "content": user_query},
        "display": {"role": "user", "content": user_query}
    })
    st.rerun()

if "pending_query" in st.session_state:
    print("Processing pending query...")
    full_response = ""

    with st.spinner("🧠 Processing..."):
        prompt_chain, variables = build_prompt_chain()
        
        # If showing internal messages, stream to a separate chat message
        if show_internal:
            with st.chat_message("internal"):
                internal_container = st.empty()
                internal_response = ""
                for chunk in generate_ai_response_stream(prompt_chain, variables):
                    full_response += chunk
                    internal_response += chunk
                    internal_container.markdown(internal_response)
        else:
            # Otherwise just collect the response without streaming
            for chunk in generate_ai_response_stream(prompt_chain, variables):
                full_response += chunk

    # Process the AI response
    parsed_response = parse_markup(full_response)
    
    # Process SQL blocks and store results
    sql_errors = []
    for block in parsed_response.get("sql", []):
        sql = block.get("query", "")
        df_name = block.get("df")
        
        if sql:
            try:
                result = st.session_state.duckdb_connection.execute(sql)
                if df_name:
                    df = result.df()
                    st.session_state.dataframes[df_name] = df
            except Exception as e:
                sql_errors.append(f"SQL Error: {str(e)}")

    # Show only the display content, not the reasoning and SQL
    display_text = []
    for item in parsed_response.get("display", []):
        display_text.append(item['text'])
    
    final_display = "\n\n".join(display_text)
    if sql_errors:
        final_display += "\n\n⚠️ SQL Errors:\n" + "\n".join(sql_errors)
        
    # Show the AI's response in its own chat message
    with st.chat_message("ai"):
        # Show just the display content
        st.markdown(final_display)
        
        # Display any dataframes from SQL queries that specified a df attribute
        for block in parsed_response.get("sql", []):
            if block.get("df"):  # Only if df was specified
                df_name = block["df"]
                if df_name in st.session_state.dataframes:
                    st.dataframe(st.session_state.dataframes[df_name])

    # Store the response in message history
    st.session_state.message_log.append({
        "internal": {"role": "ai", "content": full_response},
        "display": {"role": "ai", "content": final_display}
    })
    
    # Clear the pending flag without triggering a rerun
    if "pending_query" in st.session_state:
        del st.session_state.pending_query
