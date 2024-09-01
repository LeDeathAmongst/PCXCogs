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
DEFAULT_REGION = "us-central"  # Set your preferred default region here

DEFAULT_DESCRIPTION = (
    "Use the buttons below to manage your channel.\n\n"
    "✅ **Allow**: Allow a user to join the channel.\n"
    "🔊 **Bitrate**: Change the channel's bitrate.\n"
    "👑 **Claim**: Claim ownership of the channel.\n"
    "❌ **Deny**: Deny a user access to the channel.\n"
    "🔒 **Locked**: Lock the channel (no one can join).\n"
    "✏️ **Name**: Change the channel's name.\n"
    "🔐 **Private**: Make the channel private.\n"
    "🌐 **Public**: Make the channel public.\n"
    "⚙️ **Settings**: View current channel settings.\n"
    "👥 **Users**: Set a user limit for the channel.\n"
    "🌍 **Region**: Change the voice region of the channel.\n"
    "🔄 **Transfer Owner**: Transfer channel ownership to another user.\n"
    "ℹ️ **Info**: View information about the current voice channel."
)

class AutoRoomCommands(MixinMeta, ABC):
    """The autoroom command."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    @commands.command(name="controlpanel")
    @commands.guild_only()
    async def autoroom_controlpanel(self, ctx: commands.Context) -> None:
        """Send the master control panel for the guild."""
        # Use the default description
        embed = discord.Embed(title="Master Control Panel", description=DEFAULT_DESCRIPTION, color=0x7289da)
        view = discord.ui.View()

        # Define fixed buttons
        buttons = {
            "allow": {"emoji": "✅", "name": "Allow", "style": discord.ButtonStyle.primary},
            "bitrate": {"emoji": "🔊", "name": "Bitrate", "style": discord.ButtonStyle.primary},
            "claim": {"emoji": "👑", "name": "Claim", "style": discord.ButtonStyle.primary},
            "deny": {"emoji": "❌", "name": "Deny", "style": discord.ButtonStyle.primary},
            "locked": {"emoji": "🔒", "name": "Locked", "style": discord.ButtonStyle.primary},
            "name": {"emoji": "✏️", "name": "Name", "style": discord.ButtonStyle.primary},
            "private": {"emoji": "🔐", "name": "Private", "style": discord.ButtonStyle.primary},
            "public": {"emoji": "🌐", "name": "Public", "style": discord.ButtonStyle.primary},
            "settings": {"emoji": "⚙️", "name": "Settings", "style": discord.ButtonStyle.primary},
            "users": {"emoji": "👥", "name": "Users", "style": discord.ButtonStyle.primary},
            "region": {"emoji": "🌍", "name": "Region", "style": discord.ButtonStyle.primary},
            "transfer": {"emoji": "🔄", "name": "Transfer Owner", "style": discord.ButtonStyle.primary},
            "info": {"emoji": "ℹ️", "name": "Info", "style": discord.ButtonStyle.primary},
        }

        for key, button in buttons.items():
            view.add_item(discord.ui.Button(
                label=button["name"],
                emoji=button["emoji"],
                custom_id=key,
                style=button["style"]
            ))

        await ctx.send(embed=embed, view=view)

    @commands.Cog.listener()
    async def on_interaction(self, interaction: discord.Interaction):
        """Handle button interactions."""
        if interaction.type != discord.InteractionType.component:
            return

        custom_id = interaction.data['custom_id']
        voice_channel = self._get_current_voice_channel(interaction.user)

        if not voice_channel:
            await interaction.response.send_message("You must be in a voice channel to use this command.", ephemeral=True)
            return

        autoroom_info = await self.get_autoroom_info(voice_channel)
        if not autoroom_info:
            await interaction.response.send_message("This voice channel is not managed by AutoRoom.", ephemeral=True)
            return

        # Check if the user is the owner of the channel or has override permissions
        if autoroom_info.get("owner") != interaction.user.id and not self._has_override_permissions(interaction.user, autoroom_info):
            owner_id = autoroom_info.get("owner")
            owner = interaction.guild.get_member(owner_id)
            owner_name = owner.display_name if owner else "Unknown"
            await interaction.response.send_message(
                f"Only {owner_name} or an admin can control the panel.", ephemeral=True
            )
            return

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
        elif custom_id == "name":
            await interaction.response.send_modal(ChangeNameModal(self, voice_channel))
        elif custom_id == "private":
            await self.private(interaction, voice_channel)
        elif custom_id == "public":
            await self.public(interaction, voice_channel)
        elif custom_id == "settings":
            await self.autoroom_settings(interaction, voice_channel)
        elif custom_id == "users":
            await interaction.response.send_modal(SetUserLimitModal(self, voice_channel))
        elif custom_id == "region":
            await self.change_region(interaction, voice_channel)
        elif custom_id == "transfer":
            await interaction.response.send_modal(TransferOwnerModal(self, voice_channel))
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

        embed = discord.Embed(title=f"Info for {channel.name}", color=0x7289da)
        embed.add_field(name="Owner", value=f"{owner_name} ({owner_mention})")
        embed.add_field(name="Age", value=humanize_timedelta(timedelta=channel_age))
        embed.add_field(name="Bitrate", value=f"{bitrate} kbps")

        await interaction.response.send_message(embed=embed, ephemeral=True)

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
        await interaction.response.send_message("You have claimed ownership of this AutoRoom.", ephemeral=True)

    async def locked(self, interaction: discord.Interaction, channel: discord.VoiceChannel):
        """Lock your AutoRoom (visible, but no one can join)."""
        await self._process_allow_deny(interaction, "lock", channel=channel)

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

        await interaction.response.send_message(embed=embed, ephemeral=True)

    async def change_region(self, interaction: discord.Interaction, channel: discord.VoiceChannel):
        """Change the voice region of your AutoRoom."""
        # Define fixed list of regions
        regions = [
            {"name": "Brazil", "id": "brazil"},
            {"name": "Hong Kong", "id": "hongkong"},
            {"name": "India", "id": "india"},
            {"name": "Japan", "id": "japan"},
            {"name": "Rotterdam", "id": "rotterdam"},
            {"name": "Russia", "id": "russia"},
            {"name": "Singapore", "id": "singapore"},
            {"name": "South Africa", "id": "southafrica"},
            {"name": "Sydney", "id": "sydney"},
            {"name": "US Central", "id": "us-central"},
            {"name": "US East", "id": "us-east"},
            {"name": "US South", "id": "us-south"},
            {"name": "US West", "id": "us-west"},
        ]

        options = [discord.SelectOption(label=region["name"], value=region["id"]) for region in regions]
        select = discord.ui.Select(placeholder="Select a voice region", options=options)

        async def select_callback(select_interaction: discord.Interaction):
            region_id = select.values[0]
            await channel.edit(rtc_region=region_id)
            await select_interaction.response.send_message(f"Voice region changed to {region_id}.", ephemeral=True)

        select.callback = select_callback
        view = discord.ui.View()
        view.add_item(select)
        await interaction.response.send_message("Select a voice region:", view=view, ephemeral=True)

    def _has_override_permissions(self, user: discord.Member, autoroom_info: dict) -> bool:
        """Check if the user has override permissions."""
        if user.guild_permissions.administrator:
            return True
        if user.id == user.guild.owner_id:
            return True
        return False

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

    async def _get_role_from_input(self, guild: discord.Guild, role_input: str) -> Optional[discord.Role]:
        """Helper method to get a role object from an ID or mention."""
        if role_input.isdigit():
            return guild.get_role(int(role_input))
        elif role_input.startswith("<@&") and role_input.endswith(">"):
            role_id = role_input[3:-1]
            return guild.get_role(int(role_id))
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
                ctx, f"you are not the owner of this AutoRoom{reason_server}.", ephemeral=True
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
        hint = await ctx.send(error(f"{ctx.message.author.mention}, {message}"), ephemeral=True)
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
            await interaction.response.send_message(f"User limit set to {user_limit_value}.", ephemeral=True)


class TransferOwnerModal(discord.ui.Modal, title="Transfer Channel Ownership"):
    def __init__(self, cog, channel):
        self.cog = cog
        self.channel = channel
        super().__init__()

    new_owner_input = discord.ui.TextInput(label="User ID or Username", custom_id="new_owner_input", style=discord.TextStyle.short)

    async def on_submit(self, interaction: discord.Interaction):
        user_input = self.new_owner_input.value
        user = await self.cog._get_user_from_input(interaction.guild, user_input)
        if user:
            await self.cog.config.channel(self.channel).owner.set(user.id)
            await interaction.response.send_message(f"Ownership transferred to {user.display_name}.", ephemeral=True)
        else:
            await interaction.response.send_message("User not found. Please enter a valid user ID or username.", ephemeral=True)
