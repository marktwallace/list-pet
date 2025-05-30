#!/usr/bin/env python3
import os
import sys
import re

# The pattern to match include directives
# Format: @include path/to/file.txt
INCLUDE_PATTERN = r'^\s*@include\s+(.+?)\s*$'

def get_prompts(config_base_path: str):
    prompts = {}
    prompts_dir = os.path.join(config_base_path, "prompts")

    if not os.path.isdir(prompts_dir):
        print(f"ERROR: Prompts directory not found: {prompts_dir}. Returning empty prompts.", file=sys.stderr)
        # Try falling back to a local prompts dir if config_base_path was used but prompts not there
        if config_base_path != ".": # Check if it wasn't already the default path
            fallback_prompts_dir = os.path.join(".", "prompts")
            if os.path.isdir(fallback_prompts_dir):
                print(f"INFO: Falling back to local prompts directory: {fallback_prompts_dir}", file=sys.stderr)
                prompts_dir = fallback_prompts_dir
            else:
                return prompts # Return empty if fallback also not found
        else:
            return prompts # Return empty if default path prompts not found
        
    # Get all files in prompts directory
    for filename in os.listdir(prompts_dir):
        file_path = os.path.join(prompts_dir, filename)
        if os.path.isfile(file_path):
            # Get base name without extension
            base_name = os.path.splitext(filename)[0]
            # Process file and store result
            prompts[base_name] = process_file(file_path)
            
    return prompts

def process_file(file_path, processed_files=None):
    if processed_files is None:
        processed_files = set()
    
    # Prevent infinite recursion
    if file_path in processed_files:
        return f"ERROR: Circular inclusion detected for {file_path}\n"
    
    processed_files.add(file_path)
    
    if not os.path.exists(file_path):
        return f"ERROR: File not found: {file_path}\n"
    
    result = []
    with open(file_path, 'r') as f:
        for line_num, line in enumerate(f, 1):
            include_match = re.match(INCLUDE_PATTERN, line)
            if include_match:
                include_path = include_match.group(1)
                # Make the path relative to the including file
                base_dir = os.path.dirname(file_path)
                include_full_path = os.path.normpath(os.path.join(base_dir, include_path))
                
                # Process the included file
                included_content = process_file(include_full_path, processed_files.copy())
                result.append(included_content)
            else:
                result.append(line)
    
    return ''.join(result)

def main():
    if len(sys.argv) < 2:
        print(f"Usage: {sys.argv[0]} input_file [output_file]")
        sys.exit(1)
    
    input_file = sys.argv[1]
    
    try:
        processed_content = process_file(input_file)
        
        if len(sys.argv) > 2:
            output_file = sys.argv[2]
            with open(output_file, 'w') as f:
                f.write(processed_content)
            print(f"Processed content written to {output_file}")
        else:
            print(processed_content)
    
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main() 