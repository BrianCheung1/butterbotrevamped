async def setup(bot):
    from .balance import setup as balance_setup
    from .gamestats import setup as gamestats_setup
    from .mining import setup as mining_setup

    await balance_setup(bot)
    await gamestats_setup(bot)
    await mining_setup(bot)
