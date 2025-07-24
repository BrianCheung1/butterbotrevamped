import os

import discord
from discord import app_commands
from discord.ext import commands
from utils.autcomplete import patch_number_autocomplete
from utils.checks import is_owner_check

DEV_GUILD_ID = int(os.getenv("DEV_GUILD_ID"))


class DeletePatchNote(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(
        name="patchnote-delete",
        description="Delete a patch note by its visible number",
    )
    @app_commands.describe(
        patch_number="The visible patch number to delete (e.g., 1 = oldest, N = latest)"
    )
    @app_commands.check(is_owner_check)
    @app_commands.guilds(DEV_GUILD_ID)
    @app_commands.autocomplete(patch_number=patch_number_autocomplete)
    async def patchnotes_delete(
        self, interaction: discord.Interaction, patch_number: int
    ):
        # Fetch and sort entries (latest first)
        entries = await self.bot.database.patch_notes_db.get_all_patch_notes()
        entries.sort(key=lambda e: e["timestamp"], reverse=True)

        # Convert visible number to index
        index = len(entries) - patch_number

        if index < 0 or index >= len(entries):
            await interaction.response.send_message(
                f"Patch note #{patch_number} not found.", ephemeral=True
            )
            return

        note = entries[index]
        await self.bot.database.patch_notes_db.delete_patch_note_by_id(note["id"])

        await interaction.response.send_message(
            f"✅ Patch note #{patch_number} (ID: {note['id']}) deleted successfully."
        )


async def setup(bot):
    await bot.add_cog(DeletePatchNote(bot))
