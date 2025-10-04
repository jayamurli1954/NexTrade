#!/usr/bin/env python3
"""
Patched main.py for TradingBot
- Uses enhanced.main_enhanced.EnhancedTradingBot for pre-market analysis
- Runs analysis in a background thread and caches results for a TTL (default 300s)
- Provides a simple Tkinter GUI with a Pre-Market button and a scrollable results area
- Adds a yfinance fallback price refresher for UI LTP display
- Writes logs to logs/ and snapshot to data/premarket_snapshot.json
USAGE:
1. BACKUP your existing main.py (copy it before replacing)
2. Place this file as main.py in your project root:
   C:\Users\Muralidhar\Desktop\TradingBot\main.py
3. Activate your tradingbot environment and run:
   python main.py
Notes:
- This file expects an 'enhanced' package/folder with main_enhanced.py and its EnhancedTradingBot class
- It does not change your Angel credentials; EnhancedTradingBot will use config/credentials.json or env vars if available
- If you prefer, change constants below to adjust TTL and UI behavior
"""
import os, sys, json, threading, time, traceback, logging
from datetime import datetime, timedelta
from pathlib import Path
import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext

# --- Configuration ---
PROJECT_ROOT = Path(__file__).resolve().parent
LOGS_DIR = PROJECT_ROOT / "logs"
DATA_DIR = PROJECT_ROOT / "data"
SNAPSHOT_FILE = DATA_DIR / "premarket_snapshot.json"
SNAPSHOT_TTL = 300  # seconds (5 minutes)
ANALYZER_MODULE = "enhanced.main_enhanced"
ANALYZER_CLASS = "EnhancedTradingBot"
PRICE_REFRESH_INTERVAL = 10  # seconds for yfinance fallback refresh

# Ensure folders exist
LOGS_DIR.mkdir(parents=True, exist_ok=True)
DATA_DIR.mkdir(parents=True, exist_ok=True)

# --- Logging setup ---
logfile = LOGS_DIR / f"trading_bot_{datetime.now().strftime('%Y%m%d')}.log"
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.FileHandler(logfile, encoding='utf-8'), logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger("TradingBot")

# --- Import analyzer safely ---
EnhancedTradingBot = None
try:
    import importlib
    mod = importlib.import_module(ANALYZER_MODULE)
    EnhancedTradingBot = getattr(mod, ANALYZER_CLASS, None)
    logger.info("Loaded enhanced analyzer module: %s", ANALYZER_MODULE)
except Exception as e:
    logger.exception("Failed to import enhanced analyzer - falling back to dummy analyzer: %s", e)
    EnhancedTradingBot = None

# --- Snapshot utilities ---
snapshot_lock = threading.Lock()

def snapshot_is_valid():
    try:
        if not SNAPSHOT_FILE.exists():
            return False
        with SNAPSHOT_FILE.open("r", encoding="utf-8") as fh:
            meta = json.load(fh)
        gen = meta.get("_generated_at")
        if not gen:
            return False
        ts = datetime.fromisoformat(gen)
        return (datetime.utcnow() - ts).total_seconds() < SNAPSHOT_TTL
    except Exception:
        return False

def save_snapshot(signals, raw=None):
    payload = {
        "_generated_at": datetime.utcnow().isoformat(),
        "signals": signals,
        "raw": raw or {},
    }
    with SNAPSHOT_FILE.open("w", encoding="utf-8") as fh:
        json.dump(payload, fh, default=str, indent=2)

def load_snapshot():
    if not SNAPSHOT_FILE.exists():
        return None
    try:
        with SNAPSHOT_FILE.open("r", encoding="utf-8") as fh:
            return json.load(fh)
    except Exception:
        return None

# --- Analyzer runner ---
def run_premarket_analysis(force=False):
    """
    Runs enhanced analyzer if available; caches snapshot on disk for SNAPSHOT_TTL seconds.
    Returns signals list.
    """
    with snapshot_lock:
        if not force and snapshot_is_valid():
            logger.info("Using cached premarket snapshot")
            data = load_snapshot()
            return data.get("signals", []) if data else []
        logger.info("Running premarket analysis (force=%s)...", force)
        signals = []
        raw = {}
        try:
            if EnhancedTradingBot is None:
                logger.warning("No enhanced analyzer available. Returning empty signals.")
                signals = []
            else:
                analyzer = EnhancedTradingBot()
                # analyzer.run_analysis() expected to return a list of signals (dicts)
                signals = analyzer.run_analysis() or []
                raw['_analyzer_version'] = getattr(analyzer, '__version__', None)
            save_snapshot(signals, raw)
            logger.info("Premarket analysis complete, found %d signals", len(signals))
        except Exception as e:
            logger.exception("Premarket analysis failed: %s", e)
            # if analysis fails but snapshot exists, return it; else return empty list
            if snapshot_is_valid():
                data = load_snapshot()
                return data.get("signals", []) if data else []
            signals = []
            save_snapshot(signals, raw)
        return signals

# --- Simple yfinance LTP refresher for UI fallback (non-blocking) ---
def start_price_refresher(app):
    try:
        import yfinance as yf
    except Exception:
        logger.warning("yfinance not installed; price refresher disabled")
        return

    def refresher():
        while True:
            try:
                symbols = app.get_monitored_symbols()
                if symbols:
                    for sym in symbols:
                        ticker = sym if sym.upper().endswith(".NS") else f"{sym}.NS"
                        try:
                            t = yf.Ticker(ticker)
                            hist = t.history(period="1d", interval="1m")
                            last = None
                            if hist is not None and not hist.empty:
                                last = float(hist['Close'].iloc[-1])
                            app.update_ltp(sym, last)
                        except Exception as e:
                            # ignore per-symbol failures
                            logger.debug("yfinance error for %s: %s", sym, e)
                time.sleep(max(PRICE_REFRESH_INTERVAL, 5))
            except Exception as e:
                logger.exception("Price refresher loop exception: %s", e)
                time.sleep(5)
    t = threading.Thread(target=refresher, daemon=True)
    t.start()

# --- GUI components ---
class ScrollableFrame(tk.Frame):
    def __init__(self, parent, *args, **kwargs):
        super().__init__(parent, *args, **kwargs)
        self.canvas = tk.Canvas(self, borderwidth=0, highlightthickness=0)
        self.vscroll = tk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=self.vscroll.set)
        self.inner = tk.Frame(self.canvas)
        self.inner_id = self.canvas.create_window((0,0), window=self.inner, anchor='nw')
        self.canvas.pack(side="left", fill="both", expand=True)
        self.vscroll.pack(side="right", fill="y")
        self.inner.bind("<Configure>", self._on_frame_config)
        self.canvas.bind('<Configure>', self._on_canvas_config)
        self.canvas.bind_all("<MouseWheel>", self._on_mousewheel)

    def _on_frame_config(self, event):
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))

    def _on_canvas_config(self, event):
        canvas_width = event.width
        self.canvas.itemconfig(self.inner_id, width=canvas_width)

    def _on_mousewheel(self, event):
        self.canvas.yview_scroll(int(-1*(event.delta/120)), "units")

class TradingBotUI:
    def __init__(self, root):
        self.root = root
        root.title("Angel One Trading Bot - Dashboard (Patched)")
        root.geometry("1000x700")
        self.signals = []
        self.ltp_map = {}  # symbol -> latest LTP for display
        # top frame: controls
        ctrl = tk.Frame(root, pady=8)
        ctrl.pack(fill='x')
        self.premarket_button = tk.Button(ctrl, text="Pre-Market Analysis", bg="#ffd24d", command=self.on_premarket_clicked)
        self.premarket_button.pack(side='left', padx=8)
        self.force_button = tk.Button(ctrl, text="Force Refresh", bg="#ff6b6b", command=lambda: self.on_premarket_clicked(force=True))
        self.force_button.pack(side='left', padx=4)
        tk.Button(ctrl, text="Export Signals", command=self.export_signals).pack(side='left', padx=4)
        self.snapshot_label = tk.Label(ctrl, text="No snapshot", anchor='w')
        self.snapshot_label.pack(side='right', padx=8)
        # results area
        self.results_frame = ScrollableFrame(root)
        self.results_frame.pack(fill='both', expand=True, padx=8, pady=8)
        # status bar
        self.status = tk.Label(root, text="Ready", bd=1, relief='sunken', anchor='w')
        self.status.pack(side='bottom', fill='x')
        # initial population
        self.refresh_ui_from_snapshot()

    def set_status(self, txt):
        self.status.config(text=txt)
        logger.info("UI status: %s", txt)

    def get_monitored_symbols(self):
        # read from your config or a default list; try to load from enhanced module if possible
        try:
            cfg_file = PROJECT_ROOT / "config" / "watchlist.json"
            if cfg_file.exists():
                data = json.loads(cfg_file.read_text(encoding='utf-8'))
                if isinstance(data, list) and data:
                    return data
            # fallback: load top 25 from enhanced if available
            if EnhancedTradingBot:
                try:
                    dummy = EnhancedTradingBot()
                    return getattr(dummy, "stock_list", [])
                except Exception:
                    return []
        except Exception:
            logger.exception("get_monitored_symbols failed")
        return []

    def update_ltp(self, symbol, ltp):
        # update LTP mapping and refresh any displayed rows that show price
        if ltp is None:
            return
        self.ltp_map[symbol] = ltp
        # try update label in UI if present
        for child in self.results_frame.inner.winfo_children():
            meta = getattr(child, "_meta", None)
            if meta and meta.get("symbol") == symbol:
                price_label = getattr(child, "_price_label", None)
                if price_label:
                    price_label.config(text=f"Price: ₹{ltp:.2f}")

    def clear_results_ui(self):
        for c in self.results_frame.inner.winfo_children():
            c.destroy()

    def show_details(self, sig):
        # simple detail modal
        d = tk.Toplevel(self.root)
        d.title(f"Details — {sig.get('symbol')}")
        txt = scrolledtext.ScrolledText(d, width=80, height=20)
        txt.pack(fill='both', expand=True)
        txt.insert('end', json.dumps(sig, indent=2, default=str))
        txt.config(state='disabled')

    def refresh_ui_from_snapshot(self):
        self.clear_results_ui()
        data = load_snapshot()
        if not data:
            self.snapshot_label.config(text="No snapshot available")
            return
        gen = data.get("_generated_at")
        signals = data.get("signals", [])
        self.signals = signals
        self.snapshot_label.config(text=f"Snapshot: {gen} (valid {SNAPSHOT_TTL//60}m)")
        # display signals
        if not signals:
            lbl = tk.Label(self.results_frame.inner, text="No high-confidence signals found", font=('Arial', 14))
            lbl.pack(pady=8)
            return
        for idx, s in enumerate(signals, start=1):
            row = tk.Frame(self.results_frame.inner, bd=1, relief='ridge', padx=8, pady=6)
            row.pack(fill='x', pady=6, padx=4)
            row._meta = {"symbol": s.get("symbol")}
            left = tk.Frame(row)
            left.pack(side='left', fill='x', expand=True)
            tk.Label(left, text=f"{idx}. {s.get('symbol')}", font=('Arial', 12, 'bold')).pack(anchor='w')
            tk.Label(left, text=f"{s.get('signal')} Signal | Confidence: {s.get('confidence')}", fg="green" if s.get('signal')=='BUY' else 'red').pack(anchor='w')
            tk.Label(left, text=f"CMP: ₹{s.get('current_price',0):.2f} | RSI: {s.get('rsi',0):.2f} | Data: {s.get('data_source','-')}", font=('Arial',10)).pack(anchor='w')
            # price label stored for updates
            price_label = tk.Label(left, text=f"Price: ₹{self.ltp_map.get(s.get('symbol'), s.get('current_price',0)):.2f}", font=('Arial',10,'italic'))
            price_label.pack(anchor='w')
            row._price_label = price_label
            # right side controls
            right = tk.Frame(row)
            right.pack(side='right')
            tk.Button(right, text="Details", command=lambda ss=s: self.show_details(ss)).pack(padx=6, pady=2)
            tk.Button(right, text="Buy", command=lambda ss=s: messagebox.showinfo("Buy", f"PLACE BUY for {ss.get('symbol')} (paper mode)")).pack(padx=6, pady=2)
            tk.Button(right, text="Sell", command=lambda ss=s: messagebox.showinfo("Sell", f"PLACE SELL for {ss.get('symbol')} (paper mode)")).pack(padx=6, pady=2)

    def export_signals(self):
        data = load_snapshot()
        if not data:
            messagebox.showinfo("Export", "No snapshot to export")
            return
        fn = DATA_DIR / f"premarket_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with fn.open("w", encoding="utf-8") as fh:
            json.dump(data, fh, default=str, indent=2)
        messagebox.showinfo("Export", f"Snapshot exported to {fn}")

    def on_premarket_clicked(self, force=False):
        # disable to prevent spam
        self.premarket_button.config(state='disabled')
        self.force_button.config(state='disabled')
        self.set_status("Running premarket analysis...")
        def worker():
            try:
                signals = run_premarket_analysis(force=force)
                # update UI in main thread
                self.root.after(0, lambda: self.refresh_ui_from_snapshot())
                self.root.after(0, lambda: self.set_status(f"Premarket complete — {len(signals)} signals"))
            except Exception as e:
                logger.exception("Premarket worker error: %s", e)
                self.root.after(0, lambda: messagebox.showerror("Analysis Error", str(e)))
            finally:
                # keep disabled until TTL expires automatically; enable a small moment to allow force
                def reenable():
                    self.premarket_button.config(state='normal')
                    self.force_button.config(state='normal')
                self.root.after(1000, reenable)
        t = threading.Thread(target=worker, daemon=True)
        t.start()

# --- Main entrypoint ---
def main():
    # create GUI
    root = tk.Tk()
    app = TradingBotUI(root)
    # start price refresher (yfinance fallback)
    start_price_refresher(app)
    # start the tkinter main loop
    root.mainloop()

if __name__ == "__main__":
    main()
