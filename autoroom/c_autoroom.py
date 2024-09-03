import datetime
from Star_Utils import Cog
from abc import ABC
from typing import Optional

import discord
from redbot.core import commands, Config
from redbot.core.utils.chat_formatting import humanize_timedelta

from .abc import MixinMeta

MAX_CHANNEL_NAME_LENGTH = 100
MAX_BITRATE = 96  # Maximum bitrate in kbps
DEFAULT_REGION = "us-central"  # Set your preferred default region here
DEFAULT_CHANNEL_NAME = "New Voice Channel"

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
    "delete": "<:TrashCan:1279875131136806993>",  # TrashCan
    "create_text": "<:SpeachBubble:1279890650535428198>",  # Speech Bubble
    "reset": "<:reset:1280057459146362880>"  # Reset
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
        self.config = Config.get_conf(self, identifier=1234567890, force_registration=True)

    @commands.command(name="controlpanel")
    @commands.guild_only()
    async def autoroom_controlpanel(self, ctx: commands.Context) -> None:
        """Send the master control panel for the guild. Restricted to guild owner."""
        if ctx.author.id != ctx.guild.owner_id:
            await ctx.send("You do not have permission to use this command.")
            return

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
            f"{DEFAULT_EMOJIS['delete']} Delete Channel",
            f"{DEFAULT_EMOJIS['create_text']} Create Text Channel",
            f"{DEFAULT_EMOJIS['reset']} Reset Configurations"
        ])
        embed.description = description

        view = ControlPanelView(self)

        await ctx.send(embed=embed, view=view)

    async def locked(self, interaction: discord.Interaction, channel: discord.VoiceChannel):
        """Lock your AutoRoom."""
        try:
            await interaction.response.defer(ephemeral=True)
            await channel.set_permissions(interaction.guild.default_role, connect=False)
            await interaction.followup.send(content="The AutoRoom is now locked.", ephemeral=True)
        except Exception as e:
            await self.handle_error(interaction, e)

    async def unlock(self, interaction: discord.Interaction, channel: discord.VoiceChannel):
        """Unlock your AutoRoom."""
        try:
            await interaction.response.defer(ephemeral=True)
            await channel.set_permissions(interaction.guild.default_role, connect=True)
            await interaction.followup.send(content="The AutoRoom is now unlocked.", ephemeral=True)
        except Exception as e:
            await self.handle_error(interaction, e)

    async def create_text_channel(self, interaction: discord.Interaction, channel: discord.VoiceChannel):
        """Create a temporary text channel linked to the voice channel."""
        try:
            existing_text_channel = self.get_text_channel(channel)
            if existing_text_channel:
                await interaction.response.send_message(f"You already have a linked text channel: {existing_text_channel.mention}.", ephemeral=True)
                return

            category = channel.category
            text_channel = await category.create_text_channel(
                name=f"{channel.name}-text",
                topic=f"Voice Channel ID: {channel.id}"
            )
            await text_channel.set_permissions(interaction.guild.default_role, read_messages=False)
            for member in channel.members:
                await text_channel.set_permissions(member, read_messages=True, send_messages=True)

            # Update the voice channel topic with the text channel ID
            await channel.edit(topic=f"Text Channel ID: {text_channel.id}")

            await interaction.response.send_message(f"Temporary text channel {text_channel.mention} created.", ephemeral=True)
        except discord.errors.HTTPException as e:
            # Handle specific error if topic contains restricted words
            if "Channel topic contains at least one word that is not allowed" in str(e):
                await interaction.response.send_message("Failed to set channel topic due to restricted words.", ephemeral=True)
            else:
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
        """Delete the voice channel and linked text channel."""
        try:
            await interaction.response.defer(ephemeral=True)
            view = DeleteConfirmationView(self, interaction, channel)
            await interaction.followup.send(content="Are you sure you want to delete the channel?", view=view, ephemeral=True)
        except Exception as e:
            await self.handle_error(interaction, e)

    async def transfer_ownership(self, interaction: discord.Interaction, channel: discord.VoiceChannel, new_owner: discord.Member):
        """Transfer ownership of the channel."""
        try:
            await self.config.channel(channel).owner.set(new_owner.id)
            await channel.edit(name=f"{new_owner.display_name}'s Channel")
            await interaction.response.send_message(f"Ownership transferred to {new_owner.display_name}.", ephemeral=True)
        except Exception as e:
            await self.handle_error(interaction, e)

    async def _process_allow_deny(self, interaction: discord.Interaction, action: str, channel: discord.VoiceChannel):
        """Process allowing or denying users/roles access to the AutoRoom."""
        try:
            text_channel = self.get_text_channel(channel)

            if action == "allow":
                await channel.set_permissions(interaction.guild.default_role, connect=True)
                if text_channel:
                    await text_channel.set_permissions(interaction.guild.default_role, read_messages=True)
                await interaction.followup.send(content="The AutoRoom is now public.", ephemeral=True)
            elif action == "deny":
                await channel.set_permissions(interaction.guild.default_role, connect=False)
                if text_channel:
                    await text_channel.set_permissions(interaction.guild.default_role, read_messages=False)
                await interaction.followup.send(content="The AutoRoom is now private.", ephemeral=True)
            elif action == "lock":
                await channel.set_permissions(interaction.guild.default_role, connect=False)
                if text_channel:
                    await text_channel.set_permissions(interaction.guild.default_role, send_messages=False)
                await interaction.followup.send(content="The AutoRoom is now locked.", ephemeral=True)
            elif action == "unlock":
                await channel.set_permissions(interaction.guild.default_role, connect=True)
                if text_channel:
                    await text_channel.set_permissions(interaction.guild.default_role, send_messages=True)
                await interaction.followup.send(content="The AutoRoom is now unlocked.", ephemeral=True)
            elif action == "private":
                await channel.set_permissions(interaction.guild.default_role, view_channel=False)
                if text_channel:
                    await text_channel.set_permissions(interaction.guild.default_role, view_channel=False)
                await interaction.followup.send(content="The AutoRoom is now private.", ephemeral=True)
            elif action == "public":
                await channel.set_permissions(interaction.guild.default_role, view_channel=True)
                if text_channel:
                    await text_channel.set_permissions(interaction.guild.default_role, view_channel=True)
                await interaction.followup.send(content="The AutoRoom is now public.", ephemeral=True)
            elif action == "delete":
                await channel.delete()
                if text_channel:
                    await text_channel.delete()
                await interaction.followup.send(content="The channel has been deleted.", ephemeral=True)
            else:
                await interaction.followup.send(content="Invalid action.", ephemeral=True)
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

            channel_age = datetime.datetime.utcnow() - channel.created_at.replace(tzinfo=None)
            bitrate = channel.bitrate // 1000  # Convert to kbps
            user_limit = channel.user_limit or "Unlimited"
            rtc_region = channel.rtc_region or "Automatic"

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

    async def reset_configurations(self, interaction: discord.Interaction, channel: discord.VoiceChannel):
        """Reset all configurations for the channel."""
        try:
            await interaction.response.defer(ephemeral=True)
            # Reset logic here (e.g., reset permissions, name, etc.)
            await channel.edit(name=DEFAULT_CHANNEL_NAME, user_limit=None, rtc_region=None)
            await interaction.followup.send("All configurations have been reset to default.", ephemeral=True)
        except Exception as e:
            await self.handle_error(interaction, e)

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

    def get_text_channel(self, voice_channel: discord.VoiceChannel) -> Optional[discord.TextChannel]:
        """Find a text channel associated with the voice channel."""
        category = voice_channel.category
        if category:
            for channel in category.channels:
                if isinstance(channel, discord.TextChannel) and channel.topic and f"Voice Channel ID: {voice_channel.id}" in channel.topic:
                    return channel
        return None

    def is_name_valid(self, name: str) -> bool:
        """Check if the name is valid (not explicit or racist)."""
        # Implement a basic filter or use an external library for advanced filtering
        banned_words = ["explicit_word1", "explicit_word2", "racist_word1"]
        return not any(banned_word in name.lower() for banned_word in banned_words)

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
        if voice_channel:
            invite = await voice_channel.create_invite(max_uses=1, unique=True)
            await interaction.response.send_message(f"Here is your invite to the voice channel: {invite.url}", ephemeral=True)

    @discord.ui.button(label="", emoji=DEFAULT_EMOJIS["ban"], custom_id="ban")
    async def ban(self, interaction: discord.Interaction, button: discord.ui.Button):
        voice_channel = self.cog._get_current_voice_channel(interaction.user)
        if voice_channel and await self.ensure_owner(interaction, voice_channel):
            await interaction.response.send_modal(DenyAllowSelect(self.cog, voice_channel, action="deny"))

    @discord.ui.button(label="", emoji=DEFAULT_EMOJIS["permit"], custom_id="permit")
    async def permit(self, interaction: discord.Interaction, button: discord.ui.Button):
        voice_channel = self.cog._get_current_voice_channel(interaction.user)
        if voice_channel and await self.ensure_owner(interaction, voice_channel):
            await interaction.response.send_modal(DenyAllowSelect(self.cog, voice_channel, action="allow"))

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
            await interaction.response.send_modal(TransferOwnershipSelect(self.cog, voice_channel))

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

    @discord.ui.button(label="", emoji=DEFAULT_EMOJIS["create_text"], custom_id="create_text")
    async def create_text(self, interaction: discord.Interaction, button: discord.ui.Button):
        voice_channel = self.cog._get_current_voice_channel(interaction.user)
        if voice_channel and await self.ensure_owner(interaction, voice_channel):
            await self.cog.create_text_channel(interaction, voice_channel)

    @discord.ui.button(label="", emoji=DEFAULT_EMOJIS["reset"], custom_id="reset")
    async def reset(self, interaction: discord.Interaction, button: discord.ui.Button):
        voice_channel = self.cog._get_current_voice_channel(interaction.user)
        if voice_channel and await self.ensure_owner(interaction, voice_channel):
            await self.cog.reset_configurations(interaction, voice_channel)

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
        await interaction.response.edit_message(content=f"{self.prompt} cancelled.", view=None)
        self.stop()

# Delete Confirmation View

class DeleteConfirmationView(discord.ui.View):
    def __init__(self, cog, interaction, channel):
        super().__init__()
        self.cog = cog
        self.interaction = interaction
        self.channel = channel

    @discord.ui.button(label="Yes", style=discord.ButtonStyle.success)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user != self.interaction.user:
            await interaction.response.send_message("You cannot confirm this action.", ephemeral=True)
            return
        await self.cog._process_allow_deny(self.interaction, "delete", self.channel)
        self.stop()

    @discord.ui.button(label="No", style=discord.ButtonStyle.danger)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user != self.interaction.user:
            await interaction.response.send_message("You cannot cancel this action.", ephemeral=True)
            return
        await interaction.response.edit_message(content="Deletion cancelled.", view=None)
        self.stop()

# Select Menus

class DenyAllowSelect(discord.ui.View):
    def __init__(self, cog, channel, action):
        super().__init__()
        self.cog = cog
        self.channel = channel
        self.action = action

        options = [discord.SelectOption(label=member.display_name, value=str(member.id)) for member in channel.guild.members]
        self.select = discord.ui.UserSelect(placeholder="Select a member", options=options)
        self.select.callback = self.on_select
        self.add_item(self.select)

    async def on_select(self, interaction: discord.Interaction):
        try:
            selected_user_id = int(self.select.values[0])
            user = self.channel.guild.get_member(selected_user_id)

            if user:
                permission = True if self.action == "allow" else False
                await self.channel.set_permissions(user, connect=permission)
                await interaction.response.send_message(f"{user.display_name} has been {'allowed' if permission else 'denied'} access to the channel.", ephemeral=True)
        except Exception as e:
            await self.cog.handle_error(interaction, e)

class TransferOwnershipSelect(discord.ui.View):
    def __init__(self, cog, channel):
        super().__init__()
        self.cog = cog
        self.channel = channel

        options = [discord.SelectOption(label=member.display_name, value=str(member.id)) for member in channel.members]
        self.select = discord.ui.UserSelect(placeholder="Select a new owner", options=options)
        self.select.callback = self.on_select
        self.add_item(self.select)

    async def on_select(self, interaction: discord.Interaction):
        try:
            selected_user_id = int(self.select.values[0])
            new_owner = self.channel.guild.get_member(selected_user_id)

            if new_owner:
                await self.cog.transfer_ownership(interaction, self.channel, new_owner)
        except Exception as e:
            await self.cog.handle_error(interaction, e)

# Modal Classes

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
            if not self.cog.is_name_valid(new_name):
                await interaction.followup.send("The channel name contains inappropriate content. Please choose another name.", ephemeral=True)
                return

            if self.channel:
                await self.channel.edit(name=new_name)
                text_channel = self.cog.get_text_channel(self.channel)
                if text_channel:
                    await text_channel.edit(name=f"{new_name}-text")
                await interaction.followup.send(f"Channel name changed to {new_name}.", ephemeral=True)
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
