#!/usr/bin/env python3
"""Revenue engine entrypoint.

    python3 money.py plan --scenarios      what $100k actually demands
    python3 money.py run -f urls.txt       scan, rank, queue, draft
    python3 money.py today                 what to do now

The reasoning behind all of it is in STRATEGY.md.
"""
from __future__ import annotations

import sys

from engine.cli import main

if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
