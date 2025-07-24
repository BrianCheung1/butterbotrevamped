from datetime import datetime, timezone
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands
from utils.autcomplete import patch_number_autocomplete


class ViewPatchNote(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="patchnote-view", description="View saved patch notes")
    @app_commands.describe(
        patch_number="(Optional) Patch number to view (e.g., 1 for latest)"
    )
    @app_commands.allowed_installs(guilds=True, users=True)
    @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
    @app_commands.autocomplete(patch_number=patch_number_autocomplete)
    async def patchnotes_view(
        self, interaction: discord.Interaction, patch_number: Optional[int] = None
    ):
        await interaction.response.defer()

        entries = await self.bot.database.patch_notes_db.get_all_patch_notes()
        entries.sort(key=lambda e: e["timestamp"], reverse=True)  # Latest first

        if not entries:
            await interaction.followup.send("No patch notes available yet.")
            return
        if patch_number is not None:
            index = len(entries) - patch_number  # Flip display to match sorted list

            if index < 0 or index >= len(entries):
                await interaction.followup.send(
                    f"Patch note #{patch_number} not found.", ephemeral=True
                )
                return

            entry = entries[index]
            changes = "\n".join(
                f"- {item.strip().capitalize()}"
                for item in entry["changes"].split(";")
                if item.strip()
            )
            timestamp_dt = datetime.fromisoformat(entry["timestamp"]).replace(
                tzinfo=timezone.utc
            )

            embed = discord.Embed(
                title=f"🛠️ Patch #{patch_number}",
                description=changes,
                color=discord.Color.blue(),
                timestamp=timestamp_dt,
            )
            embed.set_footer(text=f"By {entry['author_name']}")
            if entry["image_url"]:
                embed.set_image(url=entry["image_url"])

            await interaction.followup.send(embed=embed)
            if interaction.user.id == entry["author_id"]:
                raw_changes = entry["changes"].strip()
                await interaction.followup.send(
                    f"📝 Here's your unformatted patch note for editing:\n```\n{raw_changes}\n```",
                    ephemeral=True,
                )
        else:
            # Show all patch notes with pagination
            view = PatchNotesView(entries, interaction.user)
            embed = view.create_embed()
            await interaction.followup.send(embed=embed, view=view)


class PatchNotesView(discord.ui.View):
    def __init__(self, entries: list[dict], user: discord.User):
        super().__init__(timeout=60)
        self.entries = entries
        self.user = user
        self.page = 0
        self.max_page = len(entries) - 1
        self.update_buttons()

    def update_buttons(self):
        self.prev_button.disabled = self.page == 0
        self.next_button.disabled = self.page == self.max_page

    def create_embed(self) -> discord.Embed:
        entry = self.entries[self.page]
        display_number = len(self.entries) - self.page  # Patch #N, not #1

        changes = "\n".join(
            f"- {item.strip().capitalize()}"
            for item in entry["changes"].split(";")
            if item.strip()
        )
        timestamp_dt = datetime.fromisoformat(entry["timestamp"]).replace(
            tzinfo=timezone.utc
        )

        embed = discord.Embed(
            title=f"🛠️ Patch #{display_number}",
            description=changes,
            color=discord.Color.blue(),
            timestamp=timestamp_dt,
        )
        embed.set_footer(
            text=f"By {entry['author_name']} • Page {self.page + 1}/{self.max_page + 1}"
        )
        if entry["image_url"]:
            embed.set_image(url=entry["image_url"])
        return embed

    @discord.ui.button(label="⬅ Previous", style=discord.ButtonStyle.gray)
    async def prev_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        if interaction.user != self.user:
            await interaction.response.send_message(
                "You're not allowed to use these buttons.", ephemeral=True
            )
            return

        self.page -= 1
        self.update_buttons()
        await interaction.response.edit_message(embed=self.create_embed(), view=self)

    @discord.ui.button(label="➡ Next", style=discord.ButtonStyle.gray)
    async def next_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        if interaction.user != self.user:
            await interaction.response.send_message(
                "You're not allowed to use these buttons.", ephemeral=True
            )
            return

        self.page += 1
        self.update_buttons()
        await interaction.response.edit_message(embed=self.create_embed(), view=self)


async def setup(bot):
    await bot.add_cog(ViewPatchNote(bot))
