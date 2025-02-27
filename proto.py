import streamlit as st
import duckdb
import json
from langchain_openai import ChatOpenAI
from langchain.prompts import ChatPromptTemplate
from langchain.output_parsers import StructuredOutputParser, ResponseSchema

# ----- CONFIGURATION -----
OPENAI_API_KEY = "your-api-key-here"  # Replace with your actual API key

# ----- SETUP LANGCHAIN -----
# Define the expected JSON schema for the AI response
schemas = [
    ResponseSchema(name="reasoning", description="Explanation of AI's reasoning."),
    ResponseSchema(name="actions", description="List of SQL actions to execute."),
    ResponseSchema(name="display", description="User-facing response."),
]

# Create a structured output parser from the schema
parser = StructuredOutputParser.from_response_schemas(schemas)

# This step ensures the LLM is explicitly instructed to return structured JSON.
# LangChain automatically appends a system prompt that includes format instructions.
format_instructions = parser.get_format_instructions()

# Create a prompt template that informs the LLM about the task and format.
prompt = ChatPromptTemplate.from_messages([
    ("system", "You are an AI data assistant that translates user requests into SQL."),
    ("user", "{user_input}"),
    ("assistant", format_instructions)  # <-- This tells the LLM to return JSON!
])

# Initialize OpenAI LLM with JSON-friendly output
llm = ChatOpenAI(model="gpt-4o", temperature=0, openai_api_key=OPENAI_API_KEY)

# ----- STREAMLIT APP UI -----
st.title("AI-Powered SQL Assistant")
st.write("Type a request, and I'll generate the SQL for you.")

# Store chat history
if "messages" not in st.session_state:
    st.session_state.messages = []

# Display chat history
for msg in st.session_state.messages:
    st.chat_message(msg["role"]).write(msg["content"])

# Handle user input
if user_input := st.chat_input("Ask me to work with your data..."):
    st.session_state.messages.append({"role": "user", "content": user_input})
    st.chat_message("user").write(user_input)

    # Format the prompt for the LLM
    formatted_prompt = prompt.format(user_input=user_input)

    # Generate response from LLM
    response = llm.predict(formatted_prompt)

    # Ensure output is valid JSON
    try:
        structured_response = parser.parse(response)
    except json.JSONDecodeError:
        structured_response = {"reasoning": "Error parsing AI output.", "actions": [], "display": "Something went wrong."}

    # Add assistant response to history
    st.session_state.messages.append({"role": "assistant", "content": structured_response["display"]})
    st.chat_message("assistant").write(structured_response["display"])

    # Display AI reasoning
    with st.expander("AI Reasoning"):
        st.write(structured_response["reasoning"])

    # Execute SQL actions if any
    if "actions" in structured_response and structured_response["actions"]:
        con = duckdb.connect(database=":memory:")  # Using in-memory DuckDB
        for action in structured_response["actions"]:
            if action["type"] == "sql":
                try:
                    con.execute(action["query"])
                    st.success(f"Executed SQL:\n\n```sql\n{action['query']}\n```")
                except Exception as e:
                    st.error(f"SQL Error: {e}")

    # Display the SQL queries generated by AI
    with st.expander("Generated SQL Queries"):
        for action in structured_response["actions"]:
            if action["type"] == "sql":
                st.code(action["query"], language="sql")
