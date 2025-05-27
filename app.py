# app.py
# import sys # No longer needed for arg parsing here
# import os # No longer needed for arg parsing here
from src import streamlit_ui

if __name__ == "__main__":
    # All config path logic is now handled within streamlit_ui.py via an environment variable
    streamlit_ui.main()
