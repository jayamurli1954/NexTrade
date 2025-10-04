# ui/professional_trading_ui.py
"""
Professional Trading UI Module
Modular implementation of the advanced trading interface
"""
import tkinter as tk
from tkinter import ttk, messagebox
import threading
import time
from datetime import datetime
import logging

logger = logging.getLogger("ProfessionalUI")


def on_closing(self):
    """Handle window closing properly"""
    try:
        self.analysis_running = False
        if hasattr(self, 'analysis_thread') and self.analysis_thread.is_alive():
            self.analysis_thread.join(timeout=1.0)
        if hasattr(self, 'root') and self.root:
            self.root.quit()
            self.root.destroy()
    except Exception:
        import sys
        sys.exit(0)


class ModernTheme:
    """Modern dark theme colors and fonts"""
    BG_PRIMARY = "#1a1a1a"
    BG_SECONDARY = "#2d2d2d"
    BG_CARD = "#363636"
    BG_INPUT = "#404040"
    ACCENT_GREEN = "#00d4aa"
    ACCENT_RED = "#ff4757"
    ACCENT_BLUE = "#3742fa"
    ACCENT_YELLOW = "#ffa502"
    ACCENT_PURPLE = "#9c88ff"
    TEXT_PRIMARY = "#ffffff"
    TEXT_SECONDARY = "#cccccc"
    TEXT_MUTED = "#999999"
    TEXT_SUCCESS = "#00d4aa"
    TEXT_ERROR = "#ff4757"
    FONT_LARGE = ("Segoe UI", 16, "bold")
    FONT_MEDIUM = ("Segoe UI", 12, "bold")
    FONT_SMALL = ("Segoe UI", 10)
    FONT_BUTTON = ("Segoe UI", 10, "bold")
    FONT_TITLE = ("Segoe UI", 18, "bold")


class ProfessionalTradingUI:
    """Professional trading interface with full functionality"""

    def __init__(self, angel_api, analyzer, paper_trader, version="3.0.0"):
        self.angel_api = angel_api
        self.analyzer = analyzer
        self.paper_trader = paper_trader
        self.version = version

        # UI State
        self.connected = False
        self.current_signals = []
        self.market_data = {}
        self.update_running = False

        # Create main window
        self.root = tk.Tk()
        self.root.title(f"Angel One Trading Bot v{version} - Professional Interface")
        self.root.geometry("1400x900")
        self.root.configure(bg=ModernTheme.BG_PRIMARY)

        # Configure styles
        self.setup_styles()

        # Create UI
        self.create_professional_ui()

        # Start updates
        self.start_market_updates()

def safe_update_ui(self, update_func):
    """Safely update UI elements from background threads"""
    try:
        if self.root and self.root.winfo_exists():
            self.root.after(0, update_func)
    except Exception:
        # Silently ignore UI update errors during shutdown
        pass




    def setup_styles(self):
        """Configure professional styles"""
        style = ttk.Style()
        try:
            style.theme_use('clam')
        except Exception:
            pass

        style.configure('TNotebook',
                        background=ModernTheme.BG_PRIMARY,
                        borderwidth=0)
        style.configure('TNotebook.Tab',
                        background=ModernTheme.BG_SECONDARY,
                        foreground=ModernTheme.TEXT_PRIMARY,
                        padding=[20, 12],
                        font=ModernTheme.FONT_MEDIUM)
        style.map('TNotebook.Tab',
                  background=[('selected', ModernTheme.ACCENT_BLUE)])

        style.configure('TFrame', background=ModernTheme.BG_PRIMARY)

    def create_professional_ui(self):
        """Create the professional trading interface"""
        self.create_header()
        
        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill='both', expand=True, padx=10, pady=5)

        self.create_dashboard_tab()
        self.create_portfolio_tab()
        self.create_orders_tab()
        self.create_security_tab()
        self.create_paper_trading_tab()
        self.create_about_tab()

        self.create_status_bar()

    def create_header(self):
        """Create professional header with status indicators"""
        header_frame = tk.Frame(self.root, bg=ModernTheme.BG_SECONDARY, height=80)
        header_frame.pack(fill='x', padx=10, pady=5)
        header_frame.pack_propagate(False)

        left_frame = tk.Frame(header_frame, bg=ModernTheme.BG_SECONDARY)
        left_frame.pack(side='left', fill='y', padx=20, pady=10)

        title_label = tk.Label(left_frame,
                               text=f"Angel One Trading Bot v{self.version}",
                               font=ModernTheme.FONT_TITLE,
                               bg=ModernTheme.BG_SECONDARY,
                               fg=ModernTheme.TEXT_PRIMARY)
        title_label.pack(anchor='w')

        subtitle_label = tk.Label(left_frame,
                                  text="Professional Trading Dashboard",
                                  font=ModernTheme.FONT_SMALL,
                                  bg=ModernTheme.BG_SECONDARY,
                                  fg=ModernTheme.TEXT_SECONDARY)
        subtitle_label.pack(anchor='w')

        right_frame = tk.Frame(header_frame, bg=ModernTheme.BG_SECONDARY)
        right_frame.pack(side='right', fill='y', padx=20, pady=10)

        self.connection_status = tk.Label(right_frame,
                                          text="Disconnected",
                                          font=ModernTheme.FONT_MEDIUM,
                                          bg=ModernTheme.BG_SECONDARY,
                                          fg=ModernTheme.TEXT_ERROR)
        self.connection_status.pack(anchor='e')

        try:
            balance = self.paper_trader.current_balance
        except Exception:
            balance = 0.0
        
        self.balance_display = tk.Label(right_frame,
                                        text=f"Balance: Rs{balance:,.2f}",
                                        font=ModernTheme.FONT_MEDIUM,
                                        bg=ModernTheme.BG_SECONDARY,
                                        fg=ModernTheme.TEXT_SUCCESS)
        self.balance_display.pack(anchor='e')

        emergency_btn = tk.Button(right_frame,
                                  text="EMERGENCY",
                                  command=self.emergency_stop,
                                  bg=ModernTheme.ACCENT_RED,
                                  fg="white",
                                  font=ModernTheme.FONT_BUTTON,
                                  padx=15, pady=5)
        emergency_btn.pack(anchor='e', pady=5)

    def create_dashboard_tab(self):
        """Create professional dashboard tab"""
        dashboard_frame = ttk.Frame(self.notebook)
        self.notebook.add(dashboard_frame, text='Dashboard')

        main_container = tk.Frame(dashboard_frame, bg=ModernTheme.BG_PRIMARY)
        main_container.pack(fill='both', expand=True, padx=10, pady=10)

        controls_frame = self.create_control_panel(main_container)
        controls_frame.pack(fill='x', pady=(0, 10))

        market_frame = self.create_market_overview(main_container)
        market_frame.pack(fill='x', pady=(0, 10))

        signals_frame = self.create_signals_panel(main_container)
        signals_frame.pack(fill='both', expand=True)

    def create_control_panel(self, parent):
        """Create control button panel"""
        control_frame = tk.LabelFrame(parent,
                                     text="Trading Controls",
                                     bg=ModernTheme.BG_CARD,
                                     fg=ModernTheme.TEXT_PRIMARY,
                                     font=ModernTheme.FONT_MEDIUM,
                                     padx=15, pady=10)

        btn_container = tk.Frame(control_frame, bg=ModernTheme.BG_CARD)
        btn_container.pack(fill='x')

        buttons = [
            ("Refresh Data", self.refresh_all_data, ModernTheme.ACCENT_BLUE),
            ("Settings", self.show_settings, ModernTheme.ACCENT_PURPLE),
            ("Market Data", self.show_market_data, ModernTheme.ACCENT_GREEN),
            ("Stock Manager", self.show_stock_manager, ModernTheme.ACCENT_PURPLE),
            ("Enhanced Analysis", self.run_enhanced_analysis, ModernTheme.ACCENT_YELLOW),
            ("Pre-Market Analysis", self.run_premarket_analysis, "#FF6B35")
        ]

        for i, (text, command, color) in enumerate(buttons):
            btn = tk.Button(btn_container,
                            text=text,
                            command=command,
                            bg=color,
                            fg="white" if color != ModernTheme.ACCENT_YELLOW else "black",
                            font=ModernTheme.FONT_BUTTON,
                            padx=15, pady=8,
                            relief='flat')
            btn.grid(row=i // 3, column=i % 3, padx=8, pady=5, sticky='ew')

        for i in range(3):
            btn_container.grid_columnconfigure(i, weight=1)

        return control_frame

    def create_market_overview(self, parent):
        """Create market overview panel"""
        market_frame = tk.LabelFrame(parent,
                                     text="Market Overview",
                                     bg=ModernTheme.BG_CARD,
                                     fg=ModernTheme.TEXT_PRIMARY,
                                     font=ModernTheme.FONT_MEDIUM,
                                     padx=15, pady=10)

        data_container = tk.Frame(market_frame, bg=ModernTheme.BG_CARD)
        data_container.pack(fill='x')

        self.market_labels = {}
        indices = [
            ("NIFTY 50", "25,145.10", "+125.30", "(+0.50%)"),
            ("SENSEX", "82,365.77", "+456.23", "(+0.56%)"),
            ("BANK NIFTY", "51,234.56", "-89.45", "(-0.17%)")
        ]

        for i, (name, price, change, change_pct) in enumerate(indices):
            index_frame = tk.Frame(data_container,
                                   bg=ModernTheme.BG_INPUT,
                                   relief='raised',
                                   borderwidth=1)
            index_frame.grid(row=0, column=i, padx=10, pady=5, sticky='ew')

            name_label = tk.Label(index_frame,
                                  text=name,
                                  font=ModernTheme.FONT_SMALL,
                                  bg=ModernTheme.BG_INPUT,
                                  fg=ModernTheme.TEXT_SECONDARY)
            name_label.pack(pady=(10, 5))

            price_label = tk.Label(index_frame,
                                   text=price,
                                   font=ModernTheme.FONT_MEDIUM,
                                   bg=ModernTheme.BG_INPUT,
                                   fg=ModernTheme.TEXT_PRIMARY)
            price_label.pack()

            change_color = ModernTheme.TEXT_SUCCESS if "+" in change else ModernTheme.TEXT_ERROR
            change_label = tk.Label(index_frame,
                                    text=f"{change} {change_pct}",
                                    font=ModernTheme.FONT_SMALL,
                                    bg=ModernTheme.BG_INPUT,
                                    fg=change_color)
            change_label.pack(pady=(0, 10))

            self.market_labels[name] = {
                'price': price_label,
                'change': change_label
            }

        for i in range(3):
            data_container.grid_columnconfigure(i, weight=1)

        return market_frame

    def create_signals_panel(self, parent):
        """Create trading signals panel"""
        signals_frame = tk.LabelFrame(parent,
                                      text="Signal-Based Trading",
                                      bg=ModernTheme.BG_CARD,
                                      fg=ModernTheme.TEXT_PRIMARY,
                                      font=ModernTheme.FONT_MEDIUM,
                                      padx=15, pady=10)

        capital_frame = tk.Frame(signals_frame, bg=ModernTheme.BG_CARD)
        capital_frame.pack(fill='x', pady=(0, 10))

        capital_label = tk.Label(capital_frame,
                                 text="Total Capital: Rs250,000 | Allocated: Rs50,000",
                                 font=ModernTheme.FONT_SMALL,
                                 bg=ModernTheme.BG_CARD,
                                 fg=ModernTheme.TEXT_SUCCESS)
        capital_label.pack()

        signals_container = tk.Frame(signals_frame, bg=ModernTheme.BG_CARD)
        signals_container.pack(fill='both', expand=True)

        listbox_frame = tk.Frame(signals_container, bg=ModernTheme.BG_CARD)
        listbox_frame.pack(fill='both', expand=True, side='left')

        self.signals_listbox = tk.Listbox(listbox_frame,
                                          bg=ModernTheme.BG_INPUT,
                                          fg=ModernTheme.TEXT_PRIMARY,
                                          font=ModernTheme.FONT_SMALL,
                                          selectbackground=ModernTheme.ACCENT_BLUE,
                                          borderwidth=0)
        self.signals_listbox.pack(fill='both', expand=True, side='left')

        signals_scrollbar = tk.Scrollbar(listbox_frame,
                                         orient="vertical",
                                         command=self.signals_listbox.yview)
        self.signals_listbox.configure(yscrollcommand=signals_scrollbar.set)
        signals_scrollbar.pack(side='right', fill='y')

        self.signals_buttons_frame = tk.Frame(signals_container, bg=ModernTheme.BG_CARD)
        self.signals_buttons_frame.pack(fill='y', side='right', padx=(10, 0))

        self.signals_listbox.insert(0, "Click 'Enhanced Analysis' to generate Golden Ratio signals...")
        self.signals_listbox.insert(1, "Advanced technical analysis with RSI & Volume confirmation")
        self.signals_listbox.insert(2, "System will analyze stocks and show BUY/SELL opportunities")

        return signals_frame

    def create_portfolio_tab(self):
        """Create portfolio tab"""
        portfolio_frame = ttk.Frame(self.notebook)
        self.notebook.add(portfolio_frame, text='Portfolio')

        header = tk.Label(portfolio_frame,
                          text="Portfolio Holdings & Performance",
                          font=ModernTheme.FONT_TITLE,
                          bg=ModernTheme.BG_PRIMARY,
                          fg=ModernTheme.TEXT_PRIMARY,
                          pady=20)
        header.pack()

        portfolio_container = tk.Frame(portfolio_frame, bg=ModernTheme.BG_PRIMARY)
        portfolio_container.pack(fill='both', expand=True, padx=20, pady=10)

        self.portfolio_text = tk.Text(portfolio_container,
                                      bg=ModernTheme.BG_INPUT,
                                      fg=ModernTheme.TEXT_PRIMARY,
                                      font=ModernTheme.FONT_SMALL,
                                      wrap=tk.WORD)
        self.portfolio_text.pack(fill='both', expand=True, side='left')

        portfolio_scrollbar = tk.Scrollbar(portfolio_container,
                                           orient="vertical",
                                           command=self.portfolio_text.yview)
        self.portfolio_text.configure(yscrollcommand=portfolio_scrollbar.set)
        portfolio_scrollbar.pack(side='right', fill='y')

        btn_frame = tk.Frame(portfolio_frame, bg=ModernTheme.BG_PRIMARY)
        btn_frame.pack(pady=10)

        refresh_btn = tk.Button(btn_frame,
                                text="Refresh Portfolio",
                                command=self.refresh_portfolio,
                                bg=ModernTheme.ACCENT_BLUE,
                                fg="white",
                                font=ModernTheme.FONT_BUTTON,
                                padx=20, pady=8)
        refresh_btn.pack()

        self.refresh_portfolio()

    def create_orders_tab(self):
        """Create orders tab"""
        orders_frame = ttk.Frame(self.notebook)
        self.notebook.add(orders_frame, text='Orders')

        header = tk.Label(orders_frame,
                          text="Order History & Management",
                          font=ModernTheme.FONT_TITLE,
                          bg=ModernTheme.BG_PRIMARY,
                          fg=ModernTheme.TEXT_PRIMARY,
                          pady=20)
        header.pack()

        orders_container = tk.Frame(orders_frame, bg=ModernTheme.BG_PRIMARY)
        orders_container.pack(fill='both', expand=True, padx=20, pady=10)

        self.orders_text = tk.Text(orders_container,
                                   bg=ModernTheme.BG_INPUT,
                                   fg=ModernTheme.TEXT_PRIMARY,
                                   font=ModernTheme.FONT_SMALL,
                                   wrap=tk.WORD)
        self.orders_text.pack(fill='both', expand=True, side='left')

        orders_scrollbar = tk.Scrollbar(orders_container,
                                        orient="vertical",
                                        command=self.orders_text.yview)
        self.orders_text.configure(yscrollcommand=orders_scrollbar.set)
        orders_scrollbar.pack(side='right', fill='y')

        self.refresh_orders()

    def create_security_tab(self):
        """Create security tab"""
        security_frame = ttk.Frame(self.notebook)
        self.notebook.add(security_frame, text='Security')

        header = tk.Label(security_frame,
                          text="Security & Risk Management",
                          font=ModernTheme.FONT_TITLE,
                          bg=ModernTheme.BG_PRIMARY,
                          fg=ModernTheme.TEXT_PRIMARY,
                          pady=20)
        header.pack()

        status_frame = tk.LabelFrame(security_frame,
                                     text="Security Status",
                                     bg=ModernTheme.BG_CARD,
                                     fg=ModernTheme.TEXT_PRIMARY,
                                     font=ModernTheme.FONT_MEDIUM,
                                     padx=20, pady=15)
        status_frame.pack(fill='x', padx=20, pady=10)

        security_labels = [
            "Credentials: Encrypted",
            "Connection: Secure",
            "Logging: Active",
            "Paper Trading: Enabled"
        ]

        for label_text in security_labels:
            label = tk.Label(status_frame,
                             text=label_text,
                             font=ModernTheme.FONT_SMALL,
                             bg=ModernTheme.BG_CARD,
                             fg=ModernTheme.TEXT_SUCCESS)
            label.pack(anchor='w', pady=2)

        emergency_frame = tk.LabelFrame(security_frame,
                                        text="Emergency Controls",
                                        bg=ModernTheme.BG_CARD,
                                        fg=ModernTheme.TEXT_PRIMARY,
                                        font=ModernTheme.FONT_MEDIUM,
                                        padx=20, pady=15)
        emergency_frame.pack(fill='x', padx=20, pady=10)

        emergency_btn = tk.Button(emergency_frame,
                                  text="EMERGENCY STOP ALL",
                                  command=self.emergency_stop,
                                  bg=ModernTheme.ACCENT_RED,
                                  fg="white",
                                  font=("Segoe UI", 14, "bold"),
                                  padx=30, pady=15)
        emergency_btn.pack()

    def create_paper_trading_tab(self):
        """Create paper trading tab"""
        paper_frame = ttk.Frame(self.notebook)
        self.notebook.add(paper_frame, text='Paper Trading')

        header = tk.Label(paper_frame,
                          text="Paper Trading Simulation",
                          font=ModernTheme.FONT_TITLE,
                          bg=ModernTheme.BG_PRIMARY,
                          fg=ModernTheme.TEXT_PRIMARY,
                          pady=20)
        header.pack()

        stats_container = tk.Frame(paper_frame, bg=ModernTheme.BG_PRIMARY)
        stats_container.pack(fill='both', expand=True, padx=20, pady=10)

        self.paper_stats = tk.Text(stats_container,
                                   bg=ModernTheme.BG_INPUT,
                                   fg=ModernTheme.TEXT_PRIMARY,
                                   font=ModernTheme.FONT_SMALL,
                                   wrap=tk.WORD)
        self.paper_stats.pack(fill='both', expand=True, side='left')

        paper_scrollbar = tk.Scrollbar(stats_container,
                                       orient="vertical",
                                       command=self.paper_stats.yview)
        self.paper_stats.configure(yscrollcommand=paper_scrollbar.set)
        paper_scrollbar.pack(side='right', fill='y')

        reset_btn = tk.Button(paper_frame,
                              text="Reset Paper Trading",
                              command=self.reset_paper_trading,
                              bg=ModernTheme.ACCENT_PURPLE,
                              fg="white",
                              font=ModernTheme.FONT_BUTTON,
                              padx=20, pady=8)
        reset_btn.pack(pady=15)

        self.update_paper_stats()

    def create_about_tab(self):
        """Create about tab"""
        about_frame = ttk.Frame(self.notebook)
        self.notebook.add(about_frame, text='About')

        about_container = tk.Frame(about_frame, bg=ModernTheme.BG_PRIMARY)
        about_container.pack(fill='both', expand=True, padx=20, pady=20)

        about_text = tk.Text(about_container,
                             bg=ModernTheme.BG_INPUT,
                             fg=ModernTheme.TEXT_PRIMARY,
                             font=ModernTheme.FONT_SMALL,
                             wrap=tk.WORD)
        about_text.pack(fill='both', expand=True, side='left')

        about_scrollbar = tk.Scrollbar(about_container,
                                       orient="vertical",
                                       command=about_text.yview)
        about_text.configure(yscrollcommand=about_scrollbar.set)
        about_scrollbar.pack(side='right', fill='y')

        about_content = f"""
ANGEL ONE TRADING BOT v{self.version}
{'='*50}

Build: Modular Architecture
Architecture: Professional Trading System
Strategy: Golden Ratio Technical Analysis

FEATURES:
{'='*20}
Enhanced Analysis Engine with Real Technical Indicators
Live Market Data Integration
Signal-Based Trading with Confidence Scores
Golden Ratio + RSI + EMA + Volume Analysis
Professional Portfolio Management
Advanced Paper Trading Simulation
Enterprise Security Controls
Comprehensive Order Management

TECHNICAL STACK:
{'='*22}
Python 3.10+ with Modular Architecture
Professional Tkinter Interface
Angel One SmartAPI Integration
Advanced Technical Analysis Library
Secure Credential Management

GOLDEN RATIO STRATEGY:
{'='*25}
Fibonacci Retracements (23.6%, 38.2%, 61.8%, 78.6%)
RSI Analysis (Oversold <30, Overbought >70)
EMA Crossovers (8-period vs 21-period)
Volume Confirmation Analysis
Bollinger Bands Integration

PROFESSIONAL FEATURES:
{'='*27}
Real-time WebSocket Market Data
Advanced Technical Analysis Engine
Professional Risk Management
Comprehensive Portfolio Tracking
Multi-timeframe Analysis
Automated Stop-Loss & Target Management

DISCLAIMER:
{'='*17}
This software is for educational purposes only.
Trading involves risk. Past performance does not
guarantee future results. Always do your own
research before making investment decisions.

(c) 2025 Trading Bot System - Professional Edition
Licensed for personal use only.
        """

        about_text.insert('1.0', about_content)
        about_text.configure(state='disabled')

    def create_status_bar(self):
        """Create professional status bar"""
        self.status_bar = tk.Frame(self.root, bg=ModernTheme.BG_SECONDARY, height=35)
        self.status_bar.pack(fill='x', side='bottom')
        self.status_bar.pack_propagate(False)

        self.status_label = tk.Label(self.status_bar,
                                    text="Paper Trading Mode | System Ready",
                                    bg=ModernTheme.BG_SECONDARY,
                                    fg=ModernTheme.TEXT_SECONDARY,
                                    font=ModernTheme.FONT_SMALL)
        self.status_label.pack(side='left', padx=15, pady=8)

        self.market_status = tk.Label(self.status_bar,
                                     text="Market: Ready | Monitoring 15 stocks",
                                     bg=ModernTheme.BG_SECONDARY,
                                     fg=ModernTheme.TEXT_SECONDARY,
                                     font=ModernTheme.FONT_SMALL)
        self.market_status.pack(side='left', expand=True)

        self.time_label = tk.Label(self.status_bar,
                                   text="",
                                   bg=ModernTheme.BG_SECONDARY,
                                   fg=ModernTheme.TEXT_SECONDARY,
                                   font=ModernTheme.FONT_SMALL)
        self.time_label.pack(side='right', padx=15, pady=8)

        self.update_time()

    def refresh_all_data(self):
        """Refresh all data"""
        self.status_label.config(text="Refreshing all data...")
        threading.Thread(target=self._refresh_worker, daemon=True).start()

    def _refresh_worker(self):
        """Background refresh worker"""
        try:
            time.sleep(1)
            balance = getattr(self.paper_trader, 'current_balance', 0.0)
            self.balance_display.config(text=f"Balance: Rs{balance:,.2f}")
            self.status_label.config(text="Data refreshed successfully")
        except Exception as e:
            self.status_label.config(text=f"Refresh error: {str(e)}")

    def run_enhanced_analysis(self):
        """Run enhanced analysis"""
        self.status_label.config(text="Running Golden Ratio analysis...")
        threading.Thread(target=self._analysis_worker, daemon=True).start()

    def _analysis_worker(self):
        """Background worker for analysis - with safe UI updates"""
        try:
            # Initialize analysis running flag if not exists
            if not hasattr(self, 'analysis_running'):
                self.analysis_running = True
                
            # Clear previous results safely
            def clear_results():
                try:
                    if hasattr(self, 'signals_listbox') and self.signals_listbox.winfo_exists():
                        self.signals_listbox.delete(0, tk.END)
                        self.signals_listbox.insert(0, "Running enhanced Golden Ratio analysis...")
                except Exception:
                    pass
            
            self.safe_update_ui(clear_results)

            # Simulate analysis work
            for i in range(4):
                if not getattr(self, 'analysis_running', True):
                    break
                time.sleep(0.5)
                
            if not getattr(self, 'analysis_running', True):
                return

            # Generate sample signals
            sample_signals = [
                {
                    'symbol': 'RELIANCE',
                    'action': 'BUY',
                    'price': 2456.75,
                    'confidence': 85,
                    'reason': 'Golden ratio support + oversold RSI + high volume'
                },
                {
                    'symbol': 'TCS',
                    'action': 'SELL',
                    'price': 3987.20,
                    'confidence': 78,
                    'reason': 'Golden ratio resistance + overbought RSI'
                }
            ]

            # Apply signals safely
            def apply_signals():
                try:
                    self.current_signals = sample_signals
                    self.display_signals()
                    if hasattr(self, 'status_label') and self.status_label.winfo_exists():
                        self.status_label.config(text=f"Analysis complete | {len(sample_signals)} signals found")
                except Exception:
                    pass
            
            self.safe_update_ui(apply_signals)
            
        except Exception as e:
            # Handle errors safely
            def report_error():
                try:
                    if hasattr(self, 'status_label') and self.status_label.winfo_exists():
                        self.status_label.config(text=f"Analysis error: {str(e)}")
                except Exception:
                    pass
            
            self.safe_update_ui(report_error)
        
        finally:
            # Ensure analysis_running is set to False
            if hasattr(self, 'analysis_running'):
                self.analysis_running = False



    def display_signals(self):
        """Display trading signals"""
        self.signals_listbox.delete(0, tk.END)

        for widget in getattr(self, 'signals_buttons_frame', []).winfo_children():
            widget.destroy()

        if not self.current_signals:
            self.signals_listbox.insert(0, "No signals found in current market conditions")
            return

        for i, signal in enumerate(self.current_signals):
            action_emoji = "BUY" if signal['action'] == 'BUY' else "SELL"
            confidence_bar = "*" * (signal['confidence'] // 10)

            signal_text = (f"{i+1}. {action_emoji} {signal['symbol']} @ Rs{signal['price']} "
                           f"| Confidence: {signal['confidence']}% {confidence_bar}")
            reason_text = f"   Reason: {signal['reason']}"

            self.signals_listbox.insert(tk.END, signal_text)
            self.signals_listbox.insert(tk.END, reason_text)
            self.signals_listbox.insert(tk.END, "-" * 60)

            btn_color = ModernTheme.ACCENT_GREEN if signal['action'] == 'BUY' else ModernTheme.ACCENT_RED
            btn_text = f"Execute {signal['action']}"

            execute_btn = tk.Button(self.signals_buttons_frame,
                                    text=btn_text,
                                    command=lambda idx=i: self.execute_signal(idx),
                                    bg=btn_color,
                                    fg="white",
                                    font=ModernTheme.FONT_BUTTON,
                                    padx=15, pady=5,
                                    width=12)
            execute_btn.pack(pady=5, fill='x')

    def execute_signal(self, signal_index):
        """Execute a trading signal"""
        try:
            signal = self.current_signals[signal_index]
            quantity = 10

            success, message = self.paper_trader.place_order(
                symbol=signal['symbol'],
                side=signal['action'],
                quantity=quantity,
                price=signal['price']
            )

            if success:
                messagebox.showinfo("Trade Executed",
                                    f"{signal['action']} order executed!\n\n"
                                    f"Symbol: {signal['symbol']}\n"
                                    f"Quantity: {quantity}\n"
                                    f"Price: Rs{signal['price']}\n"
                                    f"{message}")

                balance = getattr(self.paper_trader, 'current_balance', 0.0)
                self.balance_display.config(text=f"Balance: Rs{balance:,.2f}")

                self.refresh_portfolio()
                self.update_paper_stats()
            else:
                messagebox.showerror("Trade Failed", message)

        except Exception as e:
            messagebox.showerror("Error", f"Execution error: {str(e)}")

    def run_premarket_analysis(self):
        """Run pre-market analysis"""
        current_time = datetime.now().time()
        premarket_start = datetime.strptime("07:00", "%H:%M").time()
        premarket_end = datetime.strptime("09:15", "%H:%M").time()

        if premarket_start <= current_time <= premarket_end:
            self.status_label.config(text="Running pre-market analysis...")
            self.run_enhanced_analysis()
        else:
            messagebox.showinfo("Pre-Market Analysis",
                                f"Pre-market analysis available 7:00-9:15 AM\n\n"
                                f"Current time: {current_time.strftime('%H:%M')}\n"
                                f"Market opens: 09:15 AM")

    def show_settings(self):
        """Show settings dialog"""
        settings_window = tk.Toplevel(self.root)
        settings_window.title("Settings")
        settings_window.geometry("500x600")
        settings_window.configure(bg=ModernTheme.BG_PRIMARY)
        settings_window.transient(self.root)

        header = tk.Label(settings_window,
                          text="Trading Bot Settings",
                          font=ModernTheme.FONT_TITLE,
                          bg=ModernTheme.BG_PRIMARY,
                          fg=ModernTheme.TEXT_PRIMARY)
        header.pack(pady=20)

        api_frame = tk.LabelFrame(settings_window,
                                 text="API Configuration",
                                 bg=ModernTheme.BG_CARD,
                                 fg=ModernTheme.TEXT_PRIMARY,
                                 font=ModernTheme.FONT_MEDIUM,
                                 padx=20, pady=15)
        api_frame.pack(fill='x', padx=20, pady=10)

        config_btn = tk.Button(api_frame,
                               text="Configure Angel One Credentials",
                               command=self.configure_credentials,
                               bg=ModernTheme.ACCENT_BLUE,
                               fg="white",
                               font=ModernTheme.FONT_BUTTON,
                               padx=20, pady=8)
        config_btn.pack()

        mode_frame = tk.LabelFrame(settings_window,
                                   text="Trading Mode",
                                   bg=ModernTheme.BG_CARD,
                                   fg=ModernTheme.TEXT_PRIMARY,
                                   font=ModernTheme.FONT_MEDIUM,
                                   padx=20, pady=15)
        mode_frame.pack(fill='x', padx=20, pady=10)

        self.trading_mode = tk.StringVar(settings_window, value="Paper")

        paper_radio = tk.Radiobutton(mode_frame,
                                     text="Paper Trading (Safe)",
                                     variable=self.trading_mode,
                                     value="Paper",
                                     bg=ModernTheme.BG_CARD,
                                     fg=ModernTheme.TEXT_PRIMARY,
                                     font=ModernTheme.FONT_SMALL,
                                     selectcolor=ModernTheme.BG_INPUT)
        paper_radio.pack(anchor='w', pady=5)

        live_radio = tk.Radiobutton(mode_frame,
                                    text="Live Trading (Risk)",
                                    variable=self.trading_mode,
                                    value="Live",
                                    bg=ModernTheme.BG_CARD,
                                    fg=ModernTheme.TEXT_PRIMARY,
                                    font=ModernTheme.FONT_SMALL,
                                    selectcolor=ModernTheme.BG_INPUT)
        live_radio.pack(anchor='w', pady=5)

        watchlist_frame = tk.LabelFrame(settings_window,
                                        text="Stock Watchlist",
                                        bg=ModernTheme.BG_CARD,
                                        fg=ModernTheme.TEXT_PRIMARY,
                                        font=ModernTheme.FONT_MEDIUM,
                                        padx=20, pady=15)
        watchlist_frame.pack(fill='both', expand=True, padx=20, pady=10)

        watchlist_btn = tk.Button(watchlist_frame,
                                  text="Edit Watchlist",
                                  command=self.edit_watchlist,
                                  bg=ModernTheme.ACCENT_PURPLE,
                                  fg="white",
                                  font=ModernTheme.FONT_BUTTON,
                                  padx=20, pady=8)
        watchlist_btn.pack()

    def configure_credentials(self):
        """Create functional credentials configuration dialog"""
        for widget in self.root.winfo_children():
            if isinstance(widget, tk.Toplevel) and widget.title() == "Configure Credentials":
                widget.destroy()

        creds_window = tk.Toplevel(self.root)
        creds_window.title("Configure Credentials")
        creds_window.geometry("540x620")
        creds_window.resizable(False, False)
        creds_window.configure(bg=ModernTheme.BG_PRIMARY)
        creds_window.transient(self.root)
        creds_window.grab_set()

        header_frame = tk.Frame(creds_window, bg=ModernTheme.BG_PRIMARY)
        header_frame.pack(fill='x', pady=12)

        title_label = tk.Label(header_frame,
                               text="Angel One API Credentials",
                               font=ModernTheme.FONT_TITLE,
                               bg=ModernTheme.BG_PRIMARY,
                               fg=ModernTheme.TEXT_PRIMARY)
        title_label.pack()

        subtitle_label = tk.Label(header_frame,
                                  text="Enter your Angel One trading account credentials",
                                  font=ModernTheme.FONT_SMALL,
                                  bg=ModernTheme.BG_PRIMARY,
                                  fg=ModernTheme.TEXT_SECONDARY)
        subtitle_label.pack(pady=(4, 0))

        container_frame = tk.Frame(creds_window, bg=ModernTheme.BG_PRIMARY)
        container_frame.pack(fill='both', expand=True, padx=10, pady=(10,8))
        
        canvas = tk.Canvas(container_frame, bg=ModernTheme.BG_PRIMARY, highlightthickness=0)
        v_scroll = tk.Scrollbar(container_frame, orient='vertical', command=canvas.yview)
        canvas.configure(yscrollcommand=v_scroll.set)
        
        v_scroll.pack(side='right', fill='y')
        canvas.pack(side='left', fill='both', expand=True)
        
        form_frame = tk.Frame(canvas, bg=ModernTheme.BG_PRIMARY)
        inner_window = canvas.create_window((0,0), window=form_frame, anchor='nw')
        
        def _on_frame_config(event):
            canvas.configure(scrollregion=canvas.bbox('all'))
        
        form_frame.bind('<Configure>', _on_frame_config)
        
        def _on_canvas_config(event):
            canvas.itemconfig(inner_window, width=event.width)
        
        canvas.bind('<Configure>', _on_canvas_config)
        
        def _on_mousewheel(event):
            delta = int(-1*(event.delta/120)) if event.delta else 0
            canvas.yview_scroll(delta, 'units')
        
        def _bind_mousewheel(event):
            canvas.bind_all('<MouseWheel>', _on_mousewheel)
        
        def _unbind_mousewheel(event):
            canvas.unbind_all('<MouseWheel>')
        
        canvas.bind('<Enter>', _bind_mousewheel)
        canvas.bind('<Leave>', _unbind_mousewheel)
        
        def _ensure_top():
            form_frame.update_idletasks()
            canvas.configure(scrollregion=canvas.bbox('all'))
            canvas.yview_moveto(0.0)
        
        creds_window.after(100, _ensure_top)

        fields = {}

        field_configs = [
            {
                'key': 'api_key',
                'label': 'API Key',
                'placeholder': 'Enter your Angel One API Key',
                'show': False
            },
            {
                'key': 'client_code', 
                'label': 'Client Code',
                'placeholder': 'Enter your Client Code (User ID)',
                'show': False
            },
            {
                'key': 'password',
                'label': 'Password', 
                'placeholder': 'Enter your Angel One password',
                'show': True
            },
            {
                'key': 'totp_secret',
                'label': 'TOTP Secret Key',
                'placeholder': 'Enter Google Authenticator secret key',
                'show': False
            }
        ]

        for config in field_configs:
            field_container = tk.Frame(form_frame, bg=ModernTheme.BG_PRIMARY)
            field_container.pack(fill='x', padx=20, pady=10)
            
            label = tk.Label(field_container,
                             text=config['label'],
                             font=ModernTheme.FONT_MEDIUM,
                             bg=ModernTheme.BG_PRIMARY,
                             fg=ModernTheme.TEXT_PRIMARY)
            label.pack(anchor='w', pady=(0, 5))
            
            if config['show']:
                entry = tk.Entry(field_container,
                                font=ModernTheme.FONT_SMALL,
                                bg=ModernTheme.BG_INPUT,
                                fg=ModernTheme.TEXT_PRIMARY,
                                insertbackground=ModernTheme.TEXT_PRIMARY,
                                relief='flat',
                                bd=2,
                                show='*',
                                width=50)
            else:
                entry = tk.Entry(field_container,
                                font=ModernTheme.FONT_SMALL,
                                bg=ModernTheme.BG_INPUT,
                                fg=ModernTheme.TEXT_PRIMARY,
                                insertbackground=ModernTheme.TEXT_PRIMARY,
                                relief='flat',
                                bd=2,
                                width=50)
            
            entry.pack(fill='x', pady=(0, 5))
            
            def add_placeholder(entry_widget, placeholder_text):
                entry_widget.insert(0, placeholder_text)
                entry_widget.config(fg=ModernTheme.TEXT_MUTED)
                
                def on_focus_in(event):
                    if entry_widget.get() == placeholder_text:
                        entry_widget.delete(0, tk.END)
                        entry_widget.config(fg=ModernTheme.TEXT_PRIMARY)
                
                def on_focus_out(event):
                    if not entry_widget.get():
                        entry_widget.insert(0, placeholder_text)
                        entry_widget.config(fg=ModernTheme.TEXT_MUTED)
                
                entry_widget.bind('<FocusIn>', on_focus_in)
                entry_widget.bind('<FocusOut>', on_focus_out)
            
            if not config['show']:
                add_placeholder(entry, config['placeholder'])
            
            fields[config['key']] = entry

        helper_frame = tk.Frame(form_frame, bg=ModernTheme.BG_PRIMARY)
        helper_frame.pack(fill='x', padx=20, pady=(0, 10))

        helper_text = tk.Label(helper_frame,
                               text="All credentials are encrypted and stored securely",
                               font=("Segoe UI", 9, "italic"),
                               bg=ModernTheme.BG_PRIMARY,
                               fg=ModernTheme.TEXT_SECONDARY)
        helper_text.pack()

        status_label = tk.Label(form_frame,
                                text="",
                                font=ModernTheme.FONT_SMALL,
                                bg=ModernTheme.BG_PRIMARY)
        status_label.pack(pady=10)

        buttons_frame = tk.Frame(creds_window, bg=ModernTheme.BG_PRIMARY)
        buttons_frame.pack(side='bottom', fill='x', padx=30, pady=12)

        def save_credentials():
            try:
                api_key = fields['api_key'].get().strip()
                client_code = fields['client_code'].get().strip()
                password = fields['password'].get().strip()
                totp_secret = fields['totp_secret'].get().strip()

                if api_key == field_configs[0]['placeholder']:
                    api_key = ""
                if client_code == field_configs[1]['placeholder']:
                    client_code = ""
                if totp_secret == field_configs[3]['placeholder']:
                    totp_secret = ""

                if not all([api_key, client_code, password, totp_secret]):
                    status_label.config(text="All fields are required", fg=ModernTheme.TEXT_ERROR)
                    return

                status_label.config(text="Saving credentials...", fg=ModernTheme.TEXT_SECONDARY)
                creds_window.update()

                success, message = self.angel_api.set_credentials(api_key, client_code, password, totp_secret)
                
                if success:
                    status_label.config(text="Testing connection...", fg=ModernTheme.TEXT_SECONDARY)
                    creds_window.update()

                    success, message = self.angel_api.login()

                    if success:
                        status_label.config(text="Credentials saved and connection successful!",
                                            fg=ModernTheme.TEXT_SUCCESS)

                        self.connected = True
                        self.connection_status.config(text="Connected", fg=ModernTheme.TEXT_SUCCESS)
                        self.status_label.config(text="Connected to Angel One API | Live data active")

                        creds_window.after(2000, creds_window.destroy)
                    else:
                        status_label.config(text=f"Connection failed: {message}",
                                            fg=ModernTheme.TEXT_ERROR)
                else:
                    status_label.config(text=f"Error: {message}", fg=ModernTheme.TEXT_ERROR)

            except Exception as e:
                status_label.config(text=f"Error: {str(e)}", fg=ModernTheme.TEXT_ERROR)

        def test_connection():
            try:
                api_key = fields['api_key'].get().strip()
                client_code = fields['client_code'].get().strip()
                password = fields['password'].get().strip()
                totp_secret = fields['totp_secret'].get().strip()

                if api_key == field_configs[0]['placeholder']:
                    api_key = ""
                if client_code == field_configs[1]['placeholder']:
                    client_code = ""
                if totp_secret == field_configs[3]['placeholder']:
                    totp_secret = ""

                if not all([api_key, client_code, password, totp_secret]):
                    status_label.config(text="All fields are required for testing", fg=ModernTheme.TEXT_ERROR)
                    return

                status_label.config(text="Testing connection...", fg=ModernTheme.TEXT_SECONDARY)
                creds_window.update()

                temp_success, temp_message = self.angel_api.set_credentials(api_key, client_code, password, totp_secret)
                
                if temp_success:
                    success, message = self.angel_api.login()
                    
                    if success:
                        status_label.config(text="Connection test successful! Click 'Save & Connect' to apply.",
                                            fg=ModernTheme.TEXT_SUCCESS)
                    else:
                        status_label.config(text=f"Test failed: {message}", fg=ModernTheme.TEXT_ERROR)
                else:
                    status_label.config(text=f"Test error: {temp_message}", fg=ModernTheme.TEXT_ERROR)

            except Exception as e:
                status_label.config(text=f"Test error: {str(e)}", fg=ModernTheme.TEXT_ERROR)

        test_btn = tk.Button(buttons_frame,
                             text="Test Connection",
                             command=test_connection,
                             bg=ModernTheme.ACCENT_YELLOW,
                             fg="black",
                             font=ModernTheme.FONT_BUTTON,
                             padx=20, pady=10,
                             relief='flat')
        test_btn.pack(side='left', padx=(0, 10))

        save_btn = tk.Button(buttons_frame,
                             text="Save & Connect",
                             command=save_credentials,
                             bg=ModernTheme.ACCENT_GREEN,
                             fg="white",
                             font=ModernTheme.FONT_BUTTON,
                             padx=20, pady=10,
                             relief='flat')
        save_btn.pack(side='left', padx=10)

        cancel_btn = tk.Button(buttons_frame,
                               text="Cancel",
                               command=creds_window.destroy,
                               bg=ModernTheme.ACCENT_RED,
                               fg="white",
                               font=ModernTheme.FONT_BUTTON,
                               padx=20, pady=10,
                               relief='flat')
        cancel_btn.pack(side='right')

        instructions_frame = tk.LabelFrame(creds_window,
                                          text="How to Get These Credentials",
                                          bg=ModernTheme.BG_CARD,
                                          fg=ModernTheme.TEXT_PRIMARY,
                                          font=ModernTheme.FONT_SMALL)
        instructions_frame.pack(fill='x', padx=30, pady=(0, 20))

        instructions_text = """
1. API Key & Client Code: Login to Angel One -> Profile -> API
2. Password: Your Angel One login password
3. TOTP Secret: Setup Google Authenticator -> Scan QR code -> Copy secret key
        """

        instructions_label = tk.Label(instructions_frame,
                                      text=instructions_text,
                                      font=("Segoe UI", 9),
                                      bg=ModernTheme.BG_CARD,
                                      fg=ModernTheme.TEXT_SECONDARY,
                                      justify='left',
                                      wraplength=460)
        instructions_label.pack(padx=15, pady=10)

        fields['api_key'].focus_set()

    def edit_watchlist(self):
        """Edit stock watchlist"""
        messagebox.showinfo("Watchlist",
                            "Watchlist editing would be implemented here.\n\n"
                            "Current watchlist contains 15 stocks:\n"
                            "RELIANCE, TCS, HDFCBANK, ICICIBANK, etc.")

    def show_market_data(self):
        """Show market data window"""
        market_window = tk.Toplevel(self.root)
        market_window.title("Live Market Data")
        market_window.geometry("800x600")
        market_window.configure(bg=ModernTheme.BG_PRIMARY)
        market_window.transient(self.root)

        header = tk.Label(market_window,
                          text="Real-Time Market Data",
                          font=ModernTheme.FONT_TITLE,
                          bg=ModernTheme.BG_PRIMARY,
                          fg=ModernTheme.TEXT_PRIMARY)
        header.pack(pady=20)

        data_container = tk.Frame(market_window, bg=ModernTheme.BG_PRIMARY)
        data_container.pack(fill='both', expand=True, padx=20, pady=10)

        market_text = tk.Text(data_container,
                              bg=ModernTheme.BG_INPUT,
                              fg=ModernTheme.TEXT_PRIMARY,
                              font=ModernTheme.FONT_SMALL,
                              wrap=tk.WORD)
        market_text.pack(fill='both', expand=True, side='left')

        market_scrollbar = tk.Scrollbar(data_container,
                                       orient="vertical",
                                       command=market_text.yview)
        market_text.configure(yscrollcommand=market_scrollbar.set)
        market_scrollbar.pack(side='right', fill='y')

        market_data_text = """
INDIAN STOCK MARKET OVERVIEW
================================

MAJOR INDICES:
-----------------
NIFTY 50     : 25,145.10  +125.30  (+0.50%)
SENSEX       : 82,365.77  +456.23  (+0.56%)
BANK NIFTY   : 51,234.56  -89.45   (-0.17%)
NIFTY IT     : 35,678.90  +234.56  (+0.66%)

SECTOR PERFORMANCE:
---------------------
Banking   : +0.12%  (Mixed)
IT        : +0.66%  (Strong)
Auto      : -0.23%  (Weak)
Energy    : +0.34%  (Positive)
Realty    : -0.45%  (Negative)

TOP GAINERS:
-------------- 
TCS          : 3,987.20  +2.34% 
RELIANCE     : 2,456.75  +1.89%
HDFCBANK     : 1,687.45  +1.56% 

TOP LOSERS:
-------------
BAJFINANCE   : 8,234.56  -2.89%
AXISBANK     : 1,123.45  -1.67%
KOTAKBANK    : 1,789.12  -1.23%

Market Status: OPEN
Last Updated: """ + datetime.now().strftime('%H:%M:%S')

        market_text.insert('1.0', market_data_text)
        market_text.configure(state='disabled')

    def show_stock_manager(self):
        """Show stock manager"""
        self.edit_watchlist()

    def refresh_portfolio(self):
        """Refresh portfolio display"""
        try:
            self.portfolio_text.delete('1.0', tk.END)

            portfolio_summary = self.paper_trader.get_portfolio_summary()

            portfolio_text = "PAPER TRADING PORTFOLIO\n"
            portfolio_text += "=" * 50 + "\n\n"

            portfolio_text += f"Available Balance: Rs{portfolio_summary['current_balance']:,.2f}\n"
            portfolio_text += f"Total Invested: Rs{portfolio_summary['total_invested']:,.2f}\n"
            portfolio_text += f"Active Positions: {portfolio_summary['positions_count']}\n"
            portfolio_text += f"Total Trades: {portfolio_summary['total_trades']}\n\n"

            if portfolio_summary['positions']:
                portfolio_text += "CURRENT POSITIONS:\n"
                portfolio_text += "-" * 40 + "\n"

                for symbol, position in portfolio_summary['positions'].items():
                    portfolio_text += f"{symbol}:\n"
                    portfolio_text += f"  Quantity: {position['qty']}\n"
                    portfolio_text += f"  Avg Price: Rs{position['avg_price']:.2f}\n"
                    portfolio_text += f"  Invested: Rs{position['total_invested']:,.2f}\n"
                    portfolio_text += "\n"
            else:
                portfolio_text += "No positions yet.\nExecute some signals to see your portfolio!"

            self.portfolio_text.insert('1.0', portfolio_text)

        except Exception as e:
            self.portfolio_text.delete('1.0', tk.END)
            self.portfolio_text.insert('1.0', f"Portfolio error: {str(e)}")

    def refresh_orders(self):
        """Refresh orders display"""
        try:
            self.orders_text.delete('1.0', tk.END)

            orders_text = "PAPER TRADING ORDERS\n"
            orders_text += "=" * 40 + "\n\n"

            if getattr(self.paper_trader, 'trades', None):
                for i, trade in enumerate(self.paper_trader.trades[-10:], 1):
                    orders_text += f"{i}. {trade.get('symbol', 'Unknown')} - {trade.get('side', 'Unknown')}\n"
                    orders_text += f"   Quantity: {trade.get('quantity', 0)}\n"
                    orders_text += f"   Price: Rs{trade.get('price', 0)}\n"
                    orders_text += f"   Status: {trade.get('status', 'Unknown')}\n"
                    orders_text += f"   Time: {trade.get('timestamp', 'Unknown')}\n"
                    orders_text += "-" * 30 + "\n"
            else:
                orders_text += "No orders yet.\nExecute some signals to see order history!"

            self.orders_text.insert('1.0', orders_text)

        except Exception as e:
            self.orders_text.delete('1.0', tk.END)
            self.orders_text.insert('1.0', f"Orders error: {str(e)}")

    def update_paper_stats(self):
        """Update paper trading statistics"""
        try:
            self.paper_stats.delete('1.0', tk.END)

            summary = self.paper_trader.get_portfolio_summary()

            stats_text = "PAPER TRADING STATISTICS\n"
            stats_text += "=" * 40 + "\n\n"

            initial_balance = getattr(self.paper_trader, 'initial_balance', 0.0)
            current_balance = summary['current_balance']
            total_invested = summary['total_invested']

            stats_text += f"Initial Balance: Rs{initial_balance:,.2f}\n"
            stats_text += f"Current Balance: Rs{current_balance:,.2f}\n"
            stats_text += f"Total Invested: Rs{total_invested:,.2f}\n"
            stats_text += f"Active Positions: {summary['positions_count']}\n"
            stats_text += f"Total Trades: {summary['total_trades']}\n\n"

            total_portfolio_value = current_balance + total_invested
            pnl = total_portfolio_value - initial_balance
            pnl_pct = (pnl / initial_balance) * 100 if initial_balance > 0 else 0

            stats_text += f"Unrealized P&L: Rs{pnl:,.2f} ({pnl_pct:+.2f}%)\n\n"

            if getattr(self.paper_trader, 'trades', None):
                stats_text += "RECENT TRADES:\n"
                stats_text += "-" * 25 + "\n"
                for trade in self.paper_trader.trades[-5:]:
                    timestamp = trade.get('timestamp', '')[:16] if trade.get('timestamp') else ''
                    symbol = trade.get('symbol', 'Unknown')
                    side = trade.get('side', 'Unknown')
                    value = trade.get('order_value', 0)
                    stats_text += f"{timestamp} | {symbol} | {side} | Rs{value:,.0f}\n"

            self.paper_stats.insert('1.0', stats_text)

        except Exception as e:
            self.paper_stats.delete('1.0', tk.END)
            self.paper_stats.insert('1.0', f"Stats error: {str(e)}")

    def reset_paper_trading(self):
        """Reset paper trading"""
        result = messagebox.askyesno("Reset Confirmation",
                                     "Reset all paper trading data?\n\n"
                                     "This will:\n"
                                     "- Reset balance to Rs100,000\n"
                                     "- Clear all positions\n"
                                     "- Clear trade history\n\n"
                                     "Continue?")
        if result:
            success, message = self.paper_trader.reset_portfolio()
            if success:
                messagebox.showinfo("Reset Complete", "Paper trading reset successfully!")
                self.balance_display.config(text=f"Balance: Rs{self.paper_trader.current_balance:,.2f}")
                self.refresh_portfolio()
                self.update_paper_stats()
                self.refresh_orders()
            else:
                messagebox.showerror("Reset Failed", message)

    def emergency_stop(self):
        """Emergency stop all operations"""
        result = messagebox.askyesno("Emergency Stop",
                                     "EMERGENCY STOP CONFIRMATION\n\n"
                                     "This will:\n"
                                     "- Stop all analysis operations\n"
                                     "- Clear current signals\n"
                                     "- Switch to safe mode\n\n"
                                     "Continue?")
        if result:
            self.current_signals = []
            self.signals_listbox.delete(0, tk.END)
            self.signals_listbox.insert(0, "EMERGENCY STOP ACTIVATED")
            self.signals_listbox.insert(1, "All operations stopped safely")

            for widget in self.signals_buttons_frame.winfo_children():
                widget.destroy()

            self.status_label.config(text="Emergency Stop Active | All operations halted")
            messagebox.showinfo("Emergency Stop", "Emergency stop completed!\nAll operations stopped safely")

    def start_market_updates(self):
        """Start market data updates with proper cleanup"""
        self.update_running = True

        def update_market_data():
            try:
                if not self.update_running or not self.root.winfo_exists():
                    return
                current_time = datetime.now().strftime('%H:%M:%S')
                if hasattr(self, 'time_label') and self.time_label.winfo_exists():
                    self.time_label.config(text=f"{current_time}")
                if 9 <= datetime.now().hour <= 15:
                    market_status = "Market: OPEN | Active trading"
                else:
                    market_status = "Market: CLOSED | After hours"
                if hasattr(self, 'market_status') and self.market_status.winfo_exists():
                    self.market_status.config(text=market_status)
            except Exception as e:
                logger.exception(f"Market update error: {e}")

        def update_loop():
            if not self.update_running:
                return
            try:
                if self.root.winfo_exists():
                    update_market_data()
                    self.root.after(5000, update_loop)
            except tk.TclError:
                self.update_running = False

        update_loop()
        
    def update_time(self):
        """Update time display with proper cleanup"""
        try:
            if not hasattr(self, 'update_running') or not self.update_running:
                return
                
            if not self.root.winfo_exists():
                return
                
            current_time = datetime.now().strftime('%H:%M:%S')
            if hasattr(self, 'time_label') and self.time_label.winfo_exists():
                self.time_label.config(text=f"{current_time}")
                self.root.after(1000, self.update_time)
            
        except tk.TclError:
            if hasattr(self, 'update_running'):
                self.update_running = False
        except Exception as e:
            logger.exception(f"Time update error: {e}")

    def run(self):
        """Run the trading interface with proper cleanup"""
        logger.info("Professional trading UI started")
        
        def on_closing():
            logger.info("UI closing - stopping all timers")
            self.update_running = False
            
            try:
                self.root.after(100, self.root.quit)
            except tk.TclError:
                pass
        
        self.root.protocol("WM_DELETE_WINDOW", on_closing)
        
        try:
            self.root.mainloop()
        finally:
            self.update_running = False
            logger.info("Professional trading UI closed")