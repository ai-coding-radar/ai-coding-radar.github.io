"""Apify runtime entry point."""

from __future__ import annotations

from .core import collect_releases


async def run_actor(actor: object) -> None:
    actor_input = await actor.get_input() or {}
    if not isinstance(actor_input, dict):
        raise ValueError("Actor input must be an object")

    releases = collect_releases(
        tools=actor_input.get("tools"),
        limit_per_tool=actor_input.get("limitPerTool", 5),
    )
    charge = await actor.push_data(releases)
    if charge.charged_count < len(releases):
        actor.log.info("Charge limit reached; returned only charged records")
    await actor.set_status_message(
        f"Published {charge.charged_count} verified stable release records"
    )


async def main() -> None:
    from apify import Actor

    async with Actor:
        await run_actor(Actor)
