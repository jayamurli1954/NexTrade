"""
NexTrade Phase 7 — Excel Trading Logger & Periodical P&L Exporter.

Generates native Microsoft Excel (.xlsx) workbooks tracking:
1. Today's Executed Trades Log (Symbol, Entry/Exit ₹, P&L ₹, Exit Reason).
2. Daily P&L Summary (Starting Capital ₹, Ending Capital ₹, Net P&L ₹, Win Rate %).
3. Cumulative Period Performance & Periodical P&L.
"""

import os
import time
from datetime import datetime
from typing import List, Dict, Any

import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter


class ExcelTradeLogger:
    """
    Manages automated Excel report generation for market closure and periodical reviews.
    """

    def __init__(self, reports_dir: str = "reports") -> None:
        self.reports_dir = reports_dir
        os.makedirs(self.reports_dir, exist_ok=True)

    def generate_excel_report(
        self,
        filename: str = None,
        executed_trades: List[Dict[str, Any]] = None,
        daily_summary: Dict[str, Any] = None,
        cumulative_summary: Dict[str, Any] = None
    ) -> str:
        """
        Creates a formatted multi-sheet Excel file (.xlsx) with trade logs, daily P&L, and cumulative performance.
        """
        date_str = datetime.now().strftime("%Y%m%d")
        if not filename:
            filename = f"NexTrade_Trading_Log_{date_str}.xlsx"

        filepath = os.path.join(self.reports_dir, filename)

        wb = openpyxl.Workbook()
        
        # Define Color Palette & Styles
        header_fill = PatternFill(start_color="1F2937", end_color="1F2937", fill_type="solid")
        header_font = Font(name="Arial", size=11, bold=True, color="FFFFFF")
        title_font = Font(name="Arial", size=14, bold=True, color="00E676")
        section_font = Font(name="Arial", size=12, bold=True, color="1E88E5")
        bold_font = Font(name="Arial", size=10, bold=True)
        normal_font = Font(name="Arial", size=10)
        
        green_font = Font(name="Arial", size=10, bold=True, color="008000")
        red_font = Font(name="Arial", size=10, bold=True, color="C62828")

        thin_border = Border(
            left=Side(style="thin", color="CCCCCC"),
            right=Side(style="thin", color="CCCCCC"),
            top=Side(style="thin", color="CCCCCC"),
            bottom=Side(style="thin", color="CCCCCC")
        )

        # -------------------------------------------------------------
        # SHEET 1: TODAY'S EXECUTED TRADES
        # -------------------------------------------------------------
        ws1 = wb.active
        ws1.title = "Today Executed Trades"
        ws1.views.sheetView[0].showGridLines = True

        ws1.cell(row=1, column=1, value="NexTrade — Today's Executed Trades Log").font = title_font
        ws1.cell(row=2, column=1, value=f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} | Currency: INR (₹)").font = normal_font

        headers_ws1 = [
            "Trade ID", "Timestamp", "Symbol", "Style", "Strategy",
            "Direction", "Qty", "Entry Price (₹)", "Exit Price (₹)",
            "Exit Reason", "Gross P&L (₹)", "Status"
        ]

        start_row = 4
        for col_idx, h_text in enumerate(headers_ws1, 1):
            cell = ws1.cell(row=start_row, column=col_idx, value=h_text)
            cell.fill = header_fill
            cell.font = header_font
            cell.alignment = Alignment(horizontal="center", vertical="center")

        trades = executed_trades or []
        current_row = start_row + 1

        if not trades:
            ws1.cell(row=current_row, column=1, value="No trades executed today.").font = normal_font
            current_row += 1
        else:
            for t in trades:
                ws1.cell(row=current_row, column=1, value=t.get("trade_id", "-")).font = normal_font
                ws1.cell(row=current_row, column=2, value=t.get("timestamp", "-")).font = normal_font
                ws1.cell(row=current_row, column=3, value=t.get("symbol", "-")).font = bold_font
                ws1.cell(row=current_row, column=4, value=t.get("style", "-")).font = normal_font
                ws1.cell(row=current_row, column=5, value=t.get("strategy", "-")).font = normal_font
                ws1.cell(row=current_row, column=6, value=t.get("direction", "-")).font = normal_font
                ws1.cell(row=current_row, column=7, value=t.get("quantity", 0)).font = normal_font
                ws1.cell(row=current_row, column=8, value=t.get("entry_price", 0.0)).font = normal_font
                ws1.cell(row=current_row, column=9, value=t.get("exit_price", 0.0)).font = normal_font
                ws1.cell(row=current_row, column=10, value=t.get("exit_reason", "-")).font = normal_font
                
                pnl = t.get("pnl", 0.0)
                pnl_cell = ws1.cell(row=current_row, column=11, value=pnl)
                pnl_cell.font = green_font if pnl >= 0 else red_font
                
                ws1.cell(row=current_row, column=12, value=t.get("status", "CLOSED")).font = normal_font

                for c in range(1, 13):
                    ws1.cell(row=current_row, column=c).border = thin_border
                current_row += 1

        # Auto-fit columns
        for col in ws1.columns:
            max_len = max(len(str(cell.value or "")) for cell in col)
            col_letter = get_column_letter(col[0].column)
            ws1.column_dimensions[col_letter].width = max(max_len + 3, 12)

        # -------------------------------------------------------------
        # SHEET 2: DAILY & CUMULATIVE P&L SUMMARY
        # -------------------------------------------------------------
        ws2 = wb.create_sheet(title="Daily & Cumulative Summary")
        ws2.views.sheetView[0].showGridLines = True

        ws2.cell(row=1, column=1, value="NexTrade — Daily & Cumulative Performance Report").font = title_font

        # Daily Section
        ws2.cell(row=3, column=1, value="1. Today's Performance Summary").font = section_font
        daily_data = daily_summary or {
            "date": datetime.now().strftime("%Y-%m-%d"),
            "starting_capital": 100000.0,
            "ending_capital": 100000.0,
            "todays_net_pnl": 0.0,
            "todays_win_rate_pct": 0.0,
            "total_trades_today": 0
        }

        daily_rows = [
            ("Trading Date", daily_data.get("date", "-")),
            ("Starting Capital (₹)", f"₹{daily_data.get('starting_capital', 100000.0):,.2f}"),
            ("Ending Capital (₹)", f"₹{daily_data.get('ending_capital', 100000.0):,.2f}"),
            ("Today's Net P&L (₹)", f"₹{daily_data.get('todays_net_pnl', 0.0):,.2f}"),
            ("Today's Win Rate (%)", f"{daily_data.get('todays_win_rate_pct', 0.0):.1f}%"),
            ("Total Trades Today", daily_data.get("total_trades_today", 0))
        ]

        r = 4
        for label, val in daily_rows:
            ws2.cell(row=r, column=1, value=label).font = bold_font
            cell_v = ws2.cell(row=r, column=2, value=str(val))
            cell_v.font = normal_font
            ws2.cell(row=r, column=1).border = thin_border
            ws2.cell(row=r, column=2).border = thin_border
            r += 1

        # Cumulative Section
        r += 1
        ws2.cell(row=r, column=1, value="2. Cumulative Periodical Performance Log").font = section_font
        r += 1

        cum_data = cumulative_summary or {
            "period_start": datetime.now().strftime("%Y-%m-%d"),
            "cumulative_net_pnl": 0.0,
            "cumulative_trades": 0,
            "cumulative_win_rate_pct": 0.0,
            "profit_factor": 0.0,
            "max_drawdown": 0.0
        }

        cum_rows = [
            ("Period Start Date", cum_data.get("period_start", "-")),
            ("Cumulative Net P&L (₹)", f"₹{cum_data.get('cumulative_net_pnl', 0.0):,.2f}"),
            ("Cumulative Total Trades", cum_data.get("cumulative_trades", 0)),
            ("Cumulative Win Rate (%)", f"{cum_data.get('cumulative_win_rate_pct', 0.0):.1f}%"),
            ("Profit Factor", f"{cum_data.get('profit_factor', 0.0):.2f}"),
            ("Max Drawdown (₹)", f"₹{cum_data.get('max_drawdown', 0.0):,.2f}")
        ]

        for label, val in cum_rows:
            ws2.cell(row=r, column=1, value=label).font = bold_font
            cell_v = ws2.cell(row=r, column=2, value=str(val))
            cell_v.font = normal_font
            ws2.cell(row=r, column=1).border = thin_border
            ws2.cell(row=r, column=2).border = thin_border
            r += 1

        # Auto-fit Sheet 2 columns
        for col in ws2.columns:
            max_len = max(len(str(cell.value or "")) for cell in col)
            col_letter = get_column_letter(col[0].column)
            ws2.column_dimensions[col_letter].width = max(max_len + 4, 15)

        wb.save(filepath)
        return filepath
