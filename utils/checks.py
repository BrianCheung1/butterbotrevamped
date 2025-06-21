import discord
import os
from logger import setup_logger

logger = setup_logger("ChecksHandler")


OWNER_ID = int(os.getenv("OWNER_ID"))


def is_owner_or_mod_check(interaction: discord.Interaction) -> bool:
    try:
        if (
            interaction.user.id == interaction.client.owner_id
            or interaction.user.id == OWNER_ID
        ):
            return True

        # Check if user has moderator permissions in this guild
        if interaction.guild:
            member = interaction.guild.get_member(interaction.user.id)
            if member and member.guild_permissions.moderate_members:
                return True

        return False
    except Exception as e:
        logger.error(f"Error in is_owner_check: {e}", exc_info=True)


def is_owner_check(interaction: discord.Interaction) -> bool:
    try:
        if (
            interaction.user.id == interaction.client.owner_id
            or interaction.user.id == OWNER_ID
        ):
            return True
        return False
    except Exception as e:
        logger.error(f"Error in is_owner_check: {e}", exc_info=True)
