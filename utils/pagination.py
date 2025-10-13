from typing import List, Optional, Callable
import discord


class PaginatedView(discord.ui.View):
    """
    Unified reusable paginated view that supports both:
    1. Dynamic embed generation (original behavior)
    2. Pre-built embed lists (for complex paginated views)
    """

    def __init__(
        self,
        data: List,
        interaction: discord.Interaction,
        entries_per_page: int = 10,
        timeout: float = 300,
        pre_built_embeds: Optional[List[discord.Embed]] = None,
    ):
        super().__init__(timeout=timeout)
        self.data = data
        self.pre_built_embeds = pre_built_embeds
        self.interaction = interaction
        self.page = 0
        self.entries_per_page = entries_per_page

        if pre_built_embeds:
            # Use pre-built embeds
            self.max_page = len(pre_built_embeds) - 1
        else:
            # Calculate from data
            self.max_page = max(0, (len(data) - 1) // entries_per_page)

        self.prev_button.disabled = True
        if self.max_page <= 0:
            self.next_button.disabled = True

    async def on_timeout(self):
        """Disable buttons on timeout."""
        for child in self.children:
            child.disabled = True
        if self.interaction:
            try:
                await self.interaction.edit_original_response(view=self)
            except discord.HTTPException:
                pass

    def generate_embed(self) -> discord.Embed:
        """
        Override in subclass to generate embeds dynamically.
        If pre_built_embeds provided, returns from there instead.
        """
        if self.pre_built_embeds:
            return self.pre_built_embeds[self.page]

        raise NotImplementedError(
            "Override generate_embed() or provide pre_built_embeds"
        )

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
