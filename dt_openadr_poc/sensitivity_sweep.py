# sensitivity_sweep.py
# Sensitivity sweep for the Digital Twin Sandbox
# Runs the existing code across multiple scenarios and summarizes results

import os
import sys
import csv
import numpy as np
import matplotlib.pyplot as plt
import pandas as pd
from typing import List, Dict, Any, Tuple

# Add current folder to path to resolve imports
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from config import CONFIG
from models.building_model import BuildingThermalModel
from models.ev_fleet_model import EVFleetModel
from core.dt_sandbox import DigitalTwinSandbox

def load_profiles() -> Tuple[np.ndarray, np.ndarray]:
    """Load temperature and base load profiles from CSV."""
    csv_path = os.path.join(os.path.dirname(__file__), 'data', 'profiles.csv')
    steps = []
    times = []
    T_out_profile = []
    base_load_profile = []

    with open(csv_path, mode='r') as f:
        reader = csv.DictReader(f)
        for row in reader:
            steps.append(int(row['step']))
            times.append(row['time'])
            T_out_profile.append(float(row['T_out']))
            base_load_profile.append(float(row['base_load']))

    T_out_profile = np.array(T_out_profile)
    base_load_profile = np.array(base_load_profile)
    
    return T_out_profile, base_load_profile