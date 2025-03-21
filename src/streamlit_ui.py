import duckdb
import streamlit as st
import re
from langchain_core.prompts import (
    SystemMessagePromptTemplate,
    HumanMessagePromptTemplate,
    AIMessagePromptTemplate,
    ChatPromptTemplate
)
from langchain_openai import ChatOpenAI
from langchain_core.output_parsers import StrOutputParser

from .prompt_loader import get_prompts
from .database import Database
from .parsing import get_elements, SQL_REGEX

# Define roles
USER_ROLE = "user"
ASSISTANT_ROLE = "assistant"
SYSTEM_ROLE = "system"

def add_message(role, content, db):
    message = {"role": role, "content": content}
    st.session_state.db_messages.append(message)
    db.log_message(message)
    if role == USER_ROLE:
        st.session_state.lc_messages.append(HumanMessagePromptTemplate.from_template(content))
    elif role == ASSISTANT_ROLE:
        st.session_state.lc_messages.append(AIMessagePromptTemplate.from_template(content))
    elif role == SYSTEM_ROLE:
        st.session_state.lc_messages.append(SystemMessagePromptTemplate.from_template(content))
            
def init_session_state(sess,db):
    if "prompts" not in sess:
        sess.prompts = get_prompts()
    if "lc_messages" not in sess:
        sess.prompt_sequence = [
            AIMessagePromptTemplate.from_template(sess.prompts["system_prompt"])
        ]
    if "conn" not in sess:
        sess.conn = duckdb.connect('db/list_pet.db')
        db.initialize_pet_meta_schema()
    if "lc_messages" not in sess:
        sess.lc_messages = []
    if "db_messages" not in sess:
        sess.db_messages = db.load_messages()            
    if len(sess.db_messages) == 0:
        add_message(role=SYSTEM_ROLE, content=sess.prompts["welcome_message"], db=db)
    if "pending_chart" not in sess:
        sess.pending_chart = False
    if "pending_sql" not in sess:
        sess.pending_sql = False
    if "pending_response" not in sess:
        sess.pending_response = False

def is_expanded(idx):
    if f"expanded_{idx}" not in st.session_state:
        st.session_state[f"expanded_{idx}"] = False  # Initialize if not present
    return st.session_state[f"expanded_{idx}"]

def toggle_expander(idx):
    st.session_state[f"expanded_{idx}"] = not st.session_state[f"expanded_{idx}"]

def title_text(input):
    # trim the input to 60 characters, append ellipsis if trimmed
    return input[:60] + "..." if len(input) > 60 else input

def main():
    db = Database()
    sess = st.session_state
    init_session_state(sess,db)

    st.set_page_config(page_title="List Pet", page_icon="🐾", layout="wide")
    st.title("🐾 List Pet")
    st.caption("Your friendly SQL assistant")

    # Display chat messages
    for idx, message in enumerate(sess.db_messages):
        with st.chat_message(message["role"]):
            msg = get_elements(message["content"])
            
            st.markdown(msg["markdown"]) if "markdown" in msg

            if "sql" in msg:
                for item in msg["sql"]:
                    with st.expander(title_text(item["content"]),
                                    expanded=is_expanded(idx),
                                    on_change=lambda idx=idx: toggle_expander(idx)):
                        st.code(item["content"])

            if "dataframe" in msg:
                for item in msg["dataframe"]:
                    content = item["content"]
                    attributes = item["attributes"]
                    if not "name" in attributes:
                        st.error("Dataframe must have a name")
                        continue
                    with st.expander(title_text(attributes["name"]),
                                        expanded=is_expanded(idx),
                                        on_change=lambda idx=idx: toggle_expander(idx)):
                        key = "dataframe_" + attributes["name"]
                        if key in sess:
                            df = sess[key]  
                            st.dataframe(df, use_container_width=True, hide_index=True)
                        else:
                            msg_idx = attributes["msg_idx"]
                            tag_idx = attributes["tag_idx"]
                            sql = sess.db_messages[msg_idx]["content"][tag_idx]
                            sess[f"df_btn_{idx}_sql"] = sql
                            button_clicked = st.button(
                                "Regenerate Dataframe",
                                key=f"df_btn_{idx}",
                                type="primary",
                                use_container_width=True,
                            )

            if msg["error"]:
                with st.expander(title_text(msg["error"]), 
                                 expanded=is_expanded(idx), 
                                 on_change=lambda idx=idx: toggle_expander(idx)):
                    st.code(msg["error"])


            # title, chart, chart_key = get_chart(message, sess)
            # if title:
            #     with st.expander(title, expanded=is_expanded(idx), on_change=lambda idx=idx: toggle_expander(idx)):
            #         if chart:
            #             st.plotly_chart(chart, use_container_width=True, key=chart_key)
            #         else:
            #             button_clicked = st.button(
            #                 "Regenerate Chart",
            #                 key=f"chart_btn_{idx}",
            #                 type="primary",
            #                 use_container_width=True,
            #             )

    # Handle Button Clicks
    for idx, message in enumerate(sess.db_messages):
        msg = get_elements(message["content"])

        if sess.get(f"df_btn_{idx}"):
            sess[f"df_btn_{idx}"] = False
            sql = sess[f"df_btn_{idx}_sql"]
            df,err = db.execute_query(sql)
            if err:
                print(f"ERROR - {err} for dataframe {attributes['name']} while rerunning SQL: {sql} ")
            else:
                sess["dataframe_" + attributes["name"]] = df
                st.rerun()

        # if sess.get(f"chart_btn_{idx}"):
        #     sess[f"chart_btn_{idx}"] = False
        #     st.write(f"Regenerating Chart for message {idx}...")
        #     new_chart = regenerate_chart(message, sess)
        #     st.rerun()

    if sess.pending_sql:
        # pop one sql message from the list, process it, then rerun()
        sql_tuple = sess.pending_sql.pop(0)
        df,err = db.execute_query(sql_tuple[1])
        if df:
            tsv_output = []
            tsv_output.append("\t".join(df.columns))
            for idx, (_, row) in enumerate(df.iterrows()):
                if idx >= 5 and len(df) > 20:
                    tsv_output.append("...")
                    break
                tsv_output.append("\t".join(str(val) for val in row))
            table_name = err # 2nd return of execute_query CAN be the table name (awkward)
            # msg_idx below is the index of the message in the db_messages list, which
            # must be the last message in the list at this point
            msg_idx = len(sess.db_messages) - 1
            content = f'<dataframe name="{table_name}" msg_idx="{msg_idx}" tag_idx="{sql_tuple[0]}" >\n'
            content += "\n".join(tsv_output) + "\n"
            content += "</dataframe>\n"
            add_message(role=USER_ROLE, content=content, db=db)
            sess["dataframe_" + table_name] = df
            st.rerun()
        elif err:
            content = f"<error>\n{err}\n</error>\n"
            add_message(role=USER_ROLE, content=content, db=db)
            st.rerun()

    # if sess.pending_chart:
    #     chart = sess.pending_chart.pop(0)
    #     # response = generate_chart(chart)
    #     # add_message(role=USER_ROLE, content=response)
    #     # st.rerun()

    if sess.pending_response:
        sess.pending_response = False
        llm = ChatOpenAI(model="gpt-4o-mini", temperature=0.0)
        prompt_template = ChatPromptTemplate.from_messages(sess.lc_messages)
        processing_pipeline = prompt_template | llm | StrOutputParser()
        response = "".join(processing_pipeline.stream({}))
        msg = get_elements(response)
        add_message(role=ASSISTANT_ROLE, content=msg["markdown"], db=db)
        sess.pending_sql = list(enumerate(msg["sql"]))
        sess.pending_chart = list(enumerate(msg["chart"]))       
        st.rerun()
        
    if input := st.chat_input("Type your message..."):
        add_message(role=USER_ROLE, content=input, db=db)
        sess.pending_response = True
        if re.match(SQL_REGEX, input.strip(), re.IGNORECASE):
            input = "<sql>\n" + input + "\n</sql>\n"
        msg = get_elements(input)
        sess.pending_sql = msg["sql"]
        st.rerun()
