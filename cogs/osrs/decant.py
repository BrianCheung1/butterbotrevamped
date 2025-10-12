import json
import math
import os
import time
from datetime import datetime

import discord
from discord import app_commands
from discord.ext import commands
from logger import setup_logger

# Default filters
DEFAULT_MIN_PROFIT = 100_000
DEFAULT_MIN_VOLUME = 50_000
MIN_GE_LIMIT = 2000

# Load potion data
project_root = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
json_path = os.path.join(project_root, "constants", "potion_limits.json")
with open(json_path, "r") as f:
    POTIONS = json.load(f)

logger = setup_logger("OSRSDecant")


class DecantPaginator(discord.ui.View):
    def __init__(self, pages, used_cache: bool, cache_time: int, cog_instance):
        super().__init__(timeout=3600)
        self.pages = pages
        self.current = 0
        self.used_cache = used_cache
        self.cache_time = cache_time
        self.cog = cog_instance

    def create_embed(self):
        data = self.pages[self.current]

        # Color coding based on profit level
        if data["avg_profit"] >= 400_000:
            color = 0x00FF00  # Bright green for very high profit
        elif data["avg_profit"] >= 200_000:
            color = 0x32CD32  # Lime green for high profit
        elif data["avg_profit"] >= 100_000:
            color = 0x90EE90  # Light green for decent profit
        else:
            color = 0xFFD700  # Gold for lower profit

        embed = discord.Embed(
            title=f"💰 **{data['potion']}** Decant Analysis",
            description=(
                f"📈 **Average Profit:** `{int(data['avg_profit']):,}` gp | **ROI:** `{data['roi_pct']:.1f}%`\n"
                f"💸 **Capital Required:** `{data['capital_required']:,}` gp | **Page:** `{self.current + 1}/{len(self.pages)}`"
            ),
            color=color,
        )

        # Current GE Prices
        embed.add_field(
            name="🏷️ **Current GE Prices**",
            value=(
                f"**3-dose:** `{data['low3']:,}` - `{data['high3']:,}` gp\n"
                f"<t:{data['low3_time']}:R> - <t:{data['high3_time']}:R>\n\n"
                f"**4-dose:** `{data['low4']:,}` - `{data['high4']:,}` gp\n"
                f"<t:{data['low4_time']}:R> - <t:{data['high4_time']}:R>"
            ),
            inline=True,
        )

        # Key Metrics
        embed.add_field(
            name="📊 **Key Metrics**",
            value=(
                f"**Best Profit:** `{int(max(data['profits'].values())):,}` gp\n"
                f"**Worst Profit:** `{int(min(data['profits'].values())):,}` gp\n"
                f"**Daily Range 3-dose:** `{data['daily_low_3']:,}` - `{data['daily_high_3']:,}` gp\n"
                f"**Daily Range 4-dose:** `{data['daily_low_4']:,}` - `{data['daily_high_4']:,}` gp"
            ),
            inline=True,
        )

        embed.add_field(name="\u200b", value="\u200b", inline=False)

        # Profit Scenarios
        profit_scenarios = [
            ("🟢 Buy Low → Sell High", data["profits"]["Buy Low→Sell High"]),
            ("🟡 Buy Low → Sell Low", data["profits"]["Buy Low→Sell Low"]),
            ("🟠 Buy High → Sell High", data["profits"]["Buy High→Sell High"]),
            ("🔴 Buy High → Sell Low", data["profits"]["Buy High→Sell Low"]),
        ]

        profit_text = "\n".join(
            [
                f"{scenario}: `{int(profit):,}` gp"
                for scenario, profit in profit_scenarios
            ]
        )

        embed.add_field(
            name="📋 **Profit Scenarios** (per 2,000 doses)",
            value=profit_text,
            inline=True,
        )

        # Daily Trading Volume
        embed.add_field(
            name="📈 **Daily Trading Volume**",
            value=(
                f"**3-dose Daily Volume:**\n"
                f"Buy Orders: `{data.get('daily_buy_vol_3', 0):,}`\n"
                f"Sell Orders: `{data.get('daily_sell_vol_3', 0):,}`\n\n"
                f"**4-dose Daily Volume:**\n"
                f"Buy Orders: `{data.get('daily_buy_vol_4', 0):,}`\n"
                f"Sell Orders: `{data.get('daily_sell_vol_4', 0):,}`"
            ),
            inline=True,
        )

        embed.add_field(
            name="📦 **Expected Fill**",
            value=(
                f"**3-dose:** `{data.get('expected_fill_3', 0):,}` / 2000 expected\n"
            ),
            inline=True,
        )

        # Item thumbnail
        embed.set_thumbnail(
            url=f"https://prices.runescape.wiki/osrs/item/{data['item_id']}.png"
        )

        # Footer
        cache_status = "🟢 Live Data" if not self.used_cache else "🟡 Cached Data"
        last_updated = datetime.fromtimestamp(self.cache_time).strftime(
            "%Y-%m-%d %H:%M:%S UTC"
        )
        embed.set_footer(
            text=f"{cache_status} | Last Updated: {last_updated} | 5min intervals",
            icon_url="https://oldschool.runescape.wiki/images/thumb/6/6d/Coins_10000.png/21px-Coins_10000.png",
        )

        return embed

    @discord.ui.button(label="⬅️ Previous", style=discord.ButtonStyle.primary)
    async def previous(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        self.current = (self.current - 1) % len(self.pages)
        await interaction.response.edit_message(embed=self.create_embed(), view=self)

    @discord.ui.button(label="➡️ Next", style=discord.ButtonStyle.primary)
    async def next(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.current = (self.current + 1) % len(self.pages)
        await interaction.response.edit_message(embed=self.create_embed(), view=self)

    @discord.ui.button(label="🔄 Run Again", style=discord.ButtonStyle.primary)
    async def run_again(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        await interaction.response.defer()
        try:
            # Force refresh data through data manager
            alerts, used_cache, cache_time = await self.cog.analyze_decants(
                force_refresh=True
            )

            if not alerts:
                embed = discord.Embed(
                    title="💊 Potion Decant Check",
                    description=(
                        "No profitable potion decants found at this time.\n"
                        f"Minimum profit threshold: `{DEFAULT_MIN_PROFIT:,}` gp"
                    ),
                    color=discord.Color.orange(),
                )
                embed.set_footer(text="Try again later or adjust your filters!")
                await interaction.followup.send(embed=embed, view=None)
                return

            self.pages = alerts
            self.used_cache = used_cache
            self.cache_time = cache_time
            self.current = 0

            embed = self.create_embed()
            await interaction.followup.send(embed=embed, view=self)

        except Exception as e:
            error_embed = discord.Embed(
                title="❌ Error",
                description=f"Failed to refresh potion prices:\n```{str(e)[:100]}```",
                color=discord.Color.red(),
            )
            await interaction.followup.send(embed=error_embed, view=None)


class DecantChecker(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        # Use centralized data manager instead of local caching
        self.data_manager = bot.osrs_data

    def aggregate_5m_data(self, data_points):
        """Aggregate 5-minute timeseries data into daily stats"""
        if not data_points:
            return {
                "daily_high": 0,
                "daily_low": 0,
                "total_buy_volume": 0,
                "total_sell_volume": 0,
            }

        # Filter out None values and get valid prices
        valid_highs = [
            point.get("avgHighPrice")
            for point in data_points
            if point.get("avgHighPrice") is not None and point.get("avgHighPrice") > 0
        ]
        valid_lows = [
            point.get("avgLowPrice")
            for point in data_points
            if point.get("avgLowPrice") is not None and point.get("avgLowPrice") > 0
        ]

        # Sum all volumes (treating None as 0)
        total_buy_volume = sum(
            point.get("lowPriceVolume") or 0 for point in data_points
        )
        total_sell_volume = sum(
            point.get("highPriceVolume") or 0 for point in data_points
        )

        return {
            "daily_high": max(valid_highs) if valid_highs else 0,
            "daily_low": min(valid_lows) if valid_lows else 0,
            "total_buy_volume": total_buy_volume,
            "total_sell_volume": total_sell_volume,
        }

    def expected_fill(
        self,
        desired_qty: int,
        ts_volume: int,
        ge_limit: int,
        adjustment_factor: float = 0.9,
    ) -> int:
        """
        Estimate how many potions of `desired_qty` are likely to fill based on recent volume.
        """
        ts_volume /= 288
        if ts_volume <= 0:
            return min(desired_qty, ge_limit)

        fill_estimate = min(desired_qty, math.ceil(ts_volume / adjustment_factor))
        return min(fill_estimate, ge_limit)

    @staticmethod
    def calc_profit(buy3_price, sell4_price):
        """Calculate profit for 2000-dose purchase with 2% GE tax"""
        cost = buy3_price * 2000  # Buy 2000x 3-dose potions
        revenue = sell4_price * 1500 * 0.98  # Sell 1500x 4-dose potions (2% tax)
        return revenue - cost

    async def analyze_decants(
        self,
        min_profit=DEFAULT_MIN_PROFIT,
        min_volume=DEFAULT_MIN_VOLUME,
        force_refresh=False,
    ):
        """
        Analyze potions for profitable decanting opportunities using data manager.

        Returns:
            Tuple of (alerts_list, used_cache, cache_timestamp)
        """
        # Get all required potion IDs
        potion_ids = list(
            {v["3"] for v in POTIONS.values()} | {v["4"] for v in POTIONS.values()}
        )

        # Fetch latest prices (cached by data manager)
        latest_data = await self.data_manager.get_latest_prices(
            potion_ids, force_refresh=force_refresh
        )
        latest = latest_data.get("data", {})

        # Check if we used cache
        cache_key = f"latest_{','.join(map(str, potion_ids))}"
        used_cache = not force_refresh and self.data_manager._is_cache_valid(
            cache_key, "latest"
        )
        cache_time = self.data_manager._cache_timestamps.get(cache_key, time.time())

        # Fetch 5m timeseries data for all potions (cached by data manager)
        ts_data = {}
        for potion_id in potion_ids:
            timeseries = await self.data_manager.get_timeseries(
                potion_id, timestep="5m", force_refresh=force_refresh
            )

            # Get data from the last 24 hours (288 data points at 5min intervals)
            recent_points = timeseries[-288:] if len(timeseries) > 288 else timeseries

            # Aggregate the 5-minute data
            aggregated = self.aggregate_5m_data(recent_points)
            ts_data[str(potion_id)] = aggregated

        # Analyze potions
        alerts = []
        current_time = time.time()

        def get_safe_volume(ts_volume, last_update_time, ge_limit):
            """Get volume with fallback for recent activity"""
            if ts_volume > 0:
                return ts_volume

            # If price updated recently (within 15 minutes), estimate volume
            if current_time - last_update_time < 900:
                return max(int(ge_limit * 0.5), min_volume)

            return 0

        for potion_name, potion_data in POTIONS.items():

            # Skip potions with low GE limits
            if potion_data["limit"] < MIN_GE_LIMIT:
                continue

            dose3_id, dose4_id = str(potion_data["3"]), str(potion_data["4"])

            # Check if both items exist in price data
            if dose3_id not in latest or dose4_id not in latest:
                print("Missing price data for potion IDs:", dose3_id, dose4_id)
                continue

            price3, price4 = latest[dose3_id], latest[dose4_id]

            # Get sorted prices (low/high) from latest API data
            low3, high3 = sorted([price3["low"], price3["high"]])
            low4, high4 = sorted([price4["low"], price4["high"]])

            # Skip if any price is missing
            if not all([low3, high3, low4, high4]):
                continue

            # Get price update timestamps
            price_times = {
                "low3_time": price3.get("lowTime", 0),
                "high3_time": price3.get("highTime", 0),
                "low4_time": price4.get("lowTime", 0),
                "high4_time": price4.get("highTime", 0),
            }

            # Get aggregated daily data for display purposes only
            if dose3_id in ts_data and dose4_id in ts_data:
                ts3_data = ts_data[dose3_id]
                ts4_data = ts_data[dose4_id]

                daily_low_3 = ts3_data["daily_low"]
                daily_high_3 = ts3_data["daily_high"]
                daily_low_4 = ts4_data["daily_low"]
                daily_high_4 = ts4_data["daily_high"]

                daily_buy_vol_3 = ts3_data["total_buy_volume"]
                daily_sell_vol_3 = ts3_data["total_sell_volume"]
                daily_buy_vol_4 = ts4_data["total_buy_volume"]
                daily_sell_vol_4 = ts4_data["total_sell_volume"]
            else:
                # Fallback to latest data if timeseries unavailable
                daily_low_3 = low3
                daily_high_3 = high3
                daily_low_4 = low4
                daily_high_4 = high4
                daily_buy_vol_3 = daily_sell_vol_3 = daily_buy_vol_4 = (
                    daily_sell_vol_4
                ) = 0

            # Calculate volumes with fallbacks (for filtering only)
            volumes = {
                "avg_low_vol_3": get_safe_volume(
                    daily_buy_vol_3,
                    price_times["low3_time"],
                    potion_data["limit"],
                ),
                "avg_high_vol_3": get_safe_volume(
                    daily_sell_vol_3,
                    price_times["high3_time"],
                    potion_data["limit"],
                ),
                "avg_low_vol_4": get_safe_volume(
                    daily_buy_vol_4,
                    price_times["low4_time"],
                    potion_data["limit"],
                ),
                "avg_high_vol_4": get_safe_volume(
                    daily_sell_vol_4,
                    price_times["high4_time"],
                    potion_data["limit"],
                ),
            }

            # Check minimum volume requirement first
            min_required_volumes = [
                volumes["avg_low_vol_3"],
                volumes["avg_high_vol_3"],
                volumes["avg_low_vol_4"],
                volumes["avg_high_vol_4"],
            ]

            # Skip if any volume is below minimum threshold
            if any(vol < min_volume for vol in min_required_volumes):
                continue

            desired_order = 2000  # Example: 2000 potions per order

            expected_fill_3 = self.expected_fill(
                desired_order,
                volumes["avg_low_vol_3"],
                potion_data["limit"],
            )

            # Calculate all profit scenarios using ORIGINAL latest API prices
            profit_scenarios = {
                "Buy Low→Sell Low": self.calc_profit(low3, low4),
                "Buy Low→Sell High": self.calc_profit(low3, high4),
                "Buy High→Sell Low": self.calc_profit(high3, low4),
                "Buy High→Sell High": self.calc_profit(high3, high4),
            }

            avg_profit = sum(profit_scenarios.values()) / len(profit_scenarios)
            capital_cost = low3 * 2000
            roi_percent = (avg_profit / capital_cost * 100) if capital_cost > 0 else 0
            spread_percent = ((high4 - low4) / low4 * 100) if low4 else 0

            # Only include profitable opportunities
            if avg_profit >= min_profit:
                alerts.append(
                    {
                        "potion": potion_name,
                        "low3": low3,
                        "high3": high3,
                        "low4": low4,
                        "high4": high4,
                        **price_times,
                        "daily_low_3": daily_low_3,
                        "daily_high_3": daily_high_3,
                        "daily_low_4": daily_low_4,
                        "daily_high_4": daily_high_4,
                        "avg_profit": avg_profit,
                        "profits": profit_scenarios,
                        **volumes,
                        "daily_buy_vol_3": daily_buy_vol_3,
                        "daily_sell_vol_3": daily_sell_vol_3,
                        "daily_buy_vol_4": daily_buy_vol_4,
                        "daily_sell_vol_4": daily_sell_vol_4,
                        "spread_pct": spread_percent,
                        "roi_pct": roi_percent,
                        "ge_limit": potion_data["limit"],
                        "capital_required": capital_cost,
                        "expected_fill_3": expected_fill_3,
                        "item_id": dose4_id,
                    }
                )

        # Sort by average profit (highest first)
        alerts.sort(key=lambda x: x["avg_profit"], reverse=True)
        return alerts, used_cache, cache_time

    @app_commands.command(
        name="osrs-decant",
        description="Check profitable potion decanting opportunities",
    )
    @app_commands.allowed_installs(guilds=True, users=True)
    @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
    @app_commands.describe(
        min_profit="Minimum average profit per decant (default: 100,000 gp)",
        min_volume="Minimum average trading volume (default: 50,000)",
    )
    async def decant_check(
        self,
        interaction: discord.Interaction,
        min_profit: int = DEFAULT_MIN_PROFIT,
        min_volume: int = DEFAULT_MIN_VOLUME,
    ):
        await interaction.response.defer()

        try:
            # Analyze using data manager
            alerts, used_cache, cache_time = await self.analyze_decants(
                min_profit, min_volume
            )

            if not alerts:
                embed = discord.Embed(
                    title="💊 Potion Decant Check",
                    description=(
                        "No profitable potion decants found at this time.\n"
                        f"📉 Minimum profit threshold: `{min_profit:,}` gp\n"
                        f"📦 Minimum volume: `{min_volume:,}`"
                    ),
                    color=discord.Color.orange(),
                )
                embed.set_footer(text="Try again later or adjust your filters!")
                await interaction.followup.send(embed=embed)
                return

            # Create paginated view
            view = DecantPaginator(alerts, used_cache, cache_time, self)
            embed = view.create_embed()
            await interaction.followup.send(embed=embed, view=view)

        except Exception as e:
            logger.error(f"[DecantChecker] Error: {e}", exc_info=True)
            error_embed = discord.Embed(
                title="❌ Error",
                description=f"Failed to fetch potion prices:\n```{str(e)[:100]}```",
                color=discord.Color.red(),
            )
            await interaction.followup.send(embed=error_embed)


async def setup(bot):
    await bot.add_cog(DecantChecker(bot))
