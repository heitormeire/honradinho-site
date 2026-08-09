from __future__ import annotations

import asyncio
import os
import runpy
from unittest.mock import patch

from discord import app_commands


EXPECTED_COMMANDS = 42
EXPECTED_PERSISTENT_VIEWS = 3


async def main() -> None:
    os.environ["DISCORD_TOKEN"] = "validation-only"
    os.environ["HONRADINHO_DB_PATH"] = ":memory:"

    with patch("discord.ext.commands.Bot.run"):
        namespace = runpy.run_path("bot.py")

    bot = namespace["bot"]

    async def fake_sync():
        return []

    bot.tree.sync = fake_sync
    await bot.setup_hook()

    commands = list(bot.tree.walk_commands())
    leaves = [command for command in commands if not isinstance(command, app_commands.Group)]

    if len(leaves) != EXPECTED_COMMANDS:
        raise RuntimeError(f"Expected {EXPECTED_COMMANDS} commands, found {len(leaves)}")
    if len(bot.persistent_views) != EXPECTED_PERSISTENT_VIEWS:
        raise RuntimeError(
            f"Expected {EXPECTED_PERSISTENT_VIEWS} persistent views, found {len(bot.persistent_views)}"
        )

    print(
        f"Bot check OK: discord.py {namespace['discord'].__version__}, "
        f"{len(leaves)} commands and {len(bot.persistent_views)} persistent views."
    )


if __name__ == "__main__":
    asyncio.run(main())
