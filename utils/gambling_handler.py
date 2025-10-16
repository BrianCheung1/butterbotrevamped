from typing import Callable, Optional, Dict
from dataclasses import dataclass
from enum import Enum

import discord
from constants.game_config import GameEventType
from utils.formatting import format_number
from logger import setup_logger

logger = setup_logger("GamblingHandler")


class GameType(Enum):
    """Enum for different game types."""

    ROLL = "roll"
    SLOTS = "slots"
    BLACKJACK = "blackjack"
    ROULETTE = "roulette"


@dataclass
class GameResult:
    """Unified result for any gambling game."""

    # Outcome
    win_status: bool  # True = win, False = loss, None = tie
    outcome_amount: int  # Amount won (positive) or lost (negative)

    # Display
    title: str  # e.g., "🎲 Dice Roll Result"
    description: str  # Main result text
    color: discord.Color
    footer_text: Optional[str] = None
    extra_fields: Optional[Dict[str, str]] = None  # Additional embed fields

    # Game-specific display
    content: Optional[str] = None  # For slots board display, etc

    # Stats
    final_balance: int = 0
    prev_balance: int = 0
    bet_amount: int = 0
    multiplier: int = 1


async def execute_gambling_game(
    bot,
    interaction: discord.Interaction,
    user_id: int,
    amount: int,
    game_func: Callable,
    game_type: GameType,
    prev_balance: Optional[int] = None,
    add_play_again_button: bool = True,
    play_again_label: str = "Play Again",
    action: Optional[str] = None,
) -> None:
    """
    Unified executor for any gambling game.

    Args:
        bot: Discord bot instance
        interaction: Discord interaction
        user_id: User ID performing the action
        amount: Amount bet
        game_func: Async function(bot, user_id, amount, prev_balance) -> GameResult
        game_type: Type of game being played
        prev_balance: Optional pre-fetched balance (avoids extra DB call)
        add_play_again_button: Whether to add a "Play Again" button
        play_again_label: Custom label for play again button
        action: Optional action string (for percentage-based bets)

    Usage:
        await execute_gambling_game(
            bot, interaction, user_id, amount,
            game_func=perform_roll,
            game_type=GameType.ROLL,
            prev_balance=balance,
            add_play_again_button=True,
            play_again_label="Roll Again",
            action=action_choice
        )
    """
    if prev_balance is None:
        prev_balance = await bot.database.user_db.get_balance(user_id)

    try:
        # Execute game logic
        result = await game_func(bot, user_id, amount, prev_balance)
        result.prev_balance = prev_balance
        result.bet_amount = amount
        result.final_balance = prev_balance + result.outcome_amount

        # Update balance
        await bot.database.user_db.increment_balance(user_id, result.outcome_amount)

        # Log game stats
        await bot.database.game_db.set_user_game_stats(
            user_id,
            GameEventType[game_type.value.upper()],
            result.win_status,
            amount * result.multiplier if result.win_status else amount,
        )

    except Exception as e:
        logger.error(f"Game execution failed for {game_type.value}: {e}", exc_info=True)

        # Send error message to user
        error_embed = discord.Embed(
            title="❌ Game Error",
            description="An error occurred while processing your game. Please try again.",
            color=discord.Color.red(),
        )
        await interaction.edit_original_response(embed=error_embed, view=None)
        return

    # Build embed
    embed = _create_game_embed(result)

    # Create view if requested
    view = None
    if add_play_again_button:
        view = GameAgainView(
            bot,
            user_id,
            amount if not action else None,
            action,
            game_func,
            game_type,
            button_label=play_again_label,
        )

    # Send response
    content = result.content if result.content else None
    await interaction.edit_original_response(content=content, embed=embed, view=view)

    # Store message reference in view
    if view:
        try:
            msg = await interaction.original_response()
            view.message = msg
            view.message_id = msg.id
            view.channel = interaction.channel
        except Exception as e:
            logger.debug(f"Could not store message reference: {e}")

    logger.debug(
        f"Game {game_type.value} completed: user={user_id}, bet={amount}, "
        f"outcome={result.outcome_amount}, win={result.win_status}"
    )


def _create_game_embed(result: GameResult) -> discord.Embed:
    """Create standardized game result embed."""
    embed = discord.Embed(
        title=result.title,
        description=result.description,
        color=result.color,
    )

    embed.add_field(
        name="Bet Amount",
        value=f"${format_number(result.bet_amount)}",
        inline=True,
    )
    embed.add_field(
        name="Previous Balance",
        value=f"${format_number(result.prev_balance)}",
        inline=True,
    )
    embed.add_field(
        name="Current Balance",
        value=f"${format_number(result.final_balance)}",
        inline=True,
    )

    # Add extra fields if provided
    if result.extra_fields:
        for field_name, field_value in result.extra_fields.items():
            embed.add_field(name=field_name, value=field_value, inline=False)

    if result.footer_text:
        embed.set_footer(text=result.footer_text)

    return embed


class GameAgainView(discord.ui.View):
    """
    Generic reusable view for all gambling games with "Play Again" button.

    Usage:
        view = GameAgainView(bot, user_id, amount, action, perform_game, GameType.ROLL)
        view.message = await interaction.followup.send(embed=embed, view=view)
    """

    def __init__(
        self,
        bot,
        user_id: int,
        amount: Optional[int],
        action: Optional[str],
        game_func: Callable,
        game_type: GameType,
        button_label: str = "Play Again",
    ):
        super().__init__(timeout=300)
        self.bot = bot
        self.user_id = user_id
        self.amount = amount
        self.action = action
        self.game_func = game_func
        self.game_type = game_type
        self.message = None
        self.message_id = None
        self.channel = None

        # Update button label
        self.play_again_btn.label = button_label

    async def on_timeout(self):
        """Disable buttons on timeout."""
        for child in self.children:
            if isinstance(child, discord.ui.Button):
                child.disabled = True

        if self.message_id and self.channel:
            try:
                message = await self.channel.fetch_message(self.message_id)
                await message.edit(view=self)
            except discord.HTTPException:
                logger.debug(
                    f"Game message expired or timed out (ID: {self.message_id})"
                )

    @discord.ui.button(label="Play Again", style=discord.ButtonStyle.green)
    async def play_again_btn(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        """Handle play again button."""
        if interaction.user.id != self.user_id:
            await interaction.followup.send(
                content="You can't use this button.", ephemeral=True
            )
            return

        await interaction.response.defer()

        # Fetch current balance
        current_balance = await self.bot.database.user_db.get_balance(self.user_id)

        # Calculate bet amount
        from utils.balance_helper import calculate_percentage_amount

        logger.info(
            f"Action: {self.action}, Amount: {self.amount}, Current Balance: {current_balance}"
        )

        if self.action:
            # Always recalculate percentage based on current balance
            bet_amount = calculate_percentage_amount(current_balance, self.action)
        elif self.amount:
            # Use the fixed amount
            bet_amount = self.amount

        # Validate balance
        from utils.balance_helper import validate_amount

        error = validate_amount(bet_amount, current_balance)
        if error:
            await interaction.edit_original_response(content=error, view=None)
            return

        # Execute game using generic handler, passing action to preserve percentage behavior
        await execute_gambling_game(
            self.bot,
            interaction,
            self.user_id,
            bet_amount,
            game_func=self.game_func,
            game_type=self.game_type,
            prev_balance=current_balance,
            action=self.action,  # CRITICAL FIX: Pass action to preserve percentage behavior
        )

        # Get updated message and attach this view to it for next play
        try:
            updated_msg = await interaction.original_response()
            self.message = updated_msg
            self.message_id = updated_msg.id
        except Exception as e:
            logger.debug(f"Could not fetch updated message: {e}")
