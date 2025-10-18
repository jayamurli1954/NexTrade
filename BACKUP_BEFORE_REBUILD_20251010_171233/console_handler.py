"""
COMPLETE SCRIPT - console_handler.py
Enhanced Console and File Logging System
Save this as: c:/Users/Dell/tradingbot_new/console_handler.py

NO PATCHING REQUIRED - This is the complete file
"""

import logging
import sys
from datetime import datetime
from queue import Queue, Empty
import threading

class ConsoleLogHandler(logging.Handler):
    """Custom handler that sends logs to both console and GUI"""
    
    def __init__(self, console_widget=None, max_lines=1000):
        super().__init__()
        self.console_widget = console_widget
        self.max_lines = max_lines
        self.log_queue = Queue()
        self.running = True
        
        # Start background thread to process logs
        self.thread = threading.Thread(target=self._process_logs, daemon=True)
        self.thread.start()
    
    def emit(self, record):
        """Called when a log record is emitted"""
        try:
            msg = self.format(record)
            
            # Add to queue for GUI processing
            if self.console_widget:
                self.log_queue.put(msg)
            
            # Also print to console
            print(msg, flush=True)
            
        except Exception:
            self.handleError(record)
    
    def _process_logs(self):
        """Background thread to update GUI console"""
        while self.running:
            try:
                msg = self.log_queue.get(timeout=0.1)
                if self.console_widget:
                    self._update_console(msg)
            except Empty:
                continue
            except Exception as e:
                print(f"Error processing log: {e}")
    
    def _update_console(self, msg):
        """Update GUI console widget"""
        try:
            # Add timestamp color coding based on log level
            if 'ERROR' in msg:
                color = 'red'
            elif 'WARNING' in msg:
                color = 'orange'
            elif 'INFO' in msg and '✓' in msg:
                color = 'green'
            else:
                color = 'white'
            
            # Add to console widget (assuming Qt or similar)
            if hasattr(self.console_widget, 'append'):
                self.console_widget.append(msg)
            elif hasattr(self.console_widget, 'insert'):
                self.console_widget.insert('end', msg + '\n')
            
            # Trim old lines if too many
            if hasattr(self.console_widget, 'get'):
                lines = self.console_widget.get('1.0', 'end').split('\n')
                if len(lines) > self.max_lines:
                    self.console_widget.delete('1.0', f'{len(lines) - self.max_lines}.0')
        except Exception as e:
            print(f"Error updating console widget: {e}")
    
    def stop(self):
        """Stop the background thread"""
        self.running = False
        if self.thread.is_alive():
            self.thread.join(timeout=1)


def setup_enhanced_logging(console_widget=None, log_level=logging.INFO):
    """
    Setup enhanced logging system with both file and console output
    
    Args:
        console_widget: GUI widget to display logs (optional)
        log_level: Logging level (default: INFO)
    """
    
    # Create logs directory
    import os
    today = datetime.now().strftime('%Y-%m-%d')
    log_dir = os.path.join('logs', today)
    os.makedirs(log_dir, exist_ok=True)
    
    # Get root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)
    
    # Remove existing handlers
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)
    
    # Create formatters
    detailed_formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    simple_formatter = logging.Formatter(
        '%(asctime)s | %(levelname)-8s | %(message)s',
        datefmt='%H:%M:%S'
    )
    
    # File handler - detailed logs
    file_handler = logging.FileHandler(
        os.path.join(log_dir, 'app.log'),
        encoding='utf-8'
    )
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(detailed_formatter)
    root_logger.addHandler(file_handler)
    
    # Console handler - mirrors command prompt
    console_handler = ConsoleLogHandler(console_widget)
    console_handler.setLevel(log_level)
    console_handler.setFormatter(simple_formatter)
    root_logger.addHandler(console_handler)
    
    # Suppress noisy third-party loggers
    logging.getLogger('urllib3').setLevel(logging.WARNING)
    logging.getLogger('SmartApi').setLevel(logging.WARNING)
    
    logger = logging.getLogger(__name__)
    logger.info("=" * 80)
    logger.info("Enhanced logging initialized")
    logger.info(f"Log file: {log_dir}/app.log")
    logger.info("=" * 80)
    
    return console_handler


class TradingBotLogger:
    """Convenience wrapper for trading bot logging"""
    
    def __init__(self, name='TradingBot'):
        self.logger = logging.getLogger(name)
    
    def trade_executed(self, action, symbol, quantity, price, order_id):
        """Log trade execution"""
        self.logger.info(
            f"✓ TRADE EXECUTED: {action} {quantity} {symbol} @ ₹{price:.2f} "
            f"[Order: {order_id}]"
        )
    
    def signal_generated(self, symbol, signal_type, reason):
        """Log signal generation"""
        emoji = "📈" if signal_type == "BUY" else "📉" if signal_type == "SELL" else "⏸️"
        self.logger.info(f"{emoji} SIGNAL: {signal_type} {symbol} - {reason}")
    
    def api_error(self, operation, error):
        """Log API errors"""
        self.logger.error(f"API Error [{operation}]: {error}")
    
    def connection_status(self, status, details=''):
        """Log connection status"""
        emoji = "✓" if status == "connected" else "✗"
        self.logger.info(f"{emoji} Connection: {status.upper()} {details}")
    
    def portfolio_update(self, holdings_count, total_value, available_funds):
        """Log portfolio update"""
        self.logger.info(
            f"📊 Portfolio: {holdings_count} holdings | "
            f"Value: ₹{total_value:,.2f} | "
            f"Available: ₹{available_funds:,.2f}"
        )
    
    def pnl_update(self, symbol, pnl, pnl_percent):
        """Log P&L update"""
        emoji = "🟢" if pnl >= 0 else "🔴"
        self.logger.info(
            f"{emoji} P&L [{symbol}]: ₹{pnl:.2f} ({pnl_percent:+.2f}%)"
        )
    
    def system_status(self, status, message):
        """Log system status"""
        self.logger.info(f"⚙️  System: {status} - {message}")
    
    def error(self, message):
        """Log error"""
        self.logger.error(f"❌ {message}")
    
    def warning(self, message):
        """Log warning"""
        self.logger.warning(f"⚠️  {message}")
    
    def debug(self, message):
        """Log debug info"""
        self.logger.debug(message)