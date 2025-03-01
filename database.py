import duckdb
import streamlit as st
import pandas as pd
import os

@st.cache_resource
def get_database():
    """Get or create database connection"""
    os.makedirs("db", exist_ok=True)
    return Database()

class Database:
    def __init__(self):
        self.conn = duckdb.connect('db/list_pet.db')
    
    def execute_query(self, sql: str) -> tuple[pd.DataFrame | None, str | None]:
        """Execute SQL and return (dataframe, error_message)"""
        try:
            result = self.conn.execute(sql)
            
            # If it's a SELECT statement and returns data, return the dataframe
            if sql.strip().upper().startswith("SELECT"):
                try:
                    df = result.df()
                    if not df.empty:
                        return df, None
                except Exception as e:
                    return None, f"Error displaying results: {str(e)}"
            return None, None
                    
        except Exception as e:
            return None, f"SQL Error: {str(e)}" 