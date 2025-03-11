import streamlit as st
from .commands import get_logger
from .constants import ASSISTANT_ROLE, USER_ROLE, USER_ACTOR, DATABASE_ACTOR

class MessageManager:
    """
    Class to manage conversation messages with integrated logging.
    Encapsulates operations on st.session_state.messages.
    """
    
    def __init__(self):
        """Initialize the message manager and ensure session state is set up."""
        self.logger = get_logger()
        self._initialize_session_state()
    
    def _initialize_session_state(self):
        """Initialize session state messages if they don't exist."""
        if "messages" not in st.session_state:
            st.session_state.messages = []
            
            # Add the first assistant message if available
            try:
                with open('prompts/first.txt', 'r') as f:
                    first_message = f.read()
                self.add_assistant_message(first_message)
            except Exception as e:
                print(f"ERROR - Failed to load first message: {str(e)}")
    
    def get_messages(self):
        """Get all messages in the conversation."""
        return st.session_state.messages
    
    def add_message(self, message):
        """Add a message to the conversation and log it."""
        st.session_state.messages.append(message)
        self.logger.log_message(message)
    
    def add_user_message(self, content):
        """Add a user message to the conversation."""
        formatted_content = f"{USER_ACTOR}: {content}"
        message = {"role": USER_ROLE, "content": formatted_content}
        self.add_message(message)
        return message
    
    def add_assistant_message(self, content):
        """Add an assistant message to the conversation."""
        message = {"role": ASSISTANT_ROLE, "content": content}
        self.add_message(message)
        return message
    
    def add_database_message(self, content, dataframe=None):
        """Add a database message to the conversation."""
        formatted_content = f"{DATABASE_ACTOR}:\n{content}"
        message = {"role": USER_ROLE, "content": formatted_content}
        if dataframe is not None:
            message["dataframe"] = dataframe
        self.add_message(message)
        return message
    
    def add_plot_message(self, dataframe, figure, plot_index=0):
        """Add a plot message to the conversation."""
        # Get the current message count for a unique ID
        message_count = len(st.session_state.messages)
        plot_msg_id = f"plot_{message_count}_{plot_index}"
        message = {
            "role": USER_ROLE, 
            "content": f"{DATABASE_ACTOR}:\nPlot created successfully", 
            "dataframe": dataframe,
            "figure": figure,
            "plot_index": plot_index,
            "plot_msg_id": plot_msg_id
        }
        self.add_message(message)
        return message
    
    def add_map_message(self, dataframe, map_figure, map_index=0):
        """Add a map message to the conversation."""
        # Get the current message count for a unique ID
        message_count = len(st.session_state.messages)
        map_msg_id = f"map_{message_count}_{map_index}"
        message = {
            "role": USER_ROLE, 
            "content": f"{DATABASE_ACTOR}:\nMap created successfully", 
            "dataframe": dataframe,
            "map_figure": map_figure,
            "map_index": map_index,
            "map_msg_id": map_msg_id
        }
        self.add_message(message)
        return message

def get_message_manager():
    """Get or create the message manager instance."""
    if "message_manager" not in st.session_state:
        st.session_state.message_manager = MessageManager()
    return st.session_state.message_manager 