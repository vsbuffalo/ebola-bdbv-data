"""Importable modules shared across the scripts.

Everything directly under `scripts/` is a command-line entry point, invoked by a
workflow rule as `python scripts/<name>.py --args`. Everything in here is
imported, never run. Keeping the distinction structural rather than a naming
hint means it cannot quietly erode: a module that grows a `__main__` belongs one
level up, and shared code buried inside a CLI script belongs here.

Scripts run with `scripts/` as sys.path[0], so these import as `lib.<module>`.
"""
