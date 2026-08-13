"""Run the Actor with ``python -m apify_actor``."""

import asyncio

from .main import main


asyncio.run(main())
