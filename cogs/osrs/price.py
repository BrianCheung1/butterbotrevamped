import math
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from statistics import mean, median
from typing import Dict, List, Optional, Tuple

import aiohttp
import discord
from discord import app_commands
from discord.ext import commands

# API Endpoints
PRICE_URL = "https://prices.runescape.wiki/api/v1/osrs/latest"
TS_5M_URL = (
    "https://prices.runescape.wiki/api/v1/osrs/timeseries?timestep=5m&id={item_id}"
)
TS_1H_URL = (
    "https://prices.runescape.wiki/api/v1/osrs/timeseries?timestep=1h&id={item_id}"
)
TS_6H_URL = (
    "https://prices.runescape.wiki/api/v1/osrs/timeseries?timestep=6h&id={item_id}"
)
TS_24H_URL = (
    "https://prices.runescape.wiki/api/v1/osrs/timeseries?timestep=24h&id={item_id}"
)
MAPPING_URL = "https://prices.runescape.wiki/api/v1/osrs/mapping"


class PriceAnalyzer:
    """Analyzes market data to provide insights."""

    @staticmethod
    def calculate_price_trend(
        prices: List[float], periods: int = 5
    ) -> Tuple[str, float]:
        """Calculate price trend over recent periods."""
        if len(prices) < 2:
            return "Unknown", 0.0

        recent_prices = prices[-min(periods, len(prices)) :]
        if len(recent_prices) < 2:
            return "Stable", 0.0

        # Simple trend calculation
        start_price = recent_prices[0]
        end_price = recent_prices[-1]

        if start_price == 0:
            return "Unknown", 0.0

        change_percent = ((end_price - start_price) / start_price) * 100

        if change_percent > 5:
            return "📈 Rising", change_percent
        elif change_percent < -5:
            return "📉 Falling", change_percent
        else:
            return "➡️ Stable", change_percent

    @staticmethod
    def calculate_volatility(prices: List[float]) -> Tuple[str, float]:
        """Calculate price volatility."""
        if len(prices) < 2:
            return "Unknown", 0.0

        valid_prices = [p for p in prices if p > 0]
        if len(valid_prices) < 2:
            return "Unknown", 0.0

        avg_price = mean(valid_prices)
        variance = sum((p - avg_price) ** 2 for p in valid_prices) / len(valid_prices)
        volatility = (math.sqrt(variance) / avg_price) * 100 if avg_price > 0 else 0

        if volatility > 15:
            return "🔥 High", volatility
        elif volatility > 5:
            return "⚡ Medium", volatility
        else:
            return "🧊 Low", volatility

    @staticmethod
    def analyze_volume_trend(volumes: List[int], periods: int = 5) -> Tuple[str, float]:
        """Analyze volume trends."""
        if len(volumes) < 2:
            return "Unknown", 0.0

        recent_volumes = volumes[-min(periods, len(volumes)) :]
        if len(recent_volumes) < 2:
            return "Normal", 0.0

        avg_recent = mean(recent_volumes)
        avg_overall = mean(volumes)

        if avg_overall == 0:
            return "Unknown", 0.0

        volume_ratio = avg_recent / avg_overall

        if volume_ratio > 2.0:
            return "🚀 High Activity", volume_ratio
        elif volume_ratio > 1.5:
            return "📊 Increased", volume_ratio
        elif volume_ratio < 0.5:
            return "💤 Low Activity", volume_ratio
        else:
            return "➡️ Normal", volume_ratio

    @staticmethod
    def get_market_status(
        buy_price: int, sell_price: int, volume_high: int, volume_low: int
    ) -> str:
        """Determine overall market status."""
        spread_percent = (
            ((sell_price - buy_price) / buy_price) * 100 if buy_price > 0 else 0
        )
        total_volume = volume_high + volume_low

        status_indicators = []

        if spread_percent > 10:
            status_indicators.append("💸 Wide Spread")
        elif spread_percent < 2:
            status_indicators.append("🎯 Tight Spread")

        if total_volume > 1000:
            status_indicators.append("🔥 Active")
        elif total_volume < 100:
            status_indicators.append("💤 Quiet")

        if buy_price > sell_price * 0.98:  # Very close prices
            status_indicators.append("⚡ Liquid")

        return " | ".join(status_indicators) if status_indicators else "➡️ Normal"


class RefreshView(discord.ui.View):
    def __init__(self, cog, item_id: int, item_name: str, timeout: int = 300):
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

    @discord.ui.button(label="📊 Analysis", style=discord.ButtonStyle.secondary)
    async def analysis_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        await interaction.response.defer()
        embed = await self.cog.build_analysis_embed(self.item_id, self.item_name)
        await interaction.message.edit(
            embed=embed, view=RefreshView(self.cog, self.item_id, self.item_name)
        )

    @discord.ui.button(label="💰 Profit", style=discord.ButtonStyle.success)
    async def profit_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        await interaction.response.defer()
        embed = await self.cog.build_profit_embed(self.item_id, self.item_name)
        await interaction.message.edit(
            embed=embed, view=RefreshView(self.cog, self.item_id, self.item_name)
        )


class EnhancedPriceChecker(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.items_data = []
        self.name_to_id = {}
        self.id_to_item = {}
        self.analyzer = PriceAnalyzer()

    async def load_items(self):
        """Load items with search index for fast autocomplete."""
        async with aiohttp.ClientSession() as session:
            async with session.get(MAPPING_URL) as response:
                data = await response.json()
                self.items_data = data
                self.name_to_id = {i["name"].lower(): i["id"] for i in self.items_data}
                self.id_to_item = {i["id"]: i for i in self.items_data}

                # Build search indices
                self._build_search_indices()

        self.bot.logger.info(
            f"[PriceChecker] Loaded {len(self.items_data)} items for autocomplete."
        )

    def _build_search_indices(self):
        """Build multiple indices for ultra-fast autocomplete."""
        self.exact_match_index = {}  # Full name -> item
        self.prefix_index = defaultdict(list)  # 2-3 char prefix -> items
        self.word_index = defaultdict(list)  # Individual words -> items

        for item in self.items_data:
            name = item["name"]
            name_lower = name.lower()

            # Exact match index
            self.exact_match_index[name_lower] = item

            # Prefix indices (2 and 3 characters)
            if len(name_lower) >= 2:
                prefix2 = name_lower[:2]
                if len(self.prefix_index[prefix2]) < 100:  # Limit per prefix
                    self.prefix_index[prefix2].append(item)

            if len(name_lower) >= 3:
                prefix3 = name_lower[:3]
                if len(self.prefix_index[prefix3]) < 100:
                    self.prefix_index[prefix3].append(item)

            # Word index for multi-word items
            words = name_lower.split()
            for word in words:
                if len(word) >= 3:
                    if len(self.word_index[word]) < 50:
                        self.word_index[word].append(item)

                    # ✅ NEW: also index the first 3 letters of each word
                    word_prefix = word[:3]
                    if len(self.prefix_index[word_prefix]) < 100:
                        self.prefix_index[word_prefix].append(item)

    async def fetch_comprehensive_data(self, item_id: int):
        """Fetch all available market data for comprehensive analysis."""
        async with aiohttp.ClientSession() as session:
            # Latest prices
            async with session.get(f"{PRICE_URL}?id={item_id}") as resp:
                latest_data = await resp.json()
            latest = latest_data.get("data", {}).get(str(item_id), {})

            # Multiple timeframes for comprehensive analysis
            timeframes = {
                "5m": TS_5M_URL.format(item_id=item_id),
                "1h": TS_1H_URL.format(item_id=item_id),
                "6h": TS_6H_URL.format(item_id=item_id),
                "24h": TS_24H_URL.format(item_id=item_id),
            }

            history = {}
            for timeframe, url in timeframes.items():
                try:
                    async with session.get(url) as resp:
                        data = await resp.json()
                    history[timeframe] = data.get("data", [])
                except:
                    history[timeframe] = []

            # Get 24h volume data using the same method as decant checker
            volume_24h_data = {}
            if history.get("24h"):
                data_points = history["24h"]
                if data_points:
                    last_point = data_points[-1]
                    volume_24h_data = {
                        "avgLowVolume": last_point.get("lowPriceVolume") or 0,
                        "avgHighVolume": last_point.get("highPriceVolume") or 0,
                    }

        return latest, history, volume_24h_data

    async def item_autocomplete(
        self, interaction: discord.Interaction, current: str
    ) -> List[app_commands.Choice]:
        """Ultra-fast autocomplete using pre-built indices."""
        if not self.items_data:
            return []

        current_lower = current.lower()
        matches = []
        seen = set()

        # No input: show first 25 items
        if len(current_lower) == 0:
            return [
                app_commands.Choice(name=item["name"], value=item["name"])
                for item in self.items_data[:25]
            ]

        # For 1 character: only check items starting with that letter (faster)
        if len(current_lower) == 1:
            for item in self.items_data:
                if len(matches) >= 25:
                    break
                name = item["name"]
                name_lower = name.lower()
                if name_lower.startswith(current_lower):
                    matches.append(app_commands.Choice(name=name, value=name))
                    seen.add(name_lower)
            return matches

        # Strategy 1: Check for exact match first
        if current_lower in self.exact_match_index:
            item = self.exact_match_index[current_lower]
            matches.append(app_commands.Choice(name=item["name"], value=item["name"]))
            seen.add(current_lower)

        # Strategy 2: Use prefix index for fast lookup
        if len(current_lower) >= 3:
            candidates = self.prefix_index.get(current_lower[:3], [])
        else:
            candidates = self.prefix_index.get(current_lower[:2], [])

        # Filter candidates
        for item in candidates:
            if len(matches) >= 25:
                break

            name = item["name"]
            name_lower = name.lower()

            if current_lower in name_lower and name_lower not in seen:
                matches.append(app_commands.Choice(name=name, value=name))
                seen.add(name_lower)

        # Strategy 3: If still under 25, check word index
        if len(matches) < 25:
            words = current_lower.split()
            for word in words:
                if len(word) >= 3 and word in self.word_index:
                    for item in self.word_index[word]:
                        if len(matches) >= 25:
                            break

                        name = item["name"]
                        name_lower = name.lower()

                        if current_lower in name_lower and name_lower not in seen:
                            matches.append(app_commands.Choice(name=name, value=name))
                            seen.add(name_lower)

        # Strategy 4: Final pass with limited dataset if still not enough
        if len(matches) < 25:
            # Only search first 200 items as fallback
            for item in self.items_data[:200]:
                if len(matches) >= 25:
                    break

                name = item["name"]
                name_lower = name.lower()

                if current_lower in name_lower and name_lower not in seen:
                    matches.append(app_commands.Choice(name=name, value=name))
                    seen.add(name_lower)

        # Sort by relevance: exact > startswith > contains
        exact = [m for m in matches if m.name.lower() == current_lower]
        starts = [
            m
            for m in matches
            if m.name.lower().startswith(current_lower)
            and m.name.lower() != current_lower
        ]
        contains = [m for m in matches if m not in exact and m not in starts]

        return (exact + starts + contains)[:25]

    def format_time_ago(self, timestamp: Optional[int]) -> str:
        """Format timestamp as relative time."""
        if not timestamp:
            return "Never"
        return f"<t:{int(timestamp)}:R>"

    def calculate_profit_metrics(
        self, buy_price: int, sell_price: int, limit: int, tax_rate: float = 0.02
    ) -> Dict:
        """Calculate comprehensive profit metrics."""
        if not buy_price or not sell_price or not limit:
            return {"error": "Insufficient data"}

        # GE tax calculation (1% for most items, 0% for some)
        ge_tax = int(sell_price * tax_rate)
        profit_per_item = sell_price - buy_price - ge_tax

        # Different scenarios
        max_profit = profit_per_item * limit
        roi_percent = (profit_per_item / buy_price) * 100 if buy_price > 0 else 0

        # Investment required
        total_investment = buy_price * limit

        # Profit margin analysis
        margin_percent = (profit_per_item / sell_price) * 100 if sell_price > 0 else 0

        return {
            "profit_per_item": int(profit_per_item),
            "max_profit": int(max_profit),
            "roi_percent": roi_percent,
            "margin_percent": margin_percent,
            "total_investment": total_investment,
            "ge_tax": int(ge_tax),
            "effective_sell_price": int(sell_price - ge_tax),
        }

    async def build_price_embed(self, item_id: int, item_name: str) -> discord.Embed:
        """Build comprehensive price information embed."""
        latest, history, volume_24h_data = await self.fetch_comprehensive_data(item_id)

        if not latest:
            return discord.Embed(
                title="❌ Error",
                description="Market data not available for this item.",
                color=discord.Color.red(),
            )

        item_info = self.id_to_item.get(item_id, {})

        # Basic price data
        high = latest.get("high") or 0
        low = latest.get("low") or 0
        buy_price = low  # Buy at low price
        sell_price = high  # Sell at high price

        # Timestamps
        last_buy_time = self.format_time_ago(latest.get("lowTime"))
        last_sell_time = self.format_time_ago(latest.get("highTime"))

        # Get comprehensive price history
        day_prices_high = []
        day_prices_low = []

        if history.get("5m"):
            # Last 24 hours of 5-minute data
            recent_5m = history["5m"][-288:]  # 24h * 12 (5min intervals)
            day_prices_high = [
                dp.get("avgHighPrice", 0) for dp in recent_5m if dp.get("avgHighPrice")
            ]
            day_prices_low = [
                dp.get("avgLowPrice", 0) for dp in recent_5m if dp.get("avgLowPrice")
            ]

        day_high = max(day_prices_high) if day_prices_high else 0
        day_low = min([p for p in day_prices_low if p > 0], default=0)

        # Volume analysis using 24h timeseries data (same as decant checker)
        avg_vol_low_24h = volume_24h_data.get("avgLowVolume", 0)
        avg_vol_high_24h = volume_24h_data.get("avgHighVolume", 0)
        total_24h_volume = avg_vol_low_24h + avg_vol_high_24h

        # Get recent 5m volumes for current activity
        current_vol_high = 0
        current_vol_low = 0
        if history.get("5m") and len(history["5m"]) > 0:
            recent_5m = history["5m"][-1]  # Most recent 5m data
            current_vol_high = recent_5m.get("highPriceVolume", 0)
            current_vol_low = recent_5m.get("lowPriceVolume", 0)

        # Market analysis
        market_status = self.analyzer.get_market_status(
            buy_price, sell_price, current_vol_high, current_vol_low
        )
        price_trend, trend_percent = self.analyzer.calculate_price_trend(
            day_prices_low[-10:] if day_prices_low else []
        )
        volatility_status, volatility_percent = self.analyzer.calculate_volatility(
            day_prices_low if day_prices_low else []
        )

        # Item metadata
        limit = item_info.get("limit", 0)
        highalch = item_info.get("highalch", 0)
        value = item_info.get("value", 0)
        members = "Members" if item_info.get("members") else "F2P"

        embed = discord.Embed(
            title=f"📊 {item_name}",
            description=(
                f"**ID:** {item_id} | **Type:** {members}\n"
                f"**Status:** {market_status}"
            ),
            color=discord.Color.blue(),
            timestamp=datetime.now(timezone.utc),
        )

        # Current Prices
        spread = sell_price - buy_price
        spread_percent = (spread / buy_price * 100) if buy_price > 0 else 0

        embed.add_field(
            name="💰 Current Prices",
            value=(
                f"**Buy (Insta-sell):** {buy_price:,} gp {last_buy_time}\n"
                f"**Sell (Insta-buy):** {sell_price:,} gp {last_sell_time}\n"
                f"**Spread:** {spread:,} gp ({spread_percent:.1f}%)\n"
                f"**Trend:** {price_trend} ({trend_percent:+.1f}%)"
            ),
            inline=True,
        )

        # 24H Statistics (now using consistent volume calculation)
        embed.add_field(
            name="📈 24H Statistics",
            value=(
                f"**24H High:** {day_high:,} gp\n"
                f"**24H Low:** {day_low:,} gp\n"
                f"**Volatility:** {volatility_status} ({volatility_percent:.1f}%)\n"
                f"**24H Volume:** {total_24h_volume:,} items"
            ),
            inline=True,
        )

        # Trading Information
        profit_metrics = self.calculate_profit_metrics(buy_price, sell_price, limit)

        embed.add_field(
            name="🏪 Trading Info",
            value=(
                f"**Buy Limit:** {limit:,} items\n"
                f"**High Alch:** {highalch:,} gp\n"
                f"**Shop Value:** {value:,} gp\n"
                f"**Max Investment:** {buy_price * limit:,} gp"
            ),
            inline=True,
        )

        # Quick Profit Overview
        if not profit_metrics.get("error"):
            profit_color = "🟢" if profit_metrics["profit_per_item"] > 0 else "🔴"
            embed.add_field(
                name=f"{profit_color} Quick Profit",
                value=(
                    f"**Per Item:** {profit_metrics['profit_per_item']:,} gp\n"
                    f"**Max Profit:** {profit_metrics['max_profit']:,} gp\n"
                    f"**ROI:** {profit_metrics['roi_percent']:.1f}%\n"
                    f"**GE Tax:** {profit_metrics['ge_tax']:,} gp"
                ),
                inline=True,
            )

        # Recent Activity (showing both 5m current + 24h averages)
        embed.add_field(
            name="📊 Recent Activity",
            value=(
                f"**Buy Volume (5m):** {current_vol_low:,}\n"
                f"**Sell Volume (5m):** {current_vol_high:,}\n"
                f"**24H Avg Buy Vol:** {avg_vol_low_24h:,}\n"
                f"**24H Avg Sell Vol:** {avg_vol_high_24h:,}"
            ),
            inline=True,
        )

        # Add item image
        embed.set_thumbnail(url=f"https://prices.runescape.wiki/img/{item_id}.png")
        embed.set_footer(
            text="Use buttons below for detailed analysis • Data from OSRS Wiki"
        )

        return embed

    async def build_analysis_embed(self, item_id: int, item_name: str) -> discord.Embed:
        """Build detailed market analysis embed."""
        latest, history, volume_24h_data = await self.fetch_comprehensive_data(item_id)

        embed = discord.Embed(
            title=f"📊 Market Analysis: {item_name}",
            color=discord.Color.purple(),
            timestamp=datetime.now(timezone.utc),
        )

        # Analyze price history across different timeframes
        timeframe_analysis = {}
        for tf in ["1h", "6h", "24h"]:
            if history.get(tf):
                prices = [
                    dp.get("avgLowPrice", 0)
                    for dp in history[tf][-10:]
                    if dp.get("avgLowPrice")
                ]
                volumes = [
                    dp.get("lowPriceVolume", 0) + dp.get("highPriceVolume", 0)
                    for dp in history[tf][-10:]
                ]

                trend, trend_pct = self.analyzer.calculate_price_trend(prices)
                vol_trend, vol_ratio = self.analyzer.analyze_volume_trend(volumes)

                timeframe_analysis[tf] = {
                    "trend": trend,
                    "trend_percent": trend_pct,
                    "volume_trend": vol_trend,
                    "volume_ratio": vol_ratio,
                    "avg_price": mean(prices) if prices else 0,
                    "avg_volume": mean(volumes) if volumes else 0,
                }

        # Price Analysis
        analysis_text = ""
        for tf, data in timeframe_analysis.items():
            analysis_text += f"**{tf.upper()}:** {data['trend']} ({data['trend_percent']:+.1f}%) | Vol: {data['volume_trend']}\n"

        embed.add_field(
            name="📈 Price Trends",
            value=analysis_text or "Insufficient data for trend analysis",
            inline=False,
        )

        # Market Insights
        insights = []
        if timeframe_analysis.get("1h", {}).get("trend_percent", 0) < -10:
            insights.append("⚠️ Rapid price decline in last hour")
        if timeframe_analysis.get("24h", {}).get("volume_ratio", 1) > 2:
            insights.append("🔥 High trading activity detected")

        latest_data = latest or {}
        buy_price = latest_data.get("low", 0)
        sell_price = latest_data.get("high", 0)

        if buy_price and sell_price:
            spread_pct = ((sell_price - buy_price) / buy_price) * 100
            if spread_pct > 15:
                insights.append("💸 Wide spread - low liquidity")
            elif spread_pct < 2:
                insights.append("🎯 Tight spread - high liquidity")

        if insights:
            embed.add_field(
                name="💡 Market Insights", value="\n".join(insights), inline=False
            )

        return embed

    async def build_profit_embed(self, item_id: int, item_name: str) -> discord.Embed:
        """Build detailed profit analysis embed."""
        latest, history, volume_24h_data = await self.fetch_comprehensive_data(item_id)
        item_info = self.id_to_item.get(item_id, {})

        embed = discord.Embed(
            title=f"💰 Profit Analysis: {item_name}",
            color=discord.Color.gold(),
            timestamp=datetime.now(timezone.utc),
        )

        buy_price = latest.get("low", 0) if latest else 0
        sell_price = latest.get("high", 0) if latest else 0
        limit = item_info.get("limit", 0)
        highalch = item_info.get("highalch", 0)

        if not all([buy_price, sell_price, limit]):
            embed.description = "❌ Insufficient data for profit analysis"
            return embed

        # Comprehensive profit analysis
        profit_metrics = self.calculate_profit_metrics(buy_price, sell_price, limit)

        # Flipping Analysis
        embed.add_field(
            name="🔄 Flipping Analysis",
            value=(
                f"**Buy at:** {buy_price:,} gp\n"
                f"**Sell at:** {sell_price:,} gp (after tax: {profit_metrics['effective_sell_price']:,} gp)\n"
                f"**Profit per item:** {profit_metrics['profit_per_item']:,} gp\n"
                f"**ROI:** {profit_metrics['roi_percent']:.2f}%\n"
                f"**Margin:** {profit_metrics['margin_percent']:.2f}%"
            ),
            inline=True,
        )

        # Investment Analysis
        embed.add_field(
            name="💼 Investment Breakdown",
            value=(
                f"**Total Investment:** {profit_metrics['total_investment']:,} gp\n"
                f"**Max Profit:** {profit_metrics['max_profit']:,} gp\n"
                f"**GE Tax (2%):** {profit_metrics['ge_tax']:,} gp\n"
                f"**Buy Limit:** {limit:,} items\n"
                f"**Trades Needed:** 1"
            ),
            inline=True,
        )

        # Alternative Strategies
        alch_profit = highalch - buy_price if highalch and buy_price else 0
        strategies = []

        if alch_profit > 0:
            strategies.append(f"**High Alch:** {alch_profit:,} gp profit per item")

        if profit_metrics["profit_per_item"] > 0:
            strategies.append(
                f"**Flipping:** {profit_metrics['profit_per_item']:,} gp profit per item"
            )

        if strategies:
            embed.add_field(
                name="🎯 Strategy Comparison", value="\n".join(strategies), inline=False
            )

        # Risk Assessment
        risk_factors = []
        if profit_metrics["roi_percent"] > 10:
            risk_factors.append("🟢 High ROI opportunity")
        elif profit_metrics["roi_percent"] > 3:
            risk_factors.append("🟡 Moderate profit potential")
        else:
            risk_factors.append("🔴 Low profit margin")

        if profit_metrics["total_investment"] > 10000000:  # 10M+
            risk_factors.append("⚠️ High capital requirement")

        embed.add_field(
            name="⚖️ Risk Assessment",
            value="\n".join(risk_factors) if risk_factors else "Low risk opportunity",
            inline=False,
        )

        return embed

    @app_commands.command(
        name="osrs-price",
        description="Get comprehensive OSRS item market data and analysis",
    )
    @app_commands.describe(item="Name of the item to analyze")
    @app_commands.autocomplete(item=item_autocomplete)
    @app_commands.allowed_installs(guilds=True, users=True)
    @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
    async def osrs_price(self, interaction: discord.Interaction, item: str):
        await interaction.response.defer()

        item_id = self.name_to_id.get(item.lower())
        if not item_id:
            embed = discord.Embed(
                title="❌ Item Not Found",
                description=f"Could not find an item named '{item}'. Try using the autocomplete suggestions.",
                color=discord.Color.red(),
            )
            await interaction.followup.send(embed=embed, ephemeral=True)
            return

        try:
            embed = await self.build_price_embed(item_id, item)
            view = RefreshView(self, item_id, item, timeout=3600)  # 10 minute timeout
            await interaction.followup.send(embed=embed, view=view)
        except Exception as e:
            self.bot.logger.error(f"[PriceChecker] Error building embed: {e}")
            error_embed = discord.Embed(
                title="❌ Error",
                description="Failed to fetch market data. Please try again later.",
                color=discord.Color.red(),
            )
            await interaction.followup.send(embed=error_embed, ephemeral=True)


async def setup(bot: commands.Bot):
    cog = EnhancedPriceChecker(bot)
    await cog.load_items()
    await bot.add_cog(cog)
