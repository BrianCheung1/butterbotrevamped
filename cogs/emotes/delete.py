import discord
from discord import app_commands
from discord.ext import commands


class DeleteEmote(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    # --- Autocomplete function ---
    async def emoji_autocomplete(
        self, interaction: discord.Interaction, current: str
    ) -> list[app_commands.Choice[str]]:
        """Autocomplete emojis by name"""
        choices = []
        for emoji in interaction.guild.emojis:
            # Filter by name if user typed something
            if current.lower() in emoji.name.lower():
                choices.append(
                    app_commands.Choice(
                        name=f"{emoji} {emoji.name}", value=str(emoji.id)
                    )
                )
        return choices[:25]  # Discord max autocomplete results = 25

    @app_commands.command(
        name="delete-emote", description="Delete an emoji from this server."
    )
    @app_commands.describe(emote="The emoji you want to delete")
    @app_commands.autocomplete(emote=emoji_autocomplete)
    async def delete_emote(self, interaction: discord.Interaction, emote: str):
        if not interaction.user.guild_permissions.manage_emojis_and_stickers:
            return await interaction.response.send_message(
                "❌ You need `Manage Emojis and Stickers` permission to delete emojis.",
                ephemeral=True,
            )

        # Find emoji by ID
        emoji = discord.utils.get(interaction.guild.emojis, id=int(emote))
        if not emoji:
            return await interaction.response.send_message(
                "❌ Emoji not found.", ephemeral=True
            )

        try:
            await emoji.delete(reason=f"Deleted by {interaction.user}")
            await interaction.response.send_message(
                f"🗑️ Emoji `{emoji.name}` was deleted successfully."
            )
        except Exception as e:
            await interaction.response.send_message(
                f"❌ Failed to delete emoji: {e}", ephemeral=True
            )


async def setup(bot):
    await bot.add_cog(DeleteEmote(bot))
