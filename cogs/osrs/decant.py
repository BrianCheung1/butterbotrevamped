import json
import os
import time

import aiohttp
import discord
from discord import app_commands
from discord.ext import commands

PRICE_URL = "https://prices.runescape.wiki/api/v1/osrs/latest"
TS_URL = "https://prices.runescape.wiki/api/v1/osrs/timeseries"
MIN_PROFIT = 125_000
MIN_GE_LIMIT = 2000

# Resolve path to JSON
project_root = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
json_path = os.path.join(project_root, "constants", "potion_limits.json")
with open(json_path, "r") as f:
    POTIONS = json.load(f)


class DecantPaginator(discord.ui.View):
    def __init__(self, pages, used_cache: bool, cache_time: int):
        super().__init__(timeout=180)
        self.pages = pages
        self.current = 0
        self.used_cache = used_cache
        self.cache_time = cache_time

    def create_embed(self):
        data = self.pages[self.current]
        embed = discord.Embed(
            title=f"💊 {data['potion']} - **Avg Profit:** `{int(data['avg_profit']):,}` gp "
            f"({self.current + 1}/{len(self.pages)})",
            color=discord.Color.green(),
        )

        embed.add_field(
            name="💰 Prices",
            value=(
                f"**3-dose:**\n"
                f"Low `{data['low3']:,}` <t:{data['low3_time']}:R>\n"
                f"High `{data['high3']:,}` <t:{data['high3_time']}:R>\n"
                f"**4-dose:**\n"
                f"Low `{data['low4']:,}` <t:{data['low4_time']}:R>\n"
                f"High `{data['high4']:,}` <t:{data['high4_time']}:R>"
            ),
            inline=False,
        )

        embed.add_field(
            name="📊 Profits",
            value="\n".join([f"{k}: `{int(v):,}`" for k, v in data["profits"].items()])
            + f"\n**Avg Profit:** `{int(data['avg_profit']):,}` gp\n"
            f"**ROI:** `{data['roi_pct']:.2f}%`\n"
            f"**Capital Needed:** `{data['capital_required']:,} gp`",
            inline=False,
        )

        embed.add_field(
            name="📈 Market Data (24h)",
            value=(
                f"**3-dose:**\n"
                f"Avg Low: `{data.get('avg_low_ts_3', 0):,}` (Vol: `{data.get('avg_low_vol_3', 0):,}`)\n"
                f"Avg High: `{data.get('avg_high_ts_3', 0):,}` (Vol: `{data.get('avg_high_vol_3', 0):,}`)\n"
                f"**4-dose:**\n"
                f"Avg Low: `{data.get('avg_low_ts_4', 0):,}` (Vol: `{data.get('avg_low_vol_4', 0):,}`)\n"
                f"Avg High: `{data.get('avg_high_ts_4', 0):,}` (Vol: `{data.get('avg_high_vol_4', 0):,}`)\n"
                f"Spread (4-dose): `{data.get('spread_pct', 0):.2f}%`\n"
                f"GE Limit: `{data['ge_limit']:,}`"
            ),
            inline=False,
        )

        embed.set_image(
            url=f"https://prices.runescape.wiki/osrs/item/{data['item_id']}.png"
        )

        embed.add_field(
            name="⏱️ Data Age",
            value=f"<t:{int(self.cache_time)}:R>",
            inline=False,
        )

        return embed

    @discord.ui.button(label="⬅️", style=discord.ButtonStyle.secondary)
    async def previous(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        self.current = (self.current - 1) % len(self.pages)
        await interaction.response.edit_message(embed=self.create_embed(), view=self)

    @discord.ui.button(label="➡️", style=discord.ButtonStyle.secondary)
    async def next(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.current = (self.current + 1) % len(self.pages)
        await interaction.response.edit_message(embed=self.create_embed(), view=self)


class DecantChecker(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self._price_cache = {"timestamp": 0, "data": None}
        self._ts_cache = {"timestamp": 0, "data": None}
        self._cache_duration = 60

    async def fetch_prices(self):
        """Fetch latest + 24h timeseries prices with caching"""
        now = time.time()
        used_cache = False

        # Latest prices
        if (
            not self._price_cache["data"]
            or now - self._price_cache["timestamp"] > self._cache_duration
        ):
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    PRICE_URL, headers={"User-Agent": "PotionDecantChecker/2.0"}
                ) as resp:
                    resp.raise_for_status()
                    latest = await resp.json()
                    self._price_cache = {"timestamp": now, "data": latest["data"]}
        else:
            used_cache = True

        # 24h Timeseries
        if (
            not self._ts_cache["data"]
            or now - self._ts_cache["timestamp"] > self._cache_duration
        ):
            ts_data = {}
            async with aiohttp.ClientSession() as session:
                for pid in {str(v["3"]) for v in POTIONS.values()} | {
                    str(v["4"]) for v in POTIONS.values()
                }:
                    url = f"{TS_URL}?timestep=24h&id={pid}"
                    async with session.get(
                        url, headers={"User-Agent": "PotionDecantChecker/2.0"}
                    ) as resp:
                        resp.raise_for_status()
                        d = await resp.json()
                        data_points = d.get("data", [])
                        if data_points:
                            last = data_points[-1]
                            ts_data[pid] = {
                                "avgLowPrice": last.get("avgLowPrice") or 0,
                                "avgHighPrice": last.get("avgHighPrice") or 0,
                                "avgLowVolume": last.get("lowPriceVolume") or 0,
                                "avgHighVolume": last.get("highPriceVolume") or 0,
                            }
            self._ts_cache = {"timestamp": now, "data": ts_data}
        else:
            used_cache = True

        cache_time = min(self._price_cache["timestamp"], self._ts_cache["timestamp"])
        return self._price_cache["data"], self._ts_cache["data"], used_cache, cache_time

    @staticmethod
    def calc_profit(buy3, sell4):
        """Calculate profit assuming 2000-dose purchase and 2% tax"""
        cost = buy3 * 2000
        revenue = sell4 * 1500 * 0.98
        return revenue - cost

    def analyze_potions(self, latest, ts_data):
        alerts = []

        for pname, pdata in POTIONS.items():
            if pdata["limit"] < MIN_GE_LIMIT:
                continue

            id3, id4 = str(pdata["3"]), str(pdata["4"])
            if id3 not in latest or id4 not in latest:
                continue

            p3, p4 = latest[id3], latest[id4]
            low3, high3 = sorted([p3["low"], p3["high"]])
            low4, high4 = sorted([p4["low"], p4["high"]])

            if not all([low3, high3, low4, high4]):
                continue

            # Timeseries volumes
            avg_low_vol_3 = ts_data.get(id3, {}).get("avgLowVolume", 0)
            avg_high_vol_3 = ts_data.get(id3, {}).get("avgHighVolume", 0)
            avg_low_vol_4 = ts_data.get(id4, {}).get("avgLowVolume", 0)
            avg_high_vol_4 = ts_data.get(id4, {}).get("avgHighVolume", 0)

            # Skip potions with very low volume
            if min(avg_low_vol_3, avg_high_vol_3, avg_low_vol_4, avg_high_vol_4) < 5000:
                continue

            # Fetch latest timestamps
            low3_time = p3.get("lowTime", 0)
            high3_time = p3.get("highTime", 0)
            low4_time = p4.get("lowTime", 0)
            high4_time = p4.get("highTime", 0)

            profits = [
                self.calc_profit(low3, low4),
                self.calc_profit(low3, high4),
                self.calc_profit(high3, low4),
                self.calc_profit(high3, high4),
            ]
            avg_profit = sum(profits) / len(profits)
            cost = low3 * 2000
            roi = (avg_profit / cost) * 100 if cost > 0 else 0
            spread = (high4 - low4) / low4 * 100 if low4 else 0

            if avg_profit >= MIN_PROFIT:
                alerts.append(
                    {
                        "potion": pname,
                        "low3": low3,
                        "high3": high3,
                        "low4": low4,
                        "high4": high4,
                        "low3_time": low3_time,
                        "high3_time": high3_time,
                        "low4_time": low4_time,
                        "high4_time": high4_time,
                        "avg_profit": avg_profit,
                        "profits": {
                            "Buy Low→Sell Low": profits[0],
                            "Buy Low→Sell High": profits[1],
                            "Buy High→Sell Low": profits[2],
                            "Buy High→Sell High": profits[3],
                        },
                        "avg_low_ts_3": ts_data.get(id3, {}).get("avgLowPrice", 0),
                        "avg_high_ts_3": ts_data.get(id3, {}).get("avgHighPrice", 0),
                        "avg_low_ts_4": ts_data.get(id4, {}).get("avgLowPrice", 0),
                        "avg_high_ts_4": ts_data.get(id4, {}).get("avgHighPrice", 0),
                        "avg_low_vol_3": avg_low_vol_3,
                        "avg_high_vol_3": avg_high_vol_3,
                        "avg_low_vol_4": avg_low_vol_4,
                        "avg_high_vol_4": avg_high_vol_4,
                        "spread_pct": spread,
                        "roi_pct": roi,
                        "ge_limit": pdata["limit"],
                        "capital_required": cost,
                        "item_id": id4,
                    }
                )

        alerts.sort(key=lambda x: x["avg_profit"], reverse=True)
        return alerts

    @app_commands.command(
        name="osrs-decant", description="Check profitable potion decants"
    )
    async def decant_check(self, interaction: discord.Interaction):
        await interaction.response.defer()
        try:
            latest, ts_data, used_cache, cache_time = await self.fetch_prices()
            alerts = self.analyze_potions(latest, ts_data)

            if not alerts:
                await interaction.followup.send(
                    "No profitable potion decants found at this time."
                )
                return

            view = DecantPaginator(alerts, used_cache, cache_time)
            embed = view.create_embed()
            await interaction.followup.send(embed=embed, view=view)

        except Exception as e:
            await interaction.followup.send(f"Error fetching potion prices: {e}")


async def setup(bot):
    await bot.add_cog(DecantChecker(bot))
