# models/eta_model.py
# Modulo per il calcolo del rendimento dinamico dei convertitori (modello analitico)

class ConverterEfficiency:
    """
    Implements an analytical converter efficiency model based on normalized load (P/Pnom).
    Uses the peer-reviewed de Mango / inverter efficiency loss model:
        eta(x) = x / (x + p0 + p1 * x^2)
    where:
        - x is the normalized power ratio P/Pnom.
        - p0 represents no-load/constant losses.
        - p1 represents load-dependent / resistive copper losses.
    
    This provides a rigorous mathematical formulation suitable for publication
    """
    def __init__(self, p0: float = 0.015, p1: float = 0.025) -> None:
        """
        Initializes the efficiency model coefficients.
        Default parameters yield a peak efficiency of ~96.2% at 77% load.
        """
        self.p0 = p0
        self.p1 = p1

    def calculate_efficiency(self, load_ratio: float) -> float:
        """
        Calculates the efficiency η for a given normalized load ratio (P/Pnom).
        """
        x = float(abs(load_ratio))
        if x <= 1e-4:
            return 0.0  # Zero load implies zero efficiency/no power transfer
        
        # Calculate efficiency using the loss formula
        efficiency = x / (x + self.p0 + self.p1 * (x ** 2))
        
        # Clamp efficiency to realistic boundaries (e.g., max 98%, min 10%)
        return max(0.1, min(efficiency, 0.98))
