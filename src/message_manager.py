import streamlit as st
from .commands import get_logger
from .constants import ASSISTANT_ROLE, USER_ROLE, USER_ACTOR, DATABASE_ACTOR
from .database import get_database
import os
import uuid

class MessageManager:
    """
    Class to manage conversation messages with integrated logging.
    Encapsulates operations on st.session_state.messages.
    """
    
    def __init__(self):
        """Initialize the message manager and ensure session state is set up."""
        self.logger = get_logger()
        self.db = get_database()
        self._initialize_session_state()
    
    def _initialize_session_state(self):
        """Initialize session state messages if they don't exist."""
        if "messages" not in st.session_state:
            # Try to load messages from the database first
            db_messages = self.db.load_messages()
            if db_messages:
                print(f"DEBUG - Loaded {len(db_messages)} messages from database")
                st.session_state.messages = db_messages
            else:
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
        # Also log to database
        self.db.log_message(message)
    
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
    
    def add_database_message(self, content, dataframe=None, query_text=None):
        """Add a database message to the conversation."""
        formatted_content = f"{DATABASE_ACTOR}:\n{content}"
        message = {"role": USER_ROLE, "content": formatted_content}
        
        # If a dataframe is provided, store it
        if dataframe is not None:
            # Generate a unique ID for the dataframe
            df_id = str(uuid.uuid4())
            
            # Create metadata about the dataframe
            metadata = {
                "columns": dataframe.columns.tolist(),
                "shape": dataframe.shape,
            }
            
            # Add sample data (first few rows) to metadata for preview
            try:
                # Get first 5 rows as dict records
                sample_rows = dataframe.head(5).to_dict(orient='records')
                metadata["sample_data"] = sample_rows
            except Exception as e:
                print(f"Error creating sample data: {e}")
            
            # Store the dataframe directly in the message
            message["dataframe"] = dataframe
            message["dataframe_metadata"] = metadata
            
            # Store in data_artifacts table
            if query_text:
                self.db.store_data_artifact(
                    message_id=len(st.session_state.messages),  # Current message index
                    artifact_type="dataframe",
                    metadata=metadata,
                    query_text=query_text
                )
        
        # Add query_text if provided
        if query_text is not None:
            message["query_text"] = query_text
        
        self.add_message(message)
        return message
    
    def add_plot_message(self, dataframe, figure, plot_index=0, plot_spec=None, query_text=None):
        """Add a plot message to the conversation."""
        # Get the current message count for a unique ID
        message_count = len(st.session_state.messages)
        plot_msg_id = f"plot_{message_count}_{plot_index}"
        
        # Create metadata about the dataframe
        metadata = {}
        if dataframe is not None:
            metadata = {
                "columns": dataframe.columns.tolist(),
                "shape": dataframe.shape,
            }
            
            # Add sample data (first few rows) to metadata for preview
            try:
                # Get first 5 rows as dict records
                sample_rows = dataframe.head(5).to_dict(orient='records')
                metadata["sample_data"] = sample_rows
            except Exception as e:
                print(f"Error creating sample data: {e}")
        
        # Add plot specification to metadata
        if plot_spec:
            metadata["plot_spec"] = plot_spec
        
        # Create a descriptive title for the plot
        plot_title = "Plot created successfully"
        if plot_spec and "title" in plot_spec:
            plot_title = f"Plot: {plot_spec['title']}"
        
        message = {
            "role": USER_ROLE, 
            "content": f"{DATABASE_ACTOR}:\n{plot_title}", 
            "dataframe": dataframe,
            "figure": figure,
            "plot_index": plot_index,
            "plot_msg_id": plot_msg_id,
            "plot_metadata": metadata
        }
        
        # Store plot specification and query text for potential regeneration
        if plot_spec:
            message["plot_spec"] = plot_spec
        if query_text:
            message["query_text"] = query_text
        
        # Store in data_artifacts table
        if query_text:
            self.db.store_data_artifact(
                message_id=len(st.session_state.messages),  # Current message index
                artifact_type="plot",
                metadata=metadata,
                query_text=query_text
            )
        
        self.add_message(message)
        return message
    
    def add_map_message(self, dataframe, map_figure, map_index=0, map_spec=None, query_text=None):
        """Add a map message to the conversation."""
        # Get the current message count for a unique ID
        message_count = len(st.session_state.messages)
        map_msg_id = f"map_{message_count}_{map_index}"
        
        # Create metadata about the dataframe
        metadata = {}
        if dataframe is not None:
            metadata = {
                "columns": dataframe.columns.tolist(),
                "shape": dataframe.shape,
            }
            
            # Add sample data (first few rows) to metadata for preview
            try:
                # Get first 5 rows as dict records
                sample_rows = dataframe.head(5).to_dict(orient='records')
                metadata["sample_data"] = sample_rows
            except Exception as e:
                print(f"Error creating sample data: {e}")
        
        # Add map specification to metadata
        if map_spec:
            metadata["map_spec"] = map_spec
        
        # Create a descriptive title for the map
        map_title = "Map created successfully"
        if map_spec and "title" in map_spec:
            map_title = f"Map: {map_spec['title']}"
        
        message = {
            "role": USER_ROLE, 
            "content": f"{DATABASE_ACTOR}:\n{map_title}", 
            "dataframe": dataframe,
            "map_figure": map_figure,
            "map_index": map_index,
            "map_msg_id": map_msg_id,
            "map_metadata": metadata
        }
        
        # Store map specification and query text for potential regeneration
        if map_spec:
            message["map_spec"] = map_spec
        if query_text:
            message["query_text"] = query_text
        
        # Store in data_artifacts table
        if query_text:
            self.db.store_data_artifact(
                message_id=len(st.session_state.messages),  # Current message index
                artifact_type="map",
                metadata=metadata,
                query_text=query_text
            )
        
        self.add_message(message)
        return message

def get_message_manager():
    """Get or create the message manager instance."""
    if "message_manager" not in st.session_state:
        st.session_state.message_manager = MessageManager()
    return st.session_state.message_manager 