import discord
from discord import app_commands
from discord.ext import commands
from datetime import datetime, timezone

REMINDERS_PER_PAGE = 10


class RemindersPaginator(discord.ui.View):
    def __init__(self, reminders: list[tuple[int, str, str]], author_id: int):
        # If no pagination needed, disable buttons immediately
        self.reminders = reminders
        self.author_id = author_id
        self.current_page = 0
        self.max_page = (len(reminders) - 1) // REMINDERS_PER_PAGE
        timeout = 120  # seconds

        super().__init__(timeout=timeout)

        # Disable buttons if only one page or no reminders
        if self.max_page == 0:
            self.previous_button.disabled = True
            self.next_button.disabled = True

    def format_embed(self) -> discord.Embed:
        start = self.current_page * REMINDERS_PER_PAGE
        end = start + REMINDERS_PER_PAGE
        page_items = self.reminders[start:end]

        embed = discord.Embed(
            title=f"Your Reminders (Page {self.current_page + 1}/{self.max_page + 1})",
            color=discord.Color.blurple(),
        )

        if not page_items:
            embed.description = "No reminders on this page."
            return embed

        self.index_to_id = {}  # map from displayed index to actual reminder ID
        lines = []
        for i, (reminder_id, reminder_text, remind_at_str) in enumerate(
            page_items, start=1
        ):
            remind_at = datetime.fromisoformat(remind_at_str)
            timestamp = int(remind_at.replace(tzinfo=timezone.utc).timestamp())
            lines.append(
                f"**{i}.** <t:{timestamp}:F> (<t:{timestamp}:R>)\n{reminder_text}"
            )
            self.index_to_id[i] = reminder_id

        embed.description = "\n\n".join(lines)
        return embed

    async def update_message(self, interaction: discord.Interaction):
        embed = self.format_embed()
        # Update button states for first/last page
        self.previous_button.disabled = self.current_page == 0
        self.next_button.disabled = self.current_page == self.max_page
        await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label="Previous", style=discord.ButtonStyle.secondary)
    async def previous_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        if interaction.user.id != self.author_id:
            return await interaction.response.send_message(
                "This is not your paginator!", ephemeral=True
            )

        if self.current_page > 0:
            self.current_page -= 1
            await self.update_message(interaction)
        else:
            await interaction.response.defer()

    @discord.ui.button(label="Next", style=discord.ButtonStyle.secondary)
    async def next_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        if interaction.user.id != self.author_id:
            return await interaction.response.send_message(
                "This is not your paginator!", ephemeral=True
            )

        if self.current_page < self.max_page:
            self.current_page += 1
            await self.update_message(interaction)
        else:
            await interaction.response.defer()

    async def on_timeout(self):
        for child in self.children:
            child.disabled = True
        # Optionally edit the message to disable buttons on timeout
        # You can keep a reference to the message if you want to edit it here


class RemindList(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(
        name="reminders-list", description="List all your active reminders"
    )
    async def reminders_list(self, interaction: discord.Interaction):
        reminders = await self.bot.database.reminders_db.get_user_reminders(
            interaction.user.id
        )
        if not reminders:
            return await interaction.response.send_message(
                "You have no active reminders.", ephemeral=True
            )

        paginator = RemindersPaginator(reminders, interaction.user.id)
        embed = paginator.format_embed()
        await interaction.response.send_message(
            embed=embed, view=paginator, ephemeral=True
        )


async def setup(bot):
    await bot.add_cog(RemindList(bot))
