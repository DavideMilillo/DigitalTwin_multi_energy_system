# models/eta_model.py
# Modulo per il calcolo del rendimento dinamico dei convertitori

import numpy as np
from scipy.interpolate import interp1d

class ConverterEfficiency:
    """
    Implements a conversion efficiency curve based on normalized load (P/Pnom).
    Derived from experimental data in ENEA's previous project.
    """
    def __init__(self) -> None:
        # Normalized converter load (P/Pnom)
        self.xdata = np.array([
            0.0, 0.01, 0.025, 0.05, 0.105, 0.122, 0.138, 0.16, 0.181, 0.212,
            0.249, 0.303, 0.396, 0.5, 0.596, 0.699, 0.799, 0.898, 0.991,
            1.41, 2.0
        ])

        # Corresponding efficiency values (square root transformed for cascaded conversion steps)
        self.ydata = np.array([
            0.8944, 0.9198, 0.9623, 0.9752, 0.9767, 0.9788, 0.9803,
            0.9823, 0.9849, 0.9869, 0.9889, 0.9899, 0.9905, 0.9905,
            0.9905, 0.9905, 0.9905, 0.9899, 0.9894, 0.8426, 0.6708
        ])

        # Interpolator (MATLAB interp1 equivalent)
        self._interp = interp1d(
            self.xdata,
            self.ydata,
            kind='linear',
            bounds_error=False,
            fill_value=0.0011111  # Consistent MATLAB default
        )

    def calculate_efficiency(self, load_ratio: float) -> float:
        """
        Calculates the efficiency η for a given normalized load ratio (P/Pnom).
        """
        ratio = float(abs(load_ratio))
        # Ensure we cap the ratio at the maximum of our data to prevent out-of-bounds fill value drops
        ratio = min(ratio, 2.0)
        return float(self._interp(ratio))
