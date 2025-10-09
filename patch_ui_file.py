import os
import re
import time as time_module  # For rate limiting

def patch_ui_file(file_path):
    if not os.path.exists(file_path):
        print(f"Error: File {file_path} not found!")
        return

    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()

    # Ensure imports for threading and queue are present (if not already from previous patches)
    if 'import threading' not in content or 'import queue' not in content:
        import_section = r'import tkinter as tk\nfrom tkinter import ttk, messagebox, simpledialog\nimport json\nimport os\n'
        new_imports = r'import tkinter as tk\nfrom tkinter import ttk, messagebox, simpledialog\nimport json\nimport os\nimport threading\nimport queue\n'
        content = content.replace(import_section, new_imports, 1)

    # Patch for Analyzer tab: Thread the analysis to prevent freezing
    # Adjust pattern to match _run_premarket_analysis or similar; based on your code
    analyzer_pattern = r'def _run_premarket_analysis\(self\):.*?def _execute_selected_trade\(self\):'
    new_analyzer = r'''def _run_premarket_analysis(self):
        def background_analysis(q):
            try:
                signals = self.analyzer.run_premarket_analysis(self.watchlist)
                q.put(signals)
            except Exception as e:
                q.put(f"Error during analysis: {e}")

        def update_analyzer_ui(result):
            self._analysis_tree.delete(*self._analysis_tree.get_children())
            if isinstance(result, str):  # Error case
                messagebox.showerror("Analysis Error", result)
                return
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            analyzed_count = result['total_symbols_analyzed']
            signals_found = result['signals_found']
            high_conf = result['high_confidence_signals']
            summary = f"Timestamp: {timestamp} | Analyzed: {analyzed_count} | Signals Found: {signals_found} | High Confidence: {high_conf}"
            q.put(('summary', summary))  # Assuming you have a label for summary; adjust if needed
            for sig in result['signals']:
                qty = self._calculate_quantity(sig['price'])
                self._analysis_tree.insert('', 'end', values=(
                    sig['symbol'],
                    sig['action'],
                    f"{sig['confidence']:.2%}",
                    f"₹{sig['price']:.2f}",
                    qty,
                    f"₹{sig['target']:.2f}",
                    f"₹{sig['stop_loss']:.2f}",
                    sig['reason']
                ))

        q = queue.Queue()
        threading.Thread(target=background_analysis, args=(q,)).start()
        self.root.after(100, lambda q=q: update_analyzer_ui(q.get()))

    def _execute_selected_trade(self):'''

    content = re.sub(analyzer_pattern, new_analyzer, content, flags=re.DOTALL | re.MULTILINE)

    # Write UI patch
    with open(file_path, 'w', encoding='utf-8') as f:
        f.write(content)

    print(f"Analyzer freeze patch applied to {file_path}.")

def patch_provider(provider_path):
    if not os.path.exists(provider_path):
        print(f"Error: File {provider_path} not found!")
        return

    with open(provider_path, 'r', encoding='utf-8') as f:
        prov_content = f.read()

    # Patch for get_historical: Add rate limiting delay
    historical_pattern = r'def get_historical\(self, symbol, exchange="NSE", period_days=50, interval="ONE_MINUTE"\):.*?return df'
    new_historical = r'''def get_historical(self, symbol, exchange="NSE", period_days=50, interval="ONE_MINUTE"):
        if self.paper_mode or not self.is_connected:
            return self._generate_fallback_historical(symbol, period_days)

        try:
            token = self.get_token(symbol, exchange)
            if not token:
                return self._generate_fallback_historical(symbol, period_days)

            fromdate = (datetime.now() - timedelta(days=period_days)).strftime('%Y-%m-%d %H:%M')
            todate = datetime.now().strftime('%Y-%m-%d %H:%M')
            params = {
                'exchange': exchange,
                'symboltoken': token,
                'interval': interval,
                'fromdate': fromdate,
                'todate': todate
            }
            time_module.sleep(0.5)  # Increased delay to 500ms for rate limiting
            data = self.smart_api.getCandleData(params)
            if data.get('status'):
                df = pd.DataFrame(
                    data['data'],
                    columns=['timestamp', 'open', 'high', 'low', 'close', 'volume']
                )
                df['timestamp'] = pd.to_datetime(df['timestamp'])
                df.set_index('timestamp', inplace=True)
                return df
        except Exception as e:
            logger.error(f"Historical data error for {symbol}: {e}")

        return self._generate_fallback_historical(symbol, period_days)'''

    prov_content = re.sub(historical_pattern, new_historical, prov_content, flags=re.DOTALL | re.MULTILINE)

    with open(provider_path, 'w', encoding='utf-8') as f:
        f.write(prov_content)

    print(f"Rate limiting (0.5s delay) added to get_historical in {provider_path}.")

# Create UI backup
ui_file = r'c:\Users\Dell\tradingbot_new\ui\professional_trading_ui.py'
if os.path.exists(ui_file):
    backup_ui = r'c:\Users\Dell\tradingbot_new\ui\professional_trading_ui.py.backup_final_analyzer'
    with open(ui_file, 'rb') as src, open(backup_ui, 'wb') as dst:
        dst.write(src.read())

# Apply UI patch
patch_ui_file(ui_file)

# Create provider backup and apply patch
provider_file = r'c:\Users\Dell\tradingbot_new\data_provider\angel_provider.py'
if os.path.exists(provider_file):
    backup_provider = r'c:\Users\Dell\tradingbot_new\data_provider\angel_provider.py.backup_rate_05s'
    with open(provider_file, 'rb') as src, open(backup_provider, 'wb') as dst:
        dst.write(src.read())
    patch_provider(provider_file)
else:
    print("Provider file not found; rate limit patch skipped.")