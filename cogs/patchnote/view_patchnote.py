from datetime import datetime, timezone
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands


class ViewPatchNote(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="patchnotes-view", description="View saved patch notes")
    @app_commands.describe(patch_id="(Optional) Specific patch note ID to view")
    @app_commands.allowed_installs(guilds=True, users=True)
    @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
    async def patchnotes_view(
        self, interaction: discord.Interaction, patch_id: Optional[int] = None
    ):
        await interaction.response.defer()

        if patch_id is not None:
            # Show a single patch note by ID
            entry = await self.bot.database.patch_notes_db.get_patch_note_by_id(
                patch_id
            )
            if not entry:
                await interaction.followup.send(
                    f"Patch note #{patch_id} not found.", ephemeral=True
                )
                return

            changes = "\n".join(
                f"- {item.strip().capitalize()}"
                for item in entry["changes"].split(";")
                if item.strip()
            )
            timestamp_dt = datetime.fromisoformat(entry["timestamp"]).replace(
                tzinfo=timezone.utc
            )

            embed = discord.Embed(
                title=f"🛠️ Patch Notes #{entry['id']}",
                description=changes,
                color=discord.Color.blue(),
                timestamp=timestamp_dt,
            )
            embed.set_footer(text=f"By {entry['author_name']}")
            embed.set_image(url=entry["image_url"]) if entry["image_url"] else None

            await interaction.followup.send(embed=embed)

        else:
            # Show all patch notes with pagination
            entries = await self.bot.database.patch_notes_db.get_all_patch_notes()

            if not entries:
                await interaction.followup.send("No patch notes available yet.")
                return

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

        changes = "\n".join(
            f"- {item.strip().capitalize()}"
            for item in entry["changes"].split(";")
            if item.strip()
        )
        timestamp_dt = datetime.fromisoformat(entry["timestamp"]).replace(
            tzinfo=timezone.utc
        )

        embed = discord.Embed(
            title=f"🛠️ Patch #{entry['id']} Notes",
            description=changes,
            color=discord.Color.blue(),
            timestamp=timestamp_dt,
        )
        embed.set_footer(
            text=f"By {entry['author_name']} • Page {self.page + 1}/{self.max_page + 1}"
        )
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
