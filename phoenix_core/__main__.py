"""
Entry point for running Phoenix Core as a module.
Usage: python -m phoenix_core
"""
import sys

from phoenix_core.cli import main

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nPhoenix Core stopped by user.")
        sys.exit(0)
    except Exception as e:
        print(f"\nPhoenix Core crashed: {e}")
        sys.exit(1)
