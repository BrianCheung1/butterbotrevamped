import os

import discord
from discord import app_commands
from discord.ext import commands
from utils.checks import is_owner_check

DEV_GUILD_ID = int(os.getenv("DEV_GUILD_ID"))


class DeletePatchNote(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(
        name="patchnotes-delete", description="Delete a patch note by its ID"
    )
    @app_commands.describe(patch_id="The patch note ID to delete")
    @app_commands.check(is_owner_check)
    @app_commands.guilds(DEV_GUILD_ID)
    async def patchnotes_delete(self, interaction: discord.Interaction, patch_id: int):
        # Check if patch note exists
        note = await self.bot.database.patch_notes_db.get_patch_note_by_id(patch_id)
        if not note:
            await interaction.response.send_message(
                f"Patch note #{patch_id} not found.", ephemeral=True
            )
            return

        # Delete patch note
        await self.bot.database.patch_notes_db.delete_patch_note_by_id(patch_id)
        await interaction.response.send_message(
            f"Patch note #{patch_id} deleted successfully."
        )


async def setup(bot):
    await bot.add_cog(DeletePatchNote(bot))
