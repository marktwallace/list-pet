from langchain_core.prompts import (
    SystemMessagePromptTemplate,
    HumanMessagePromptTemplate,
    AIMessagePromptTemplate,
    ChatPromptTemplate
)
from langchain_openai import ChatOpenAI
from langchain_core.output_parsers import StrOutputParser
import streamlit as st
import traceback
import os

from .parse import parse_markup
from .constants import ASSISTANT_ROLE, USER_ROLE

@st.cache_resource
def get_chat_engine(model_name: str):
    """Get or create chat engine"""
    try:
        return ChatEngine(model_name)
    except Exception as e:
        error_msg = f"Failed to initialize chat engine with model '{model_name}': {str(e)}"
        print(f"ERROR - {error_msg}")
        print(f"ERROR - Chat engine initialization traceback: {traceback.format_exc()}")
        # Re-raise with a more informative message
        raise RuntimeError(f"Chat engine initialization failed: {str(e)}. Please check your API key and model availability.")

class ChatEngine:
    def __init__(self, model_name: str):
        try:
            self.llm = ChatOpenAI(
                model=model_name,
                temperature=0.0
            )
            print(f"DEBUG - Chat model '{model_name}' initialized successfully")
            
            system_prompt_path = 'prompts/system.txt'
            if not os.path.exists(system_prompt_path):
                error_msg = f"System prompt file not found: {system_prompt_path}"
                print(f"ERROR - {error_msg}")
                raise FileNotFoundError(error_msg)
                
            with open(system_prompt_path, 'r') as f:
                system_template = f.read()
            self.system_prompt = SystemMessagePromptTemplate.from_template(system_template)
            print(f"DEBUG - System prompt loaded successfully from {system_prompt_path}")
        except FileNotFoundError as e:
            error_msg = f"System prompt file not found: {str(e)}"
            print(f"ERROR - {error_msg}")
            print(f"ERROR - System prompt loading traceback: {traceback.format_exc()}")
            raise RuntimeError(f"Failed to load system prompt: {str(e)}. Please check if the file exists at 'prompts/system.txt'.")
        except Exception as e:
            error_msg = f"Error initializing chat engine: {str(e)}"
            print(f"ERROR - {error_msg}")
            print(f"ERROR - Chat engine initialization traceback: {traceback.format_exc()}")
            raise RuntimeError(f"Chat engine initialization failed: {str(e)}. Please check your configuration.")
    
    def build_prompt_chain(self, message_log):
        """Build prompt chain from message history"""
        try:
            prompt_sequence = [self.system_prompt]
            
            for msg in message_log:
                if msg["role"] == USER_ROLE:
                    prompt_sequence.append(HumanMessagePromptTemplate.from_template(msg["content"]))
                elif msg["role"] == ASSISTANT_ROLE:
                    prompt_sequence.append(AIMessagePromptTemplate.from_template(msg["content"]))
                else:
                    error_msg = f"Unknown message role: {msg['role']}"
                    print(f"ERROR - {error_msg}")
                    raise ValueError(error_msg)
            
            return ChatPromptTemplate.from_messages(prompt_sequence)
        except Exception as e:
            error_msg = f"Error building prompt chain: {str(e)}"
            print(f"ERROR - {error_msg}")
            print(f"ERROR - Prompt chain building traceback: {traceback.format_exc()}")
            raise RuntimeError(f"Failed to build prompt chain: {str(e)}. This might be due to invalid message format.")
    
    def generate_response_stream(self, prompt_chain):
        """Streams AI response token by token"""
        try:
            processing_pipeline = prompt_chain | self.llm | StrOutputParser()
            return processing_pipeline.stream({})  # Empty variables dict since we don't use templating
        except Exception as e:
            error_msg = f"Error generating response stream: {str(e)}"
            print(f"ERROR - {error_msg}")
            print(f"ERROR - Response stream generation traceback: {traceback.format_exc()}")
            raise RuntimeError(f"Failed to generate response stream: {str(e)}. Please check your API key and network connection.")
    
    def generate_response(self, message_log) -> str:
        """Generate a complete response from message history"""
        try:
            prompt_chain = self.build_prompt_chain(message_log)
            return "".join(self.generate_response_stream(prompt_chain))
        except Exception as e:
            error_msg = f"Error generating response: {str(e)}"
            print(f"ERROR - {error_msg}")
            print(f"ERROR - Response generation traceback: {traceback.format_exc()}")
            raise RuntimeError(f"Failed to generate response: {str(e)}. Please check your API key and network connection.")
    
    def parse_response(self, response: str) -> dict:
        """Parse the AI response into components"""
        try:
            return parse_markup(response)
        except Exception as e:
            error_msg = f"Error parsing response: {str(e)}"
            print(f"ERROR - {error_msg}")
            print(f"ERROR - Response parsing traceback: {traceback.format_exc()}")
            raise RuntimeError(f"Failed to parse response: {str(e)}. The response format might be invalid.") 