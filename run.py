#!/usr/bin/env python3
"""Entry point for kunipy."""

import asyncio
import sys

from src.app import main

if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
