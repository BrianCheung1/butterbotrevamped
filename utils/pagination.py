from typing import List, Callable
import discord


class PaginatedView(discord.ui.View):
    """Reusable paginated view base class."""

    def __init__(
        self,
        data: List,
        interaction: discord.Interaction,
        entries_per_page: int = 10,
        timeout: float = 300,
    ):
        super().__init__(timeout=timeout)
        self.data = data
        self.interaction = interaction
        self.page = 0
        self.entries_per_page = entries_per_page
        self.max_page = max(0, (len(data) - 1) // entries_per_page)

        self.prev_button.disabled = True
        if self.max_page <= 0:
            self.next_button.disabled = True

    def generate_embed(self) -> discord.Embed:
        """Override in subclass."""
        raise NotImplementedError

    @discord.ui.button(label="⬅ Previous", style=discord.ButtonStyle.gray)
    async def prev_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        if interaction.user != self.interaction.user:
            await interaction.response.send_message(
                "You're not allowed to control this pagination.", ephemeral=True
            )
            return
        self.page = max(self.page - 1, 0)
        self.prev_button.disabled = self.page == 0
        self.next_button.disabled = False
        await interaction.response.edit_message(embed=self.generate_embed(), view=self)

    @discord.ui.button(label="➡ Next", style=discord.ButtonStyle.gray)
    async def next_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        if interaction.user != self.interaction.user:
            await interaction.response.send_message(
                "You're not allowed to control this pagination.", ephemeral=True
            )
            return
        self.page = min(self.page + 1, self.max_page)
        self.next_button.disabled = self.page == self.max_page
        self.prev_button.disabled = False
        await interaction.response.edit_message(embed=self.generate_embed(), view=self)
