import os
import json
import duckdb
from typing import Optional, Dict, Any, List
import streamlit as st
import pandas as pd
from src.database import get_database, Database

@st.cache_resource
def get_metadata_manager():
    """Get or create metadata manager instance"""
    db = get_database()
    return MetadataManager(db)

class MetadataManager:
    def __init__(self, db: Database):
        self.db = db
        self.initialized = False
    
    def initialize_metadata_tables(self):
        """Initialize all metadata tables if they don't exist"""
        if self.initialized:
            return
            
        self.initialize_geojson_metadata()
        self.initialized = True
    
    def initialize_geojson_metadata(self):
        """Initialize GeoJSON metadata tables from JSON files"""
        # Check if tables already exist
        result, error = self.db.execute_query("SELECT name FROM sqlite_master WHERE type='table' AND name='_md_geojson_sources'")
        if result is not None and not result.empty:
            print("GeoJSON metadata tables already exist")
            return
            
        # Define paths for metadata files
        sources_file = os.path.join('data', 'metadata', 'geojson_sources.json')
        properties_file = os.path.join('data', 'metadata', 'geojson_properties.json')
        
        # Check if metadata files exist
        if not os.path.exists(sources_file):
            raise FileNotFoundError(f"GeoJSON sources metadata file not found: {sources_file}")
            
        if not os.path.exists(properties_file):
            raise FileNotFoundError(f"GeoJSON properties metadata file not found: {properties_file}")
        
        # Create tables from JSON files
        try:
            # Create sources table directly from JSON
            _, error = self.db.execute_query(f"""
                CREATE TABLE _md_geojson_sources AS 
                SELECT * FROM read_json_auto('{sources_file}')
            """)
            # Only raise an error if there's an actual error message
            # For CREATE operations, error might be None which is fine
            if error and error.startswith("SQL Error:"):
                raise RuntimeError(f"Error creating sources table: {error}")
                
            # Add a unique constraint on source_id after creation
            _, error = self.db.execute_query(
                "CREATE UNIQUE INDEX idx_geojson_sources_id ON _md_geojson_sources(source_id)"
            )
            if error and error.startswith("SQL Error:"):
                raise RuntimeError(f"Error creating index on sources table: {error}")
            
            # Create properties table directly from JSON
            _, error = self.db.execute_query(f"""
                CREATE TABLE _md_geojson_properties AS 
                SELECT * FROM read_json_auto('{properties_file}')
            """)
            if error and error.startswith("SQL Error:"):
                raise RuntimeError(f"Error creating properties table: {error}")
                
            # Add a unique constraint on source_id + property_name after creation
            _, error = self.db.execute_query(
                "CREATE UNIQUE INDEX idx_geojson_properties_id ON _md_geojson_properties(source_id, property_name)"
            )
            if error and error.startswith("SQL Error:"):
                raise RuntimeError(f"Error creating index on properties table: {error}")
            
            print("GeoJSON metadata tables created successfully")
                
        except Exception as e:
            # Clean up any partially created tables
            try:
                self.db.execute_query("DROP TABLE IF EXISTS _md_geojson_sources")
                self.db.execute_query("DROP TABLE IF EXISTS _md_geojson_properties")
            except:
                pass
            
            # Re-raise the exception with more context
            raise RuntimeError(f"Error initializing GeoJSON metadata: {str(e)}")
    
    def get_geojson_source(self, source_id: str) -> Optional[Dict[str, Any]]:
        """Get metadata for a GeoJSON source by ID"""
        result, error = self.db.execute_query(f"""
            SELECT source_id, file_path, feature_id_property, description, scope
            FROM _md_geojson_sources
            WHERE source_id = '{source_id}'
        """)
        
        if error or result is None or result.empty:
            return None
            
        row = result.iloc[0]
        return {
            'source_id': row['source_id'],
            'file_path': row['file_path'],
            'feature_id_property': row['feature_id_property'],
            'description': row['description'],
            'scope': row['scope']
        }
    
    def get_geojson_properties(self, source_id: str) -> List[Dict[str, Any]]:
        """Get properties for a GeoJSON source by ID"""
        result, error = self.db.execute_query(f"""
            SELECT property_name, property_description, property_type
            FROM _md_geojson_properties
            WHERE source_id = '{source_id}'
        """)
        
        if error or result is None or result.empty:
            return []
        
        return [
            {
                'property_name': row['property_name'],
                'property_description': row['property_description'],
                'property_type': row['property_type']
            }
            for _, row in result.iterrows()
        ]
    
    def list_geojson_sources(self) -> List[Dict[str, Any]]:
        """List all available GeoJSON sources"""
        result, error = self.db.execute_query("""
            SELECT source_id, description, scope
            FROM _md_geojson_sources
        """)
        
        if error or result is None or result.empty:
            return []
        
        return [
            {
                'source_id': row['source_id'],
                'description': row['description'],
                'scope': row['scope']
            }
            for _, row in result.iterrows()
        ] 