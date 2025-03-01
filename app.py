import streamlit as st
import os
from chat import ChatEngine, get_chat_engine
from database import Database, get_database
from parse import parse_markup

# Initialize session state
if "message_log" not in st.session_state:
    with open('prompts/first.txt', 'r') as f:
        first_message = f.read()
    st.session_state.message_log = []
    parsed_first_message = parse_markup(first_message).get("display", [])
    rendered_first_message = "\n".join(item['text'] for item in parsed_first_message)
    st.session_state.message_log.append({
        "internal": {"role": "ai", "content": first_message},
        "display": {"role": "ai", "content": rendered_first_message}
    })

# UI Setup
st.title("🐇 List Pet")
st.caption("📋 An AI Data Assistant (instead of a spreadsheet!)")

# Initialize components first
selected_model = "gpt-4o-mini"  # Default model
chat_engine = get_chat_engine(selected_model)
db = get_database()

with st.sidebar:
    st.header("⚙️ Configuration")
    selected_model = st.selectbox(
        "Choose a model",
        ["gpt-4o-mini"],
        index=0
    )
    show_internal = st.checkbox("Show internal messages", value=False)
    show_prompt = st.checkbox("Show Current Prompt", value=False)
    
    if show_prompt:
        st.subheader("Current Prompt")
        prompt_chain = chat_engine.build_prompt_chain(st.session_state.message_log)
        messages = prompt_chain.format_messages()
        
        # Convert messages to displayable format
        prompt_json = [
            {
                "type": msg.type,
                "content": msg.content
            }
            for msg in messages
        ]
        
        # Display the entire prompt as a single JSON object
        st.json(prompt_json)

# Display chat history
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

# Handle new messages
if user_query := st.chat_input("Type your question here..."):
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
        prompt_chain = chat_engine.build_prompt_chain(st.session_state.message_log)
        
        # If showing internal messages, stream to a separate chat message
        if show_internal:
            with st.chat_message("internal"):
                internal_container = st.empty()
                internal_response = ""
                for chunk in chat_engine.generate_response_stream(prompt_chain):
                    full_response += chunk
                    internal_response += chunk
                    internal_container.markdown(internal_response)
        else:
            # Otherwise just collect the response without streaming
            for chunk in chat_engine.generate_response_stream(prompt_chain):
                full_response += chunk

    # Process the AI response
    parsed_response = chat_engine.parse_response(full_response)
    
    # Process SQL blocks and collect display text
    sql_errors = []
    display_text = []
    
    # Handle SQL execution
    for block in parsed_response.get("sql", []):
        if sql := block.get("query"):
            df, error = db.execute_query(sql)
            if error:
                sql_errors.append(error)
            if df is not None:
                st.dataframe(df)
    
    # Collect display text
    for item in parsed_response.get("display", []):
        display_text.append(item['text'])
    
    final_display = "\n\n".join(display_text)
    if sql_errors:
        final_display += "\n\n⚠️ SQL Errors:\n" + "\n".join(sql_errors)
    
    # Show the AI's response
    with st.chat_message("ai"):
        st.markdown(final_display)
    
    # Update message history
    st.session_state.message_log.append({
        "internal": {"role": "ai", "content": full_response},
        "display": {"role": "ai", "content": final_display}
    })
    
    # Clear pending query and trigger rerun to update prompt display
    del st.session_state.pending_query
    st.rerun()
