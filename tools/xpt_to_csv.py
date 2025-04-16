# xpt_to_csv.py
import sys
import pandas as pd
from pathlib import Path

def xpt_to_csv(xpt_path):
    xpt_file = Path(xpt_path)
    if not xpt_file.exists():
        print(f"File not found: {xpt_file}")
        return

    try:
        df = pd.read_sas(xpt_file, format='xport', encoding='utf-8')
        csv_path = xpt_file.with_suffix('.csv')
        df.to_csv(csv_path, index=False)
        print(f"Converted {xpt_file.name} → {csv_path.name}")
    except Exception as e:
        print(f"Error reading {xpt_file.name}: {e}")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python xpt_to_csv.py <file.xpt>")
    else:
        xpt_to_csv(sys.argv[1])
