"""The autoroom command."""

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

class AutoRoomCommands(MixinMeta, ABC):
    """The autoroom command."""

    @commands.group()
    @commands.guild_only()
    async def autoroom(self, ctx: commands.Context) -> None:
        """Manage your AutoRoom.

        For a quick rundown on how to manage your AutoRoom,
        check out [the readme](https://github.com/PhasecoreX/PCXCogs/tree/master/autoroom/README.md)
        """

    @autoroom.command(name="controlpanel")
    async def autoroom_controlpanel(self, ctx: commands.Context) -> None:
        """Send the control panel for your AutoRoom."""
        autoroom_channel, autoroom_info = await self._get_autoroom_channel_and_info(ctx)
        if not autoroom_channel or not autoroom_info:
            return

        embed = discord.Embed(title=f"Control Panel for {autoroom_channel.name}", color=0x7289da)
        embed.add_field(name='Commands:', value="Use the buttons below to manage your channel.")

        view = discord.ui.View()
        view.add_item(discord.ui.Button(label="Allow", custom_id=f"allow_{autoroom_channel.id}", style=discord.ButtonStyle.primary))
        view.add_item(discord.ui.Button(label="Bitrate", custom_id=f"bitrate_{autoroom_channel.id}", style=discord.ButtonStyle.primary))
        view.add_item(discord.ui.Button(label="Claim", custom_id=f"claim_{autoroom_channel.id}", style=discord.ButtonStyle.primary))
        view.add_item(discord.ui.Button(label="Deny", custom_id=f"deny_{autoroom_channel.id}", style=discord.ButtonStyle.primary))
        view.add_item(discord.ui.Button(label="Locked", custom_id=f"locked_{autoroom_channel.id}", style=discord.ButtonStyle.primary))
        view.add_item(discord.ui.Button(label="Name", custom_id=f"name_{autoroom_channel.id}", style=discord.ButtonStyle.primary))
        view.add_item(discord.ui.Button(label="Private", custom_id=f"private_{autoroom_channel.id}", style=discord.ButtonStyle.primary))
        view.add_item(discord.ui.Button(label="Public", custom_id=f"public_{autoroom_channel.id}", style=discord.ButtonStyle.primary))
        view.add_item(discord.ui.Button(label="Settings", custom_id=f"settings_{autoroom_channel.id}", style=discord.ButtonStyle.primary))
        view.add_item(discord.ui.Button(label="Users", custom_id=f"users_{autoroom_channel.id}", style=discord.ButtonStyle.primary))

        await ctx.send(embed=embed, view=view)

    @commands.Cog.listener()
    async def on_interaction(self, interaction: discord.Interaction):
        """Handle button interactions."""
        if interaction.type != discord.InteractionType.component:
            return

        custom_id = interaction.data['custom_id']
        channel_id = int(custom_id.split('_')[-1])
        channel = self.bot.get_channel(channel_id)

        if not channel or not isinstance(channel, discord.VoiceChannel):
            await interaction.response.send_message("Channel not found.", ephemeral=True)
            return

        if custom_id.startswith("allow"):
            await self.allow(interaction, channel)
        elif custom_id.startswith("bitrate"):
            await self.bitrate(interaction, channel)
        elif custom_id.startswith("claim"):
            await self.claim(interaction, channel)
        elif custom_id.startswith("deny"):
            await self.deny(interaction, channel)
        elif custom_id.startswith("locked"):
            await self.locked(interaction, channel)
        elif custom_id.startswith("name"):
            await self.name(interaction, channel)
        elif custom_id.startswith("private"):
            await self.private(interaction, channel)
        elif custom_id.startswith("public"):
            await self.public(interaction, channel)
        elif custom_id.startswith("settings"):
            await self.autoroom_settings(interaction, channel)
        elif custom_id.startswith("users"):
            await self.users(interaction, channel)

    async def allow(self, interaction: discord.Interaction, channel: discord.VoiceChannel):
        """Allow a user (or role) into your AutoRoom."""
        modal = AllowUserModal(self, channel)
        await interaction.response.send_modal(modal)

    async def deny(self, interaction: discord.Interaction, channel: discord.VoiceChannel):
        """Deny a user (or role) from accessing your AutoRoom."""
        modal = DenyUserModal(self, channel)
        await interaction.response.send_modal(modal)

    async def bitrate(self, interaction: discord.Interaction, channel: discord.VoiceChannel):
        """Change the bitrate of your AutoRoom."""
        modal = ChangeBitrateModal(self, channel)
        await interaction.response.send_modal(modal)

    async def claim(self, interaction: discord.Interaction, channel: discord.VoiceChannel):
        """Claim ownership of this AutoRoom."""
        autoroom_info = await self.get_autoroom_info(channel)
        if not autoroom_info:
            await interaction.response.send_message("This is not an AutoRoom.", ephemeral=True)
            return

        owner_id = autoroom_info.get("owner")
        if owner_id:
            owner = interaction.guild.get_member(owner_id)
            owner_name = owner.display_name if owner else "Unknown"
            await interaction.response.send_message(
                f"{interaction.user.mention}, this voice channel is already owned by {owner_name} and cannot be claimed.",
                ephemeral=True
            )
            return

        await self.config.channel(channel).owner.set(interaction.user.id)
        await interaction.response.send_message("You have claimed ownership of this AutoRoom.")

    async def locked(self, interaction: discord.Interaction, channel: discord.VoiceChannel):
        """Lock your AutoRoom (visible, but no one can join)."""
        await self._process_allow_deny(interaction, "lock", channel=channel)

    async def name(self, interaction: discord.Interaction, channel: discord.VoiceChannel):
        """Change the name of your AutoRoom."""
        modal = ChangeNameModal(self, channel)
        await interaction.response.send_modal(modal)

    async def private(self, interaction: discord.Interaction, channel: discord.VoiceChannel):
        """Make your AutoRoom private."""
        await self._process_allow_deny(interaction, "deny", channel=channel)

    async def public(self, interaction: discord.Interaction, channel: discord.VoiceChannel):
        """Make your AutoRoom public."""
        await self._process_allow_deny(interaction, "allow", channel=channel)

    async def autoroom_settings(self, interaction: discord.Interaction, channel: discord.VoiceChannel):
        """Display current settings."""
        autoroom_info = await self.get_autoroom_info(channel)
        if not autoroom_info:
            await interaction.response.send_message("This is not an AutoRoom.", ephemeral=True)
            return

        owner_id = autoroom_info.get("owner")
        owner = interaction.guild.get_member(owner_id)
        owner_name = owner.display_name if owner else "None"

        embed = discord.Embed(title=f"Settings for {channel.name}", color=0x7289da)
        embed.add_field(name="Owner", value=owner_name)
        embed.add_field(name="Bitrate", value=f"{channel.bitrate // 1000} kbps")
        embed.add_field(name="User Limit", value=channel.user_limit or "Unlimited")

        await interaction.response.send_message(embed=embed)

    async def users(self, interaction: discord.Interaction, channel: discord.VoiceChannel):
        """Change the user limit of your AutoRoom."""
        modal = SetUserLimitModal(self, channel)
        await interaction.response.send_modal(modal)

    async def _process_allow_deny(self, interaction: discord.Interaction, action: str, channel: discord.VoiceChannel):
        """Process allowing or denying users/roles access to the AutoRoom."""
        if action == "allow":
            # Allow everyone to connect
            await channel.set_permissions(interaction.guild.default_role, connect=True)
            await interaction.response.send_message("The AutoRoom is now public.", ephemeral=True)
        elif action == "deny":
            # Deny everyone from connecting
            await channel.set_permissions(interaction.guild.default_role, connect=False)
            await interaction.response.send_message("The AutoRoom is now private.", ephemeral=True)
        elif action == "lock":
            # Lock the room: visible but no one can join
            await channel.set_permissions(interaction.guild.default_role, connect=False)
            await interaction.response.send_message("The AutoRoom is now locked.", ephemeral=True)
        else:
            await interaction.response.send_message("Invalid action.", ephemeral=True)

    async def _get_user_from_input(self, guild: discord.Guild, user_input: str) -> Optional[discord.Member]:
        """Helper method to get a user object from an ID or mention."""
        if user_input.isdigit():
            return guild.get_member(int(user_input))
        elif user_input.startswith("<@") and user_input.endswith(">"):
            user_id = user_input[2:-1]
            return guild.get_member(int(user_id))
        return None

    async def _get_autoroom_channel_and_info(
        self, ctx: commands.Context, *, check_owner: bool = True
    ) -> tuple[Optional[discord.VoiceChannel], Optional[dict[str, Any]]]:
        autoroom_channel = self._get_current_voice_channel(ctx.message.author)
        autoroom_info = await self.get_autoroom_info(autoroom_channel)
        if not autoroom_info:
            await self._send_temp_error_message(ctx, "you are not in an AutoRoom.")
            return None, None
        if check_owner and ctx.message.author.id != autoroom_info["owner"]:
            reason_server = ""
            if not autoroom_info["owner"]:
                reason_server = " (it is a server AutoRoom)"
            await self._send_temp_error_message(
                ctx, f"you are not the owner of this AutoRoom{reason_server}."
            )
            return None, None
        return autoroom_channel, autoroom_info

    @staticmethod
    def _get_current_voice_channel(
        member: discord.Member | discord.User,
    ) -> Optional[discord.VoiceChannel]:
        """Get the members current voice channel, or None if not in a voice channel."""
        if (
            isinstance(member, discord.Member)
            and member.voice
            and isinstance(member.voice.channel, discord.VoiceChannel)
        ):
            return member.voice.channel
        return None

    async def _send_temp_error_message(
        self, ctx: commands.Context, message: str
    ) -> None:
        """Send an error message that deletes itself along with the context message."""
        hint = await ctx.send(error(f"{ctx.message.author.mention}, {message}"))
        await delete(ctx.message, delay=10)
        await delete(hint, delay=10)

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

class AllowUserModal(discord.ui.Modal, title="Allow User/Role"):
    def __init__(self, cog, channel):
        self.cog = cog
        self.channel = channel
        super().__init__()

    user_id = discord.ui.TextInput(label="User ID or Mention", custom_id="allow_user_id", style=discord.TextStyle.short)

    async def on_submit(self, interaction: discord.Interaction):
        user_input = self.user_id.value
        user = await self.cog._get_user_from_input(interaction.guild, user_input)
        if user and self.channel:
            await self.channel.set_permissions(user, connect=True)
            await interaction.response.send_message(f"{user.display_name} has been allowed to join the channel.")
        else:
            await interaction.response.send_message("User not found.", ephemeral=True)


class DenyUserModal(discord.ui.Modal, title="Deny User/Role"):
    def __init__(self, cog, channel):
        self.cog = cog
        self.channel = channel
        super().__init__()

    user_id = discord.ui.TextInput(label="User ID or Mention", custom_id="deny_user_id", style=discord.TextStyle.short)

    async def on_submit(self, interaction: discord.Interaction):
        user_input = self.user_id.value
        user = await self.cog._get_user_from_input(interaction.guild, user_input)
        if user and self.channel:
            await self.channel.set_permissions(user, connect=False)
            await interaction.response.send_message(f"{user.display_name} has been denied from joining the channel.")
        else:
            await interaction.response.send_message("User not found.", ephemeral=True)


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
            await interaction.response.send_message(f"Bitrate changed to {bitrate_value} kbps.")


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
            await interaction.response.send_message(f"Channel name changed to {new_name}.")


class SetUserLimitModal(discord.ui.Modal, title="Set User Limit"):
    def __init__(self, cog, channel):
        self.cog = cog
        self.channel = channel
        super().__init__()

    user_limit_value = discord.ui.TextInput(label="User Limit", custom_id="user_limit_value", style=discord.TextStyle.short)

    async def on_submit(self, interaction: discord.Interaction):
        user_limit_value = self.user_limit_value.value
        if not user_limit_value.isdigit():
            await interaction.response.send_message("Invalid user limit. Please enter a numeric value.", ephemeral=True)
            return

        if self.channel:
            await self.channel.edit(user_limit=int(user_limit_value))
            await interaction.response.send_message(f"User limit set to {user_limit_value}.")
