#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Threading Helper for UI - Prevents Freezing
File: ui/threading_helper.py

Purpose: Run blocking operations in background threads
         so the UI remains responsive

Usage:
    from ui.threading_helper import ThreadManager
    
    def fetch_data():
        return expensive_operation()
    
    def on_success(result):
        update_ui_with(result)
    
    def on_error(error):
        show_error_message(error)
    
    ThreadManager.run_async(
        func=fetch_data,
        on_success=on_success,
        on_error=on_error,
        root=self.root
    )
"""

import threading
import logging
import time
from typing import Callable, Optional, Any

logger = logging.getLogger("ThreadingHelper")


class ThreadManager:
    """
    Manages background threads for UI operations
    Prevents UI freezing by running operations in separate threads
    """
    
    _active_threads = []
    _thread_counter = 0
    
    @classmethod
    def run_async(
        cls,
        func: Callable[[], Any],
        on_success: Optional[Callable[[Any], None]] = None,
        on_error: Optional[Callable[[Exception], None]] = None,
        on_finally: Optional[Callable[[], None]] = None,
        root = None
    ) -> threading.Thread:
        """
        Run function in background thread with callbacks
        
        Args:
            func: Function to run in background (takes no args, returns result)
            on_success: Callback when successful (receives result)
            on_error: Callback when error occurs (receives exception)
            on_finally: Callback always executed at end
            root: Tkinter root window for scheduling callbacks on main thread
        
        Returns:
            The started thread object
        
        Example:
            def fetch():
                return api.get_data()
            
            def show_data(data):
                label.config(text=data)
            
            def show_error(err):
                label.config(text=f"Error: {err}")
            
            ThreadManager.run_async(
                func=fetch,
                on_success=show_data,
                on_error=show_error,
                root=window
            )
        """
        
        cls._thread_counter += 1
        thread_id = cls._thread_counter
        
        def wrapper():
            """Wrapper that handles execution and callbacks"""
            result = None
            error = None
            
            try:
                logger.debug(f"[Thread-{thread_id}] Starting {func.__name__}")
                start_time = time.time()
                
                # Execute the function
                result = func()
                
                elapsed = time.time() - start_time
                logger.debug(f"[Thread-{thread_id}] Completed {func.__name__} in {elapsed:.2f}s")
                
                # Schedule success callback on main thread
                if on_success and root:
                    root.after(0, lambda: cls._safe_callback(on_success, result))
                
            except Exception as e:
                logger.error(f"[Thread-{thread_id}] Error in {func.__name__}: {e}", exc_info=True)
                error = e
                
                # Schedule error callback on main thread
                if on_error and root:
                    root.after(0, lambda: cls._safe_callback(on_error, error))
            
            finally:
                # Schedule finally callback on main thread
                if on_finally and root:
                    root.after(0, lambda: cls._safe_callback(on_finally))
                
                # Remove from active threads
                try:
                    cls._active_threads.remove(threading.current_thread())
                except ValueError:
                    pass
        
        # Create and start thread
        thread = threading.Thread(
            target=wrapper,
            daemon=True,
            name=f"AsyncOp-{thread_id}-{func.__name__}"
        )
        
        cls._active_threads.append(thread)
        thread.start()
        
        logger.debug(f"[Thread-{thread_id}] Started background thread: {thread.name}")
        logger.debug(f"Active threads: {len(cls._active_threads)}")
        
        return thread
    
    @staticmethod
    def _safe_callback(callback: Callable, *args):
        """
        Safely execute callback with error handling
        """
        try:
            if args:
                callback(*args)
            else:
                callback()
        except Exception as e:
            logger.error(f"Callback error: {e}", exc_info=True)
    
    @classmethod
    def wait_all(cls, timeout: float = 5.0) -> bool:
        """
        Wait for all active threads to complete
        
        Args:
            timeout: Maximum time to wait in seconds
        
        Returns:
            True if all threads completed, False if timeout
        """
        start_time = time.time()
        
        while cls._active_threads and (time.time() - start_time) < timeout:
            for thread in cls._active_threads[:]:
                if not thread.is_alive():
                    try:
                        cls._active_threads.remove(thread)
                    except ValueError:
                        pass
            
            if cls._active_threads:
                time.sleep(0.1)
        
        remaining = len(cls._active_threads)
        if remaining > 0:
            logger.warning(f"Timeout: {remaining} threads still active")
            return False
        
        return True
    
    @classmethod
    def get_active_count(cls) -> int:
        """Get count of active background threads"""
        # Clean up dead threads
        cls._active_threads = [t for t in cls._active_threads if t.is_alive()]
        return len(cls._active_threads)
    
    @classmethod
    def is_busy(cls) -> bool:
        """Check if any background operations are running"""
        return cls.get_active_count() > 0


# Convenience decorator for async execution
def async_operation(root_attr='root'):
    """
    Decorator to make a method run asynchronously
    
    Usage:
        class MyUI:
            def __init__(self):
                self.root = tk.Tk()
            
            @async_operation()
            def fetch_data(self):
                return expensive_api_call()
    """
    def decorator(func):
        def wrapper(self, *args, **kwargs):
            root = getattr(self, root_attr, None)
            
            def execute():
                return func(self, *args, **kwargs)
            
            ThreadManager.run_async(func=execute, root=root)
        
        return wrapper
    return decorator


if __name__ == "__main__":
    # Self-test
    import tkinter as tk
    
    print("Testing ThreadManager...")
    
    root = tk.Tk()
    root.withdraw()
    
    results = []
    
    def slow_operation():
        time.sleep(1)
        return "Operation completed"
    
    def on_success(result):
        results.append(result)
        print(f"✅ Success: {result}")
    
    def on_error(error):
        print(f"❌ Error: {error}")
    
    # Test 1: Normal execution
    print("\nTest 1: Normal execution")
    ThreadManager.run_async(
        func=slow_operation,
        on_success=on_success,
        root=root
    )
    
    # Test 2: Error handling
    print("\nTest 2: Error handling")
    def failing_operation():
        raise ValueError("Test error")
    
    ThreadManager.run_async(
        func=failing_operation,
        on_error=lambda e: print(f"✅ Caught error: {e}"),
        root=root
    )
    
    # Wait for completion
    print("\nWaiting for threads...")
    ThreadManager.wait_all(timeout=3.0)
    
    print(f"\n✅ Tests complete. Active threads: {ThreadManager.get_active_count()}")
    print(f"Results collected: {results}")
    
    root.destroy()