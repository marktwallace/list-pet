from langchain_core.messages import (
    SystemMessage,
    HumanMessage,
    AIMessage
)
from langchain_openai import ChatOpenAI
from langchain_core.output_parsers import StrOutputParser
import traceback

class LLMHandler:
    def __init__(self, prompts):
        self.prompts = prompts
        self.messages = [SystemMessage(content=self.prompts["system_prompt"])]
        
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