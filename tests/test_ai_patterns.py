import unittest
import os
import sys
import json

# Add the src directory to the path so we can import modules
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.parse import parse_markup

class TestAIPatterns(unittest.TestCase):
    def test_parse_reasoning_block(self):
        """Test parsing reasoning blocks from AI response"""
        response = """
        <reasoning>
        This is a reasoning block that explains the AI's thought process.
        It can span multiple lines and contain various explanations.
        </reasoning>
        """
        
        parsed = parse_markup(response)
        
        self.assertIn("reasoning", parsed)
        self.assertEqual(len(parsed["reasoning"]), 1)
        self.assertIn("text", parsed["reasoning"][0])
        self.assertIn("This is a reasoning block", parsed["reasoning"][0]["text"])
        self.assertIn("span multiple lines", parsed["reasoning"][0]["text"])
    
    def test_parse_sql_blocks(self):
        """Test parsing SQL blocks from AI response"""
        response = """
        <reasoning>
        Let me query the data to answer this question.
        </reasoning>
        
        <sql>
        SELECT * FROM test_table WHERE id = 1
        </sql>
        
        <display>
        Here are the results from the test table.
        </display>
        """
        
        parsed = parse_markup(response)
        
        self.assertIn("sql", parsed)
        self.assertEqual(len(parsed["sql"]), 1)
        self.assertIn("query", parsed["sql"][0])
        self.assertEqual(parsed["sql"][0]["query"].strip(), "SELECT * FROM test_table WHERE id = 1")
    
    def test_parse_multiple_sql_blocks(self):
        """Test parsing multiple SQL blocks from AI response"""
        response = """
        <sql>
        SELECT * FROM test_table WHERE id = 1
        </sql>
        
        <display>
        Let me get more data.
        </display>
        
        <sql>
        SELECT * FROM test_table WHERE id = 2
        </sql>
        """
        
        parsed = parse_markup(response)
        
        self.assertIn("sql", parsed)
        self.assertEqual(len(parsed["sql"]), 2)
        self.assertEqual(parsed["sql"][0]["query"].strip(), "SELECT * FROM test_table WHERE id = 1")
        self.assertEqual(parsed["sql"][1]["query"].strip(), "SELECT * FROM test_table WHERE id = 2")
    
    def test_parse_plot_multiline_tag(self):
        """Test parsing plot specifications in multiline tag format"""
        response = """
        <plot 
            type="bar" 
            x="name" 
            y="value" 
            title="Test Plot" 
        />
        """
        
        parsed = parse_markup(response)
        
        self.assertIn("plot", parsed)
        self.assertEqual(len(parsed["plot"]), 1)
        self.assertEqual(parsed["plot"][0]["type"], "bar")
        self.assertEqual(parsed["plot"][0]["x"], "name")
        self.assertEqual(parsed["plot"][0]["y"], "value")
        self.assertEqual(parsed["plot"][0]["title"], "Test Plot")
    
    def test_parse_map_multiline_tag(self):
        """Test parsing map specifications in multiline tag format"""
        response = """
        <map 
            type="scatter_geo" 
            lat="latitude" 
            lon="longitude" 
            title="Test Map" 
        />
        """
        
        parsed = parse_markup(response)
        
        self.assertIn("map", parsed)
        self.assertEqual(len(parsed["map"]), 1)
        self.assertEqual(parsed["map"][0]["type"], "scatter_geo")
        self.assertEqual(parsed["map"][0]["lat"], "latitude")
        self.assertEqual(parsed["map"][0]["lon"], "longitude")
        self.assertEqual(parsed["map"][0]["title"], "Test Map")
    
    def test_parse_display_blocks(self):
        """Test parsing display blocks from AI response"""
        response = """
        <display>
        This is a display block that shows information to the user.
        It can contain markdown formatting and other text.
        </display>
        """
        
        parsed = parse_markup(response)
        
        self.assertIn("display", parsed)
        self.assertEqual(len(parsed["display"]), 1)
        self.assertIn("text", parsed["display"][0])
        self.assertIn("This is a display block", parsed["display"][0]["text"])
        self.assertIn("markdown formatting", parsed["display"][0]["text"])
    
    def test_parse_complex_response(self):
        """Test parsing a complex AI response with multiple block types"""
        response = """
        <reasoning>
        I need to analyze the data to answer this question.
        </reasoning>
        
        <sql>
        SELECT * FROM test_table
        </sql>
        
        <display>
        Here are the results from the test table.
        </display>
        
        <plot 
            type="bar" 
            x="name" 
            y="value" 
            title="Test Plot" 
        />
        
        <map 
            type="scatter_geo" 
            lat="latitude" 
            lon="longitude" 
            title="Test Map" 
        />
        """
        
        parsed = parse_markup(response)
        
        # Check that all block types are present
        self.assertIn("reasoning", parsed)
        self.assertIn("sql", parsed)
        self.assertIn("display", parsed)
        self.assertIn("plot", parsed)
        self.assertIn("map", parsed)
        
        # Check counts of each block type
        self.assertEqual(len(parsed["reasoning"]), 1)
        self.assertEqual(len(parsed["sql"]), 1)
        self.assertEqual(len(parsed["display"]), 1)
        self.assertEqual(len(parsed["plot"]), 1)
        self.assertEqual(len(parsed["map"]), 1)
        
        # Check content of blocks
        self.assertIn("analyze the data", parsed["reasoning"][0]["text"])
        self.assertEqual(parsed["sql"][0]["query"].strip(), "SELECT * FROM test_table")
        self.assertIn("results from the test table", parsed["display"][0]["text"])
        self.assertEqual(parsed["plot"][0]["type"], "bar")
        self.assertEqual(parsed["map"][0]["type"], "scatter_geo")

if __name__ == '__main__':
    unittest.main() 