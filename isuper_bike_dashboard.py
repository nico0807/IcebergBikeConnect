#!/usr/bin/env python3
"""
iSuper Gym Bike Dashboard - AP Mode
Connects to the bike and displays real-time sport data in a terminal dashboard.

This module is now a wrapper for the separated modules:
- isuper_bike.py: Bike connection/protocol layer
- dashboard.py: User interface layer
"""

# Import main components from split modules
from isuper_bike import ISuperBike
from dashboard import Dashboard, main

# Re-export for backward compatibility
__all__ = ['ISuperBike', 'Dashboard', 'main']

# Run main if executed directly
if __name__ == "__main__":
    main()
