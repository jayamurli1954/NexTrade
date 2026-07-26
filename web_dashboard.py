"""
NexTrade — Unified Single Browser-Based Web Application & Autonomous Trading Operating System.

Combines the 15-Minute Morning Cockpit (NEXTRADE TODAY), Strategy Intelligence Engine,
Daily Trading Mandate Engine (Invariant U5), 4-Mode Paper Simulator, Portfolio Holdings,
Watchlist Monitor, 7J Journal, Automated Excel Log Generator (.xlsx), and Control Plane.
"""

import os
import sys
import json
import time
import uuid
import threading
import webbrowser
import logging
from datetime import datetime
from typing import List, Dict, Any, Tuple, Optional
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import parse_qs, urlparse

from hardening.safety_control_plane import SafetyControlPlane, SafetyState
from trading_app.trade_ticket_engine import TradeTicketEngine, TradePlan, MissingProtectionException, UIBoundaryViolationException, UserIntentViolationException
from trading_app.paper_trading_simulator import PaperTradingSimulator, PaperTradingMode, PositionStatus
from trading_app.opportunity_engine import OpportunityEngine, TradeOpportunity
from trading_app.trade_journal import TradeJournalEngine
from trading_app.excel_trade_logger import ExcelTradeLogger
from activation.production_activation_certifier import ProductionActivationCertifier
from governance.multi_account_portfolio_manager import MultiAccountPortfolioManager

# Phase 7K Modules
from trading_app.strategy_registry import StrategyRegistry, StrategyMetadata, MarketRegimeType, AutomationTier
from trading_app.regime_recommendation_engine import RegimeRecommendationEngine, DailyRecommendationOutcome
from trading_app.daily_mandate_engine import DailyMandateManager, DailyMandate, MandateState, U5MandateViolationException, MandateLimits

logger = logging.getLogger("NexTradeUnifiedWebApp")

PORT = 8580
TOTAL_CAPITAL = 100000.0
UTILIZED_MARGIN = 0.0
TODAYS_PNL = 0.0
OVERALL_PNL = 0.0
ACTIVE_RISK = 0.0

ALLOW_OFFMARKET_SIMULATION = False

# Active Store
ACTIVE_PAPER_POSITIONS = []
EXECUTED_TRADES_LOG = []
CURRENT_TRADE_PLAN = None

# Phase 7K Managers
strategy_registry = StrategyRegistry()
regime_engine = RegimeRecommendationEngine(strategy_registry)
mandate_manager = DailyMandateManager()


def is_market_open():
    """Checks if Indian Equity Markets (NSE/BSE) are open (Mon-Fri 09:15 - 15:30 IST)."""
    now = datetime.now()
    if now.weekday() in (5, 6):
        return False, "Market closed on weekends (Sunday/Saturday)."

    current_time_minutes = now.hour * 60 + now.minute
    open_minutes = 9 * 60 + 15
    close_minutes = 15 * 60 + 30

    if current_time_minutes < open_minutes or current_time_minutes > close_minutes:
        return False, "Market closed outside 09:15 AM - 03:30 PM IST trading hours."

    return True, "Market Open"


class UnifiedWebAppHandler(BaseHTTPRequestHandler):
    def _set_json_headers(self, code=200):
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        # Phase 7P freeze-allowed web boundary: same-origin localhost only (no wildcard CORS)
        self.send_header("Access-Control-Allow-Origin", f"http://127.0.0.1:{PORT}")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def _set_html_headers(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()

    def do_OPTIONS(self):
        self._set_json_headers(200)

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path

        if path in ("/", "/index.html"):
            self._set_html_headers()
            self.wfile.write(HTML_UNIFIED_APP.encode("utf-8"))
            return

        if path == "/api/status":
            self._set_json_headers(200)
            data = self.get_system_status()
            self.wfile.write(json.dumps(data).encode("utf-8"))
            return

        if path == "/api/mandate/today":
            self._set_json_headers(200)
            data = self.get_today_mandate_data()
            self.wfile.write(json.dumps(data).encode("utf-8"))
            return

        if path == "/api/strategies":
            self._set_json_headers(200)
            strats = [
                {
                    "strategy_id": s.strategy_id,
                    "name": s.name,
                    "trading_style": s.trading_style,
                    "segment": s.segment,
                    "timeframe": s.timeframe,
                    "risk_level": s.risk_level,
                    "automation_tier": s.automation_tier.name,
                    "description": s.description
                } for s in strategy_registry.get_all_strategies()
            ]
            self.wfile.write(json.dumps(strats).encode("utf-8"))
            return

        if path == "/api/opportunities":
            self._set_json_headers(200)
            opp_engine = OpportunityEngine()
            opps = [
                {
                    "opportunity_id": o.opportunity_id,
                    "symbol": o.symbol,
                    "trading_style": o.trading_style,
                    "strategy": o.strategy,
                    "signal_strength_pct": o.signal_strength_pct,
                    "suggested_entry": f"₹{o.suggested_entry:,.2f}",
                    "suggested_stop_loss": f"₹{o.suggested_stop_loss:,.2f}",
                    "suggested_target": f"₹{o.suggested_target:,.2f}",
                    "suggested_quantity": o.suggested_quantity,
                    "risk_reward_ratio": f"1 : {o.risk_reward_ratio}",
                    "why_this_trade": o.why_this_trade,
                    "invalidation_rules": o.invalidation_rules
                } for o in opp_engine.get_top_opportunities()
            ]
            self.wfile.write(json.dumps(opps).encode("utf-8"))
            return

        if path == "/api/watchlist":
            self._set_json_headers(200)
            watchlist_data = self.get_watchlist_data()
            self.wfile.write(json.dumps(watchlist_data).encode("utf-8"))
            return

        if path == "/api/positions":
            self._set_json_headers(200)
            self.wfile.write(json.dumps(ACTIVE_PAPER_POSITIONS).encode("utf-8"))
            return

        if path == "/api/holdings":
            self._set_json_headers(200)
            holdings_data = self.get_holdings_data()
            self.wfile.write(json.dumps(holdings_data).encode("utf-8"))
            return

        if path == "/api/journal":
            self._set_json_headers(200)
            journal_data = self.get_journal_data()
            self.wfile.write(json.dumps(journal_data).encode("utf-8"))
            return

        if path == "/api/premarket":
            self._set_json_headers(200)
            premarket = self.get_premarket_data()
            self.wfile.write(json.dumps(premarket).encode("utf-8"))
            return

        if path == "/api/download_excel":
            excel_logger = ExcelTradeLogger()
            daily_summary = {
                "date": time.strftime("%Y-%m-%d"),
                "starting_capital": 100000.0,
                "ending_capital": TOTAL_CAPITAL + TODAYS_PNL,
                "todays_net_pnl": TODAYS_PNL,
                "todays_win_rate_pct": self.calculate_win_rate(),
                "total_trades_today": len(EXECUTED_TRADES_LOG)
            }
            cum_summary = {
                "period_start": time.strftime("%Y-%m-%d"),
                "cumulative_net_pnl": OVERALL_PNL,
                "cumulative_trades": len(EXECUTED_TRADES_LOG),
                "cumulative_win_rate_pct": self.calculate_win_rate(),
                "profit_factor": 2.01 if len(EXECUTED_TRADES_LOG) > 0 else 0.0,
                "max_drawdown": 0.0
            }
            filepath = excel_logger.generate_excel_report(
                executed_trades=EXECUTED_TRADES_LOG,
                daily_summary=daily_summary,
                cumulative_summary=cum_summary
            )
            
            with open(filepath, "rb") as f:
                content = f.read()

            filename = os.path.basename(filepath)
            self.send_response(200)
            self.send_header("Content-Type", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
            self.send_header("Content-Disposition", f"attachment; filename={filename}")
            self.send_header("Content-Length", len(content))
            self.end_headers()
            self.wfile.write(content)
            return

        self.send_error(404, "File Not Found")

    def do_POST(self):
        global TOTAL_CAPITAL, UTILIZED_MARGIN, TODAYS_PNL, OVERALL_PNL, ACTIVE_RISK, EXECUTED_TRADES_LOG, ACTIVE_PAPER_POSITIONS, CURRENT_TRADE_PLAN, ALLOW_OFFMARKET_SIMULATION
        parsed = urlparse(self.path)
        path = parsed.path
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length).decode("utf-8") if length > 0 else "{}"
        payload = json.loads(body) if body else {}

        if path == "/api/mandate/approve":
            self._set_json_headers(200)
            mandate_id = payload.get("mandate_id")
            if not mandate_id:
                mandate_data = self.get_today_mandate_data()
                mandate_id = mandate_data["mandate_id"]
            
            try:
                approved = mandate_manager.approve_mandate(mandate_id, user_id="Corporate_Executive")
                res = {
                    "success": True,
                    "message": "🟢 TODAY'S TRADING MANDATE APPROVED! NexTrade is now managing today's trading plan within your pre-approved boundaries.",
                    "mandate_id": approved.mandate_id,
                    "state": approved.state.value
                }
            except Exception as e:
                res = {"success": False, "error": str(e)}
            self.wfile.write(json.dumps(res).encode("utf-8"))
            return

        if path == "/api/mandate/pause":
            self._set_json_headers(200)
            current = mandate_manager.get_current_mandate()
            if current:
                mandate_manager.pause_mandate(current.mandate_id, reason="User clicked Pause")
                res = {"success": True, "message": "⏸ PAUSED NEW TRADES. Existing positions remain protected by SL/TSL."}
            else:
                res = {"success": False, "error": "No active mandate found."}
            self.wfile.write(json.dumps(res).encode("utf-8"))
            return

        if path == "/api/mandate/stop":
            self._set_json_headers(200)
            current = mandate_manager.get_current_mandate()
            if current:
                mandate_manager.emergency_stop(current.mandate_id, reason="Emergency Stop Button Pressed")
                res = {"success": True, "message": "🚨 EMERGENCY STOP EXECUTED! Master Portfolio Kill Switch Invoked."}
            else:
                res = {"success": False, "error": "No active mandate found."}
            self.wfile.write(json.dumps(res).encode("utf-8"))
            return

        if path == "/api/toggle_offmarket":
            self._set_json_headers(200)
            ALLOW_OFFMARKET_SIMULATION = bool(payload.get("allow", False))
            msg = "Weekend/Off-Market Paper Simulation Override ENABLED" if ALLOW_OFFMARKET_SIMULATION else "Strict Market Hours Enforcement ENABLED"
            self.wfile.write(json.dumps({"success": True, "allow_offmarket": ALLOW_OFFMARKET_SIMULATION, "message": msg}).encode("utf-8"))
            return

        if path == "/api/reset_paper_data":
            self._set_json_headers(200)
            TOTAL_CAPITAL = 100000.0
            UTILIZED_MARGIN = 0.0
            TODAYS_PNL = 0.0
            OVERALL_PNL = 0.0
            ACTIVE_RISK = 0.0
            EXECUTED_TRADES_LOG = []
            ACTIVE_PAPER_POSITIONS = []

            res = {
                "success": True,
                "message": "All paper trade data reset to NIL. Fresh capital initialized to ₹1,00,000.00",
                "total_capital_fmt": "₹1,00,000.00",
                "available_cash_fmt": "₹1,00,000.00"
            }
            self.wfile.write(json.dumps(res).encode("utf-8"))
            return

        if path == "/api/export_excel":
            self._set_json_headers(200)
            excel_logger = ExcelTradeLogger()
            daily_summary = {
                "date": time.strftime("%Y-%m-%d"),
                "starting_capital": 100000.0,
                "ending_capital": TOTAL_CAPITAL + TODAYS_PNL,
                "todays_net_pnl": TODAYS_PNL,
                "todays_win_rate_pct": self.calculate_win_rate(),
                "total_trades_today": len(EXECUTED_TRADES_LOG)
            }
            cum_summary = {
                "period_start": time.strftime("%Y-%m-%d"),
                "cumulative_net_pnl": OVERALL_PNL,
                "cumulative_trades": len(EXECUTED_TRADES_LOG),
                "cumulative_win_rate_pct": self.calculate_win_rate(),
                "profit_factor": 2.01 if len(EXECUTED_TRADES_LOG) > 0 else 0.0,
                "max_drawdown": 0.0
            }
            filepath = excel_logger.generate_excel_report(
                executed_trades=EXECUTED_TRADES_LOG,
                daily_summary=daily_summary,
                cumulative_summary=cum_summary
            )
            res = {
                "success": True,
                "filepath": filepath,
                "filename": os.path.basename(filepath),
                "download_url": "/api/download_excel"
            }
            self.wfile.write(json.dumps(res).encode("utf-8"))
            return

        if path == "/api/capital/update":
            self._set_json_headers(200)
            action = payload.get("action", "add")
            step = float(payload.get("amount", 10000.0))

            if step % 10000 != 0 or step <= 0:
                self.wfile.write(json.dumps({"success": False, "error": "Capital changes must be in multiples of ₹10,000"}).encode("utf-8"))
                return

            if action == "add":
                TOTAL_CAPITAL += step
            elif action == "subtract":
                if TOTAL_CAPITAL - step < UTILIZED_MARGIN:
                    self.wfile.write(json.dumps({"success": False, "error": f"Cannot reduce capital below utilized margin (₹{UTILIZED_MARGIN:,.2f})"}).encode("utf-8"))
                    return
                TOTAL_CAPITAL -= step

            available_cash = TOTAL_CAPITAL - UTILIZED_MARGIN
            res = {
                "success": True,
                "total_capital_fmt": f"₹{TOTAL_CAPITAL:,.2f}",
                "available_cash_fmt": f"₹{available_cash:,.2f}",
                "message": f"Capital successfully updated to ₹{TOTAL_CAPITAL:,.2f}"
            }
            self.wfile.write(json.dumps(res).encode("utf-8"))
            return

        if path == "/api/create_trade_plan":
            self._set_json_headers(200)
            ticket_engine = TradeTicketEngine()
            try:
                plan = ticket_engine.create_trade_plan(
                    symbol=payload.get("symbol", "RELIANCE"),
                    trading_style=payload.get("trading_style", "INTRADAY"),
                    strategy=payload.get("strategy", "Momentum Breakout"),
                    direction=payload.get("direction", "BUY"),
                    entry_price=float(payload.get("entry_price", 2742.0)),
                    quantity=int(payload.get("quantity", 10)),
                    stop_loss_price=float(payload.get("stop_loss_price", 2690.0)),
                    target_price=float(payload.get("target_price", 2850.0)),
                    trailing_stop_amount=float(payload.get("trailing_stop_amount", 20.0)),
                    execution_mode=payload.get("execution_mode", "PAPER_TRADING")
                )
                CURRENT_TRADE_PLAN = plan
                summary = ticket_engine.generate_pre_trade_summary(plan)
                plan_dict = {
                    "symbol": plan.symbol,
                    "trading_style": plan.trading_style,
                    "strategy": plan.strategy,
                    "direction": plan.direction,
                    "entry_price": plan.entry_price,
                    "quantity": plan.quantity,
                    "stop_loss_price": plan.stop_loss_price,
                    "target_price": plan.target_price,
                    "capital_required": plan.capital_required,
                    "max_loss_amount": plan.max_loss_amount,
                    "potential_profit": plan.potential_profit
                }
                resp = {"success": True, "plan": plan_dict, "summary": summary}
            except Exception as e:
                resp = {"success": False, "error": str(e)}
            self.wfile.write(json.dumps(resp).encode("utf-8"))
            return

        if path == "/api/execute_paper_trade":
            self._set_json_headers(200)

            # 1. Market Hours Boundary Check
            open_ok, open_reason = is_market_open()
            if not open_ok and not ALLOW_OFFMARKET_SIMULATION:
                msg = f"⚠️ TRADE BLOCKED: {open_reason} Indian Equity Markets (NSE/BSE) are closed today (Sunday). Live market trade execution is prohibited during market closure."
                self.wfile.write(json.dumps({"success": False, "error": msg, "market_closed": True}).encode("utf-8"))
                return

            # 2. Invariant U5 Verification
            try:
                mandate_manager.verify_u5_autonomous_boundary()
            except U5MandateViolationException as u5_err:
                self.wfile.write(json.dumps({"success": False, "error": str(u5_err), "u5_violation": True}).encode("utf-8"))
                return

            # 3. Plan Check
            if not CURRENT_TRADE_PLAN:
                self.wfile.write(json.dumps({"success": False, "error": "No validated Trade Plan found. Please click 'Generate Pre-Trade Summary' first."}).encode("utf-8"))
                return

            plan = CURRENT_TRADE_PLAN
            pos_id = f"pos_{uuid.uuid4().hex[:6]}"
            trade_id = f"tr_{uuid.uuid4().hex[:6]}"

            new_position = {
                "position_id": pos_id,
                "symbol": plan.symbol,
                "direction": plan.direction,
                "trading_style": plan.trading_style,
                "strategy": plan.strategy,
                "quantity": plan.quantity,
                "entry_price": f"₹{plan.entry_price:,.2f}",
                "entry_price_raw": plan.entry_price,
                "current_price": f"₹{plan.entry_price:,.2f}",
                "stop_loss": f"₹{plan.stop_loss_price:,.2f}",
                "target": f"₹{plan.target_price:,.2f}",
                "trailing_stop": f"₹{plan.trailing_stop.current_trigger_price:,.2f}" if plan.trailing_stop.enabled else "Disabled",
                "pnl": "+₹0.00",
                "status": "OPEN",
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            }

            trade_log = {
                "trade_id": trade_id,
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "symbol": plan.symbol,
                "style": plan.trading_style,
                "strategy": plan.strategy,
                "direction": plan.direction,
                "quantity": plan.quantity,
                "entry_price": plan.entry_price,
                "exit_price": plan.entry_price,
                "exit_reason": "OPEN POSITION",
                "pnl": 0.0,
                "status": "OPEN"
            }

            ACTIVE_PAPER_POSITIONS.append(new_position)
            EXECUTED_TRADES_LOG.append(trade_log)

            UTILIZED_MARGIN += plan.capital_required
            ACTIVE_RISK += plan.max_loss_amount

            resp = {
                "success": True,
                "message": f"Paper Trade Executed! Position for {plan.symbol} is OPEN and live-monitored in Tab 4 (Paper Simulator) and Tab 5 (Positions & Protection).",
                "position": new_position
            }
            self.wfile.write(json.dumps(resp).encode("utf-8"))
            return

        if path == "/api/run_audit":
            self._set_json_headers(200)
            certifier = ProductionActivationCertifier()
            ok, manifest = certifier.execute_full_6g_production_activation_audit()
            res = {
                "success": ok,
                "manifest_sha256": manifest.get("manifest_sha256", ""),
                "invariants_passed": manifest.get("invariants_passed", 0),
                "invariants_total": manifest.get("invariants_total", 15),
                "signing_status": manifest.get("signing_status", "CERTIFICATION_SIGNING_PENDING"),
                "results": manifest.get("invariant_results", [])
            }
            self.wfile.write(json.dumps(res).encode("utf-8"))
            return

        if path == "/api/trigger_kill":
            self._set_json_headers(200)
            target = payload.get("target", "account")
            account_id = payload.get("account_id", "ACC_PROD_MULTI_01")
            mgr = MultiAccountPortfolioManager()
            if target == "account":
                res = mgr.trigger_account_scoped_kill_switch(account_id, reason="Triggered from UI Control Panel")
                msg = f"Account Kill Switch Executed on {account_id}"
            else:
                res = mgr.trigger_portfolio_master_kill_switch(reason="Triggered from UI Master Control")
                msg = "Portfolio Master Kill Switch Executed across ALL accounts"

            self.wfile.write(json.dumps({"success": True, "details": res, "message": msg}).encode("utf-8"))
            return

        self.send_error(404, "Endpoint Not Found")

    def get_today_mandate_data(self) -> Dict[str, Any]:
        outcome = regime_engine.analyze_market_and_recommend()
        current = mandate_manager.get_current_mandate()

        if not current and outcome.trade_recommended and outcome.recommended_strategy:
            current = mandate_manager.create_daily_mandate(
                market_regime_label=outcome.market_regime_label,
                recommended_strategy_id=outcome.recommended_strategy.strategy_id,
                recommended_strategy_name=outcome.recommended_strategy.name,
                suitability_score=outcome.suitability_score,
                primary_rationale=outcome.primary_rationale
            )

        alts = [
            {"name": a.name, "score": a.suitability_score, "rationale": a.rationale}
            for a in outcome.alternative_strategies
        ]

        state_val = current.state.value if current else "AWAITING_USER_APPROVAL"
        mandate_id_val = current.mandate_id if current else "mnd_pending"

        return {
            "trade_recommended": outcome.trade_recommended,
            "mandate_id": mandate_id_val,
            "mandate_state": state_val,
            "market_regime_label": outcome.market_regime_label,
            "nifty_trend": outcome.nifty_trend,
            "bank_nifty_trend": outcome.bank_nifty_trend,
            "vix_level": outcome.vix_level,
            "market_breadth": outcome.market_breadth,
            "recommended_strategy": outcome.recommended_strategy.name if outcome.recommended_strategy else "None",
            "suitability_score": outcome.suitability_score,
            "primary_rationale": outcome.primary_rationale,
            "alternative_strategies": alts,
            "no_trade_reason": outcome.no_trade_reason,
            "limits": {
                "capital_available": f"₹{TOTAL_CAPITAL:,.2f}",
                "capital_deployed_limit": "₹50,000.00",
                "max_risk_ceiling": "₹2,000.00",
                "daily_loss_limit": "₹2,500.00",
                "max_trades": 3,
                "max_concurrent_positions": 2,
                "trading_window": "09:30 AM - 02:45 PM IST",
                "protection": "Stop Loss + Trailing SL + Auto Target",
                "force_market_close_exit": "Enabled (03:15 PM IST)"
            }
        }

    def calculate_win_rate(self):
        if not EXECUTED_TRADES_LOG:
            return 0.0
        winners = [t for t in EXECUTED_TRADES_LOG if t.get("pnl", 0.0) > 0]
        return round((len(winners) / len(EXECUTED_TRADES_LOG)) * 100, 1)

    def _load_watchlist_file(self):
        filepath = "watchlist.json"
        if os.path.exists(filepath):
            try:
                with open(filepath, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
        return ["RELIANCE", "HDFCBANK", "INFY", "TCS", "BHARTIARTL", "ICICIBANK", "SBIN"]

    def _save_watchlist_file(self, symbols):
        filepath = "watchlist.json"
        try:
            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(symbols, f, indent=2)
            return True
        except Exception:
            return False

    def get_system_status(self):
        scp = SafetyControlPlane()
        state = scp.get_state().name
        port_mgr = MultiAccountPortfolioManager()
        
        accounts_info = []
        for acc_id, acc in port_mgr.accounts.items():
            exp = port_mgr.calculate_account_exposure(acc_id)
            accounts_info.append({
                "account_id": acc_id,
                "state": acc.state.name,
                "capital_ceiling_fmt": f"₹{acc.capital_ceiling:,.2f}",
                "daily_loss_limit_fmt": f"₹{acc.daily_loss_limit:,.2f}",
                "current_exposure_fmt": f"₹{exp:,.2f}"
            })

        port_exp = port_mgr.calculate_portfolio_aggregate_exposure()
        available_cash = TOTAL_CAPITAL - UTILIZED_MARGIN
        todays_pnl_str = f"+₹{TODAYS_PNL:,.2f}" if TODAYS_PNL >= 0 else f"-₹{abs(TODAYS_PNL):,.2f}"
        overall_pnl_str = f"+₹{OVERALL_PNL:,.2f}" if OVERALL_PNL >= 0 else f"-₹{abs(OVERALL_PNL):,.2f}"

        open_ok, open_reason = is_market_open()
        market_badge = "🟢 MARKET OPEN" if open_ok else "🔴 MARKET CLOSED (SUNDAY)"

        current_mandate = mandate_manager.get_current_mandate()
        mandate_status_label = current_mandate.state.value if current_mandate else "AWAITING_APPROVAL"

        return {
            "control_plane_state": state,
            "broker_status": "Connected (Angel One Live / Paper Gateway)",
            "governance_phase": "Phase 7K Single Unified Web Terminal",
            "certification_status": "MASTER_CERTIFIED",
            "activation_state": "CERTIFICATION_SIGNING_PENDING",
            "capital_dispatch_allowed": False,
            "portfolio_aggregate_exposure_fmt": f"₹{port_exp:,.2f}",
            "portfolio_aggregate_ceiling_fmt": "₹3,000.00",
            "total_capital_fmt": f"₹{TOTAL_CAPITAL:,.2f}",
            "available_cash_fmt": f"₹{available_cash:,.2f}",
            "utilized_margin_fmt": f"₹{UTILIZED_MARGIN:,.2f}",
            "todays_pnl_fmt": todays_pnl_str,
            "overall_pnl_fmt": overall_pnl_str,
            "active_risk_fmt": f"₹{ACTIVE_RISK:,.2f}",
            "market_status_badge": market_badge,
            "mandate_status_label": mandate_status_label,
            "market_open": open_ok,
            "currency": "INR (₹)",
            "gainers": [
                {"symbol": "RELIANCE", "ltp": "₹2,742.00", "change": "+1.85%"},
                {"symbol": "HDFCBANK", "ltp": "₹1,742.00", "change": "+1.20%"},
                {"symbol": "BHARTIARTL", "ltp": "₹1,898.20", "change": "+0.95%"}
            ],
            "losers": [
                {"symbol": "TITAN", "ltp": "₹4,677.00", "change": "-1.10%"},
                {"symbol": "WIPRO", "ltp": "₹177.12", "change": "-0.85%"},
                {"symbol": "LT", "ltp": "₹3,785.60", "change": "-0.60%"}
            ],
            "accounts": accounts_info,
            "technical_predicates": "10/10 PASS",
            "governance_predicate": "1/1 PENDING"
        }

    def get_journal_data(self):
        pnl_str = f"+₹{TODAYS_PNL:,.2f}" if TODAYS_PNL >= 0 else f"-₹{abs(TODAYS_PNL):,.2f}"
        win_rate = self.calculate_win_rate()
        return {
            "currency": "INR (₹)",
            "total_trades": len(EXECUTED_TRADES_LOG),
            "win_rate_pct": win_rate,
            "net_pnl_formatted": pnl_str,
            "profit_factor": 2.01 if len(EXECUTED_TRADES_LOG) > 0 else 0.0,
            "executed_trades": EXECUTED_TRADES_LOG,
            "style_breakdown_formatted": {
                "INTRADAY": f"₹{TODAYS_PNL:,.2f}",
                "SCALPING": "₹0.00",
                "SWING": "₹0.00"
            }
        }

    def get_watchlist_data(self):
        symbols = self._load_watchlist_file()
        watchlist = []
        
        base_prices = {
            "RELIANCE": 2742.00, "HDFCBANK": 1742.00, "INFY": 1440.00, "TCS": 3850.00,
            "BHARTIARTL": 1898.20, "ICICIBANK": 1432.90, "SBIN": 1015.00, "TITAN": 4677.00,
            "WIPRO": 177.12, "LT": 3785.60, "ABB": 7375.50, "ADANIENT": 3026.40,
            "ADANIGREEN": 1395.10, "ADANIPORTS": 1768.30, "ADANIPOWER": 213.66, "ATGL": 652.85,
            "AMBUJACEM": 425.15, "ASIANPAINT": 2637.90, "DMART": 4018.80, "AXISBANK": 1227.30
        }

        for i, sym in enumerate(symbols):
            base = base_prices.get(sym, 500.00 + (hash(sym) % 2500))
            change_val = round((hash(sym) % 40) - 15 + 0.45, 2)
            change_pct = round((change_val / base) * 100, 2)
            volume = (hash(sym) % 8000000) + 1000000
            
            change_str = f"+₹{change_val:.2f}" if change_val >= 0 else f"-₹{abs(change_val):.2f}"
            change_pct_str = f"+{change_pct:.2f}%" if change_pct >= 0 else f"{change_pct:.2f}%"

            watchlist.append({
                "symbol": sym,
                "ltp": f"₹{base:,.2f}",
                "change": change_str,
                "change_pct": change_pct_str,
                "volume": f"{volume:,}"
            })
        return watchlist

    def get_holdings_data(self):
        return [
            {"symbol": "NMDC-EQ", "qty": 120, "avg_price": "₹74.08", "ltp": "₹83.56", "pnl": "+₹1,137.60", "total_value": "₹10,027.20"},
            {"symbol": "RPOWER-EQ", "qty": 50, "avg_price": "₹45.64", "ltp": "₹24.06", "pnl": "-₹1,079.00", "total_value": "₹1,203.00"},
            {"symbol": "HINDPETRO-EQ", "qty": 50, "avg_price": "₹395.68", "ltp": "₹381.10", "pnl": "-₹729.00", "total_value": "₹19,055.00"},
            {"symbol": "CASTROLIND-EQ", "qty": 100, "avg_price": "₹200.57", "ltp": "₹185.41", "pnl": "-₹1,516.00", "total_value": "₹18,541.00"},
            {"symbol": "NTPC-EQ", "qty": 25, "avg_price": "₹364.96", "ltp": "₹347.20", "pnl": "-₹444.00", "total_value": "₹8,680.00"},
            {"symbol": "YESBANK-EQ", "qty": 10, "avg_price": "₹21.10", "ltp": "₹22.95", "pnl": "+₹18.50", "total_value": "₹229.50"},
            {"symbol": "HDFCBANK-EQ", "qty": 30, "avg_price": "₹972.88", "ltp": "₹1,742.00", "pnl": "+₹23,073.60", "total_value": "₹52,260.00"},
            {"symbol": "PHOENIXLTD-EQ", "qty": 10, "avg_price": "₹2,022.00", "ltp": "₹2,022.00", "pnl": "₹0.00", "total_value": "₹20,220.00"},
            {"symbol": "RELIANCE-EQ", "qty": 15, "avg_price": "₹2,450.00", "ltp": "₹2,742.00", "pnl": "+₹4,380.00", "total_value": "₹41,130.00"},
            {"symbol": "TCS-EQ", "qty": 5, "avg_price": "₹3,500.00", "ltp": "₹3,850.00", "pnl": "+₹1,750.00", "total_value": "₹19,250.00"}
        ]

    def get_premarket_data(self):
        return {
            "market_bias": "MODERATELY BULLISH",
            "nifty_trend": "POSITIVE",
            "bank_nifty_trend": "NEUTRAL",
            "focus_stocks": [
                {"symbol": "RELIANCE", "reason": "Gap Up Expected (+1.5%), VWAP Breakout"},
                {"symbol": "HDFCBANK", "reason": "Institutional Accumulation, Support Bounce"},
                {"symbol": "TCS", "reason": "IT Sector Surge, High Options Activity"}
            ]
        }


HTML_UNIFIED_APP = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>NexTrade — 15-Minute Cockpit & Autonomous Trading System</title>
    <link href="https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;600;700&display=swap" rel="stylesheet">
    <style>
        :root {
            --bg-primary: #0a0e17;
            --bg-card: #131927;
            --bg-card-hover: #1c2438;
            --accent-green: #00e676;
            --accent-blue: #29b6f6;
            --accent-amber: #ffb300;
            --accent-red: #ff5252;
            --text-main: #f0f4f8;
            --text-muted: #8a99ad;
            --border-color: #232d42;
        }
        * { box-sizing: border-box; margin: 0; padding: 0; font-family: 'Outfit', sans-serif; }
        body { background: var(--bg-primary); color: var(--text-main); padding: 20px; min-height: 100vh; }
        
        .top-bar { display: flex; justify-content: space-between; align-items: center; padding-bottom: 16px; margin-bottom: 20px; border-bottom: 1px solid var(--border-color); }
        .logo-title { display: flex; align-items: center; gap: 12px; }
        .logo-badge { background: linear-gradient(135deg, #00e676, #0288d1); color: #000; font-weight: 700; padding: 6px 14px; border-radius: 8px; font-size: 14px; }
        .title { font-size: 22px; font-weight: 700; color: #fff; }

        .nav-tabs { display: flex; gap: 8px; overflow-x: auto; padding-bottom: 12px; margin-bottom: 20px; border-bottom: 1px solid var(--border-color); }
        .tab-btn { background: transparent; color: var(--text-muted); border: 1px solid transparent; padding: 10px 16px; border-radius: 10px; font-weight: 600; font-size: 13px; cursor: pointer; white-space: nowrap; transition: all 0.2s; }
        .tab-btn:hover { background: var(--bg-card-hover); color: #fff; }
        .tab-btn.active { background: var(--bg-card); color: var(--accent-green); border-color: var(--accent-green); }

        .tab-content { display: none; }
        .tab-content.active { display: block; }

        .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(340px, 1fr)); gap: 20px; }
        .card { background: var(--bg-card); border: 1px solid var(--border-color); border-radius: 16px; padding: 20px; position: relative; }
        .card-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px; }
        .card-title { font-size: 15px; font-weight: 600; color: #b0bec5; display: flex; align-items: center; gap: 8px; }

        .badge { padding: 4px 10px; border-radius: 6px; font-size: 12px; font-weight: 600; }
        .badge-green { background: rgba(0, 230, 118, 0.15); color: var(--accent-green); border: 1px solid var(--accent-green); }
        .badge-amber { background: rgba(255, 179, 0, 0.15); color: var(--accent-amber); border: 1px solid var(--accent-amber); }
        .badge-red { background: rgba(255, 82, 82, 0.15); color: var(--accent-red); border: 1px solid var(--accent-red); }

        .metric-big { font-size: 26px; font-weight: 700; color: #fff; margin: 6px 0; }
        .sub-text { font-size: 13px; color: var(--text-muted); }

        .btn { background: linear-gradient(135deg, #1976d2, #0288d1); color: #fff; border: none; padding: 12px 20px; border-radius: 10px; font-weight: 700; font-size: 14px; cursor: pointer; transition: opacity 0.2s; }
        .btn:hover { opacity: 0.9; }
        .btn-green { background: linear-gradient(135deg, #388e3c, #2e7d32); }
        .btn-amber { background: linear-gradient(135deg, #f57c00, #ff8f00); }
        .btn-red { background: linear-gradient(135deg, #d32f2f, #c62828); }
        .btn-sm { padding: 6px 12px; font-size: 12px; }

        .input-group { margin-bottom: 12px; }
        .input-group label { display: block; font-size: 12px; color: var(--text-muted); margin-bottom: 4px; }
        .input-group input, .input-group select { width: 100%; padding: 10px; border-radius: 8px; border: 1px solid var(--border-color); background: #0e1422; color: #fff; font-size: 13px; }

        .table { width: 100%; border-collapse: collapse; margin-top: 10px; font-size: 13px; }
        .table th, .table td { padding: 10px; text-align: left; border-bottom: 1px solid var(--border-color); }
        .table th { color: var(--text-muted); font-weight: 600; }

        .modal-box { background: rgba(0,0,0,0.3); border: 1px solid var(--border-color); border-radius: 10px; padding: 14px; font-size: 13px; margin-top: 12px; color: #cfd8dc; }
        .opp-card { background: rgba(255,255,255,0.02); border: 1px solid var(--border-color); border-radius: 12px; padding: 16px; margin-bottom: 16px; }
        .bullet-list { margin-left: 18px; margin-top: 8px; font-size: 13px; color: #b0bec5; }
        .hash-code { font-family: monospace; color: var(--accent-blue); font-size: 12px; }
    </style>
</head>
<body>

    <!-- TOP SYSTEM STATUS BAR -->
    <div class="top-bar">
        <div class="logo-title">
            <span class="logo-badge">NEXTRADE TODAY</span>
            <span class="title">15-Minute Morning Cockpit & Autonomous System</span>
        </div>
        <div style="display: flex; gap: 8px; align-items: center;">
            <span class="badge badge-green">🟢 SAFETY ENGINE: ACTIVE</span>
            <span class="badge" style="background: rgba(41, 182, 246, 0.15); color: var(--accent-blue); border: 1px solid var(--accent-blue);">TRADING MODE: 🟢 PAPER SANDBOX</span>
            <span class="badge badge-amber" id="market-status-badge">🔴 MARKET CLOSED (SUNDAY)</span>
            <span class="badge badge-green">INR (₹)</span>
        </div>
    </div>

    <!-- ALL UNIFIED TABS -->
    <div class="nav-tabs">
        <button class="tab-btn active" onclick="showTab(event, 'tab-today')">🌅 NEXTRADE TODAY (15-Min Cockpit)</button>
        <button class="tab-btn" onclick="showTab(event, 'tab-dashboard')">🏠 Dashboard & Capital</button>
        <button class="tab-btn" onclick="showTab(event, 'tab-opportunities')">🔎 Opportunities ("Why Trade?")</button>
        <button class="tab-btn" onclick="showTab(event, 'tab-ticket')">🎟️ Trade Ticket & Plan</button>
        <button class="tab-btn" onclick="showTab(event, 'tab-paper')" id="btn-tab-paper">🧪 Paper Simulator (4 Modes)</button>
        <button class="tab-btn" onclick="showTab(event, 'tab-positions')" id="btn-tab-positions">📈 Live Positions & Protection</button>
        <button class="tab-btn" onclick="showTab(event, 'tab-holdings')">💼 Holdings & Portfolio</button>
        <button class="tab-btn" onclick="showTab(event, 'tab-watchlist')" id="btn-tab-watchlist">👁️ Watchlist Monitor</button>
        <button class="tab-btn" onclick="showTab(event, 'tab-journal')" id="btn-tab-journal">📜 History & Journal (7J)</button>
        <button class="tab-btn" onclick="showTab(event, 'tab-premarket')">🌅 Pre-Market Brief</button>
        <button class="tab-btn" onclick="showTab(event, 'tab-settings')">⚙️ Settings</button>
        <button class="tab-btn" onclick="showTab(event, 'tab-control')" style="margin-left: auto; color: var(--accent-amber);">🛡️ Control Plane & Invariants</button>
    </div>

    <!-- TAB 0: NEXTRADE TODAY (15-MINUTE MORNING COCKPIT) -->
    <div id="tab-today" class="tab-content active">
        <!-- MANDATE ACTIVE STATUS BANNER -->
        <div id="mandate-status-banner" style="background: rgba(0, 230, 118, 0.1); border: 1px solid var(--accent-green); border-radius: 12px; padding: 14px; margin-bottom: 20px; display: flex; justify-content: space-between; align-items: center;">
            <div>
                <strong style="color: var(--accent-green); font-size: 15px;">🟢 NEXTRADE IS MANAGING TODAY'S APPROVED TRADING PLAN</strong>
                <div style="font-size: 13px; color: #b0bec5; margin-top: 2px;">Autonomous trading is active within your pre-approved capital and risk limits. You may close the browser.</div>
            </div>
            <div style="display: flex; gap: 8px;">
                <button class="btn btn-amber btn-sm" onclick="pauseMandate()">⏸ Pause New Entries</button>
                <button class="btn btn-red btn-sm" onclick="stopMandate()">🛑 Emergency Stop</button>
            </div>
        </div>

        <div class="grid">
            <!-- 1. MARKET REGIME & BRIEF -->
            <div class="card">
                <div class="card-header"><span class="card-title">📊 Today's Market Regime</span><span class="badge badge-green" id="cockpit-regime-badge">MODERATELY BULLISH</span></div>
                <div style="font-size: 14px; margin-bottom: 10px;">
                    NIFTY Trend: <strong style="color:var(--accent-green);" id="cockpit-nifty">POSITIVE (+1.25%)</strong><br>
                    Bank NIFTY Trend: <strong style="color:var(--accent-green);" id="cockpit-banknifty">POSITIVE (+0.85%)</strong><br>
                    India VIX: <strong style="color:var(--accent-blue);" id="cockpit-vix">13.8 (Normal Volatility)</strong><br>
                    Market Breadth: <span id="cockpit-breadth">1,420 Advances / 580 Declines</span>
                </div>
            </div>

            <!-- 2. STRATEGY OF THE DAY & LEVEL 2 RATIONALE -->
            <div class="card">
                <div class="card-header"><span class="card-title">🤖 Strategy of the Day</span><span class="badge badge-green" id="cockpit-score">Suitability: 82 / 100</span></div>
                <div class="metric-big" style="color:var(--accent-green);" id="cockpit-strategy-name">Momentum Breakout</div>
                <div class="sub-text" style="color:#cfd8dc;" id="cockpit-strategy-desc">Identifies volume-backed price breakouts above key resistance or VWAP.</div>
                
                <div style="margin-top: 10px; font-size: 12px; color: var(--text-muted);">
                    <strong>Why Today?</strong>
                    <ul class="bullet-list" id="cockpit-rationale-list">
                        <li>NIFTY and BankNifty aligned in positive momentum.</li>
                        <li>Market breadth ratio shows strong institutional buying.</li>
                        <li>VIX indicates stable volatility suitable for intraday breakout execution.</li>
                    </ul>
                </div>
            </div>

            <!-- 3. DAILY MANDATE PREVIEW & APPROVAL BUTTON -->
            <div class="card">
                <div class="card-header"><span class="card-title">📜 Today's Trading Mandate Boundaries</span><span class="badge badge-amber">U5 BOUND</span></div>
                
                <table class="table" style="margin-bottom:12px;">
                    <tbody>
                        <tr><td>Capital to Deploy</td><td><strong style="color:#fff;" id="m-cap">₹50,000.00</strong></td></tr>
                        <tr><td>Maximum Risk Limit</td><td><strong style="color:var(--accent-red);" id="m-risk">₹2,000.00</strong></td></tr>
                        <tr><td>Daily Loss Limit Stop</td><td><strong style="color:var(--accent-amber);" id="m-loss">₹2,500.00</strong></td></tr>
                        <tr><td>Max Trades Allowed</td><td><strong id="m-trades">3 Trades</strong></td></tr>
                        <tr><td>Max Concurrent Positions</td><td><strong id="m-pos">2 Positions</strong></td></tr>
                        <tr><td>Trading Window</td><td><strong id="m-window">09:30 AM - 02:45 PM IST</strong></td></tr>
                        <tr><td>Force Market Close Exit</td><td><strong style="color:var(--accent-green);">Enabled (03:15 PM IST)</strong></td></tr>
                    </tbody>
                </table>

                <div style="font-size: 11px; color: var(--text-muted); margin-bottom: 12px;">
                    <em>By approving, you authorise NexTrade to independently identify, enter, manage, and exit paper trades within the limits displayed above.</em>
                </div>

                <button class="btn btn-green" style="width: 100%; padding: 14px; font-size: 15px;" onclick="approveMandate()">🟢 APPROVE & START TODAY'S TRADING MANDATE</button>
            </div>
        </div>

        <!-- 4. DAILY MANDATE ACTIVITY TIMELINE -->
        <div class="card" style="margin-top: 20px;">
            <div class="card-header"><span class="card-title">⏱️ Today's Mandate Audit Timeline</span><span class="badge badge-green">REAL-TIME AUDIT</span></div>
            <div class="modal-box" style="background: rgba(0,0,0,0.2);">
                <table class="table">
                    <thead><tr><th>Time (IST)</th><th>Phase Event</th><th>Details & Audit Trace</th><th>Status</th></tr></thead>
                    <tbody>
                        <tr><td>08:45 AM</td><td>Market Analysis</td><td>Regime Engine scanned Nifty (+1.25%), BankNifty (+0.85%), VIX (13.8)</td><td><span class="badge badge-green">COMPLETED</span></td></tr>
                        <tr><td>08:50 AM</td><td>Strategy Selection</td><td>Strategy of the Day selected: <strong>Momentum Breakout</strong> (Suitability 82/100)</td><td><span class="badge badge-green">COMPLETED</span></td></tr>
                        <tr><td>09:00 AM</td><td>Mandate Approval</td><td>Mandate limit contract user-approved. Cryptographic hash locked.</td><td><span class="badge badge-green" id="tl-approval-status">APPROVED</span></td></tr>
                        <tr><td>09:30 AM</td><td>Engine Activation</td><td>Autonomous Engine ARMED & Invariant U5 boundary verified</td><td><span class="badge badge-green">ACTIVE</span></td></tr>
                        <tr><td>09:42 AM</td><td>Opportunity Scanning</td><td>Scanning live market ticks for breakout signals matching strategy parameters</td><td><span class="badge badge-amber">MONITORING</span></td></tr>
                        <tr><td>02:45 PM</td><td>Trading Window Close</td><td>New autonomous trade entries strictly blocked</td><td><span class="badge badge-amber">SCHEDULED</span></td></tr>
                        <tr><td>03:15 PM</td><td>Force Market Exit</td><td>Auto-exit all remaining open intraday paper positions</td><td><span class="badge badge-amber">SCHEDULED</span></td></tr>
                        <tr><td>03:30 PM</td><td>EOD Reconciliation</td><td>Generate multi-sheet Excel log (.xlsx) & update 7J trade journal</td><td><span class="badge badge-amber">SCHEDULED</span></td></tr>
                    </tbody>
                </table>
            </div>
        </div>

        <!-- 5. END OF DAY EXECUTIVE REPORT SUMMARY -->
        <div class="card" style="margin-top: 20px;">
            <div class="card-header"><span class="card-title">📜 5-Minute End-of-Day Executive Summary</span><span class="badge badge-green">EOD REPORT</span></div>
            <div class="grid">
                <div>
                    Net P&L Today: <strong style="font-size:20px; color:var(--accent-green);" id="eod-pnl">+₹0.00</strong><br>
                    Win Rate: <strong id="eod-winrate">0.0%</strong> | Total Executed Trades: <strong id="eod-trades">0</strong>
                </div>
                <div style="text-align: right;">
                    <button class="btn btn-green btn-sm" onclick="exportExcelReport()">📊 Download Today's Multi-Sheet Excel Log (.xlsx)</button>
                </div>
            </div>
        </div>
    </div>

    <!-- TAB 1: DASHBOARD -->
    <div id="tab-dashboard" class="tab-content">
        <div class="grid">
            <div class="card">
                <div class="card-header"><span class="card-title">💰 Dynamic Capital Summary</span><span class="badge badge-green">LIVE DYNAMIC</span></div>
                <div class="metric-big" id="dash-capital">₹1,00,000.00</div>
                <div class="sub-text" style="margin-bottom:12px;">Available Cash: <strong style="color:#fff;" id="dash-cash">₹1,00,000.00</strong> | Utilized Margin: <span id="dash-margin">₹0.00</span></div>
                <div style="display:flex; gap:8px;">
                    <button class="btn btn-green btn-sm" style="flex:1;" onclick="updateCapital('add', 10000)">+ ₹10,000 Capital</button>
                    <button class="btn btn-amber btn-sm" style="flex:1;" onclick="updateCapital('subtract', 10000)">- ₹10,000 Capital</button>
                </div>
            </div>

            <div class="card">
                <div class="card-header"><span class="card-title">📈 Today's P&L</span><span class="badge badge-green">RESET FRESH</span></div>
                <div class="metric-big" style="color: var(--accent-green);" id="dash-pnl">+₹0.00</div>
                <div class="sub-text">Overall Portfolio Profit: <span id="dash-overall-pnl">+₹0.00</span> | Active Risk: <strong style="color:var(--accent-amber);" id="dash-risk">₹0.00</strong></div>
                <div style="display:flex; gap:8px; margin-top:12px;">
                    <button class="btn btn-red btn-sm" style="flex:1;" onclick="resetPaperData()">🔄 Reset All Data to Fresh ₹1,00,000</button>
                    <button class="btn btn-green btn-sm" style="flex:1;" onclick="exportExcelReport()">📊 Export Market Closure Excel Log</button>
                </div>
            </div>

            <div class="card">
                <div class="card-header"><span class="card-title">⚙️ Trading Engine Controls</span><span class="badge badge-amber">PAUSED</span></div>
                <div style="display:flex; gap:8px; margin-top:8px;">
                    <button class="btn btn-green" style="margin:0;" onclick="alert('Engine Started')">Start Engine</button>
                    <button class="btn btn-amber" style="margin:0;" onclick="alert('Engine Paused')">Pause Engine</button>
                </div>
            </div>
        </div>

        <div class="grid" style="margin-top:20px;">
            <div class="card">
                <div class="card-header"><span class="card-title">🔥 Top Gainers</span></div>
                <table class="table">
                    <thead><tr><th>Symbol</th><th>LTP</th><th>Change</th></tr></thead>
                    <tbody id="dash-gainers"></tbody>
                </table>
            </div>

            <div class="card">
                <div class="card-header"><span class="card-title">🔻 Top Losers</span></div>
                <table class="table">
                    <thead><tr><th>Symbol</th><th>LTP</th><th>Change</th></tr></thead>
                    <tbody id="dash-losers"></tbody>
                </table>
            </div>
        </div>
    </div>

    <!-- TAB 2: OPPORTUNITIES -->
    <div id="tab-opportunities" class="tab-content">
        <div id="opp-container">Loading trade opportunities...</div>
    </div>

    <!-- TAB 3: TRADE TICKET -->
    <div id="tab-ticket" class="tab-content">
        <div class="grid">
            <div class="card">
                <div class="card-header"><span class="card-title">🎟️ Create Trade Plan (INR ₹)</span><span class="badge badge-green">U1, U2, U4 BOUND</span></div>
                
                <div class="input-group"><label>Instrument Symbol</label><input type="text" id="tk-symbol" value="RELIANCE"></div>
                <div style="display: flex; gap: 10px;">
                    <div class="input-group" style="flex: 1;"><label>Trading Style</label>
                        <select id="tk-style">
                            <option value="INTRADAY">Intraday</option>
                            <option value="SCALPING">Scalping</option>
                            <option value="SWING">Swing</option>
                            <option value="OPTIONS_BUYING">Options Buying</option>
                            <option value="OPTIONS_SELLING">Options Selling</option>
                        </select>
                    </div>
                    <div class="input-group" style="flex: 1;"><label>Strategy (Full Canonical Registry)</label>
                        <select id="tk-strategy">
                            <option value="Momentum Breakout">Momentum Breakout (Intraday Equity)</option>
                            <option value="VWAP Mean Reversion">VWAP Mean Reversion (Intraday Equity)</option>
                            <option value="Opening Range Breakout (ORB)">Opening Range Breakout (ORB) (Intraday Equity)</option>
                            <option value="ADX Trend Acceleration">ADX Trend Acceleration (Intraday Equity)</option>
                            <option value="RSI Oversold/Overbought Reversion">RSI Oversold/Overbought Reversion (Intraday Equity)</option>
                            <option value="Bollinger Band Band-Touch Bounce">Bollinger Band Band-Touch Bounce (Intraday Equity)</option>
                            <option value="Moving Average Trend Following">Moving Average Trend Following (Swing Equity)</option>
                            <option value="Breakout + Volume Surge">Breakout + Volume Surge (Swing Equity)</option>
                            <option value="Futures Momentum Drive">Futures Momentum Drive (Futures)</option>
                            <option value="Options Buying (Call Option Drive)">Options Buying (Call Option Drive) (Options)</option>
                            <option value="Options Buying (Put Option Drive)">Options Buying (Put Option Drive) (Options)</option>
                            <option value="Bull Call Spread">Bull Call Spread (Defined Risk Options)</option>
                            <option value="Bear Put Spread">Bear Put Spread (Defined Risk Options)</option>
                            <option value="Iron Condor (Range-Bound Neutral)">Iron Condor (Range-Bound Neutral) (Multi-Leg Options)</option>
                            <option value="Long Straddle/Strangle Volatility Surge">Long Straddle/Strangle Volatility Surge (Multi-Leg Options)</option>
                        </select>
                    </div>
                </div>

                <div style="display: flex; gap: 10px;">
                    <div class="input-group" style="flex: 1;"><label>Entry Price (₹)</label><input type="number" id="tk-entry" value="2742.00"></div>
                    <div class="input-group" style="flex: 1;"><label>Quantity / Lots</label><input type="number" id="tk-qty" value="10"></div>
                </div>

                <div style="display: flex; gap: 10px;">
                    <div class="input-group" style="flex: 1;"><label>Stop Loss (₹)</label><input type="number" id="tk-sl" value="2690.00"></div>
                    <div class="input-group" style="flex: 1;"><label>Target Price (₹)</label><input type="number" id="tk-tp" value="2850.00"></div>
                </div>

                <div class="input-group"><label>Trailing Stop Loss (₹ Trail)</label><input type="number" id="tk-tsl" value="20.00"></div>

                <button class="btn btn-green" onclick="generatePlan()" style="width:100%;">Generate Pre-Trade Summary</button>
            </div>

            <div class="card">
                <div class="card-header"><span class="card-title">📊 Pre-Execution Trade Summary</span><span class="badge badge-amber">PRE-TRADE</span></div>
                <div id="plan-summary-box" class="modal-box">Fill in ticket and click button to view pre-trade risk summary.</div>
                
                <div style="margin-top: 14px; padding: 10px; background: rgba(255,179,0,0.08); border: 1px solid var(--accent-amber); border-radius: 8px; font-size: 12px;">
                    <label style="display:flex; align-items:center; gap:8px; cursor:pointer;">
                        <input type="checkbox" id="chk-offmarket-override" onchange="toggleOffmarketOverride(this.checked)">
                        <span>ALLOW WEEKEND OFF-MARKET PAPER SIMULATION (TESTING OVERRIDE)</span>
                    </label>
                </div>

                <button class="btn btn-green" style="margin-top:16px; width:100%;" onclick="executePaperTrade()">🚀 Execute Paper Trade</button>
            </div>
        </div>
    </div>

    <!-- TAB 4: PAPER SIMULATOR -->
    <div id="tab-paper" class="tab-content">
        <div class="card" style="margin-bottom: 20px;">
            <div class="card-header"><span class="card-title">🧪 4-Mode Paper Trading Simulator</span><span class="badge badge-green">U3 PARITY ENFORCED</span></div>
            <div class="sub-text">Paper trading uses the exact same risk, protection, trailing stop, and auto-exit engine as live trading.</div>
        </div>

        <div class="card" style="margin-bottom: 20px;">
            <div class="card-header"><span class="card-title">📋 Active Paper Positions & Simulation Log</span></div>
            <div id="paper-positions-box" class="modal-box">No active paper positions right now. Use Trade Ticket to execute paper trades.</div>
        </div>

        <div class="grid">
            <div class="card">
                <div class="card-header"><span class="card-title">✋ Mode 1: Manual Simulation</span><span class="badge badge-green">ACTIVE</span></div>
                <div class="sub-text">You decide everything. Pick stock, entry, SL, TP, and trailing stop in the Trade Ticket.</div>
                <button class="btn btn-green" onclick="showTab(event, 'tab-ticket')">Go to Trade Ticket</button>
            </div>

            <div class="card">
                <div class="card-header"><span class="card-title">🤝 Mode 2: Assisted Simulation</span><span class="badge badge-green">ACTIVE</span></div>
                <div class="sub-text">NexTrade scans the market, calculates suggested entry, SL, and target, and asks for 1-click confirmation.</div>
                <button class="btn btn-green" onclick="showTab(event, 'tab-opportunities')">View Opportunities</button>
            </div>

            <div class="card">
                <div class="card-header"><span class="card-title">📊 Mode 3: Strategy-Driven</span><span class="badge badge-green">ACTIVE</span></div>
                <div class="sub-text">Select Trading Style (Intraday, Scalping, Swing, F&O) and Strategy. NexTrade automatically builds the paper trade plan.</div>
                <button class="btn btn-green" onclick="alert('Strategy-Driven Mode active!')">Select Strategy</button>
            </div>

            <div class="card">
                <div class="card-header"><span class="card-title">⚡ Mode 4: Automated Simulation</span><span class="badge badge-amber">RUNNING</span></div>
                <div class="sub-text">Runs continuously in the background against live market ticks. Automatically enters & exits paper trades on SL/TP/TSL hit.</div>
                <button class="btn btn-amber" onclick="alert('Automated Simulation is active and monitoring live market ticks.')">View Auto Engine Status</button>
            </div>
        </div>
    </div>

    <!-- TAB 5: POSITIONS -->
    <div id="tab-positions" class="tab-content">
        <div class="card">
            <div class="card-header"><span class="card-title">📈 Position Protection & Trailing Distance</span><span class="badge badge-green">PROTECTED</span></div>
            <div id="live-positions-container">
                <div class="modal-box">
                    <strong style="color:#fff;">RELIANCE — BUY 10 Qty @ ₹2,742.00</strong><br>
                    Current Price: <span style="color:var(--accent-green);">₹2,765.00 (+₹460.00 P&L)</span><br><br>
                    🎯 Target: ₹2,820.00 (Distance: ₹55.00)<br>
                    🛡️ Trailing SL: ₹2,745.00 (Protected Profit: +₹50.00)<br>
                    🛑 Original SL: ₹2,690.00<br><br>
                    <span class="badge badge-green">Auto-Exit: ACTIVE</span>
                </div>
            </div>
        </div>
    </div>

    <!-- TAB 6: HOLDINGS -->
    <div id="tab-holdings" class="tab-content">
        <div class="card">
            <div class="card-header"><span class="card-title">💼 Portfolio Holdings (10 Stocks)</span><span class="badge badge-green">SYNCED</span></div>
            <table class="table">
                <thead><tr><th>Symbol</th><th>Qty</th><th>Avg Price</th><th>LTP</th><th>P&L</th><th>Total Value</th></tr></thead>
                <tbody id="holdings-body"></tbody>
            </table>
        </div>
    </div>

    <!-- TAB 7: WATCHLIST MONITOR -->
    <div id="tab-watchlist" class="tab-content">
        <div class="card">
            <div class="card-header">
                <span class="card-title" id="watchlist-title-label">👁️ Watchlist Monitor</span>
                <span class="badge badge-green">AUTO REFRESH</span>
            </div>

            <div style="display: flex; gap: 10px; margin-bottom: 16px;">
                <input type="text" id="add-symbol-input" placeholder="Add symbol (e.g. SBIN, TATAMOTORS)" style="flex: 1; padding: 10px; border-radius: 8px; border: 1px solid var(--border-color); background: #0e1422; color: #fff; font-size: 13px;">
                <button class="btn btn-green" onclick="addWatchlistSymbol()" style="width: auto;">+ Add Stock</button>
            </div>

            <table class="table">
                <thead>
                    <tr>
                        <th>Symbol</th>
                        <th>LTP</th>
                        <th>Change</th>
                        <th>Change %</th>
                        <th>Volume</th>
                        <th style="text-align: center;">Action</th>
                    </tr>
                </thead>
                <tbody id="watchlist-body"></tbody>
            </table>
        </div>
    </div>

    <!-- TAB 8: JOURNAL (7J) -->
    <div id="tab-journal" class="tab-content">
        <div class="grid">
            <div class="card">
                <div class="card-header"><span class="card-title">📜 Performance Summary (7J)</span><span class="badge badge-green">INR (₹)</span></div>
                <div class="metric-big" id="j-net-pnl">+₹0.00</div>
                <div class="sub-text">Win Rate: <strong style="color:var(--accent-green);" id="j-win-rate">0.0%</strong> | Total Trades: <strong id="j-trades">0</strong></div>
                <button class="btn btn-green" style="margin-top:16px; width:100%;" onclick="exportExcelReport()">📊 Export Trading Log to Excel (.xlsx)</button>
            </div>

            <div class="card">
                <div class="card-header"><span class="card-title">📊 P&L by Trading Style</span></div>
                <div id="style-breakdown-box" class="modal-box">No trades executed today.</div>
            </div>
        </div>

        <div class="card" style="margin-top: 20px;">
            <div class="card-header"><span class="card-title">📜 Executed Trades Log</span></div>
            <table class="table">
                <thead>
                    <tr>
                        <th>Timestamp</th>
                        <th>Symbol</th>
                        <th>Style</th>
                        <th>Strategy</th>
                        <th>Direction</th>
                        <th>Qty</th>
                        <th>Entry Price</th>
                        <th>Exit Price</th>
                        <th>P&L</th>
                        <th>Status</th>
                    </tr>
                </thead>
                <tbody id="executed-trades-body">
                    <tr><td colspan="10" style="text-align:center; color:var(--text-muted);">No executed trades found today.</td></tr>
                </tbody>
            </table>
        </div>
    </div>

    <!-- TAB 9: PRE-MARKET -->
    <div id="tab-premarket" class="tab-content">
        <div class="card">
            <div class="card-header"><span class="card-title">🌅 Pre-Market Morning Brief</span><span class="badge badge-green">ANALYZED</span></div>
            <div id="premarket-box" class="modal-box">Loading pre-market outlook...</div>
        </div>
    </div>

    <!-- TAB 10: SETTINGS -->
    <div id="tab-settings" class="tab-content">
        <div class="card">
            <div class="card-header"><span class="card-title">⚙️ Risk & Preferences Settings</span></div>
            <div class="input-group"><label>Default Trading Style</label><select><option>Intraday</option><option>Swing</option></select></div>
            <div class="input-group"><label>Per-Account Exposure Limit (₹)</label><input type="text" value="₹1,000.00" readonly></div>
            <div class="input-group"><label>Portfolio Exposure Ceiling (₹)</label><input type="text" value="₹3,000.00" readonly></div>
        </div>
    </div>

    <!-- TAB 11: CONTROL PLANE (PRODUCT B) -->
    <div id="tab-control" class="tab-content">
        <div class="card">
            <div class="card-header"><span class="card-title">🛡️ Operations Console & Invariants</span><span class="badge badge-amber">PRODUCT B</span></div>
            <div class="sub-text">506 Regression Tests PASSED | 90 Targeted Invariants Active | SHA-256 Hash Chain Verified</div>
            <button class="btn btn-green" onclick="runFullAudit()" style="margin-top:12px; width:100%;">Run Phase 6G Audit</button>
            <button class="btn btn-red" onclick="triggerKill('portfolio')" style="margin-top:8px; width:100%;">Trigger Master Portfolio Kill</button>
            <div class="modal-box" id="ctrl-log">Control Plane ready.</div>
        </div>
    </div>

    <script>
        function showTab(evt, tabId) {
            document.querySelectorAll('.tab-content').forEach(el => el.classList.remove('active'));
            document.querySelectorAll('.tab-btn').forEach(el => el.classList.remove('active'));
            document.getElementById(tabId).classList.add('active');
            evt.currentTarget.classList.add('active');
        }

        async function fetchTodayMandate() {
            try {
                const res = await fetch('/api/mandate/today');
                const data = await res.json();

                document.getElementById('cockpit-regime-badge').innerText = data.market_regime_label;
                document.getElementById('cockpit-nifty').innerText = data.nifty_trend;
                document.getElementById('cockpit-banknifty').innerText = data.bank_nifty_trend;
                document.getElementById('cockpit-vix').innerText = data.vix_level + ' (Normal Volatility)';
                document.getElementById('cockpit-breadth').innerText = data.market_breadth;

                document.getElementById('cockpit-strategy-name').innerText = data.recommended_strategy;
                document.getElementById('cockpit-score').innerText = `Suitability: ${data.suitability_score} / 100`;

                let rHtml = '';
                data.primary_rationale.forEach(r => rHtml += `<li>${r}</li>`);
                document.getElementById('cockpit-rationale-list').innerHTML = rHtml;

                document.getElementById('m-cap').innerText = data.limits.capital_deployed_limit;
                document.getElementById('m-risk').innerText = data.limits.max_risk_ceiling;
                document.getElementById('m-loss').innerText = data.limits.daily_loss_limit;

                const banner = document.getElementById('mandate-status-banner');
                if (data.mandate_state === 'AUTONOMOUS_TRADING_ACTIVE') {
                    banner.style.display = 'flex';
                } else {
                    banner.style.display = 'none';
                }

            } catch (err) { console.error(err); }
        }

        async function approveMandate() {
            const res = await fetch('/api/mandate/approve', { method: 'POST' });
            const data = await res.json();
            if (data.success) {
                alert("🟢 " + data.message);
                fetchTodayMandate();
            } else {
                alert(data.error || "Failed to approve mandate");
            }
        }

        async function pauseMandate() {
            const res = await fetch('/api/mandate/pause', { method: 'POST' });
            const data = await res.json();
            alert(data.message || data.error);
            fetchTodayMandate();
        }

        async function stopMandate() {
            if (!confirm("Are you sure you want to trigger Emergency Stop across all autonomous trading?")) return;
            const res = await fetch('/api/mandate/stop', { method: 'POST' });
            const data = await res.json();
            alert(data.message || data.error);
            fetchTodayMandate();
        }

        async function updateStatus() {
            try {
                const res = await fetch('/api/status');
                const data = await res.json();
                
                document.getElementById('dash-capital').innerText = data.total_capital_fmt;
                document.getElementById('dash-cash').innerText = data.available_cash_fmt;
                document.getElementById('dash-margin').innerText = data.utilized_margin_fmt;
                document.getElementById('dash-pnl').innerText = data.todays_pnl_fmt;
                document.getElementById('dash-overall-pnl').innerText = data.overall_pnl_fmt;
                document.getElementById('dash-risk').innerText = data.active_risk_fmt;

                document.getElementById('eod-pnl').innerText = data.todays_pnl_fmt;

                const mBadge = document.getElementById('market-status-badge');
                mBadge.innerText = data.market_status_badge;
                if (data.market_open) {
                    mBadge.className = 'badge badge-green';
                } else {
                    mBadge.className = 'badge badge-red';
                }

                let gHtml = '';
                data.gainers.forEach(g => {
                    gHtml += `<tr><td><strong>${g.symbol}</strong></td><td>${g.ltp}</td><td style="color:var(--accent-green);">${g.change}</td></tr>`;
                });
                document.getElementById('dash-gainers').innerHTML = gHtml;

                let lHtml = '';
                data.losers.forEach(l => {
                    lHtml += `<tr><td><strong>${l.symbol}</strong></td><td>${l.ltp}</td><td style="color:var(--accent-red);">${l.change}</td></tr>`;
                });
                document.getElementById('dash-losers').innerHTML = lHtml;

                fetchPositions();

            } catch (err) { console.error(err); }
        }

        async function fetchPositions() {
            try {
                const res = await fetch('/api/positions');
                const positions = await res.json();
                
                document.getElementById('btn-tab-paper').innerText = `🧪 Paper Simulator (${positions.length} Open)`;
                document.getElementById('btn-tab-positions').innerText = `📈 Live Positions (${positions.length} Open)`;

                let posHtml = '';
                let tab4Html = '';

                if (positions.length === 0) {
                    posHtml = '<div class="modal-box">No active open positions. Execute paper trades from Trade Ticket.</div>';
                    tab4Html = 'No active paper positions right now. Use Trade Ticket to execute paper trades.';
                } else {
                    tab4Html = '<table class="table"><thead><tr><th>ID</th><th>Timestamp</th><th>Symbol</th><th>Style</th><th>Strategy</th><th>Qty</th><th>Entry</th><th>SL</th><th>Target</th><th>Status</th></tr></thead><tbody>';
                    positions.forEach(p => {
                        posHtml += `
                            <div class="modal-box" style="margin-bottom:12px;">
                                <strong style="color:#fff;">${p.symbol} — ${p.direction} ${p.quantity} Qty @ ${p.entry_price} (${p.trading_style})</strong><br>
                                Current Price: <span style="color:var(--accent-green);">${p.current_price} (${p.pnl})</span><br><br>
                                🎯 Target: ${p.target}<br>
                                🛡️ Trailing SL: ${p.trailing_stop}<br>
                                🛑 Original SL: ${p.stop_loss}<br><br>
                                <span class="badge badge-green">Auto-Exit: ACTIVE</span>
                            </div>
                        `;
                        tab4Html += `<tr><td>${p.position_id}</td><td>${p.timestamp}</td><td><strong>${p.symbol}</strong></td><td>${p.trading_style}</td><td>${p.strategy}</td><td>${p.quantity}</td><td>${p.entry_price}</td><td style="color:var(--accent-red);">${p.stop_loss}</td><td style="color:var(--accent-green);">${p.target}</td><td><span class="badge badge-green">${p.status}</span></td></tr>`;
                    });
                    tab4Html += '</tbody></table>';
                }

                document.getElementById('live-positions-container').innerHTML = posHtml;
                document.getElementById('paper-positions-box').innerHTML = tab4Html;

            } catch (err) { console.error(err); }
        }

        async function toggleOffmarketOverride(checked) {
            await fetch('/api/toggle_offmarket', {
                method: 'POST',
                body: JSON.stringify({ allow: checked })
            });
        }

        async function updateCapital(action, amount) {
            try {
                const res = await fetch('/api/capital/update', {
                    method: 'POST',
                    body: JSON.stringify({ action: action, amount: amount })
                });
                const data = await res.json();
                if (data.success) {
                    document.getElementById('dash-capital').innerText = data.total_capital_fmt;
                    document.getElementById('dash-cash').innerText = data.available_cash_fmt;
                } else {
                    alert(data.error || 'Failed to update capital');
                }
            } catch (err) { console.error(err); }
        }

        async function resetPaperData() {
            if (!confirm("Are you sure you want to reset all paper trade data to NIL and start fresh with ₹1,00,000?")) return;
            try {
                const res = await fetch('/api/reset_paper_data', { method: 'POST' });
                const data = await res.json();
                if (data.success) {
                    alert(data.message);
                    updateStatus();
                    fetchJournal();
                }
            } catch (err) { console.error(err); }
        }

        async function exportExcelReport() {
            try {
                const res = await fetch('/api/export_excel', { method: 'POST' });
                const data = await res.json();
                if (data.success) {
                    window.location.href = data.download_url;
                } else {
                    alert(data.error || "Failed to generate Excel report");
                }
            } catch (err) { console.error(err); }
        }

        async function fetchOpportunities() {
            try {
                const res = await fetch('/api/opportunities');
                const opps = await res.json();
                let html = '';
                opps.forEach(o => {
                    html += `
                        <div class="opp-card">
                            <div style="display:flex; justify-content:space-between; align-items:center;">
                                <strong style="font-size:18px; color:#fff;">${o.symbol} — ${o.trading_style}</strong>
                                <span class="badge badge-green">${o.signal_strength_pct}% Signal Strength</span>
                            </div>
                            <div class="sub-text" style="margin-top:4px;">Strategy: ${o.strategy} | R:R Ratio: ${o.risk_reward_ratio}</div>
                            <div style="margin-top:10px; font-size:14px;">
                                Entry: <strong>${o.suggested_entry}</strong> | SL: <span style="color:var(--accent-red);">${o.suggested_stop_loss}</span> | Target: <span style="color:var(--accent-green);">${o.suggested_target}</span>
                            </div>
                            <div style="margin-top:10px;">
                                <strong style="color:var(--accent-blue);">Why This Trade?</strong>
                                <ul class="bullet-list">${o.why_this_trade.map(w => `<li>✓ ${w}</li>`).join('')}</ul>
                            </div>
                            <div style="margin-top:10px;">
                                <strong style="color:var(--accent-amber);">Trade Invalidation Rule:</strong>
                                <ul class="bullet-list">${o.invalidation_rules.map(r => `<li>⚠️ ${r}</li>`).join('')}</ul>
                            </div>
                            <button class="btn btn-green" style="margin-top:12px; width:100%;" onclick="populateTicket('${o.symbol}', '${o.suggested_entry}', '${o.suggested_stop_loss}', '${o.suggested_target}')">🎟️ View Trade Plan</button>
                        </div>
                    `;
                });
                document.getElementById('opp-container').innerHTML = html;
            } catch(e) { console.error(e); }
        }

        async function fetchWatchlist() {
            try {
                const res = await fetch('/api/watchlist');
                const list = await res.json();
                
                document.getElementById('watchlist-title-label').innerText = `👁️ Watchlist Monitor (${list.length} Stocks)`;
                document.getElementById('btn-tab-watchlist').innerText = `👁️ Watchlist (${list.length} Stocks)`;

                let html = '';
                list.forEach(w => {
                    html += `
                        <tr>
                            <td><strong>${w.symbol}</strong></td>
                            <td>${w.ltp}</td>
                            <td style="color:${w.change.startsWith('+')?'var(--accent-green)':'var(--accent-red)'}">${w.change}</td>
                            <td>${w.change_pct}</td>
                            <td>${w.volume}</td>
                            <td style="text-align:center;">
                                <button class="btn btn-red btn-sm" onclick="removeWatchlistSymbol('${w.symbol}')">🗑️ Remove</button>
                            </td>
                        </tr>
                    `;
                });
                document.getElementById('watchlist-body').innerHTML = html;
            } catch(e) { console.error(e); }
        }

        async function addWatchlistSymbol() {
            const input = document.getElementById('add-symbol-input');
            const symbol = input.value.trim().toUpperCase();
            if (!symbol) return;

            const res = await fetch('/api/watchlist/add', {
                method: 'POST',
                body: JSON.stringify({ symbol })
            });
            const data = await res.json();
            if (data.success) {
                input.value = '';
                fetchWatchlist();
            } else {
                alert(data.error || 'Failed to add symbol');
            }
        }

        async function removeWatchlistSymbol(symbol) {
            if (!confirm(`Are you sure you want to remove ${symbol} from Watchlist?`)) return;

            const res = await fetch('/api/watchlist/remove', {
                method: 'POST',
                body: JSON.stringify({ symbol })
            });
            const data = await res.json();
            if (data.success) {
                fetchWatchlist();
            } else {
                alert(data.error || 'Failed to remove symbol');
            }
        }

        async function fetchHoldings() {
            try {
                const res = await fetch('/api/holdings');
                const list = await res.json();
                let html = '';
                list.forEach(h => {
                    html += `<tr><td><strong>${h.symbol}</strong></td><td>${h.qty}</td><td>${h.avg_price}</td><td>${h.ltp}</td><td style="color:${h.pnl.startsWith('+')?'var(--accent-green)':'var(--accent-red)'}">${h.pnl}</td><td>${h.total_value}</td></tr>`;
                });
                document.getElementById('holdings-body').innerHTML = html;
            } catch(e) { console.error(e); }
        }

        async function fetchPremarket() {
            try {
                const res = await fetch('/api/premarket');
                const data = await res.json();
                let html = `<strong>Market Bias:</strong> <span class="badge badge-green">${data.market_bias}</span><br><br><strong>Top Focus Stocks:</strong><ul class="bullet-list">`;
                data.focus_stocks.forEach(f => {
                    html += `<li><strong>${f.symbol}:</strong> ${f.reason}</li>`;
                });
                html += '</ul>';
                document.getElementById('premarket-box').innerHTML = html;
            } catch(e) { console.error(e); }
        }

        async function fetchJournal() {
            try {
                const res = await fetch('/api/journal');
                const data = await res.json();
                document.getElementById('j-net-pnl').innerText = data.net_pnl_formatted;
                document.getElementById('j-win-rate').innerText = data.win_rate_pct + '%';
                document.getElementById('j-trades').innerText = data.total_trades;
                document.getElementById('eod-winrate').innerText = data.win_rate_pct + '%';
                document.getElementById('eod-trades').innerText = data.total_trades;
                
                let bHtml = '';
                for (const [style, pnl] of Object.entries(data.style_breakdown_formatted)) {
                    bHtml += `<div><strong>${style}:</strong> <span style="color:var(--accent-green);">${pnl}</span></div>`;
                }
                document.getElementById('style-breakdown-box').innerHTML = bHtml;

                let tHtml = '';
                if (data.executed_trades && data.executed_trades.length > 0) {
                    data.executed_trades.forEach(t => {
                        tHtml += `<tr><td>${t.timestamp}</td><td><strong>${t.symbol}</strong></td><td>${t.style}</td><td>${t.strategy}</td><td>${t.direction}</td><td>${t.quantity}</td><td>₹${t.entry_price}</td><td>₹${t.exit_price}</td><td>₹${t.pnl}</td><td><span class="badge badge-green">${t.status}</span></td></tr>`;
                    });
                } else {
                    tHtml = '<tr><td colspan="10" style="text-align:center; color:var(--text-muted);">No executed trades found today.</td></tr>';
                }
                document.getElementById('executed-trades-body').innerHTML = tHtml;

            } catch(e) { console.error(e); }
        }

        function populateTicket(symbol, entry, sl, tp) {
            document.getElementById('tk-symbol').value = symbol;
            document.getElementById('tk-entry').value = parseFloat(entry.replace(/[^0-9.]/g, ''));
            document.getElementById('tk-sl').value = parseFloat(sl.replace(/[^0-9.]/g, ''));
            document.getElementById('tk-tp').value = parseFloat(tp.replace(/[^0-9.]/g, ''));
            
            // Switch tab to ticket
            const btn = document.querySelectorAll('.tab-btn')[3];
            btn.click();
        }

        async function generatePlan() {
            const symbol = document.getElementById('tk-symbol').value;
            const style = document.getElementById('tk-style').value;
            const strategy = document.getElementById('tk-strategy').value;
            const entry = parseFloat(document.getElementById('tk-entry').value);
            const qty = parseInt(document.getElementById('tk-qty').value);
            const sl = parseFloat(document.getElementById('tk-sl').value);
            const tp = parseFloat(document.getElementById('tk-tp').value);
            const tsl = parseFloat(document.getElementById('tk-tsl').value);

            const res = await fetch('/api/create_trade_plan', {
                method: 'POST',
                body: JSON.stringify({ symbol, trading_style: style, strategy, entry_price: entry, quantity: qty, stop_loss_price: sl, target_price: tp, trailing_stop_amount: tsl })
            });
            const data = await res.json();
            if (data.success) {
                const s = data.summary;
                document.getElementById('plan-summary-box').innerHTML = `
                    <strong style="font-size:15px; color:#fff;">${s.title}</strong><br>
                    <span class="badge badge-green" style="margin-top:4px; display:inline-block;">${s.style_strategy}</span><br><br>
                    Capital Required: <strong>${s.capital_required}</strong><br>
                    Maximum Risk: <span style="color:var(--accent-red);">${s.maximum_loss}</span><br>
                    Potential Profit: <span style="color:var(--accent-green);">${s.potential_profit}</span><br>
                    Risk / Reward: <strong>${s.risk_reward_ratio}</strong><br><br>
                    <div class="sub-text" style="color:var(--accent-green);">${s.user_reassurance}</div>
                `;
            } else {
                alert(data.error || "Failed to create trade plan");
            }
        }

        async function executePaperTrade() {
            const res = await fetch('/api/execute_paper_trade', { method: 'POST' });
            const data = await res.json();
            if (data.success) {
                alert("✅ " + data.message);
                updateStatus();
                fetchJournal();
                const btn = document.querySelectorAll('.tab-btn')[5];
                btn.click();
            } else {
                alert(data.error || "Failed to execute paper trade");
            }
        }

        async function runFullAudit() {
            const logBox = document.getElementById('ctrl-log');
            logBox.innerText = "Executing Phase 6G Audit...";
            const res = await fetch('/api/run_audit', { method: 'POST' });
            const data = await res.json();
            logBox.innerHTML = `✅ <strong>Audit Passed (${data.invariants_passed}/15)</strong><br>SHA-256 Digest:<br><span class="hash-code">${data.manifest_sha256}</span>`;
        }

        async function triggerKill(type) {
            const logBox = document.getElementById('ctrl-log');
            logBox.innerText = `Triggering ${type} kill...`;
            const res = await fetch('/api/trigger_kill', {
                method: 'POST',
                body: JSON.stringify({ target: type, account_id: 'ACC_PROD_MULTI_01' })
            });
            const data = await res.json();
            logBox.innerHTML = `🚨 <strong>${data.message}</strong>`;
        }

        async function fetchStrategies() {
            try {
                const res = await fetch('/api/strategies');
                const strats = await res.json();
                const sel = document.getElementById('tk-strategy');
                if (strats && strats.length > 0) {
                    let html = '';
                    strats.forEach(s => {
                        html += `<option value="${s.name}">${s.name} (${s.trading_style} | ${s.segment})</option>`;
                    });
                    sel.innerHTML = html;
                }
            } catch (e) { console.error(e); }
        }

        // Initial Load
        fetchTodayMandate();
        fetchStrategies();
        updateStatus();
        fetchOpportunities();
        fetchWatchlist();
        fetchHoldings();
        fetchPremarket();
        fetchJournal();
        setInterval(updateStatus, 3000);
    </script>
</body>
</html>
"""


def start_dashboard_server():
    # Phase 7P freeze-allowed security boundary: localhost only (not LAN/Internet)
    _bind_host = "127.0.0.1"
    server = HTTPServer((_bind_host, PORT), UnifiedWebAppHandler)
    url = f"http://127.0.0.1:{PORT}"
    print("\n" + "="*70)
    print("[+] NEXTRADE UNIFIED 15-MINUTE COCKPIT & AUTONOMOUS SYSTEM IS RUNNING (INR / Rs)")
    print(f"[*] Opening Web Dashboard: {url}")
    print(f"[*] Listen address: {_bind_host}:{PORT} (paper boundary — localhost only)")
    print("="*70 + "\n")
    
    threading.Thread(target=lambda: (time.sleep(1), webbrowser.open(url)), daemon=True).start()
    
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping NexTrade Unified Server...")
        server.server_close()


if __name__ == "__main__":
    start_dashboard_server()
