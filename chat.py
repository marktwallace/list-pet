from langchain_core.prompts import (
    SystemMessagePromptTemplate,
    HumanMessagePromptTemplate,
    AIMessagePromptTemplate,
    ChatPromptTemplate
)
from langchain_openai import ChatOpenAI
from langchain_core.output_parsers import StrOutputParser
from parse import parse_markup
import streamlit as st

@st.cache_resource
def get_chat_engine(model_name: str):
    """Get or create chat engine"""
    return ChatEngine(model_name)

class ChatEngine:
    def __init__(self, model_name: str):
        self.llm = ChatOpenAI(
            model=model_name,
            temperature=0.0
        )
        with open('prompts/system.txt', 'r') as f:
            system_template = f.read()
        self.system_prompt = SystemMessagePromptTemplate.from_template(system_template)
    
    def build_prompt_chain(self, message_log):
        """Build prompt chain from message history"""
        prompt_sequence = [self.system_prompt]
        
        for msg in message_log:
            if msg["internal"]["role"] == "user":
                prompt_sequence.append(HumanMessagePromptTemplate.from_template(msg["internal"]["content"]))
            elif msg["internal"]["role"] == "ai":
                prompt_sequence.append(AIMessagePromptTemplate.from_template(msg["internal"]["content"]))
        
        return ChatPromptTemplate.from_messages(prompt_sequence)
    
    def generate_response_stream(self, prompt_chain):
        """Streams AI response token by token"""
        processing_pipeline = prompt_chain | self.llm | StrOutputParser()
        return processing_pipeline.stream({})  # Empty variables dict since we don't use templating
    
    def parse_response(self, response: str) -> dict:
        """Parse the AI response into components"""
        return parse_markup(response) 