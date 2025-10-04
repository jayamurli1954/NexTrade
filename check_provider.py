"""Check what class exists in angel_provider.py"""
import inspect

try:
    from data_provider import angel_provider
    
    print("="*60)
    print("Classes in angel_provider.py:")
    print("="*60)
    
    for name, obj in inspect.getmembers(angel_provider):
        if inspect.isclass(obj) and obj.__module__ == 'data_provider.angel_provider':
            print(f"\n  Class: {name}")
            
            # Show methods
            methods = [m for m in dir(obj) if not m.startswith('_')]
            if methods:
                print(f"  Methods: {', '.join(methods[:5])}...")
    
    print("\n" + "="*60)
    
except Exception as e:
    print(f"Error: {e}")