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
    print("Processing pending query...")  # Debug print 1
    with st.chat_message("ai"):
        response_container = st.empty()
        full_response = ""

        with st.spinner("🧠 Processing..."):
            prompt_chain, variables = build_prompt_chain()
            for chunk in generate_ai_response_stream(prompt_chain, variables):  # Pass variables here
                full_response += chunk
                response_container.markdown(full_response)

        # First store the complete internal response
        print("Parsing response...")  # Debug print 2
        parsed_response = parse_markup(full_response)
        print(f"Found SQL blocks: {len(parsed_response.get('sql', []))}")  # Debug print 3
        message_index = len(st.session_state.message_log)
        st.session_state.message_log.append({
            "internal": {"role": "ai", "content": full_response},
            "display": {"role": "ai", "content": "Processing SQL..."}
        })

        # Then process SQL blocks
        sql_errors = []
        print(f"SQL blocks content: {parsed_response.get('sql', [])}")
        for block in parsed_response.get("sql", []):
            print(f"Processing block: {block}")
            sql = block.get("query", "")
            df_name = block.get("df")
            
            print(f"Extracted SQL: '{sql}', df_name: '{df_name}'")
            
            if sql:
                print(f"Running SQL: {sql}")
                try:
                    result = st.session_state.duckdb_connection.execute(sql)
                    if df_name:
                        print(f"Storing result in dataframe: {df_name}")
                        st.session_state.dataframes[df_name] = result.df()
                except Exception as e:
                    print(f"SQL Error: {str(e)}")
                    sql_errors.append(f"SQL Error: {str(e)}")

        # Finally, update the display portion with results
        display_text = "\n".join(item['text'] for item in parsed_response.get("display", []))
        if sql_errors:
            display_text += "\n\n⚠️ SQL Errors:\n" + "\n".join(sql_errors)
        
        # Update the stored message with final display content
        st.session_state.message_log[message_index]["display"]["content"] = display_text
    
    # Clear the pending flag
    del st.session_state.pending_query
    st.rerun()
