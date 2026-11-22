"""
Options paper-trading lane (OPT-PAPER, see docs/NEXTRADE_DEFERRED_IMPLEMENTATION_MEMORY_V1.md §L).

Live Angel quotes, simulated fills at the real bid/ask, own ledger under logs/options_paper/.
Never sends broker orders. Separate from the equity paper path, risk gates and capital ledger.
"""
