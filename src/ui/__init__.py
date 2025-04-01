"""
UI node module for the reactive companion system.

This package contains the visual interface components that display
the system state and provide user interaction.
"""

from .state import UIState, SystemMode, global_state

__all__ = ['UIState', 'SystemMode', 'global_state']
