from langchain_core.messages import (
    SystemMessage,
    HumanMessage,
    AIMessage
)
from langchain_openai import ChatOpenAI
from langchain_core.output_parsers import StrOutputParser
import traceback

class LLMHandler:
    def __init__(self, prompts, db=None):
        self.prompts = prompts
        self.messages = []
        self._initialize_system_prompt(db)
        
    def _initialize_system_prompt(self, db):
        """Initialize system prompt with base prompt and table metadata if available"""
        base_prompt = self.prompts["system_prompt"]
        
        if db is not None:
            try:
                # Get table metadata
                print("DEBUG - Fetching table metadata")
                tables_df = db.get_table_metadata()
                print(f"DEBUG - Got table metadata DataFrame: {tables_df.shape if tables_df is not None else 'None'}")
                
                # Format table metadata - always show the section even if no tables
                table_info = []
                if tables_df is not None:
                    for _, row in tables_df.iterrows():
                        table_info.append(f"- {row['table_name']}: {row['description']}")
                    print(f"DEBUG - Formatted {len(table_info)} table entries")
                
                if not table_info:
                    table_info = ["No tables available yet"]
                
                # Add metadata section to prompt using template
                metadata_section = self.prompts["metadata_section"].format(
                    table_list="\n".join(table_info)
                )
                base_prompt += "\n\n" + metadata_section
                print("DEBUG - Added metadata section to prompt")
                
            except Exception as e:
                print(f"ERROR - Failed to process table metadata: {str(e)}")
                print(f"ERROR - Metadata processing traceback: {traceback.format_exc()}")
                # Still add the metadata section even if we hit an error
                metadata_section = self.prompts["metadata_section"].format(
                    table_list="Error retrieving table information"
                )
                base_prompt += "\n\n" + metadata_section
        
        # Initialize with complete system prompt
        print(f"DEBUG - Final base prompt (last 500 chars): ...{base_prompt[-500:] if len(base_prompt) > 200 else base_prompt}")
        self.messages = [SystemMessage(content=base_prompt)]
        
    def add_message(self, role, content):
        """Add a message to the conversation history"""
        if role == "user":
            self.messages.append(HumanMessage(content=content))
        elif role == "assistant":
            self.messages.append(AIMessage(content=content))
        elif role == "system":
            self.messages.append(SystemMessage(content=content))
            
    def generate_response(self):
        """Generate a response from the LLM"""
        try:
            llm = ChatOpenAI(model="gpt-4o-mini", temperature=0.0)
            response = llm.invoke(self.messages)
            return response.content
        except Exception as e:
            print(f"ERROR - Failed to generate response: {str(e)}")
            print(f"ERROR - Response generation traceback: {traceback.format_exc()}")
            return None
            
    def generate_title(self, user_content):
        """Generate a title for a conversation based on its content"""
        if not user_content:
            print("DEBUG - No user content provided for title generation")
            return None
            
        print(f"DEBUG - Generating title from {len(user_content)} chars of content")
        
        try:
            llm = ChatOpenAI(model="gpt-4o-mini", temperature=0.7)
            # Format the title prompt with the user content
            formatted_prompt = self.prompts["title"].format(user_content=user_content)
            # Use a single HumanMessage since the prompt already contains the instructions
            messages = [HumanMessage(content=formatted_prompt)]
            
            response = llm.invoke(messages)
            title = response.content
            print(f"DEBUG - Raw title generated: {title}")
            
            if len(title) > 80:
                title = title[:77] + "..."
                
            return title
        except Exception as e:
            print(f"ERROR - Failed to generate title: {str(e)}")
            print(f"ERROR - Title generation traceback: {traceback.format_exc()}")
            return None
            
    def reset_conversation(self):
        """Reset the conversation history"""
        self.messages = [SystemMessage(content=self.prompts["system_prompt"])] 