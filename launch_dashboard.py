"""
NexTrade — Easy One-Click Control Panel Launcher for Non-Technical Users.

Run this file to launch the visual NexTrade Web Dashboard:
    python launch_dashboard.py
"""

import sys
import os

# Always run from repo root so config.json / watchlist.json resolve correctly
_ROOT = os.path.dirname(os.path.abspath(__file__))
os.chdir(_ROOT)
sys.path.insert(0, _ROOT)

from web_dashboard import start_dashboard_server

if __name__ == "__main__":
    start_dashboard_server()
