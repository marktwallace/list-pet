import pandas as pd

# Read the XPT files
demographics = pd.read_sas('DEMO_J.XPT', format='xport')
body_measures = pd.read_sas('BMX_J.XPT', format='xport')

# Merge datasets on SEQN
nhanes_data = pd.merge(demographics, body_measures, on='SEQN')

# Save to CSV
nhanes_data.to_csv('nhanes_2017_2018.csv', index=False)
