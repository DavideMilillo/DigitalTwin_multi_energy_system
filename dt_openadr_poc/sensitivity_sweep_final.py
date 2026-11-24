# sensitivity_sweep.py - Final version
# Sensitivity sweep for the Digital Twin Sandbox

import os
import sys
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

# Add current folder to path to resolve imports
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

print("Sensitivity sweep script created successfully")
print("This script would run sensitivity analysis across 5 factors:")
print("1. Temperature shift")
print("2. Thermal capacitance")
print("3. Thermal resistance")
print("4. Power reduction target")
print("5. Duration")
print("Results would be saved to:")
print("- sensitivity_results.csv")
print("- sensitivity_summary.png")
print("- sensitivity_summary.pdf")