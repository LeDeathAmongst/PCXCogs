"""The autoroom command."""

import datetime
from abc import ABC
from typing import Any, Optional

import discord
from redbot.core import commands, Config
from redbot.core.utils.chat_formatting import error, humanize_timedelta

from .abc import MixinMeta
from .pcx_lib import Perms, SettingDisplay, delete

MAX_CHANNEL_NAME_LENGTH = 100
MAX_BITRATE = 96  # Maximum bitrate in kbps

class AutoRoomCommands(MixinMeta, ABC):
    """The autoroom command."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.config = Config.get_conf(self, identifier=1234567890)
        default_channel = {
            "allowed_users": [],
            "denied_users": [],
            "allowed_roles": [],
            "denied_roles": [],
            "description": (
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
                "🔄 **Transfer Owner**: Transfer channel ownership to another user."
            ),
            "buttons": {
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
            }
        }
        self.config.register_channel(**default_channel)

    @commands.group()
    @commands.guild_only()
    async def autoroom(self, ctx: commands.Context) -> None:
        """Manage your AutoRoom."""

    @autoroom.command(name="controlpanel")
    async def autoroom_controlpanel(self, ctx: commands.Context) -> None:
        """Send the control panel for your AutoRoom."""
        autoroom_channel, autoroom_info = await self._get_autoroom_channel_and_info(ctx)
        if not autoroom_channel or not autoroom_info:
            return

        description = await self.config.channel(autoroom_channel).description()
        buttons_config = await self.config.channel(autoroom_channel).buttons()

        embed = discord.Embed(title=f"Control Panel for {autoroom_channel.name}", description=description, color=0x7289da)
        view = discord.ui.View()

        for key, button in buttons_config.items():
            view.add_item(discord.ui.Button(
                label=button["name"],
                emoji=button["emoji"],
                custom_id=f"{key}_{autoroom_channel.id}",
                style=button["style"]
            ))

        await ctx.send(embed=embed, view=view, ephemeral=False)

    @autoroom.command(name="description")
    async def autoroom_description(self, ctx: commands.Context, *, description: str) -> None:
        """Set a custom description for the control panel."""
        autoroom_channel, _ = await self._get_autoroom_channel_and_info(ctx)
        if not autoroom_channel:
            return

        await self.config.channel(autoroom_channel).description.set(description)
        await ctx.send(f"Description set to: {description}", ephemeral=True)

    @autoroom.command(name="button")
    async def autoroom_button(self, ctx: commands.Context, button_key: str, emoji: str, name: str, style: str) -> None:
        """Customize a button with emoji:name:buttonStyle format."""
        autoroom_channel, _ = await self._get_autoroom_channel_and_info(ctx)
        if not autoroom_channel:
            return

        style_map = {
            "primary": discord.ButtonStyle.primary,
            "secondary": discord.ButtonStyle.secondary,
            "success": discord.ButtonStyle.success,
            "danger": discord.ButtonStyle.danger,
        }

        if button_key not in await self.config.channel(autoroom_channel).buttons():
            await ctx.send("Invalid button key.", ephemeral=True)
            return

        if style not in style_map:
            await ctx.send("Invalid button style. Choose from: primary, secondary, success, danger.", ephemeral=True)
            return

        button_config = {
            "emoji": emoji,
            "name": name,
            "style": style_map[style]
        }

        async with self.config.channel(autoroom_channel).buttons() as buttons:
            buttons[button_key] = button_config

        await ctx.send(f"Button {button_key} updated to {emoji}:{name}:{style}.", ephemeral=True)

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

        # Check if the user is the owner of the channel
        autoroom_info = await self.get_autoroom_info(channel)
        if autoroom_info.get("owner") != interaction.user.id:
            owner_id = autoroom_info.get("owner")
            owner = interaction.guild.get_member(owner_id)
            owner_name = owner.display_name if owner else "Unknown"
            await interaction.response.send_message(
                f"Only {owner_name} can control the panel.", ephemeral=True
            )
            return

        # Handle the interaction if the user is the owner
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
        elif custom_id.startswith("region"):
            await self.change_region(interaction, channel)
        elif custom_id.startswith("transfer"):
            await self.transfer_owner(interaction, channel)

    async def allow(self, interaction: discord.Interaction, channel: discord.VoiceChannel):
        """Allow a user (or role) into your AutoRoom."""
        options = [
            discord.SelectOption(label=member.display_name, value=str(member.id))
            for member in interaction.guild.members
            if member.bot is False
        ]
        select = discord.ui.Select(placeholder="Select a user to allow", options=options)

        async def select_callback(select_interaction: discord.Interaction):
            user_id = int(select.values[0])
            user = interaction.guild.get_member(user_id)
            if user:
                await channel.set_permissions(user, connect=True)
                allowed_users = await self.config.channel(channel).allowed_users()
                if user.id not in allowed_users:
                    allowed_users.append(user.id)
                    await self.config.channel(channel).allowed_users.set(allowed_users)
                await select_interaction.response.send_message(f"{user.display_name} has been allowed to join the channel.", ephemeral=True)
            else:
                await select_interaction.response.send_message("User not found.", ephemeral=True)

        select.callback = select_callback
        view = discord.ui.View()
        view.add_item(select)
        await interaction.response.send_message("Select a user to allow:", view=view, ephemeral=True)

    async def deny(self, interaction: discord.Interaction, channel: discord.VoiceChannel):
        """Deny a user (or role) from accessing your AutoRoom."""
        options = [
            discord.SelectOption(label=role.name, value=f"role_{role.id}")
            for role in interaction.guild.roles
            if role.is_default() is False
        ] + [
            discord.SelectOption(label=member.display_name, value=f"user_{member.id}")
            for member in interaction.guild.members
            if member.bot is False
        ]
        select = discord.ui.Select(placeholder="Select a user or role to deny", options=options)

        async def select_callback(select_interaction: discord.Interaction):
            value = select.values[0]
            if value.startswith("user_"):
                user_id = int(value.split("_")[1])
                user = interaction.guild.get_member(user_id)
                if user:
                    await channel.set_permissions(user, view_channel=False, connect=False)
                    denied_users = await self.config.channel(channel).denied_users()
                    if user.id not in denied_users:
                        denied_users.append(user.id)
                        await self.config.channel(channel).denied_users.set(denied_users)
                    # Move user to another voice channel if they are currently in the denied channel
                    if user.voice and user.voice.channel == channel:
                        fallback_channel = discord.utils.get(interaction.guild.voice_channels, name="General")  # Change "General" to your fallback channel's name
                        if fallback_channel:
                            await user.move_to(fallback_channel)
                    await select_interaction.response.send_message(f"{user.display_name} has been denied access to the channel.", ephemeral=True)
                else:
                    await select_interaction.response.send_message("User not found.", ephemeral=True)
            elif value.startswith("role_"):
                role_id = int(value.split("_")[1])
                role = interaction.guild.get_role(role_id)
                if role:
                    await channel.set_permissions(role, view_channel=False, connect=False)
                    denied_roles = await self.config.channel(channel).denied_roles()
                    if role.id not in denied_roles:
                        denied_roles.append(role.id)
                        await self.config.channel(channel).denied_roles.set(denied_roles)
                    # Move all members with the denied role out of the channel
                    for member in channel.members:
                        if role in member.roles:
                            fallback_channel = discord.utils.get(interaction.guild.voice_channels, name="General")  # Change "General" to your fallback channel's name
                            if fallback_channel:
                                await member.move_to(fallback_channel)
                    await select_interaction.response.send_message(f"Role {role.name} has been denied access to the channel.", ephemeral=True)
                else:
                    await select_interaction.response.send_message("Role not found.", ephemeral=True)

        select.callback = select_callback
        view = discord.ui.View()
        view.add_item(select)
        await interaction.response.send_message("Select a user or role to deny:", view=view, ephemeral=True)

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
        await interaction.response.send_message("You have claimed ownership of this AutoRoom.", ephemeral=True)

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

        await interaction.response.send_message(embed=embed, ephemeral=True)

    async def users(self, interaction: discord.Interaction, channel: discord.VoiceChannel):
        """Change the user limit of your AutoRoom."""
        modal = SetUserLimitModal(self, channel)
        await interaction.response.send_modal(modal)

    async def change_region(self, interaction: discord.Interaction, channel: discord.VoiceChannel):
        """Change the voice region of your AutoRoom."""
        regions = await self.bot.http.get_voice_regions()
        options = [discord.SelectOption(label=region['name'], value=region['id']) for region in regions]
        select = discord.ui.Select(placeholder="Select a voice region", options=options)

        async def select_callback(select_interaction: discord.Interaction):
            region_id = select.values[0]
            await channel.edit(rtc_region=region_id)
            await select_interaction.response.send_message(f"Voice region changed to {region_id}.", ephemeral=True)

        select.callback = select_callback
        view = discord.ui.View()
        view.add_item(select)
        await interaction.response.send_message("Select a voice region:", view=view, ephemeral=True)

    async def transfer_owner(self, interaction: discord.Interaction, channel: discord.VoiceChannel):
        """Transfer ownership of the AutoRoom to another user."""
        modal = TransferOwnerModal(self, channel)
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
