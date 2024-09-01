import datetime
from abc import ABC
from typing import Any, Optional

import discord
from redbot.core import commands
from redbot.core.utils.chat_formatting import humanize_timedelta

from .abc import MixinMeta

MAX_CHANNEL_NAME_LENGTH = 100
MAX_BITRATE = 96  # Maximum bitrate in kbps
DEFAULT_REGION = "us-central"  # Set your preferred default region here

DEFAULT_EMOJIS = {
    "lock": "<:Locked:1279848927587467447>",  # Locked
    "unlock": "<:Unlocked:1279848944570073109>",  # Unlocked
    "limit": "<:People:1279848931043573790>",  # People
    "hide": "<:Crossed_Eye:1279848957475819723>",  # Crossed_Eye
    "unhide": "<:Eye:1279848986299076728>",  # Eye
    "invite": "<:Invite:1279857570634272818>",  # Invite/Request Join
    "ban": "<:Hammer:1279848987922530365>",  # Hammer
    "permit": "<:Check_Mark:1279848948491747411>",  # Check_Mark
    "rename": "<:Pensil:1279848929126645879>",  # Pensil
    "bitrate": "<:Headphones:1279848994327232584>",  # Headphones
    "region": "<:Servers:1279848940786810891>",  # Servers
    "claim": "<:Crown:1279848977658810451>",  # Crown
    "transfer": "<:Person_With_Rotation:1279848936752021504>",  # Person_With_Rotation
    "info": "<:Information:1279848926383702056>",  # Info
    "delete": "<:TrashCan:1279875131136806993>"  # TrashCan
}

REGION_OPTIONS = [
    ("Automatic", None),
    ("Brazil", "brazil"),
    ("Hong Kong", "hongkong"),
    ("India", "india"),
    ("Japan", "japan"),
    ("Rotterdam", "rotterdam"),
    ("Russia", "russia"),
    ("Singapore", "singapore"),
    ("South Africa", "southafrica"),
    ("Sydney", "sydney"),
    ("US Central", "us-central"),
    ("US East", "us-east"),
    ("US South", "us-south"),
    ("US West", "us-west"),
]

class AutoRoomCommands(MixinMeta, ABC):
    """The autoroom command."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    @staticmethod
    def parse_emoji(emoji_str):
        """Parse the emoji string and return a discord.PartialEmoji."""
        try:
            if emoji_str.startswith("<:") and emoji_str.endswith(">"):
                name, id = emoji_str[2:-1].split(":")
                return discord.PartialEmoji(name=name, id=int(id))
            return discord.PartialEmoji(name=emoji_str)
        except Exception as e:
            print(f"Failed to parse emoji: {emoji_str} with error: {e}")
            return None

    @commands.command(name="controlpanel")
    @commands.guild_only()
    @commands.check(lambda ctx: ctx.author.id == ctx.guild.owner_id)
    async def autoroom_controlpanel(self, ctx: commands.Context) -> None:
        """Send the master control panel for the guild. Only the server owner can use this command."""
        embed = discord.Embed(title="Master Control Panel", color=0x7289da)

        # Add a description with the button labels and emojis
        description = "\n".join([
            f"{DEFAULT_EMOJIS['lock']} Lock",
            f"{DEFAULT_EMOJIS['unlock']} Unlock",
            f"{DEFAULT_EMOJIS['limit']} Limit",
            f"{DEFAULT_EMOJIS['hide']} Hide",
            f"{DEFAULT_EMOJIS['unhide']} Unhide",
            f"{DEFAULT_EMOJIS['invite']} Invite",
            f"{DEFAULT_EMOJIS['ban']} Ban",
            f"{DEFAULT_EMOJIS['permit']} Permit",
            f"{DEFAULT_EMOJIS['rename']} Rename",
            f"{DEFAULT_EMOJIS['bitrate']} Bitrate",
            f"{DEFAULT_EMOJIS['region']} Region",
            f"{DEFAULT_EMOJIS['claim']} Claim",
            f"{DEFAULT_EMOJIS['transfer']} Transfer",
            f"{DEFAULT_EMOJIS['info']} Info",
            f"{DEFAULT_EMOJIS['delete']} Delete Channel"
        ])
        embed.description = description

        view = ControlPanelView(self)

        await ctx.send(embed=embed, view=view)

    async def locked(self, interaction: discord.Interaction, channel: discord.VoiceChannel):
        """Lock your AutoRoom."""
        try:
            await interaction.response.defer(ephemeral=True)
            view = ConfirmationView(self, interaction, channel, "lock", "Lock the room?")
            await interaction.followup.send("Are you sure you want to lock the room?", view=view, ephemeral=True)
        except Exception as e:
            await self.handle_error(interaction, e)

    async def unlock(self, interaction: discord.Interaction, channel: discord.VoiceChannel):
        """Unlock your AutoRoom."""
        try:
            await interaction.response.defer(ephemeral=True)
            view = ConfirmationView(self, interaction, channel, "unlock", "Unlock the room?")
            await interaction.followup.send("Are you sure you want to unlock the room?", view=view, ephemeral=True)
        except Exception as e:
            await self.handle_error(interaction, e)

    async def private(self, interaction: discord.Interaction, channel: discord.VoiceChannel):
        """Make the AutoRoom private."""
        try:
            await interaction.response.defer(ephemeral=True)
            view = ConfirmationView(self, interaction, channel, "private", "Make the room private?")
            await interaction.followup.send("Are you sure you want to make the room private?", view=view, ephemeral=True)
        except Exception as e:
            await self.handle_error(interaction, e)

    async def public(self, interaction: discord.Interaction, channel: discord.VoiceChannel):
        """Make the AutoRoom public."""
        try:
            await interaction.response.defer(ephemeral=True)
            view = ConfirmationView(self, interaction, channel, "public", "Make the room public?")
            await interaction.followup.send("Are you sure you want to make the room public?", view=view, ephemeral=True)
        except Exception as e:
            await self.handle_error(interaction, e)

    async def claim(self, interaction: discord.Interaction, channel: discord.VoiceChannel):
        """Claim ownership of the AutoRoom if there is no current owner, or override if admin/owner."""
        try:
            await interaction.response.defer(ephemeral=True)
            autoroom_info = await self.get_autoroom_info(channel)
            current_owner_id = autoroom_info.get("owner")

            if current_owner_id is None or self._has_override_permissions(interaction.user, autoroom_info):
                # No owner or user has override permissions, claim the channel
                await self.config.channel(channel).owner.set(interaction.user.id)
                await channel.edit(name=f"{interaction.user.display_name}'s Channel")
                await interaction.followup.send(f"You have claimed ownership of the channel.", ephemeral=True)
            else:
                # There is already an owner
                current_owner = interaction.guild.get_member(current_owner_id)
                owner_name = current_owner.display_name if current_owner else "Unknown"
                await interaction.followup.send(f"The channel is already owned by {owner_name}.", ephemeral=True)
        except Exception as e:
            await self.handle_error(interaction, e)

    async def delete_channel(self, interaction: discord.Interaction, channel: discord.VoiceChannel):
        """Delete the voice channel."""
        try:
            await interaction.response.defer(ephemeral=True)
            view = ConfirmationView(self, interaction, channel, "delete", "Delete the channel?")
            await interaction.followup.send("Are you sure you want to delete the channel?", view=view, ephemeral=True)
        except Exception as e:
            await self.handle_error(interaction, e)

    async def transfer_ownership(self, interaction: discord.Interaction, channel: discord.VoiceChannel, new_owner: discord.Member):
        """Transfer ownership of the channel with confirmation from the new owner."""
        try:
            await interaction.response.defer(ephemeral=True)
            view = TransferConfirmationView(self, interaction, channel, new_owner)
            await interaction.followup.send(f"{new_owner.display_name}, do you accept ownership of the channel?", view=view, ephemeral=True)
        except Exception as e:
            await self.handle_error(interaction, e)

    async def _process_allow_deny(self, interaction: discord.Interaction, action: str, channel: discord.VoiceChannel):
        """Process allowing or denying users/roles access to the AutoRoom."""
        try:
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
            elif action == "unlock":
                # Unlock the room: visible and joinable
                await channel.set_permissions(interaction.guild.default_role, connect=True)
                await interaction.followup.send("The AutoRoom is now unlocked.", ephemeral=True)
            elif action == "private":
                # Make the room private
                await channel.set_permissions(interaction.guild.default_role, view_channel=False)
                await interaction.followup.send("The AutoRoom is now private.", ephemeral=True)
            elif action == "public":
                # Make the room public
                await channel.set_permissions(interaction.guild.default_role, view_channel=True)
                await interaction.followup.send("The AutoRoom is now public.", ephemeral=True)
            elif action == "delete":
                # Delete the channel
                await channel.delete()
                await interaction.followup.send("The channel has been deleted.", ephemeral=True)
            else:
                await interaction.followup.send("Invalid action.", ephemeral=True)
        except Exception as e:
            await self.handle_error(interaction, e)

    async def info(self, interaction: discord.Interaction, channel: discord.VoiceChannel):
        """Provide information about the current voice channel."""
        try:
            await interaction.response.defer(ephemeral=True)
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

            # Determine allowed and denied users
            allowed_users = []
            denied_users = []
            for target, overwrite in channel.overwrites.items():
                if isinstance(target, discord.Member):
                    if overwrite.connect is True:
                        allowed_users.append(target.mention)
                    elif overwrite.connect is False:
                        denied_users.append(target.mention)

            allowed_users_text = ", ".join(allowed_users) if allowed_users else "No One"
            denied_users_text = ", ".join(denied_users) if denied_users else "No One"

            embed = discord.Embed(title=f"Info for {channel.name}", color=0x7289da)
            embed.add_field(name="Owner", value=f"{owner_name} ({owner_mention})")
            embed.add_field(name="Age", value=humanize_timedelta(timedelta=channel_age))
            embed.add_field(name="Bitrate", value=f"{bitrate} kbps")
            embed.add_field(name="User Limit", value=user_limit)
            embed.add_field(name="Region", value=rtc_region)
            embed.add_field(name="Private", value="Yes" if self._get_autoroom_type(channel, interaction.guild.default_role) == "private" else "No")
            embed.add_field(name="Allowed Users", value=allowed_users_text)
            embed.add_field(name="Denied Users", value=denied_users_text)

            await interaction.followup.send(embed=embed, ephemeral=True)
        except Exception as e:
            await self.handle_error(interaction, e)

    async def change_region(self, interaction: discord.Interaction, channel: discord.VoiceChannel):
        """Change the region of the voice channel."""
        try:
            await interaction.response.defer(ephemeral=True)
            view = RegionSelectView(self, channel)
            await interaction.followup.send("Select a region for the voice channel:", view=view, ephemeral=True)
        except Exception as e:
            await self.handle_error(interaction, e)

    async def _get_user_from_input(self, guild: discord.Guild, input_value: str) -> Optional[discord.Member]:
        """Get a user from input (ID or mention)."""
        if input_value.isdigit():
            return guild.get_member(int(input_value))
        elif input_value.startswith("<@") and input_value.endswith(">"):
            user_id = input_value.strip("<@!>")
            return guild.get_member(int(user_id))
        return None

    async def _get_role_from_input(self, guild: discord.Guild, input_value: str) -> Optional[discord.Role]:
        """Get a role from input (ID or mention)."""
        if input_value.isdigit():
            return guild.get_role(int(input_value))
        elif input_value.startswith("<@&") and input_value.endswith(">"):
            role_id = input_value.strip("<@&>")
            return guild.get_role(int(role_id))
        return None

    def _has_override_permissions(self, user: discord.Member, autoroom_info: dict) -> bool:
        """Check if the user has override permissions."""
        if user.guild_permissions.administrator or user.id == user.guild.owner_id:
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

    async def handle_error(self, interaction: discord.Interaction, error: Exception):
        """Handle errors by sending a user-friendly message and optionally logging."""
        error_message = "An error occurred while processing your request. Please try again later."
        await interaction.followup.send(error_message, ephemeral=True)

        # Optionally log the error to a file or external service
        # with open("error_log.txt", "a") as f:
        #     f.write(f"{datetime.datetime.now()}: {str(error)}\n")

# View Class for Control Panel

class ControlPanelView(discord.ui.View):
    def __init__(self, cog):
        super().__init__()
        self.cog = cog

    async def ensure_owner(self, interaction: discord.Interaction, channel: discord.VoiceChannel) -> bool:
        autoroom_info = await self.cog.get_autoroom_info(channel)
        owner_id = autoroom_info.get("owner")
        if owner_id == interaction.user.id or self.cog._has_override_permissions(interaction.user, autoroom_info):
            return True
        await interaction.response.send_message("You must be the channel owner to use this button.", ephemeral=True)
        return False

    @discord.ui.button(label="", emoji=DEFAULT_EMOJIS["lock"], custom_id="lock")
    async def lock(self, interaction: discord.Interaction, button: discord.ui.Button):
        voice_channel = self.cog._get_current_voice_channel(interaction.user)
        if voice_channel and await self.ensure_owner(interaction, voice_channel):
            await self.cog.locked(interaction, voice_channel)

    @discord.ui.button(label="", emoji=DEFAULT_EMOJIS["unlock"], custom_id="unlock")
    async def unlock(self, interaction: discord.Interaction, button: discord.ui.Button):
        voice_channel = self.cog._get_current_voice_channel(interaction.user)
        if voice_channel and await self.ensure_owner(interaction, voice_channel):
            await self.cog.unlock(interaction, voice_channel)

    @discord.ui.button(label="", emoji=DEFAULT_EMOJIS["limit"], custom_id="limit")
    async def limit(self, interaction: discord.Interaction, button: discord.ui.Button):
        voice_channel = self.cog._get_current_voice_channel(interaction.user)
        if voice_channel and await self.ensure_owner(interaction, voice_channel):
            await interaction.response.send_modal(SetUserLimitModal(self.cog, voice_channel))

    @discord.ui.button(label="", emoji=DEFAULT_EMOJIS["hide"], custom_id="hide")
    async def hide(self, interaction: discord.Interaction, button: discord.ui.Button):
        voice_channel = self.cog._get_current_voice_channel(interaction.user)
        if voice_channel and await self.ensure_owner(interaction, voice_channel):
            await self.cog.private(interaction, voice_channel)

    @discord.ui.button(label="", emoji=DEFAULT_EMOJIS["unhide"], custom_id="unhide")
    async def unhide(self, interaction: discord.Interaction, button: discord.ui.Button):
        voice_channel = self.cog._get_current_voice_channel(interaction.user)
        if voice_channel and await self.ensure_owner(interaction, voice_channel):
            await self.cog.public(interaction, voice_channel)

    @discord.ui.button(label="", emoji=DEFAULT_EMOJIS["invite"], custom_id="invite")
    async def invite(self, interaction: discord.Interaction, button: discord.ui.Button):
        voice_channel = self.cog._get_current_voice_channel(interaction.user)
        if voice_channel and await self.ensure_owner(interaction, voice_channel):
            await interaction.response.send_modal(RequestJoinModal(self.cog, voice_channel))

    @discord.ui.button(label="", emoji=DEFAULT_EMOJIS["ban"], custom_id="ban")
    async def ban(self, interaction: discord.Interaction, button: discord.ui.Button):
        voice_channel = self.cog._get_current_voice_channel(interaction.user)
        if voice_channel and await self.ensure_owner(interaction, voice_channel):
            await interaction.response.send_modal(DenyModal(self.cog, voice_channel))

    @discord.ui.button(label="", emoji=DEFAULT_EMOJIS["permit"], custom_id="permit")
    async def permit(self, interaction: discord.Interaction, button: discord.ui.Button):
        voice_channel = self.cog._get_current_voice_channel(interaction.user)
        if voice_channel and await self.ensure_owner(interaction, voice_channel):
            await interaction.response.send_modal(AllowModal(self.cog, voice_channel))

    @discord.ui.button(label="", emoji=DEFAULT_EMOJIS["rename"], custom_id="rename")
    async def rename(self, interaction: discord.Interaction, button: discord.ui.Button):
        voice_channel = self.cog._get_current_voice_channel(interaction.user)
        if voice_channel and await self.ensure_owner(interaction, voice_channel):
            await interaction.response.send_modal(ChangeNameModal(self.cog, voice_channel))

    @discord.ui.button(label="", emoji=DEFAULT_EMOJIS["bitrate"], custom_id="bitrate")
    async def bitrate(self, interaction: discord.Interaction, button: discord.ui.Button):
        voice_channel = self.cog._get_current_voice_channel(interaction.user)
        if voice_channel and await self.ensure_owner(interaction, voice_channel):
            await interaction.response.send_modal(ChangeBitrateModal(self.cog, voice_channel))

    @discord.ui.button(label="", emoji=DEFAULT_EMOJIS["region"], custom_id="region")
    async def region(self, interaction: discord.Interaction, button: discord.ui.Button):
        voice_channel = self.cog._get_current_voice_channel(interaction.user)
        if voice_channel and await self.ensure_owner(interaction, voice_channel):
            await self.cog.change_region(interaction, voice_channel)

    @discord.ui.button(label="", emoji=DEFAULT_EMOJIS["claim"], custom_id="claim")
    async def claim(self, interaction: discord.Interaction, button: discord.ui.Button):
        voice_channel = self.cog._get_current_voice_channel(interaction.user)
        if voice_channel and await self.ensure_owner(interaction, voice_channel):
            await self.cog.claim(interaction, voice_channel)

    @discord.ui.button(label="", emoji=DEFAULT_EMOJIS["transfer"], custom_id="transfer")
    async def transfer(self, interaction: discord.Interaction, button: discord.ui.Button):
        voice_channel = self.cog._get_current_voice_channel(interaction.user)
        if voice_channel and await self.ensure_owner(interaction, voice_channel):
            await interaction.response.send_modal(TransferOwnershipModal(self.cog, voice_channel))

    @discord.ui.button(label="", emoji=DEFAULT_EMOJIS["info"], custom_id="info")
    async def info(self, interaction: discord.Interaction, button: discord.ui.Button):
        voice_channel = self.cog._get_current_voice_channel(interaction.user)
        if voice_channel:
            await self.cog.info(interaction, voice_channel)

    @discord.ui.button(label="", emoji=DEFAULT_EMOJIS["delete"], custom_id="delete")
    async def delete(self, interaction: discord.Interaction, button: discord.ui.Button):
        voice_channel = self.cog._get_current_voice_channel(interaction.user)
        if voice_channel and await self.ensure_owner(interaction, voice_channel):
            await self.cog.delete_channel(interaction, voice_channel)

# Confirmation View for Actions

class ConfirmationView(discord.ui.View):
    def __init__(self, cog, interaction, channel, action, prompt):
        super().__init__()
        self.cog = cog
        self.interaction = interaction
        self.channel = channel
        self.action = action
        self.prompt = prompt

    @discord.ui.button(label="Yes", style=discord.ButtonStyle.success)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user != self.interaction.user:
            await interaction.response.send_message("You cannot confirm this action.", ephemeral=True)
            return
        await self.cog._process_allow_deny(self.interaction, self.action, self.channel)
        self.stop()

    @discord.ui.button(label="No", style=discord.ButtonStyle.danger)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user != self.interaction.user:
            await interaction.response.send_message("You cannot cancel this action.", ephemeral=True)
            return
        await interaction.response.send_message(f"{self.prompt} cancelled.", ephemeral=True)
        self.stop()

# Transfer Confirmation View

class TransferConfirmationView(discord.ui.View):
    def __init__(self, cog, interaction, channel, new_owner):
        super().__init__()
        self.cog = cog
        self.interaction = interaction
        self.channel = channel
        self.new_owner = new_owner

    @discord.ui.button(label="Accept", style=discord.ButtonStyle.success)
    async def accept(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user != self.new_owner:
            await interaction.response.send_message("You cannot accept this transfer.", ephemeral=True)
            return
        await self.cog.config.channel(self.channel).owner.set(self.new_owner.id)
        await self.channel.edit(name=f"{self.new_owner.display_name}'s Channel")
        await interaction.response.send_message(f"Ownership transferred to {self.new_owner.display_name}.", ephemeral=True)
        self.stop()

    @discord.ui.button(label="Decline", style=discord.ButtonStyle.danger)
    async def decline(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user != self.new_owner:
            await interaction.response.send_message("You cannot decline this transfer.", ephemeral=True)
            return
        await interaction.response.send_message("Transfer declined.", ephemeral=True)
        self.stop()

# Modal Classes

class AllowModal(discord.ui.Modal, title="Allow User or Role"):
    def __init__(self, cog, channel):
        self.cog = cog
        self.channel = channel
        super().__init__()

    role_or_user_input = discord.ui.TextInput(label="Role/User ID or Mention", custom_id="role_or_user_input", style=discord.TextStyle.short)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            await interaction.response.defer(ephemeral=True)
            input_value = self.role_or_user_input.value
            user = await self.cog._get_user_from_input(interaction.guild, input_value)
            role = await self.cog._get_role_from_input(interaction.guild, input_value)

            if user:
                await self.channel.set_permissions(user, connect=True)
                await interaction.followup.send(f"{user.display_name} has been allowed to join the channel.", ephemeral=True)
            elif role:
                for member in self.channel.members:
                    if role in member.roles:
                        await self.channel.set_permissions(member, connect=True)
                await interaction.followup.send(f"Role {role.name} has been allowed to join the channel.", ephemeral=True)
            else:
                await interaction.followup.send("Role or user not found. Please enter a valid ID or mention.", ephemeral=True)
        except Exception as e:
            await self.cog.handle_error(interaction, e)


class DenyModal(discord.ui.Modal, title="Deny User or Role"):
    def __init__(self, cog, channel):
        self.cog = cog
        self.channel = channel
        super().__init__()

    role_or_user_input = discord.ui.TextInput(label="Role/User ID or Mention", custom_id="role_or_user_input", style=discord.TextStyle.short)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            await interaction.response.defer(ephemeral=True)
            input_value = self.role_or_user_input.value
            user = await self.cog._get_user_from_input(interaction.guild, input_value)
            role = await self.cog._get_role_from_input(interaction.guild, input_value)

            if user:
                await self.channel.set_permissions(user, connect=False)
                await interaction.followup.send(f"{user.display_name} has been denied access to the channel.", ephemeral=True)
            elif role:
                for member in self.channel.members:
                    if role in member.roles:
                        await self.channel.set_permissions(member, connect=False)
                await interaction.followup.send(f"Role {role.name} has been denied access to the channel.", ephemeral=True)
            else:
                await interaction.followup.send("Role or user not found. Please enter a valid ID or mention.", ephemeral=True)
        except Exception as e:
            await self.cog.handle_error(interaction, e)


class ChangeBitrateModal(discord.ui.Modal, title="Change Bitrate"):
    def __init__(self, cog, channel):
        self.cog = cog
        self.channel = channel
        super().__init__()

    bitrate_value = discord.ui.TextInput(label="Bitrate (kbps)", custom_id="bitrate_value", style=discord.TextStyle.short)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            await interaction.response.defer(ephemeral=True)
            bitrate_value = self.bitrate_value.value
            if not bitrate_value.isdigit() or int(bitrate_value) > MAX_BITRATE:
                await interaction.followup.send(f"Invalid bitrate. Please enter a value between 8 and {MAX_BITRATE} kbps.", ephemeral=True)
                return

            if self.channel:
                await self.channel.edit(bitrate=int(bitrate_value) * 1000)
                await interaction.followup.send(f"Bitrate changed to {bitrate_value} kbps.", ephemeral=True)
        except Exception as e:
            await self.cog.handle_error(interaction, e)


class ChangeNameModal(discord.ui.Modal, title="Change Channel Name"):
    def __init__(self, cog, channel):
        self.cog = cog
        self.channel = channel
        super().__init__()

    new_name = discord.ui.TextInput(label="New Channel Name", custom_id="new_channel_name", style=discord.TextStyle.short, max_length=MAX_CHANNEL_NAME_LENGTH)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            await interaction.response.defer(ephemeral=True)
            new_name = self.new_name.value
            if self.channel:
                await self.channel.edit(name=new_name)
                await interaction.followup.send(f"Channel name changed to {new_name}.", ephemeral=True)
        except Exception as e:
            await self.cog.handle_error(interaction, e)


class RequestJoinModal(discord.ui.Modal, title="Request User to Join"):
    def __init__(self, cog, channel):
        self.cog = cog
        self.channel = channel
        super().__init__()

    user_input = discord.ui.TextInput(label="User ID or Username", custom_id="user_input", style=discord.TextStyle.short)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            await interaction.response.defer(ephemeral=True)
            user_input = self.user_input.value
            user = await self.cog._get_user_from_input(interaction.guild, user_input)
            if user:
                requester_name = interaction.user.display_name
                channel_link = f"https://discord.com/channels/{interaction.guild.id}/{self.channel.id}"
                await user.send(f"{requester_name} has requested that you join their voice channel. Click [here]({channel_link}) to join!")
                await interaction.followup.send(f"Request sent to {user.display_name}.", ephemeral=True)
            else:
                await interaction.followup.send("User not found. Please enter a valid user ID or username.", ephemeral=True)
        except Exception as e:
            await self.cog.handle_error(interaction, e)


class TransferOwnershipModal(discord.ui.Modal, title="Transfer Ownership"):
    def __init__(self, cog, channel):
        self.cog = cog
        self.channel = channel
        super().__init__()

    new_owner_input = discord.ui.TextInput(label="New Owner ID or Mention", custom_id="new_owner_input", style=discord.TextStyle.short)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            await interaction.response.defer(ephemeral=True)
            new_owner_input = self.new_owner_input.value
            new_owner = await self.cog._get_user_from_input(interaction.guild, new_owner_input)

            if new_owner and new_owner in self.channel.members:
                await self.cog.transfer_ownership(interaction, self.channel, new_owner)
            else:
                await interaction.followup.send("User not found or not in the channel. Please enter a valid user ID or mention.", ephemeral=True)
        except Exception as e:
            await self.cog.handle_error(interaction, e)


class SetUserLimitModal(discord.ui.Modal, title="Set User Limit"):
    def __init__(self, cog, channel):
        self.cog = cog
        self.channel = channel
        super().__init__()

    user_limit_input = discord.ui.TextInput(label="User Limit (0 for Unlimited)", custom_id="user_limit_input", style=discord.TextStyle.short)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            await interaction.response.defer(ephemeral=True)
            user_limit_value = self.user_limit_input.value
            if not user_limit_value.isdigit() or int(user_limit_value) < 0:
                await interaction.followup.send("Invalid user limit. Please enter a non-negative integer.", ephemeral=True)
                return

            user_limit = None if int(user_limit_value) == 0 else int(user_limit_value)
            await self.channel.edit(user_limit=user_limit)
            await interaction.followup.send(
                f"User limit set to {'Unlimited' if user_limit is None else str(user_limit) + ' members'}.",
                ephemeral=True
            )
        except Exception as e:
            await self.cog.handle_error(interaction, e)


class RegionSelectView(discord.ui.View):
    def __init__(self, cog, channel):
        super().__init__()
        self.cog = cog
        self.channel = channel

        options = [discord.SelectOption(label=name, value=region or "automatic") for name, region in REGION_OPTIONS]
        self.select = discord.ui.Select(placeholder="Select Region", options=options)
        self.select.callback = self.on_select
        self.add_item(self.select)

    async def on_select(self, interaction: discord.Interaction):
        try:
            await interaction.response.defer(ephemeral=True)
            selected_region = self.select.values[0]
            rtc_region = None if selected_region == "automatic" else selected_region
            await self.channel.edit(rtc_region=rtc_region)
            await interaction.followup.send(f"Region changed to {selected_region if rtc_region else 'Automatic'}.", ephemeral=True)
        except Exception as e:
            await self.cog.handle_error(interaction, e)
