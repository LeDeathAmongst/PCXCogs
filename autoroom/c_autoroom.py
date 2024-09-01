import datetime
from abc import ABC
from typing import Any, Optional

import discord
from PIL import Image, ImageDraw, ImageFont
import io
from redbot.core import commands
from redbot.core.utils.chat_formatting import humanize_timedelta

from .abc import MixinMeta

MAX_CHANNEL_NAME_LENGTH = 100
MAX_BITRATE = 96  # Maximum bitrate in kbps
DEFAULT_REGION = "us-central"  # Set your preferred default region here

DEFAULT_EMOJIS = {
DEFAULT_EMOJIS = {
    "lock": "<:Locked:1279848927587467447>",  # Locked
    "unlock": "<:Unlocked:1279848944570073109>",  # Unlocked
    "limit": "<:People:1279848931043573790>",  # People
    "hide": " <:Crossed_Eye:1279848957475819723>",  # Crossed_Eye
    "unhide": "<:Eye:1279848986299076728>",  # Eye
    "invite": "<:Invite:1279857570634272818>",  # Invite/Request Join
    "ban": "<:Hammer:1279848987922530365>",  # Hammer
    "permit": "<:Check_Mark:1279848948491747411>",  # Check_Mark
    "rename": "<:Pensil:1279848929126645879>",  # Pensil
    "bitrate": "<:Headphones:1279848994327232584>",  # Headphones
    "region": "<:Servers:1279848940786810891>",  # Servers
    "claim": "<:Crown:1279848977658810451>",  # Crown
    "transfer": "<:Person_With_Rotation:1279848936752021504>",  # Person_With_Rotation
    "info": "<:Information:1279848926383702056>"  # Info
}

class AutoRoomCommands(MixinMeta, ABC):
    """The autoroom command."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.image_path = "control_panel_image.png"

    def generate_image(self):
        """Generate an image with button names and emojis."""
        width, height = 700, 250  # Adjusted height for more buttons
        image = Image.new('RGB', (width, height), color=(255, 248, 240))
        draw = ImageDraw.Draw(image)
        font = ImageFont.load_default()

        # Define button labels
        labels = [
            ("Lock", DEFAULT_EMOJIS["lock"]), ("Unlock", DEFAULT_EMOJIS["unlock"]), ("Limit", DEFAULT_EMOJIS["limit"]), ("Hide", DEFAULT_EMOJIS["hide"]),
            ("Unhide", DEFAULT_EMOJIS["unhide"]), ("Invite", DEFAULT_EMOJIS["invite"]), ("Ban", DEFAULT_EMOJIS["ban"]), ("Permit", DEFAULT_EMOJIS["permit"]),
            ("Rename", DEFAULT_EMOJIS["rename"]), ("Bitrate", DEFAULT_EMOJIS["bitrate"]), ("Region", DEFAULT_EMOJIS["region"]), ("Claim", DEFAULT_EMOJIS["claim"]),
            ("Transfer", DEFAULT_EMOJIS["transfer"]), ("Info", DEFAULT_EMOJIS["info"])
        ]

        # Draw labels on the image
        for i, (name, emoji) in enumerate(labels):
            x = (i % 4) * 175 + 20
            y = (i // 4) * 50 + 20
            draw.rectangle([(x, y), (x + 150, y + 40)], outline=(128, 0, 0), width=2)
            draw.text((x + 10, y + 10), f"{emoji} {name}", fill=(0, 0, 0), font=font)

        # Save the image locally
        image.save(self.image_path)

    @staticmethod
    def parse_emoji(emoji_str):
        """Parse the emoji string and return a discord.PartialEmoji."""
        if emoji_str.startswith("<:") and emoji_str.endswith(">"):
            name, id = emoji_str[2:-1].split(":")
            return discord.PartialEmoji(name=name, id=int(id))
        return discord.PartialEmoji(name=emoji_str)

    @commands.command(name="controlpanel")
    @commands.guild_only()
    async def autoroom_controlpanel(self, ctx: commands.Context) -> None:
        """Send the master control panel for the guild."""
        self.generate_image()
        embed = discord.Embed(title="Master Control Panel", color=0x7289da)
        file = discord.File(self.image_path, filename="control_panel_image.png")
        embed.set_image(url=f"attachment://control_panel_image.png")

        view = discord.ui.View()

        # Define buttons with emojis
        buttons = DEFAULT_EMOJIS

        # Add buttons to the view in the specified order
        button_order = [
            ["lock", "unlock", "limit", "hide"],
            ["unhide", "invite", "ban", "permit"],
            ["rename", "bitrate", "region", "claim"],
            ["transfer", "info"]
        ]

        for row in button_order:
            for button_name in row:
                emoji = self.parse_emoji(buttons[button_name])
                view.add_item(discord.ui.Button(
                    style=discord.ButtonStyle.primary,
                    label="",
                    emoji=emoji,
                    custom_id=button_name
                ))

        await ctx.send(embed=embed, file=file, view=view)

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

        # Defer the interaction if needed
        await interaction.response.defer(ephemeral=True)

        # Handle the interaction
        if custom_id == "lock":
            await self.locked(interaction, voice_channel)
        elif custom_id == "unlock":
            await self.unlock(interaction, voice_channel)
        elif custom_id == "limit":
            view = SetUserLimitView(self, voice_channel)
            await interaction.followup.send("Select a user limit:", view=view, ephemeral=True)
        elif custom_id == "hide":
            await self.private(interaction, voice_channel)
        elif custom_id == "unhide":
            await self.public(interaction, voice_channel)
        elif custom_id == "invite":
            await interaction.response.send_modal(RequestJoinModal(self, voice_channel))
        elif custom_id == "ban":
            await interaction.response.send_modal(DenyModal(self, voice_channel))
        elif custom_id == "permit":
            await interaction.response.send_modal(AllowModal(self, voice_channel))
        elif custom_id == "rename":
            await interaction.response.send_modal(ChangeNameModal(self, voice_channel))
        elif custom_id == "bitrate":
            await interaction.response.send_modal(ChangeBitrateModal(self, voice_channel))
        elif custom_id == "region":
            await self.change_region(interaction, voice_channel)
        elif custom_id == "claim":
            await self.claim(interaction, voice_channel)
        elif custom_id == "transfer":
            await self.show_transfer_owner_menu(interaction, voice_channel)
        elif custom_id == "info":
            await self.info(interaction, voice_channel)

    async def locked(self, interaction: discord.Interaction, channel: discord.VoiceChannel):
        """Lock your AutoRoom."""
        await self._process_allow_deny(interaction, "lock", channel=channel)

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

class AllowModal(discord.ui.Modal, title="Allow User or Role"):
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
            await self.channel.set_permissions(user, connect=True)
            await interaction.response.send_message(f"{user.display_name} has been allowed to join the channel.", ephemeral=True)
        elif role:
            await self.channel.set_permissions(role, connect=True, overwrite=True)
            await interaction.response.send_message(f"Role {role.name} has been allowed to join the channel.", ephemeral=True)
        else:
            await interaction.response.send_message("Role or user not found. Please enter a valid ID or mention.", ephemeral=True)


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
            await self.channel.set_permissions(user, connect=False)
            await interaction.response.send_message(f"{user.display_name} has been denied access to the channel.", ephemeral=True)
        elif role:
            await self.channel.set_permissions(role, connect=False, overwrite=True)
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


class RequestJoinModal(discord.ui.Modal, title="Request User to Join"):
    def __init__(self, cog, channel):
        self.cog = cog
        self.channel = channel
        super().__init__()

    user_input = discord.ui.TextInput(label="User ID or Username", custom_id="user_input", style=discord.TextStyle.short)

    async def on_submit(self, interaction: discord.Interaction):
        user_input = self.user_input.value
        user = await self.cog._get_user_from_input(interaction.guild, user_input)
        if user:
            requester_name = interaction.user.display_name
            channel_link = f"https://discord.com/channels/{interaction.guild.id}/{self.channel.id}"
            await user.send(f"{requester_name} has requested that you join their voice channel. Click [here]({channel_link}) to join!")
            await interaction.response.send_message(f"Request sent to {user.display_name}.", ephemeral=True)
        else:
            await interaction.response.send_message("User not found. Please enter a valid user ID or username.", ephemeral=True)


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
