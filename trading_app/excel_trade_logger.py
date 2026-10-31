"""
NexTrade Phase 7 — Excel Trading Logger & Periodical P&L Exporter.

Generates native Microsoft Excel (.xlsx) workbooks tracking:
1. Executed Trades Log (gross + estimated net P&L).
2. Today vs Period summary (correctly separated).
3. Daily breakdown.
4. Strategy breakdown.
"""

from __future__ import annotations

import os
from datetime import datetime
from typing import Any, Dict, List, Optional

import openpyxl
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

from trading_app.journal_analytics import (
    compute_journal_metrics,
    enrich_trade_with_net,
    filter_trades_for_day,
)


class ExcelTradeLogger:
    """Manages automated Excel report generation for paper journal reviews."""

    def __init__(self, reports_dir: str = "reports") -> None:
        self.reports_dir = reports_dir
        os.makedirs(self.reports_dir, exist_ok=True)

    def generate_excel_report(
        self,
        filename: Optional[str] = None,
        executed_trades: Optional[List[Dict[str, Any]]] = None,
        daily_summary: Optional[Dict[str, Any]] = None,
        cumulative_summary: Optional[Dict[str, Any]] = None,
        starting_capital: float = 1_000_000.0,
        today: Optional[str] = None,
    ) -> str:
        now = datetime.now()
        date_str = (today or now.strftime("%Y-%m-%d")).replace("-", "")[:8] or now.strftime("%Y%m%d")
        stamp = now.strftime("%H%M%S")
        if not filename:
            filename = f"NexTrade_Trading_Log_{date_str}_{stamp}_{os.getpid()}.xlsx"

        filepath = os.path.join(self.reports_dir, filename)
        trades = list(executed_trades or [])
        today = (today or now.strftime("%Y-%m-%d"))[:10]
        period = compute_journal_metrics(trades, use_net=False)
        today_trades = filter_trades_for_day(trades, today)
        today_m = compute_journal_metrics(today_trades, use_net=False)
        period_net = compute_journal_metrics(trades, use_net=True)

        # Allow caller overrides but fill gaps from computed metrics
        daily_summary = dict(daily_summary or {})
        cumulative_summary = dict(cumulative_summary or {})
        daily_summary.setdefault("date", today)
        daily_summary.setdefault("starting_capital", float(starting_capital))
        daily_summary.setdefault("todays_net_pnl", today_m.gross_pnl)
        daily_summary.setdefault("todays_win_rate_pct", today_m.win_rate_pct)
        daily_summary.setdefault("total_trades_today", today_m.total_trades)
        daily_summary.setdefault(
            "ending_capital",
            float(starting_capital) + float(period.gross_pnl),
        )
        cumulative_summary.setdefault("period_start", period.period_start or today)
        cumulative_summary.setdefault("period_end", period.period_end or today)
        cumulative_summary.setdefault("cumulative_net_pnl", period.gross_pnl)
        cumulative_summary.setdefault("cumulative_trades", period.total_trades)
        cumulative_summary.setdefault("cumulative_win_rate_pct", period.win_rate_pct)
        cumulative_summary.setdefault("profit_factor", period.profit_factor)
        cumulative_summary.setdefault("max_drawdown", abs(period.max_drawdown))
        cumulative_summary.setdefault("expectancy", period.expectancy)
        cumulative_summary.setdefault("avg_win", period.avg_win)
        cumulative_summary.setdefault("avg_loss", period.avg_loss)
        cumulative_summary.setdefault("largest_win", period.largest_win)
        cumulative_summary.setdefault("largest_loss", period.largest_loss)
        cumulative_summary.setdefault("max_consecutive_losses", period.max_consecutive_losses)
        cumulative_summary.setdefault("est_charges", period_net.est_charges)
        cumulative_summary.setdefault("est_net_pnl", period_net.net_pnl)

        wb = openpyxl.Workbook()
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
            bottom=Side(style="thin", color="CCCCCC"),
        )

        def _autofit(ws) -> None:
            for col in ws.columns:
                max_len = max(len(str(cell.value or "")) for cell in col)
                ws.column_dimensions[get_column_letter(col[0].column)].width = max(max_len + 3, 12)

        def _kv_block(ws, start_row: int, rows: List[tuple]) -> int:
            r = start_row
            for label, val in rows:
                ws.cell(row=r, column=1, value=label).font = bold_font
                cell_v = ws.cell(row=r, column=2, value=str(val))
                cell_v.font = normal_font
                ws.cell(row=r, column=1).border = thin_border
                ws.cell(row=r, column=2).border = thin_border
                r += 1
            return r

        # ---- Sheet 1: Executed trades ----
        ws1 = wb.active
        ws1.title = "Executed Trades"
        period_label = (
            f"{period.period_start} to {period.period_end}"
            if period.period_start and period.period_end
            else today
        )
        ws1.cell(row=1, column=1, value="NexTrade — Executed Trades Log").font = title_font
        ws1.cell(
            row=2,
            column=1,
            value=(
                f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} | "
                f"Period: {period_label} | Currency: INR | Est. Net = Gross - cost proxy"
            ),
        ).font = normal_font

        headers_ws1 = [
            "Trade ID",
            "Timestamp",
            "Symbol",
            "Style",
            "Strategy",
            "Direction",
            "Qty",
            "Entry Price (INR)",
            "Exit Price (INR)",
            "Exit Reason",
            "Gross P&L (INR)",
            "Est. Charges (INR)",
            "Est. Net P&L (INR)",
            "Status",
        ]
        start_row = 4
        for col_idx, h_text in enumerate(headers_ws1, 1):
            cell = ws1.cell(row=start_row, column=col_idx, value=h_text)
            cell.fill = header_fill
            cell.font = header_font
            cell.alignment = Alignment(horizontal="center", vertical="center")

        current_row = start_row + 1
        if not trades:
            ws1.cell(row=current_row, column=1, value="No closed trades in journal.").font = normal_font
            current_row += 1
        else:
            for t in trades:
                if str(t.get("status") or "").upper() == "OPEN":
                    continue
                e = enrich_trade_with_net(t)
                ws1.cell(row=current_row, column=1, value=e.get("trade_id", "-")).font = normal_font
                ws1.cell(row=current_row, column=2, value=e.get("timestamp", "-")).font = normal_font
                ws1.cell(row=current_row, column=3, value=e.get("symbol", "-")).font = bold_font
                ws1.cell(row=current_row, column=4, value=e.get("style", "-")).font = normal_font
                ws1.cell(row=current_row, column=5, value=e.get("strategy", "-")).font = normal_font
                ws1.cell(row=current_row, column=6, value=e.get("direction", "-")).font = normal_font
                ws1.cell(row=current_row, column=7, value=e.get("quantity", 0)).font = normal_font
                ws1.cell(row=current_row, column=8, value=e.get("entry_price", 0.0)).font = normal_font
                ws1.cell(row=current_row, column=9, value=e.get("exit_price", 0.0)).font = normal_font
                ws1.cell(row=current_row, column=10, value=e.get("exit_reason", "-")).font = normal_font
                g = float(e.get("gross_pnl") or 0.0)
                n = float(e.get("net_pnl") or 0.0)
                g_cell = ws1.cell(row=current_row, column=11, value=g)
                g_cell.font = green_font if g >= 0 else red_font
                ws1.cell(row=current_row, column=12, value=float(e.get("est_charges") or 0.0)).font = normal_font
                n_cell = ws1.cell(row=current_row, column=13, value=n)
                n_cell.font = green_font if n >= 0 else red_font
                ws1.cell(row=current_row, column=14, value=e.get("status", "CLOSED")).font = normal_font
                for c in range(1, 15):
                    ws1.cell(row=current_row, column=c).border = thin_border
                current_row += 1
        _autofit(ws1)

        # ---- Sheet 2: Today vs Period ----
        ws2 = wb.create_sheet(title="Today vs Period Summary")
        ws2.cell(row=1, column=1, value="NexTrade — Today vs Period Performance").font = title_font

        ws2.cell(row=3, column=1, value="1. Today's Performance (IST calendar day only)").font = section_font
        r = _kv_block(
            ws2,
            4,
            [
                ("Trading Date", daily_summary.get("date", today)),
                ("Trades Today", int(daily_summary.get("total_trades_today", today_m.total_trades))),
                ("Today Gross P&L (INR)", f"{float(daily_summary.get('todays_net_pnl', today_m.gross_pnl)):,.2f}"),
                ("Today Win Rate (%)", f"{float(daily_summary.get('todays_win_rate_pct', today_m.win_rate_pct)):.1f}%"),
                ("Today Expectancy (INR)", f"{today_m.expectancy:,.2f}"),
            ],
        )

        r += 1
        ws2.cell(row=r, column=1, value="2. Period / Journal Performance").font = section_font
        r += 1
        capital0 = float(daily_summary.get("starting_capital", starting_capital))
        r = _kv_block(
            ws2,
            r,
            [
                ("Period Start", cumulative_summary.get("period_start", period.period_start or "-")),
                ("Period End", cumulative_summary.get("period_end", period.period_end or "-")),
                ("Starting Capital (INR)", f"{capital0:,.2f}"),
                ("Ending Capital (INR)", f"{capital0 + float(period.gross_pnl):,.2f}"),
                ("Gross P&L (INR)", f"{float(cumulative_summary.get('cumulative_net_pnl', period.gross_pnl)):,.2f}"),
                ("Est. Charges (INR)", f"{float(cumulative_summary.get('est_charges', period_net.est_charges)):,.2f}"),
                ("Est. Net P&L (INR)", f"{float(cumulative_summary.get('est_net_pnl', period_net.net_pnl)):,.2f}"),
                ("Total Trades", int(cumulative_summary.get("cumulative_trades", period.total_trades))),
                ("Win Rate (%)", f"{float(cumulative_summary.get('cumulative_win_rate_pct', period.win_rate_pct)):.1f}%"),
                ("Profit Factor", f"{float(cumulative_summary.get('profit_factor', period.profit_factor)):.2f}"),
                ("Expectancy / Trade (INR)", f"{float(cumulative_summary.get('expectancy', period.expectancy)):,.2f}"),
                ("Avg Winner (INR)", f"{float(cumulative_summary.get('avg_win', period.avg_win)):,.2f}"),
                ("Avg Loser (INR)", f"{float(cumulative_summary.get('avg_loss', period.avg_loss)):,.2f}"),
                ("Largest Winner (INR)", f"{float(cumulative_summary.get('largest_win', period.largest_win)):,.2f}"),
                ("Largest Loser (INR)", f"{float(cumulative_summary.get('largest_loss', period.largest_loss)):,.2f}"),
                ("Max Drawdown (INR)", f"{float(cumulative_summary.get('max_drawdown', abs(period.max_drawdown))):,.2f}"),
                ("Max Consecutive Losses", int(cumulative_summary.get("max_consecutive_losses", period.max_consecutive_losses))),
                ("BUY Gross P&L (INR)", f"{period.by_direction.get('BUY', 0.0):,.2f}"),
                ("SELL Gross P&L (INR)", f"{period.by_direction.get('SELL', 0.0):,.2f}"),
            ],
        )
        _autofit(ws2)

        # ---- Sheet 3: Daily breakdown ----
        ws3 = wb.create_sheet(title="Daily Breakdown")
        ws3.cell(row=1, column=1, value="NexTrade — Daily Gross P&L Breakdown").font = title_font
        for col_idx, h in enumerate(["Date", "Trades", "Wins", "Losses", "Gross P&L (INR)", "Win Rate %"], 1):
            cell = ws3.cell(row=3, column=col_idx, value=h)
            cell.fill = header_fill
            cell.font = header_font
        rr = 4
        for day, pnl in period.daily.items():
            day_m = compute_journal_metrics(filter_trades_for_day(trades, day))
            ws3.cell(row=rr, column=1, value=day).font = normal_font
            ws3.cell(row=rr, column=2, value=day_m.total_trades).font = normal_font
            ws3.cell(row=rr, column=3, value=day_m.winning_trades).font = normal_font
            ws3.cell(row=rr, column=4, value=day_m.losing_trades).font = normal_font
            pcell = ws3.cell(row=rr, column=5, value=pnl)
            pcell.font = green_font if pnl >= 0 else red_font
            ws3.cell(row=rr, column=6, value=day_m.win_rate_pct).font = normal_font
            for c in range(1, 7):
                ws3.cell(row=rr, column=c).border = thin_border
            rr += 1
        if rr == 4:
            ws3.cell(row=4, column=1, value="No daily rows.").font = normal_font
        _autofit(ws3)

        # ---- Sheet 4: Strategy breakdown ----
        ws4 = wb.create_sheet(title="Strategy Breakdown")
        ws4.cell(row=1, column=1, value="NexTrade — Strategy Performance Breakdown").font = title_font
        for col_idx, h in enumerate(
            ["Strategy", "Trades", "Wins", "Losses", "Win Rate %", "Gross P&L (INR)", "Profit Factor", "Expectancy"],
            1,
        ):
            cell = ws4.cell(row=3, column=col_idx, value=h)
            cell.fill = header_fill
            cell.font = header_font
        rr = 4
        for strat, st in period.by_strategy.items():
            ws4.cell(row=rr, column=1, value=strat).font = bold_font
            ws4.cell(row=rr, column=2, value=st["trades"]).font = normal_font
            ws4.cell(row=rr, column=3, value=st["wins"]).font = normal_font
            ws4.cell(row=rr, column=4, value=st["losses"]).font = normal_font
            ws4.cell(row=rr, column=5, value=st["win_rate_pct"]).font = normal_font
            pcell = ws4.cell(row=rr, column=6, value=st["pnl"])
            pcell.font = green_font if st["pnl"] >= 0 else red_font
            ws4.cell(row=rr, column=7, value=st["profit_factor"]).font = normal_font
            ws4.cell(row=rr, column=8, value=st["expectancy"]).font = normal_font
            for c in range(1, 9):
                ws4.cell(row=rr, column=c).border = thin_border
            rr += 1
        if rr == 4:
            ws4.cell(row=4, column=1, value="No strategy rows.").font = normal_font
        _autofit(ws4)

        try:
            wb.save(filepath)
        except PermissionError:
            alt = os.path.join(self.reports_dir, f"NexTrade_Trading_Log_{date_str}_{stamp}_alt.xlsx")
            wb.save(alt)
            filepath = alt
        finally:
            wb.close()
        return filepath
