#!/usr/bin/env python3
"""FueHub -- run the dev server.

    cd fuehub
    pip install -r requirements.txt
    python seed.py    # optional: demo clinic, staff login, sample leads
    python run.py

Then open http://localhost:5001 and log in (seed.py prints the demo
credentials). See README.md for webhook URLs and what's real vs.
simulated by default.
"""
from __future__ import annotations

import os

from app import create_app

app = create_app()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", "5001"))
    app.run(host="0.0.0.0", port=port, debug=False)
