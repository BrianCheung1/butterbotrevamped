from datetime import datetime, timezone
from statistics import mean

import aiohttp
import discord
from discord import app_commands
from discord.ext import commands

PRICE_URL = "https://prices.runescape.wiki/api/v1/osrs/latest"
TS_5M_URL = (
    "https://prices.runescape.wiki/api/v1/osrs/timeseries?timestep=5m&id={item_id}"
)
TS_24H_URL = (
    "https://prices.runescape.wiki/api/v1/osrs/timeseries?timestep=24h&id={item_id}"
)
MAPPING_URL = "https://prices.runescape.wiki/api/v1/osrs/mapping"


class RefreshView(discord.ui.View):
    def __init__(self, cog, item_id: int, item_name: str, timeout: int = 60):
        super().__init__(timeout=timeout)
        self.cog = cog
        self.item_id = item_id
        self.item_name = item_name

    @discord.ui.button(label="🔄 Refresh", style=discord.ButtonStyle.primary)
    async def refresh_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        await interaction.response.defer()
        embed = await self.cog.build_price_embed(self.item_id, self.item_name)
        await interaction.message.edit(
            embed=embed, view=RefreshView(self.cog, self.item_id, self.item_name)
        )


class PriceChecker(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.items_data = []
        self.name_to_id = {}
        self.id_to_item = {}

    async def load_items(self):
        async with aiohttp.ClientSession() as session:
            async with session.get(MAPPING_URL) as response:
                data = await response.json()
                self.items_data = data
                self.name_to_id = {i["name"].lower(): i["id"] for i in self.items_data}
                self.id_to_item = {i["id"]: i for i in self.items_data}
        print(f"[PriceChecker] Loaded {len(self.items_data)} items for autocomplete.")

    async def fetch_market_data(self, item_id: int):
        async with aiohttp.ClientSession() as session:
            # Latest prices
            async with session.get(f"{PRICE_URL}?id={item_id}") as resp:
                latest_data = await resp.json()
            latest = latest_data.get("data", {}).get(str(item_id), {})

            # 5m timeseries (for day high/low)
            async with session.get(TS_5M_URL.format(item_id=item_id)) as resp:
                ts_5m_data = await resp.json()
            history_5m = ts_5m_data.get("data", [])

            # 24h timeseries (for averages & volumes)
            async with session.get(TS_24H_URL.format(item_id=item_id)) as resp:
                ts_24h_data = await resp.json()
            history_24h = ts_24h_data.get("data", [])

        return latest, history_5m, history_24h

    async def item_autocomplete(self, interaction: discord.Interaction, current: str):
        if not self.items_data:
            return []
        current = current.lower()
        return [
            app_commands.Choice(name=i["name"], value=i["name"])
            for i in self.items_data
            if current in i["name"].lower()
        ][:25]

    async def build_price_embed(self, item_id: int, item_name: str) -> discord.Embed:
        latest, history_5m, history_24h = await self.fetch_market_data(item_id)
        if not latest:
            return discord.Embed(
                title="Error",
                description="Market data not available.",
                color=discord.Color.red(),
            )

        # Determine buy/sell
        high = latest.get("high") or 0
        low = latest.get("low") or 0
        buy_price = min(low, high)
        sell_price = max(low, high)
        margin = (sell_price - buy_price - (sell_price * 0.02)) or 0

        # Profit
        limit = self.id_to_item.get(item_id, {}).get("limit") or 0
        potential_profit = (margin * limit) or 0
        highalch = self.id_to_item.get(item_id, {}).get("highalch") or 0

        # Relative timestamps
        last_buy_ts = latest.get("highTime")
        last_sell_ts = latest.get("lowTime")
        last_buy = f"<t:{int(last_buy_ts)}:R>" if last_buy_ts else "N/A"
        last_sell = f"<t:{int(last_sell_ts)}:R>" if last_sell_ts else "N/A"

        # -----------------------------
        # Day high/low using 5m data
        # -----------------------------
        day_high = max(
            (
                dp.get("avgHighPrice")
                for dp in history_5m
                if dp.get("avgHighPrice") is not None
            ),
            default=0,
        )
        day_low = min(
            (
                dp.get("avgLowPrice")
                for dp in history_5m
                if dp.get("avgLowPrice") is not None
            ),
            default=0,
        )

        # -----------------------------
        # 24h averages using 24h data
        # -----------------------------
        if history_24h:
            last_24h = history_24h[-1]
            avg_low = last_24h.get("avgLowPrice") or 0
            avg_high = last_24h.get("avgHighPrice") or 0
            avg_vol_low = last_24h.get("lowPriceVolume") or 0
            avg_vol_high = last_24h.get("highPriceVolume") or 0
        else:
            avg_low = avg_high = avg_vol_low = avg_vol_high = 0

        embed = discord.Embed(
            title=f"📊 Market Data for {item_name}",
            description=f"**ID:** {item_id}",
            color=discord.Color.green(),
            timestamp=datetime.now(timezone.utc),
        )
        embed.add_field(
            name="💰 Price Information",
            value=(
                f"**Buy Price:** {buy_price:,} gp ({last_buy})\n"
                f"**Sell Price:** {sell_price:,} gp ({last_sell})\n"
                f"**Margin (after 2% tax):** {margin:,.0f} gp\n"
                f"**Potential Profit:** {potential_profit:,.0f} gp\n"
                f"**Day High:** {day_high:,} gp\n"
                f"**Day Low:** {day_low:,} gp\n"
                f"**24h Avg High:** {avg_high:,} gp\n"
                f"**24h Avg Low:** {avg_low:,} gp\n"
                f"**24h Avg Volume:** {(avg_vol_low + avg_vol_high):,}"
            ),
            inline=False,
        )
        embed.add_field(
            name="ℹ️ Additional Info",
            value=f"**Buy Limit:** {limit:,}\n**High Alch:** {highalch:,} gp",
            inline=True,
        )
        embed.set_image(url=f"https://prices.runescape.wiki/img/{item_id}.png")
        return embed

    @app_commands.command(name="osrs-price", description="Get OSRS item market data")
    @app_commands.describe(item="Name of the item")
    @app_commands.autocomplete(item=item_autocomplete)
    @app_commands.allowed_installs(guilds=True, users=True)
    @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
    async def price(self, interaction: discord.Interaction, item: str):
        item_id = self.name_to_id.get(item.lower())
        if not item_id:
            await interaction.response.send_message("Item not found.", ephemeral=True)
            return

        embed = await self.build_price_embed(item_id, item)
        # Increase timeout to 5 minutes (300 seconds)
        view = RefreshView(self, item_id, item, timeout=300)
        await interaction.response.send_message(embed=embed, view=view)


async def setup(bot: commands.Bot):
    cog = PriceChecker(bot)
    await cog.load_items()
    await bot.add_cog(cog)
