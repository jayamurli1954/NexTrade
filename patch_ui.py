import os
import re

def patch_ui_file(file_path):
    if not os.path.exists(file_path):
        print(f"Error: File {file_path} not found!")
        return

    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()

    # Patch for _build_watchlist_tab: Add scrollbar
    watchlist_tab_pattern = r'def _build_watchlist_tab\(self\):.*?def _build_analyzer_tab\(self\):'
    new_watchlist_tab = r'''def _build_watchlist_tab(self):
        tab = ttk.Frame(self.tabs)
        self.tabs.add(tab, text="Watchlist")

        ttk.Label(tab, text="Watchlist - Monitor Live Prices", style="Header.TLabel").pack(pady=10)

        # Frame for Treeview with scrollbar
        tree_frame = ttk.Frame(tab)
        tree_frame.pack(fill='both', expand=True, padx=10, pady=5)

        v_scroll = ttk.Scrollbar(tree_frame)
        v_scroll.pack(side='right', fill='y')

        self.watchlist_tree = ttk.Treeview(
            tree_frame,
            columns=('symbol', 'ltp'),
            show='headings',
            style="Treeview",
            yscrollcommand=v_scroll.set
        )
        v_scroll.config(command=self.watchlist_tree.yview)
        self.watchlist_tree.pack(side='left', fill='both', expand=True)

        self.watchlist_tree.heading('symbol', text='Symbol')
        self.watchlist_tree.heading('ltp', text='LTP')
        self.watchlist_tree.column('symbol', width=150, anchor='w')
        self.watchlist_tree.column('ltp', width=150, anchor='e')

        # Populate initial watchlist
        for sym in self.watchlist:
            self.watchlist_tree.insert('', 'end', values=(sym, 'N/A'))

        # Bottom buttons
        bottom = ttk.Frame(tab)
        bottom.pack(pady=10)

        self._watchlist_entry = ttk.Entry(bottom, width=20)
        self._watchlist_entry.pack(side='left', padx=5)
        self._watchlist_entry.bind('<Return>', lambda e: self._add_watchlist_item())

        ttk.Button(bottom, text="Add", command=self._add_watchlist_item).pack(side='left', padx=5)
        ttk.Button(bottom, text="Remove", command=self._remove_watchlist_item).pack(side='left', padx=5)
        ttk.Button(bottom, text="Refresh LTP", command=self._update_watchlist_display).pack(side='left', padx=5)

    def _build_analyzer_tab(self):'''

    content = re.sub(watchlist_tab_pattern, new_watchlist_tab, content, flags=re.DOTALL | re.MULTILINE)

    # Patch for _build_paper_trade_tab: Add scrollbar
    paper_trade_pattern = r'def _build_paper_trade_tab\(self\):.*?def _build_logs_tab\(self\):'
    new_paper_trade_tab = r'''def _build_paper_trade_tab(self):
        tab = ttk.Frame(self.tabs)
        self.tabs.add(tab, text="Paper Trade")

        ttk.Label(tab, text="Paper Trading Positions", style="Header.TLabel").pack(pady=10)

        # Frame for Treeview with scrollbar
        tree_frame = ttk.Frame(tab)
        tree_frame.pack(fill='both', expand=True, padx=10, pady=5)

        v_scroll = ttk.Scrollbar(tree_frame)
        v_scroll.pack(side='right', fill='y')

        self._paper_tree = ttk.Treeview(
            tree_frame,
            columns=('symbol', 'side', 'qty', 'entry', 'current', 'pnl', 'pnl_pct', 'entry_time'),
            show='headings',
            style="Treeview",
            yscrollcommand=v_scroll.set
        )
        v_scroll.config(command=self._paper_tree.yview)
        self._paper_tree.pack(side='left', fill='both', expand=True)

        self._paper_tree.heading('symbol', text='Symbol')
        self._paper_tree.heading('side', text='Side')
        self._paper_tree.heading('qty', text='Qty')
        self._paper_tree.heading('entry', text='Entry Price')
        self._paper_tree.heading('current', text='Current Price')
        self._paper_tree.heading('pnl', text='P&L')
        self._paper_tree.heading('pnl_pct', text='P&L %')
        self._paper_tree.heading('entry_time', text='Entry Time')

        self._paper_tree.tag_configure('profit', foreground='green')
        self._paper_tree.tag_configure('loss', foreground='red')

        # Refresh button
        ttk.Button(tab, text="Refresh Positions", command=self._refresh_paper_tab).pack(pady=10)

    def _build_logs_tab(self):'''

    content = re.sub(paper_trade_pattern, new_paper_trade_tab, content, flags=re.DOTALL | re.MULTILINE)

    # Write back the patched content
    with open(file_path, 'w', encoding='utf-8') as f:
        f.write(content)

    print(f"Scrollbar patches applied to Watchlist and Paper Trade tabs in {file_path}. Backup created.")

# Create backup
ui_file = r'c:\Users\Dell\tradingbot_new\ui\professional_trading_ui.py'
if os.path.exists(ui_file):
    backup_file = r'c:\Users\Dell\tradingbot_new\ui\professional_trading_ui.py.backup_scrollbars'
    with open(ui_file, 'rb') as src, open(backup_file, 'wb') as dst:
        dst.write(src.read())

# Apply patch
patch_ui_file(ui_file)