"""
NIFTY calendar / rollover spread research (CAL-2).

Research-only. Does not wire paper/live risk or execution (Validation Phase freeze).
CAL-0 locked defaults live in definition.CalendarSpreadParams.
"""

from research.calendar_spread.definition import CAL_PARAMS, CalendarSpreadParams
from research.calendar_spread.engine import CalendarSpreadEngine

__all__ = [
    "CAL_PARAMS",
    "CalendarSpreadParams",
    "CalendarSpreadEngine",
]
