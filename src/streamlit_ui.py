import streamlit as st

from .prompt_manager import get_prompts
from .database import get_database,Database

class MessageManager:
  def __init__(self):
    self.messages = []
    self.pending_response = False

  def add_message(self, message):
    self.messages.append(message)

def main():
    
  st.set_page_config(page_title="List Pet", page_icon="🐾", layout="wide")

  # Get prompts from local files
  prompts = get_prompts()

  # Get Database: db will be a singleton Database class
  db = get_database()

  if "messages" not in st.session_state:
    st.session_state.messages = db.recover_messages()
    if len(st.session_state.messages) == 0:
      st.session_state.messages.append(prompts.welcome_message) 
      
  if "pending_response" not in st.session_state:
    st.session_state.pending_response = False

  mm = get_message_manager()
  sess = st.session_state

  st.title("🐾 List Pet")
  st.caption("Your friendly SQL assistant")

  # Display chat messages
  for idx, message in enumerate(sess.messages):
    with st.chat_message(message["role"]):
      st.markdown(mm.get_content(message))

      title,err_msg,expanded = mm.get_error(message)
      if title:
        with st.expander(title,expanded=expanded):
          st.code(err_msg)

      title,sql_code,expanded = mm.get_sql(message)
      if title:
        with st.expander(title,expanded=expanded):
          st.code(sql_code)

      title,df,df_key,expanded = mm.get_dataframe(message,sess)
      if title:
        with st.expander(title,expanded=expanded):
          if df:
            st.dataframe(df, use_container_width=True, hide_index=True,
              column_config={ col: st.column_config.Column(width="auto") for col in df.columns })
          else:
             button_clicked = st.button("Regenerate Dataframe", key=f"df_btn_{idx}",
               type="primary", use_container_width=True)
             
      title,chart,chart_key,expanded = mm.get_chart(message,sess)
      if title:
        with st.expander(title,expanded=expanded):
          if chart:
            st.plotly_chart(chart, use_container_width=True, key=chart_key)
          else:
            button_clicked = st.button("Regenerate Chart", key=f"chart_btn_{idx}",
              type="primary", use_container_width=True)

  # Handle Button Clicks
  for idx, message in enumerate(sess.messages):
    if st.session_state.get(f"df_btn_{idx}"):
      st.session_state[f"df_btn_{idx}"] = False
      st.write(f"Regenerating Dataframe for message {idx}...")
      mm.regenerate_dataframe(message, sess)
      # mm call above should do this: message["dataframe"] = new_df
      st.rerun()

    if st.session_state.get(f"chart_btn_{idx}"):
      st.session_state[f"chart_btn_{idx}"] = False
      st.write(f"Regenerating Chart for message {idx}...")
      new_chart = mm.regenerate_chart(message, sess)
      # mm call above should do this: message["chart"] = new_chart
      st.rerun()

  # Handle user input
  if input := st.chat_input("Type your message..."):
    mm.add_message(role="user", content=input)
    st.session_state.pending_response = True
    st.rerun()

  # After rerun, this block executes if pending_response is True
  if st.session_state.pending_response:
    st.session_state.pending_response = False  # Reset flag
    if not handle_immediate_input(input):
      generate_ai_response()
    st.rerun()  # Restart script again to update UI
