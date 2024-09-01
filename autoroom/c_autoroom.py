import datetime
from abc import ABC
from typing import Any, Optional

import discord
from redbot.core import commands
from redbot.core.utils.chat_formatting import error, humanize_timedelta

from .abc import MixinMeta
from .pcx_lib import Perms, SettingDisplay, delete

MAX_CHANNEL_NAME_LENGTH = 100
MAX_BITRATE = 96  # Maximum bitrate in kbps
DEFAULT_REGION = "us-central"  # Set your preferred default region here

DEFAULT_DESCRIPTION = (
    "Use the buttons below to manage your channel.\n\n"
    " **Allow**: Allow a user to join the channel.\n"
    " **Bitrate**: Change the channel's bitrate.\n"
    " **Claim**: Claim ownership of the channel.\n"
    " **Deny**: Deny a user access to the channel.\n"
    " **Locked**: Lock the channel (no one can join).\n"
    " **Unlock**: Unlock the channel (everyone can join).\n"
    " **Name**: Change the channel's name.\n"
    " **Private**: Make the channel private.\n"
    " **Public**: Make the channel public.\n"
    " **Settings**: View current channel settings.\n"
    " **Users**: Set a user limit for the channel.\n"
    " **Region**: Change the voice region of the channel.\n"
    " **Transfer Owner**: Transfer channel ownership to another user.\n"
    "ℹ **Info**: View information about the current voice channel."
)

class AutoRoomCommands(MixinMeta, ABC):
    """The autoroom command."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    @commands.Cog.listener()
    async def on_interaction(self, interaction: discord.Interaction):
        """Handle button interactions."""
        if interaction.type != discord.InteractionType.component:
            return

        custom_id = interaction.data['custom_id']
        voice_channel = self._get_current_voice_channel(interaction.user)

        if not voice_channel:
            if not interaction.response.is_done():
                await interaction.response.send_message("You must be in a voice channel to use this command.", ephemeral=True)
            return

        autoroom_info = await self.get_autoroom_info(voice_channel)
        if not autoroom_info:
            if not interaction.response.is_done():
                await interaction.response.send_message("This voice channel is not managed by AutoRoom.", ephemeral=True)
            return

        # Check if the user is the owner of the channel or has override permissions
        if autoroom_info.get("owner") != interaction.user.id and not self._has_override_permissions(interaction.user, autoroom_info):
            owner_id = autoroom_info.get("owner")
            owner = interaction.guild.get_member(owner_id)
            owner_name = owner.display_name if owner else "Unknown"
            if not interaction.response.is_done():
                await interaction.response.send_message(
                    f"Only {owner_name} or an admin can control the panel.", ephemeral=True
                )
            return

        # Defer the interaction if needed
        if not interaction.response.is_done():
            await interaction.response.defer(ephemeral=True)

        # Handle the interaction
        if custom_id == "allow":
            await interaction.response.send_modal(AllowModal(self, voice_channel))
        elif custom_id == "bitrate":
            await interaction.response.send_modal(ChangeBitrateModal(self, voice_channel))
        elif custom_id == "claim":
            await self.claim(interaction, voice_channel)
        elif custom_id == "deny":
            await interaction.response.send_modal(DenyModal(self, voice_channel))
        elif custom_id == "locked":
            await self.locked(interaction, voice_channel)
        elif custom_id == "unlock":
            await self.unlock(interaction, voice_channel)
        elif custom_id == "name":
            await interaction.response.send_modal(ChangeNameModal(self, voice_channel))
        elif custom_id == "private":
            await self.private(interaction, voice_channel)
        elif custom_id == "public":
            await self.public(interaction, voice_channel)
        elif custom_id == "settings":
            await self.autoroom_settings(interaction, voice_channel)
        elif custom_id == "users":
            view = SetUserLimitView(self, voice_channel)
            await interaction.response.send_message("Select a user limit:", view=view, ephemeral=True)
        elif custom_id == "region":
            await self.change_region(interaction, voice_channel)
        elif custom_id == "transfer":
            await self.show_transfer_owner_menu(interaction, voice_channel)
        elif custom_id == "info":
            await self.info(interaction, voice_channel)

    async def info(self, interaction: discord.Interaction, channel: discord.VoiceChannel):
        """Provide information about the current voice channel."""
        autoroom_info = await self.get_autoroom_info(channel)
        owner_id = autoroom_info.get("owner")
        owner = interaction.guild.get_member(owner_id)
        owner_name = owner.display_name if owner else "None"
        owner_mention = owner.mention if owner else "None"

        # Convert channel.created_at to naive datetime for subtraction
        channel_age = datetime.datetime.utcnow() - channel.created_at.replace(tzinfo=None)
        bitrate = channel.bitrate // 1000  # Convert to kbps
        user_limit = channel.user_limit or "Unlimited"
        rtc_region = channel.rtc_region or "Automatic"

        embed = discord.Embed(title=f"Info for {channel.name}", color=0x7289da)
        embed.add_field(name="Owner", value=f"{owner_name} ({owner_mention})")
        embed.add_field(name="Age", value=humanize_timedelta(timedelta=channel_age))
        embed.add_field(name="Bitrate", value=f"{bitrate} kbps")
        embed.add_field(name="User Limit", value=user_limit)
        embed.add_field(name="Region", value=rtc_region)
        embed.add_field(name="Private", value="Yes" if self._get_autoroom_type(channel, interaction.guild.default_role) == "private" else "No")

        await interaction.response.send_message(embed=embed, ephemeral=True)

    async def autoroom_settings(self, interaction: discord.Interaction, channel: discord.VoiceChannel):
        """Display current settings."""
        autoroom_info = await self.get_autoroom_info(channel)
        if not autoroom_info:
            await interaction.response.send_message("This is not an AutoRoom.", ephemeral=True)
            return

        owner_id = autoroom_info.get("owner")
        owner = interaction.guild.get_member(owner_id)
        owner_name = owner.display_name if owner else "None"
        access_type = self._get_autoroom_type(channel, interaction.guild.default_role)
        allowed_users = [f"<@{user.id}>" for user in channel.members if channel.permissions_for(user).connect]
        denied_users = [f"<@{user.id}>" for user in channel.members if not channel.permissions_for(user).connect]

        embed = discord.Embed(title=f"Settings for {channel.name}", color=0x7289da)
        embed.add_field(name="Owner", value=owner_name)
        embed.add_field(name="Access Type", value=access_type.capitalize())
        embed.add_field(name="Allowed Users", value=", ".join(allowed_users) or "None")
        embed.add_field(name="Denied Users", value=", ".join(denied_users) or "None")
        embed.add_field(name="Bitrate", value=f"{channel.bitrate // 1000} kbps")
        embed.add_field(name="User Limit", value=channel.user_limit or "Unlimited")

        await interaction.response.send_message(embed=embed, ephemeral=True)

    async def unlock(self, interaction: discord.Interaction, channel: discord.VoiceChannel):
        """Unlock your AutoRoom."""
        await self._process_allow_deny(interaction, "allow", channel=channel)

    async def _process_allow_deny(self, interaction: discord.Interaction, action: str, channel: discord.VoiceChannel):
        """Process allowing or denying users/roles access to the AutoRoom."""
        if action == "allow":
            # Allow everyone to connect
            await channel.set_permissions(interaction.guild.default_role, connect=True)
            await interaction.followup.send("The AutoRoom is now public.", ephemeral=True)
        elif action == "deny":
            # Deny everyone from connecting
            await channel.set_permissions(interaction.guild.default_role, connect=False)
            await interaction.followup.send("The AutoRoom is now private.", ephemeral=True)
        elif action == "lock":
            # Lock the room: visible but no one can join
            await channel.set_permissions(interaction.guild.default_role, connect=False)
            await interaction.followup.send("The AutoRoom is now locked.", ephemeral=True)
        else:
            await interaction.followup.send("Invalid action.", ephemeral=True)

    async def show_transfer_owner_menu(self, interaction: discord.Interaction, channel: discord.VoiceChannel):
        """Show a dropdown menu to transfer ownership."""
        options = [
            discord.SelectOption(label=member.display_name, value=str(member.id))
            for member in channel.members if not member.bot
        ]

        if not options:
            await interaction.response.send_message("No available members to transfer ownership to.", ephemeral=True)
            return

        select = discord.ui.Select(placeholder="Select a new owner", options=options)

        async def select_callback(select_interaction: discord.Interaction):
            new_owner_id = int(select.values[0])
            new_owner = interaction.guild.get_member(new_owner_id)
            await self.config.channel(channel).owner.set(new_owner_id)
            await channel.edit(name=f"{new_owner.display_name}'s Channel")
            await select_interaction.response.send_message(f"Ownership transferred to {new_owner.display_name}.", ephemeral=True)

        select.callback = select_callback
        view = discord.ui.View()
        view.add_item(select)
        await interaction.response.send_message("Select a new owner from the list:", view=view, ephemeral=True)

    def _has_override_permissions(self, user: discord.Member, autoroom_info: dict) -> bool:
        """Check if the user has override permissions."""
        if user.guild_permissions.administrator:
            return True
        if user.id == user.guild.owner_id:
            return True
        return False

    @staticmethod
    def _get_current_voice_channel(member: discord.Member | discord.User) -> Optional[discord.VoiceChannel]:
        """Get the member's current voice channel, or None if not in a voice channel."""
        if isinstance(member, discord.Member) and member.voice and isinstance(member.voice.channel, discord.VoiceChannel):
            return member.voice.channel
        return None

    @staticmethod
    def _get_autoroom_type(autoroom: discord.VoiceChannel, role: discord.Role) -> str:
        """Get the type of access a role has in an AutoRoom (public, locked, private, etc)."""
        view_channel = role.permissions.view_channel
        connect = role.permissions.connect
        if role in autoroom.overwrites:
            overwrites_allow, overwrites_deny = autoroom.overwrites[role].pair()
            if overwrites_allow.view_channel:
                view_channel = True
            if overwrites_allow.connect:
                connect = True
            if overwrites_deny.view_channel:
                view_channel = False
            if overwrites_deny.connect:
                connect = False
        if not view_channel and not connect:
            return "private"
        if view_channel and not connect:
            return "locked"
        return "public"

# Modal Classes

class AllowModal(discord.ui.Modal, title="Allow User"):
    def __init__(self, cog, channel):
        self.cog = cog
        self.channel = channel
        super().__init__()

    user_input = discord.ui.TextInput(label="User ID or Username", custom_id="user_input", style=discord.TextStyle.short)

    async def on_submit(self, interaction: discord.Interaction):
        user_input = self.user_input.value
        user = await self.cog._get_user_from_input(interaction.guild, user_input)
        if user:
            await self.channel.set_permissions(user, connect=True)
            await interaction.response.send_message(f"{user.display_name} has been allowed to join the channel.", ephemeral=True)
        else:
            await interaction.response.send_message("User not found. Please enter a valid user ID or username.", ephemeral=True)


class DenyModal(discord.ui.Modal, title="Deny User or Role"):
    def __init__(self, cog, channel):
        self.cog = cog
        self.channel = channel
        super().__init__()

    role_or_user_input = discord.ui.TextInput(label="Role/User ID or Mention", custom_id="role_or_user_input", style=discord.TextStyle.short)

    async def on_submit(self, interaction: discord.Interaction):
        input_value = self.role_or_user_input.value
        user = await self.cog._get_user_from_input(interaction.guild, input_value)
        role = await self.cog._get_role_from_input(interaction.guild, input_value)

        if user:
            await self.channel.set_permissions(user, view_channel=False, connect=False)
            await interaction.response.send_message(f"{user.display_name} has been denied access to the channel.", ephemeral=True)
        elif role:
            await self.channel.set_permissions(role, view_channel=False, connect=False)
            await interaction.response.send_message(f"Role {role.name} has been denied access to the channel.", ephemeral=True)
        else:
            await interaction.response.send_message("Role or user not found. Please enter a valid ID or mention.", ephemeral=True)


class ChangeBitrateModal(discord.ui.Modal, title="Change Bitrate"):
    def __init__(self, cog, channel):
        self.cog = cog
        self.channel = channel
        super().__init__()

    bitrate_value = discord.ui.TextInput(label="Bitrate (kbps)", custom_id="bitrate_value", style=discord.TextStyle.short)

    async def on_submit(self, interaction: discord.Interaction):
        bitrate_value = self.bitrate_value.value
        if not bitrate_value.isdigit() or int(bitrate_value) > MAX_BITRATE:
            await interaction.response.send_message(f"Invalid bitrate. Please enter a value between 8 and {MAX_BITRATE} kbps.", ephemeral=True)
            return

        if self.channel:
            await self.channel.edit(bitrate=int(bitrate_value) * 1000)
            await interaction.response.send_message(f"Bitrate changed to {bitrate_value} kbps.", ephemeral=True)


class ChangeNameModal(discord.ui.Modal, title="Change Channel Name"):
    def __init__(self, cog, channel):
        self.cog = cog
        self.channel = channel
        super().__init__()

    new_name = discord.ui.TextInput(label="New Channel Name", custom_id="new_channel_name", style=discord.TextStyle.short, max_length=MAX_CHANNEL_NAME_LENGTH)

    async def on_submit(self, interaction: discord.Interaction):
        new_name = self.new_name.value
        if self.channel:
            await self.channel.edit(name=new_name)
            await interaction.response.send_message(f"Channel name changed to {new_name}.", ephemeral=True)


class SetUserLimitView(discord.ui.View):
    def __init__(self, cog, channel):
        super().__init__()
        self.cog = cog
        self.channel = channel

        # Define the options for the dropdown menu
        options = [discord.SelectOption(label="Unlimited (No limit)", value="0")]  # 0 will represent unlimited
        options.extend(discord.SelectOption(label=f"{i} members", value=str(i)) for i in range(1, 21))

        # Create the select menu
        self.select = discord.ui.Select(placeholder="Select user limit", options=options)
        self.select.callback = self.on_select
        self.add_item(self.select)

    async def on_select(self, interaction: discord.Interaction):
        # Get the selected value
        user_limit_value = int(self.select.values[0])

        # Update the user limit
        if self.channel:
            user_limit = None if user_limit_value == 0 else user_limit_value
            await self.channel.edit(user_limit=user_limit)
            await interaction.response.send_message(
                f"User limit set to {'Unlimited' if user_limit is None else str(user_limit) + ' members'}.",
                ephemeral=True
            )
