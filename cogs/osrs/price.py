from datetime import datetime, timezone
from statistics import mean
from typing import Dict, List, Tuple

import discord
from discord import app_commands
from discord.ext import commands

# Timeframe configurations: (step, lookback_count)
TIMEFRAMES = {
    "24h": ("5m", 288),  # 24h * 12 (5min intervals)
    "7d": ("1h", 168),  # 7d * 24 hours
}


class PriceAnalyzer:
    """Analyzes market data with static methods."""

    @staticmethod
    def analyze_trend(prices: List[float], threshold: int = 5) -> Tuple[str, float]:
        """Calculate trend with configurable threshold."""
        if len(prices) < 2 or prices[0] == 0:
            return "Unknown", 0.0

        change = ((prices[-1] - prices[0]) / prices[0]) * 100

        if change > threshold:
            return "📈 Rising", change
        elif change < -threshold:
            return "📉 Falling", change
        return "➡️ Stable", change


class RefreshView(discord.ui.View):
    """Interactive view with refresh buttons."""

    def __init__(self, cog, item_id: int, item_name: str):
        super().__init__(timeout=3600)
        self.cog = cog
        self.item_id = item_id
        self.item_name = item_name

    async def _handle_interaction(self, interaction: discord.Interaction, mode: str):
        """Generic button handler."""
        await interaction.response.defer()
        embed = await self.cog.build_embed(self.item_id, self.item_name, mode)
        await interaction.message.edit(embed=embed, view=self)

    @discord.ui.button(label="🔄 Refresh", style=discord.ButtonStyle.primary)
    async def refresh(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        await self._handle_interaction(interaction, "price")

    @discord.ui.button(label="📊 Analysis", style=discord.ButtonStyle.secondary)
    async def analysis(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        await self._handle_interaction(interaction, "analysis")

    @discord.ui.button(label="💰 Profit", style=discord.ButtonStyle.success)
    async def profit(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._handle_interaction(interaction, "profit")


class EnhancedPriceChecker(commands.Cog):
    """OSRS price checking cog with comprehensive market analysis."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.analyzer = PriceAnalyzer()

        # Use centralized data manager
        self.data_manager = bot.osrs_data

        self.nature_rune_price = 0  # Cache for nature rune price
        self.NATURE_RUNE_ID = 561  # Nature rune item ID
        self._items_loaded = False

    async def cog_load(self):
        """Called when cog is loaded - data is already loaded by data manager."""
        self._items_loaded = True
        await self.update_nature_rune_price()
        self.bot.logger.info("[PriceChecker] Using centralized data manager")

    async def fetch_data(self, item_id: int) -> Tuple[Dict, Dict, Dict]:
        """Fetch latest prices, history, and calculated stats using data manager."""
        # Single call gets all data with intelligent caching
        data = await self.data_manager.get_comprehensive_item_data(item_id)

        latest = data["latest"]
        history = data["history"]
        stats = self._calculate_stats(history)

        return latest, history, stats

    def _calculate_stats(self, history: Dict) -> Dict:
        """Calculate 24h and 7d statistics from timeseries data."""
        stats = {}

        for period, (step, count) in TIMEFRAMES.items():
            data = history.get(step, [])[-count:] if history.get(step) else []

            if not data:
                stats[period] = {}
                continue

            # Extract prices and volumes
            high_prices = [d["avgHighPrice"] for d in data if d.get("avgHighPrice")]
            low_prices = [d["avgLowPrice"] for d in data if d.get("avgLowPrice")]
            volumes = [
                (d.get("highPriceVolume", 0) + d.get("lowPriceVolume", 0)) for d in data
            ]

            stats[period] = {
                "high": max(high_prices) if high_prices else 0,
                "low": min([p for p in low_prices if p > 0], default=0),
                "avg_high": mean(high_prices) if high_prices else 0,
                "avg_low": mean(low_prices) if low_prices else 0,
                "volume": sum(volumes),
                "avg_vol": mean(volumes) if volumes else 0,
            }

        return stats

    async def item_autocomplete(
        self, interaction: discord.Interaction, current: str
    ) -> List[app_commands.Choice]:
        """Fast autocomplete using centralized data manager."""
        # Use data manager's optimized autocomplete
        matches = self.data_manager.autocomplete_items(current, limit=25)

        return [
            app_commands.Choice(name=item["name"], value=item["name"])
            for item in matches
        ]

    def calculate_profit(
        self, buy: int, sell: int, limit: int, item_name: str = ""
    ) -> Dict:
        """Calculate comprehensive profit metrics with GE tax and special cases."""
        if not all([buy, sell, limit]):
            return {"error": True}

        tax = int(sell * 0.01)  # 1% GE tax

        # Special case: Old school bonds require 1M to become tradeable
        bond_cost = 1_000_000 if "bond" in item_name.lower() else 0

        profit = sell - buy - tax - bond_cost

        return {
            "profit": profit,
            "max": profit * limit,
            "roi": (profit / (buy + bond_cost)) * 100 if (buy + bond_cost) > 0 else 0,
            "margin": (profit / sell) * 100,
            "investment": (buy + bond_cost) * limit,
            "tax": tax,
            "bond_cost": bond_cost,
            "net_sell": sell - tax,
            "total_cost": buy + bond_cost,
        }

    async def update_nature_rune_price(self):
        """Fetch and cache the current nature rune price."""
        try:
            # Use data manager with caching
            latest_data = await self.data_manager.get_latest_prices(
                [self.NATURE_RUNE_ID]
            )
            nature_data = latest_data.get("data", {}).get(str(self.NATURE_RUNE_ID), {})
            self.nature_rune_price = nature_data.get("high", 0)

            if self.nature_rune_price > 0:
                self.bot.logger.info(
                    f"[PriceChecker] Nature rune price: {self.nature_rune_price} gp"
                )
            else:
                self.bot.logger.warning(
                    "[PriceChecker] Could not fetch nature rune price"
                )
        except Exception as e:
            self.bot.logger.error(
                f"[PriceChecker] Failed to fetch nature rune price: {e}"
            )
            self.nature_rune_price = 0

    async def build_embed(
        self, item_id: int, name: str, mode: str = "price"
    ) -> discord.Embed:
        """Build embed with error handling."""
        try:
            # Update nature rune price for fresh data
            await self.update_nature_rune_price()

            latest, history, stats = await self.fetch_data(item_id)

            if not latest and mode == "price":
                return discord.Embed(
                    title="❌ Error",
                    description="Market data unavailable",
                    color=discord.Color.red(),
                )

            # Route to appropriate builder
            builders = {
                "price": self._build_price,
                "analysis": self._build_analysis,
                "profit": self._build_profit,
            }

            return builders[mode](item_id, name, latest, history, stats)

        except Exception as e:
            self.bot.logger.error(f"[PriceChecker] Build error: {e}", exc_info=True)
            return discord.Embed(
                title="❌ Error",
                description="Failed to build embed",
                color=discord.Color.red(),
            )

    def _build_price(
        self, item_id: int, name: str, latest: Dict, history: Dict, stats: Dict
    ) -> discord.Embed:
        """Build comprehensive price embed."""
        # Get item info from cached mapping
        item = self.data_manager.get_item_info(item_id) or {}
        buy, sell = latest.get("low", 0), latest.get("high", 0)

        # Get current volume from latest 5m data
        cur_vol_buy = cur_vol_sell = 0
        if history.get("5m"):
            last = history["5m"][-1]
            cur_vol_buy = last.get("lowPriceVolume", 0)
            cur_vol_sell = last.get("highPriceVolume", 0)

        cur_vol = cur_vol_buy + cur_vol_sell

        # Analyze trend
        recent_prices = [
            d.get("avgLowPrice", 0)
            for d in history.get("5m", [])[-12:]
            if d.get("avgLowPrice")
        ]
        trend, trend_pct = self.analyzer.analyze_trend(
            recent_prices[-5:] if recent_prices else []
        )

        # Build embed
        embed = discord.Embed(
            title=f"📊 {name}",
            description=f"**ID:** {item_id} | **Type:** {'Members' if item.get('members') else 'F2P'}\n[📈 View Price Graph](https://prices.osrs.cloud/item/{item_id})",
            color=discord.Color.blue(),
            timestamp=datetime.now(timezone.utc),
        )

        # Current prices
        spread = sell - buy
        spread_pct = (spread / buy * 100) if buy > 0 else 0

        embed.add_field(
            name="💰 Current Prices",
            value=f"**Buy:** {buy:,} gp <t:{latest.get('lowTime', 0)}:R>\n"
            f"**Sell:** {sell:,} gp <t:{latest.get('highTime', 0)}:R>\n"
            f"**Spread:** {spread:,} gp ({spread_pct:.1f}%)\n"
            f"**Trend:** {trend} ({trend_pct:+.1f}%)",
            inline=True,
        )

        # Add timeframe stats
        for period, label in [("24h", "📈 24H Statistics"), ("7d", "📅 7D Statistics")]:
            s = stats.get(period, {})
            embed.add_field(
                name=label,
                value=f"**High:** {s.get('high', 0):,} gp\n"
                f"**Low:** {s.get('low', 0):,} gp\n"
                f"**Avg Buy:** {int(s.get('avg_low', 0)):,} gp\n"
                f"**Avg Sell:** {int(s.get('avg_high', 0)):,} gp\n"
                f"**Volume:** {s.get('volume', 0):,}",
                inline=True,
            )

        # Trading info
        limit = item.get("limit", 0)
        embed.add_field(
            name="🏪 Trading Info",
            value=f"**Limit:** {limit:,}\n"
            f"**High Alch:** {item.get('highalch', 0):,} gp\n"
            f"**Shop Value:** {item.get('value', 0):,} gp",
            inline=True,
        )

        # Quick profit
        profit = self.calculate_profit(buy, sell, limit, name)
        if not profit.get("error"):
            color = "🟢" if profit["profit"] > 0 else "🔴"
            profit_text = (
                f"**Per Item:** {profit['profit']:,} gp\n"
                f"**Max:** {profit['max']:,} gp\n"
                f"**ROI:** {profit['roi']:.1f}%\n"
                f"**Investment:** {profit['investment']:,} gp"
            )
            if profit.get("bond_cost", 0) > 0:
                profit_text += f"\n**Bond Fee:** {profit['bond_cost']:,} gp"

            embed.add_field(
                name=f"{color} Quick Profit", value=profit_text, inline=True
            )

        # Recent activity
        embed.add_field(
            name="📊 Activity (5m)",
            value=f"**Buy Vol:** {cur_vol_buy:,}\n"
            f"**Sell Vol:** {cur_vol_sell:,}\n"
            f"**Total:** {cur_vol:,}\n"
            f"**24H Avg/Int:** {int(stats.get('24h', {}).get('avg_vol', 0)):,}",
            inline=True,
        )

        embed.set_thumbnail(url=f"https://prices.runescape.wiki/img/{item_id}.png")
        embed.set_footer(text="Data from OSRS Wiki • Use buttons for more details")

        return embed

    def _build_analysis(
        self, item_id: int, name: str, latest: Dict, history: Dict, stats: Dict
    ) -> discord.Embed:
        """Build market analysis embed."""
        embed = discord.Embed(
            title=f"📊 Market Analysis: {name}",
            description=f"[📈 View Price Graph](https://prices.osrs.cloud/item/{item_id})",
            color=discord.Color.purple(),
            timestamp=datetime.now(timezone.utc),
        )

        # Multi-timeframe trend analysis
        trends = []
        timeframe_config = [
            ("5m", 12, "1 Hour"),
            ("1h", 6, "6 Hours"),
            ("1h", 24, "24 Hours"),
            ("1h", 168, "7 Days"),
        ]

        for step, lookback, label in timeframe_config:
            if history.get(step):
                prices = [
                    d.get("avgLowPrice", 0)
                    for d in history[step][-lookback:]
                    if d.get("avgLowPrice")
                ]
                if prices and len(prices) >= 2:
                    trend, pct = self.analyzer.analyze_trend(prices)
                    trends.append(f"**{label}:** {trend} ({pct:+.1f}%)")

        if trends:
            embed.add_field(
                name="📈 Price Trends", value="\n".join(trends), inline=False
            )

        # Period comparison
        day_avg = stats.get("24h", {}).get("avg_low", 0)
        week_avg = stats.get("7d", {}).get("avg_low", 0)

        if day_avg and week_avg:
            change = ((day_avg - week_avg) / week_avg) * 100
            icon = "📈" if change > 0 else "📉" if change < 0 else "➡️"

            embed.add_field(
                name="📊 24H vs 7D",
                value=f"**24H Avg:** {int(day_avg):,} gp\n"
                f"**7D Avg:** {int(week_avg):,} gp\n"
                f"**Change:** {icon} {change:+.2f}%",
                inline=False,
            )

        return embed

    def _build_profit(
        self, item_id: int, name: str, latest: Dict, history: Dict, stats: Dict
    ) -> discord.Embed:
        """Build profit analysis embed."""
        # Get item info from cached mapping
        item = self.data_manager.get_item_info(item_id) or {}

        embed = discord.Embed(
            title=f"💰 Profit Analysis: {name}",
            description=f"[📈 View Price Graph](https://prices.osrs.cloud/item/{item_id})",
            color=discord.Color.gold(),
            timestamp=datetime.now(timezone.utc),
        )

        buy, sell, limit = (
            latest.get("low", 0),
            latest.get("high", 0),
            item.get("limit", 0),
        )

        if not all([buy, sell, limit]):
            embed.description = "❌ Insufficient data for analysis"
            return embed

        profit = self.calculate_profit(buy, sell, limit, name)

        # Flipping metrics
        flip_value = (
            f"**Buy:** {buy:,} gp\n"
            f"**Sell:** {sell:,} gp (net: {profit['net_sell']:,})\n"
        )
        if profit.get("bond_cost", 0) > 0:
            flip_value += f"**Bond Fee:** {profit['bond_cost']:,} gp\n"

        flip_value += (
            f"**Profit:** {profit['profit']:,} gp\n"
            f"**ROI:** {profit['roi']:.2f}%\n"
            f"**Margin:** {profit['margin']:.2f}%"
        )

        embed.add_field(name="🔄 Flipping", value=flip_value, inline=True)

        # Investment breakdown
        invest_value = (
            f"**Total:** {profit['investment']:,} gp\n"
            f"**Max Profit:** {profit['max']:,} gp\n"
            f"**GE Tax:** {profit['tax']:,} gp\n"
        )
        if profit.get("bond_cost", 0) > 0:
            invest_value += f"**Bond Fee/Item:** {profit['bond_cost']:,} gp\n"

        invest_value += f"**Limit:** {limit:,}"

        embed.add_field(name="💼 Investment", value=invest_value, inline=True)

        # Average price comparison
        day_avg = stats.get("24h", {}).get("avg_low", 0)
        week_avg = stats.get("7d", {}).get("avg_low", 0)

        if day_avg and week_avg:
            embed.add_field(
                name="📊 Averages",
                value=f"**24H:** {int(day_avg):,} gp\n" f"**7D:** {int(week_avg):,} gp",
                inline=True,
            )

        # Strategy recommendations
        strategies = []
        alch = item.get("highalch", 0)

        # Only show alching if we have a valid nature rune price
        if alch > buy and self.nature_rune_price > 0:
            # Calculate high alch profit including nature rune cost
            alch_profit = alch - buy - self.nature_rune_price
            if alch_profit > 0:
                strategies.append(
                    f"**Alching:** {alch_profit:,} gp/item (Alch: {alch:,} - Buy: {buy:,} - Nature: {self.nature_rune_price:,})"
                )
            else:
                strategies.append(f"**Alching:** 🔴 {alch_profit:,} gp loss/item")

        if profit["profit"] > 0:
            strategies.append(f"**Flipping:** {profit['profit']:,} gp/item")

        # Price position analysis
        if day_avg and buy < day_avg * 0.95:
            strategies.append(
                f"🟢 {((1 - buy/day_avg) * 100):.1f}% below 24H avg - good buy"
            )
        elif day_avg and buy > day_avg * 1.05:
            strategies.append(
                f"🔴 {((buy/day_avg - 1) * 100):.1f}% above 24H avg - overpriced"
            )

        if strategies:
            embed.add_field(
                name="🎯 Strategies", value="\n".join(strategies), inline=False
            )

        # Risk assessment
        risks = []
        if profit["roi"] > 10:
            risks.append("🟢 High ROI opportunity")
        elif profit["roi"] > 3:
            risks.append("🟡 Moderate returns")
        else:
            risks.append("🔴 Low margin")

        if profit["investment"] > 10_000_000:
            risks.append("⚠️ High capital required")

        vol = stats.get("24h", {}).get("volume", 0)
        if vol < 100:
            risks.append("⚠️ Low volume - slow flips")
        elif vol > 10_000:
            risks.append("🟢 High liquidity")

        embed.add_field(name="⚖️ Risk", value="\n".join(risks), inline=False)

        return embed

    @app_commands.command(
        name="osrs-price", description="Get OSRS item market data and analysis"
    )
    @app_commands.describe(item="Item name to analyze")
    @app_commands.autocomplete(item=item_autocomplete)
    @app_commands.allowed_installs(guilds=True, users=True)
    @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
    async def osrs_price(self, interaction: discord.Interaction, item: str):
        await interaction.response.defer()

        # Get item ID from data manager
        item_id = self.data_manager.get_item_id(item)
        if not item_id:
            return await interaction.followup.send(
                embed=discord.Embed(
                    title="❌ Item Not Found",
                    description=f"'{item}' not found. Use autocomplete.",
                    color=discord.Color.red(),
                ),
                ephemeral=True,
            )

        try:
            embed = await self.build_embed(item_id, item)
            await interaction.followup.send(
                embed=embed, view=RefreshView(self, item_id, item)
            )
        except Exception as e:
            self.bot.logger.error(f"[PriceChecker] Command error: {e}", exc_info=True)
            await interaction.followup.send(
                embed=discord.Embed(
                    title="❌ Error",
                    description="Failed to fetch data",
                    color=discord.Color.red(),
                ),
                ephemeral=True,
            )


async def setup(bot: commands.Bot):
    cog = EnhancedPriceChecker(bot)
    await bot.add_cog(cog)
