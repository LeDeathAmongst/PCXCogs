"""AutoRoom cog for Red-DiscordBot by PhasecoreX."""

from abc import ABC
from contextlib import suppress
from typing import Any, ClassVar

import discord
from redbot.core import Config, commands
from redbot.core.bot import Red
from redbot.core.utils.chat_formatting import humanize_timedelta

from .c_autoroom import AutoRoomCommands
from .c_autoroomset import AutoRoomSetCommands, channel_name_template
from .pcx_lib import Perms, SettingDisplay
from .pcx_template import Template


class CompositeMetaClass(type(commands.Cog), type(ABC)):
    """Allows the metaclass used for proper type detection to coexist with discord.py's metaclass."""


class AutoRoom(
    AutoRoomCommands,
    AutoRoomSetCommands,
    commands.Cog,
    metaclass=CompositeMetaClass,
):
    """Automatic voice channel management with control panel integration.

    This cog facilitates automatic voice channel creation.
    When a member joins an AutoRoom Source (voice channel),
    this cog will move them to a brand new AutoRoom that they have control over.
    Once everyone leaves the AutoRoom, it is automatically deleted.

    For a quick rundown on how to get started with this cog,
    check out [the readme](https://github.com/PhasecoreX/PCXCogs/tree/master/autoroom/README.md)
    """

    __author__ = "PhasecoreX"
    __version__ = "3.9.0"

    default_global_settings: ClassVar[dict[str, int]] = {"schema_version": 0}
    default_guild_settings: ClassVar[dict[str, bool | list[int]]] = {
        "admin_access": True,
        "mod_access": False,
        "bot_access": [],
    }
    default_autoroom_source_settings: ClassVar[dict[str, int | str | None]] = {
        "dest_category_id": None,
        "room_type": "public",
        "legacy_text_channel": False,
        "text_channel_hint": None,
        "text_channel_topic": "",
        "channel_name_type": "username",
        "channel_name_format": "",
        "perm_owner_manage_channels": True,
        "perm_send_messages": True,
    }
    default_channel_settings: ClassVar[dict[str, int | list[int] | None]] = {
        "source_channel": None,
        "owner": None,
        "associated_text_channel": None,
        "denied": [],
    }
    extra_channel_name_change_delay = 4

    perms_bot_source: ClassVar[dict[str, bool]] = {
        "view_channel": True,
        "connect": True,
        "move_members": True,
    }
    perms_bot_dest: ClassVar[dict[str, bool]] = {
        "view_channel": True,
        "connect": True,
        "send_messages": True,
        "manage_channels": True,
        "manage_messages": True,
        "move_members": True,
    }

    perms_legacy_text: ClassVar[list[str]] = ["read_message_history", "read_messages"]
    perms_legacy_text_allow: ClassVar[dict[str, bool]] = dict.fromkeys(
        perms_legacy_text, True
    )
    perms_legacy_text_deny: ClassVar[dict[str, bool]] = dict.fromkeys(
        perms_legacy_text, False
    )
    perms_legacy_text_reset: ClassVar[dict[str, None]] = dict.fromkeys(
        perms_legacy_text, None
    )
    perms_autoroom_owner_legacy_text: ClassVar[dict[str, bool]] = {
        **perms_legacy_text_allow,
        "manage_channels": True,
        "manage_messages": True,
    }
    perms_bot_dest_legacy_text = perms_autoroom_owner_legacy_text

    def __init__(self, bot: Red) -> None:
        """Set up the cog."""
        super().__init__()
        self.bot = bot
        self.config = Config.get_conf(
            self, identifier=1224364860, force_registration=True
        )
        self.config.register_global(**self.default_global_settings)
        self.config.register_guild(**self.default_guild_settings)
        self.config.init_custom("AUTOROOM_SOURCE", 2)
        self.config.register_custom(
            "AUTOROOM_SOURCE", **self.default_autoroom_source_settings
        )
        self.config.register_channel(**self.default_channel_settings)
        self.template = Template()
        self.bucket_autoroom_create = commands.CooldownMapping.from_cooldown(
            2, 60, lambda member: member
        )
        self.bucket_autoroom_create_warn = commands.CooldownMapping.from_cooldown(
            1, 3600, lambda member: member
        )
        self.bucket_autoroom_name = commands.CooldownMapping.from_cooldown(
            2, 600 + self.extra_channel_name_change_delay, lambda channel: channel
        )
        self.bucket_autoroom_owner_claim = commands.CooldownMapping.from_cooldown(
            1, 120, lambda channel: channel
        )

    #
    # Red methods
    #

    def format_help_for_context(self, ctx: commands.Context) -> str:
        """Show version in help."""
        pre_processed = super().format_help_for_context(ctx)
        return f"{pre_processed}\n\nCog Version: {self.__version__}"

    async def red_delete_data_for_user(self, *, _requester: str, _user_id: int) -> None:
        """Nothing to delete."""
        return

    #
    # Initialization methods
    #

    async def initialize(self) -> None:
        """Perform setup actions before loading cog."""
        await self._migrate_config()
        self.bot.loop.create_task(self._cleanup_autorooms())

    async def _migrate_config(self) -> None:
        """Perform some configuration migrations."""
        schema_version = await self.config.schema_version()

        if schema_version < 1:
            # Migrate private -> room_type
            guild_dict = await self.config.all_guilds()
            for guild_id in guild_dict:
                avcs = await self.config.guild_from_id(guild_id).get_raw(
                    "auto_voice_channels", default={}
                )
                if avcs:
                    for avc_settings in avcs.values():
                        if "private" in avc_settings:
                            avc_settings["room_type"] = (
                                "private" if avc_settings["private"] else "public"
                            )
                            del avc_settings["private"]
                    await self.config.guild_from_id(guild_id).set_raw(
                        "auto_voice_channels", value=avcs
                    )
            await self.config.schema_version.set(1)

        if schema_version < 2:  # noqa: PLR2004
            # Migrate member_role -> per auto_voice_channel member_roles
            guild_dict = await self.config.all_guilds()
            for guild_id in guild_dict:
                await self.config.guild_from_id(guild_id).clear_raw("member_role")
            await self.config.schema_version.set(2)

        if schema_version < 4:  # noqa: PLR2004
            # Migrate to AUTOROOM_SOURCE custom config group
            guild_dict = await self.config.all_guilds()
            for guild_id in guild_dict:
                avcs = await self.config.guild_from_id(guild_id).get_raw(
                    "auto_voice_channels", default={}
                )
                for avc_id, avc_settings in avcs.items():
                    new_dict = {
                        "dest_category_id": avc_settings["dest_category_id"],
                        "room_type": avc_settings["room_type"],
                    }
                    # The rest of these were optional
                    if "channel_name_type" in avc_settings:
                        new_dict["channel_name_type"] = avc_settings[
                            "channel_name_type"
                        ]
                    await self.config.custom("AUTOROOM_SOURCE", guild_id, avc_id).set(
                        new_dict
                    )
                await self.config.guild_from_id(guild_id).clear_raw(
                    "auto_voice_channels"
                )
            await self.config.schema_version.set(4)

        if schema_version < 5:  # noqa: PLR2004
            # Upgrade room templates
            all_autoroom_sources = await self.config.custom("AUTOROOM_SOURCE").all()
            for guild_id, guild_autoroom_sources in all_autoroom_sources.items():
                for (
                    avc_id,
                    autoroom_source_config,
                ) in guild_autoroom_sources.items():
                    if autoroom_source_config.get("channel_name_format"):
                        # Change username and game template variables
                        new_template = (
                            autoroom_source_config["channel_name_format"]
                            .replace("{username}", "{{username}}")
                            .replace("{game}", "{{game}}")
                        )
                        if autoroom_source_config.get("increment_always"):
                            if "increment_format" in autoroom_source_config:
                                # Always show number, custom format
                                new_template += autoroom_source_config[
                                    "increment_format"
                                ].replace("{number}", "{{dupenum}}")
                            else:
                                # Always show number, default format
                                new_template += " ({{dupenum}})"
                        elif "increment_format" in autoroom_source_config:
                            # Show numbers > 1, custom format
                            new_template += (
                                "{% if dupenum > 1 %}"
                                + autoroom_source_config["increment_format"].replace(
                                    "{number}", "{{dupenum}}"
                                )
                                + "{% endif %}"
                            )
                        else:
                            # Show numbers > 1, default format
                            new_template += (
                                "{% if dupenum > 1 %} ({{dupenum}}){% endif %}"
                            )
                        await self.config.custom(
                            "AUTOROOM_SOURCE", guild_id, avc_id
                        ).channel_name_format.set(new_template)
                        await self.config.custom(
                            "AUTOROOM_SOURCE", guild_id, avc_id
                        ).clear_raw("increment_always")
                        await self.config.custom(
                            "AUTOROOM_SOURCE", guild_id, avc_id
                        ).clear_raw("increment_format")
            await self.config.schema_version.set(5)

        if schema_version < 6:  # noqa: PLR2004
            # Remove member roles
            all_autoroom_sources = await self.config.custom("AUTOROOM_SOURCE").all()
            for guild_id, guild_autoroom_sources in all_autoroom_sources.items():
                for avc_id in guild_autoroom_sources:
                    await self.config.custom(
                        "AUTOROOM_SOURCE", guild_id, avc_id
                    ).clear_raw("member_roles")
            await self.config.schema_version.set(6)

        if schema_version < 7:  # noqa: PLR2004
            # Remove auto text channels
            guild_dict = await self.config.all_guilds()
            for guild_id in guild_dict:
                await self.config.guild_from_id(guild_id).clear_raw("admin_access_text")
                await self.config.guild_from_id(guild_id).clear_raw("mod_access_text")
            all_autoroom_sources = await self.config.custom("AUTOROOM_SOURCE").all()
            for guild_id, guild_autoroom_sources in all_autoroom_sources.items():
                for avc_id in guild_autoroom_sources:
                    await self.config.custom(
                        "AUTOROOM_SOURCE", guild_id, avc_id
                    ).clear_raw("text_channel")
            await self.config.schema_version.set(7)

    async def _cleanup_autorooms(self) -> None:
        """Remove non-existent AutoRooms from the config."""
        await self.bot.wait_until_ready()
        voice_channel_dict = await self.config.all_channels()
        for voice_channel_id, voice_channel_settings in voice_channel_dict.items():
            voice_channel = self.bot.get_channel(voice_channel_id)
            if voice_channel:
                if isinstance(voice_channel, discord.VoiceChannel):
                    # Delete AutoRoom if it is empty
                    await self._process_autoroom_delete(voice_channel)
            else:
                # AutoRoom has already been deleted, clean up legacy text channel if it still exists
                legacy_text_channel = await self.get_autoroom_legacy_text_channel(
                    voice_channel_settings["associated_text_channel"]
                )
                if legacy_text_channel:
                    await legacy_text_channel.delete(
                        reason="AutoRoom: Associated voice channel deleted."
                    )
                await self.config.channel_from_id(voice_channel_id).clear()

    #
    # Listener methods
    #

    @commands.Cog.listener()
    async def on_guild_channel_delete(
        self, guild_channel: discord.abc.GuildChannel
    ) -> None:
        """Clean up config when an AutoRoom (or Source) is deleted (either by the bot or the user)."""
        if not isinstance(guild_channel, discord.VoiceChannel):
            return
        if await self.get_autoroom_source_config(guild_channel):
            # AutoRoom Source was deleted, remove configuration
            await self.config.custom(
                "AUTOROOM_SOURCE", str(guild_channel.guild.id), str(guild_channel.id)
            ).clear()
        else:
            # AutoRoom was deleted, remove associated text channel if it exists
            legacy_text_channel = await self.get_autoroom_legacy_text_channel(
                guild_channel
            )
            if legacy_text_channel:
                await legacy_text_channel.delete(
                    reason="AutoRoom: Associated voice channel deleted."
                )
            await self.config.channel(guild_channel).clear()

    @commands.Cog.listener()
    async def on_voice_state_update(
        self,
        member: discord.Member,
        leaving: discord.VoiceState,
        joining: discord.VoiceState,
    ) -> None:
        """Do voice channel stuff when users move about channels."""
        if await self.bot.cog_disabled_in_guild(self, member.guild):
            return

        # If user left an AutoRoom, do cleanup
        if isinstance(leaving.channel, discord.VoiceChannel):
            autoroom_info = await self.get_autoroom_info(leaving.channel)
            if autoroom_info:
                deleted = await self._process_autoroom_delete(leaving.channel)
                if not deleted:
                    # AutoRoom wasn't deleted, so update text channel perms
                    await self._process_autoroom_legacy_text_perms(leaving.channel)

                    if member.id == autoroom_info["owner"]:
                        # There are still users left and the AutoRoom Owner left.
                        # Start a countdown so that others can claim the AutoRoom.
                        bucket = self.bucket_autoroom_owner_claim.get_bucket(
                            leaving.channel
                        )
                        if bucket:
                            bucket.reset()
                            bucket.update_rate_limit()

        if isinstance(joining.channel, discord.VoiceChannel):
            # If user entered an AutoRoom Source channel, create new AutoRoom
            asc = await self.get_autoroom_source_config(joining.channel)
            if asc:
                await self._process_autoroom_create(joining.channel, asc, member)
            # If user entered an AutoRoom, allow them into the associated text channel
            if await self.get_autoroom_info(joining.channel):
                await self._process_autoroom_legacy_text_perms(joining.channel)

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member) -> None:
        """Check joining users against existing AutoRooms, re-adds their deny override if missing."""
        for autoroom_channel in member.guild.voice_channels:
            autoroom_info = await self.get_autoroom_info(autoroom_channel)
            if autoroom_info and member.id in autoroom_info["denied"]:
                source_channel = member.guild.get_channel(
                    autoroom_info["source_channel"]
                )
                asc = await self.get_autoroom_source_config(source_channel)
                if not asc:
                    continue
                perms = Perms(autoroom_channel.overwrites)
                perms.update(member, asc["perms"]["deny"])
                if perms.modified:
                    await autoroom_channel.edit(
                        overwrites=perms.overwrites if perms.overwrites else {},
                        reason="AutoRoom: Rejoining user, prevent deny evasion",
                    )

    #
    # Private methods
    #

    async def _process_autoroom_create(
        self,
        autoroom_source: discord.VoiceChannel,
        autoroom_source_config: dict[str, Any],
        member: discord.Member,
    ) -> None:
        """Create a voice channel for a member in an AutoRoom Source channel."""
        # Check perms for guild, source, and dest
        guild = autoroom_source.guild
        dest_category = guild.get_channel(autoroom_source_config["dest_category_id"])
        if not isinstance(dest_category, discord.CategoryChannel):
            return
        required_check, optional_check, _ = self.check_perms_source_dest(
            autoroom_source, dest_category
        )
        if not required_check or not optional_check:
            return

        # Check that user isn't spamming
        bucket = self.bucket_autoroom_create.get_bucket(member)
        if bucket:
            retry_after = bucket.update_rate_limit()
            if retry_after:
                warn_bucket = self.bucket_autoroom_create_warn.get_bucket(member)
                if warn_bucket:
                    if not warn_bucket.update_rate_limit():
                        with suppress(
                            discord.Forbidden,
                            discord.NotFound,
                            discord.HTTPException,
                        ):
                            await member.send(
                                "Hello there! It looks like you're trying to make an AutoRoom."
                                "\n"
                                f"Please note that you are only allowed to make **{bucket.rate}** AutoRooms "
                                f"every **{humanize_timedelta(seconds=bucket.per)}**."
                                "\n"
                                f"You can try again in **{humanize_timedelta(seconds=max(retry_after, 1))}**."
                            )
                    return

        # Generate channel name
        taken_channel_names = [
            voice_channel.name for voice_channel in dest_category.voice_channels
        ]
        new_channel_name = self._generate_channel_name(
            autoroom_source_config, member, taken_channel_names
        )

        # Generate overwrites
        perms = Perms()
        dest_perms = dest_category.permissions_for(dest_category.guild.me)
        source_overwrites = (
            autoroom_source.overwrites if autoroom_source.overwrites else {}
        )
        member_roles = self.get_member_roles(autoroom_source)
        for target, permissions in source_overwrites.items():
            # We can't put manage_roles in overwrites, so just get rid of it
            permissions.update(manage_roles=None)
            # Check each permission for each overwrite target to make sure the bot has it allowed in the dest category
            failed_checks = {}
            for name, value in permissions:
                if value is not None:
                    permission_check_result = getattr(dest_perms, name)
                    if not permission_check_result:
                        # If the bot doesn't have the permission allowed in the dest category, just ignore it. Too bad!
                        failed_checks[name] = None
            if failed_checks:
                permissions.update(**failed_checks)
            perms.overwrite(target, permissions)
            if member_roles and target in member_roles:
                # If we have member roles and this target is one, apply AutoRoom type permissions
                perms.update(target, autoroom_source_config["perms"]["access"])

        # Update overwrites for default role to account for AutoRoom type
        if member_roles:
            perms.update(guild.default_role, autoroom_source_config["perms"]["deny"])
        else:
            perms.update(guild.default_role, autoroom_source_config["perms"]["access"])

        # Bot overwrites
        perms.update(guild.me, self.perms_bot_dest)

        # AutoRoom Owner overwrites
        if autoroom_source_config["room_type"] != "server":
            perms.update(member, autoroom_source_config["perms"]["owner"])

        # Admin/moderator/bot overwrites
        # Add bot roles to be allowed
        additional_allowed_roles = await self.get_bot_roles(guild)
        if await self.config.guild(guild).mod_access():
            # Add mod roles to be allowed
            additional_allowed_roles += await self.bot.get_mod_roles(guild)
        if await self.config.guild(guild).admin_access():
            # Add admin roles to be allowed
            additional_allowed_roles += await self.bot.get_admin_roles(guild)
        for role in additional_allowed_roles:
            # Add all the mod/admin roles, if required
            perms.update(role, autoroom_source_config["perms"]["allow"])

        # Create new AutoRoom
        new_voice_channel = await guild.create_voice_channel(
            name=new_channel_name,
            category=dest_category,
            reason="AutoRoom: New AutoRoom needed.",
            overwrites=perms.overwrites if perms.overwrites else {},
            bitrate=min(autoroom_source.bitrate, int(guild.bitrate_limit)),
            user_limit=autoroom_source.user_limit,
        )
        await self.config.channel(new_voice_channel).source_channel.set(
            autoroom_source.id
        )
        if autoroom_source_config["room_type"] != "server":
            await self.config.channel(new_voice_channel).owner.set(member.id)
        try:
            await member.move_to(
                new_voice_channel, reason="AutoRoom: Move user to new AutoRoom."
            )
        except discord.HTTPException:
            await self._process_autoroom_delete(new_voice_channel)
            return

        # Add control panel
        await self.add_control_panel(new_voice_channel, member)

        # Create optional legacy text channel
        new_legacy_text_channel = None
        if autoroom_source_config["legacy_text_channel"]:
            # Sanity check on required permissions
            for perm_name in self.perms_bot_dest_legacy_text:
                if not getattr(dest_perms, perm_name):
                    return
            # Generate overwrites
            perms = Perms()
            perms.update(guild.me, self.perms_bot_dest_legacy_text)
            perms.update(guild.default_role, self.perms_legacy_text_deny)
            if autoroom_source_config["room_type"] != "server":
                perms.update(member, self.perms_autoroom_owner_legacy_text)
            else:
                perms.update(member, self.perms_legacy_text_allow)
            # Admin/moderator overwrites
            additional_allowed_roles_text = []
            if await self.config.guild(guild).mod_access():
                # Add mod roles to be allowed
                additional_allowed_roles_text += await self.bot.get_mod_roles(guild)
            if await self.config.guild(guild).admin_access():
                # Add admin roles to be allowed
                additional_allowed_roles_text += await self.bot.get_admin_roles(guild)
            for role in additional_allowed_roles_text:
                # Add all the mod/admin roles, if required
                perms.update(role, self.perms_legacy_text_allow)
            # Create text channel
            text_channel_topic = self.template.render(
                autoroom_source_config["text_channel_topic"],
                self.get_template_data(member),
            )
            new_legacy_text_channel = await guild.create_text_channel(
                name=new_channel_name.replace("'s ", " "),
                category=dest_category,
                topic=text_channel_topic,
                reason="AutoRoom: New legacy text channel needed.",
                overwrites=perms.overwrites if perms.overwrites else {},
            )

            await self.config.channel(new_voice_channel).associated_text_channel.set(
                new_legacy_text_channel.id
            )

        # Send text chat hint if enabled
        if autoroom_source_config["text_channel_hint"]:
            with suppress(RuntimeError):
                hint = self.template.render(
                    autoroom_source_config["text_channel_hint"],
                    self.get_template_data(member),
                )
                if hint:
                    if new_legacy_text_channel:
                        await new_legacy_text_channel.send(hint)
                    else:
                        await new_voice_channel.send(hint)

    async def add_control_panel(self, channel: discord.VoiceChannel, member: discord.Member):
        """Add a control panel to the voice channel."""
        embed = discord.Embed(title=f"Control Panel for {channel.name}", color=0x7289da)
        embed.add_field(name='Commands:', value="Use the buttons below to manage your channel.")

        view = discord.ui.View()
        view.add_item(discord.ui.Button(label="Lock", custom_id=f"lock_{channel.id}", style=discord.ButtonStyle.primary))
        view.add_item(discord.ui.Button(label="Unlock", custom_id=f"unlock_{channel.id}", style=discord.ButtonStyle.primary))
        view.add_item(discord.ui.Button(label="Name", custom_id=f"name_{channel.id}", style=discord.ButtonStyle.primary))
        view.add_item(discord.ui.Button(label="Limit", custom_id=f"limit_{channel.id}", style=discord.ButtonStyle.primary))
        view.add_item(discord.ui.Button(label="Permit", custom_id=f"permit_{channel.id}", style=discord.ButtonStyle.primary))
        view.add_item(discord.ui.Button(label="Claim", custom_id=f"claim_{channel.id}", style=discord.ButtonStyle.primary))
        view.add_item(discord.ui.Button(label="Reject", custom_id=f"reject_{channel.id}", style=discord.ButtonStyle.primary))

        # Assuming you have a text channel to send this message to
        text_channel = await self.get_autoroom_legacy_text_channel(channel)
        if text_channel:
            await text_channel.send(embed=embed, view=view)

    @commands.Cog.listener()
    async def on_interaction(self, interaction: discord.Interaction):
        """Handle button interactions."""
        if interaction.type != discord.InteractionType.component:
            return

        custom_id = interaction.data['custom_id']
        # Extract the channel ID from the custom_id
        channel_id = int(custom_id.split('_')[-1])
        channel = self.bot.get_channel(channel_id)

        if not channel or not isinstance(channel, discord.VoiceChannel):
            await interaction.response.send_message("Channel not found.", ephemeral=True)
            return

        if custom_id.startswith("lock"):
            await self.lock(channel, interaction)
        elif custom_id.startswith("unlock"):
            await self.unlock(channel, interaction)
        elif custom_id.startswith("name"):
            await self.name(channel, interaction)
        elif custom_id.startswith("limit"):
            await self.limit(channel, interaction)
        elif custom_id.startswith("permit"):
            await self.permit(channel, interaction)
        elif custom_id.startswith("claim"):
            await self.claim(channel, interaction)
        elif custom_id.startswith("reject"):
            await self.reject(channel, interaction)

    async def lock(self, channel: discord.VoiceChannel, interaction: discord.Interaction):
        """Lock the voice channel."""
        await channel.set_permissions(interaction.guild.default_role, connect=False)
        await interaction.response.send_message("Channel locked.")

    async def unlock(self, channel: discord.VoiceChannel, interaction: discord.Interaction):
        """Unlock the voice channel."""
        await channel.set_permissions(interaction.guild.default_role, connect=True)
        await interaction.response.send_message("Channel unlocked.")

    async def name(self, channel: discord.VoiceChannel, interaction: discord.Interaction):
        """Change the name of the voice channel."""
        await interaction.response.send_modal(
            title="Change Channel Name",
            custom_id=f"change_name_modal_{channel.id}",
            components=[
                discord.ui.TextInput(
                    label="New Channel Name",
                    custom_id="new_channel_name",
                    style=discord.TextStyle.short,
                    max_length=100,
                )
            ],
        )

    async def limit(self, channel: discord.VoiceChannel, interaction: discord.Interaction):
        """Change the user limit of the voice channel."""
        await interaction.response.send_modal(
            title="Set Channel Limit",
            custom_id=f"set_limit_modal_{channel.id}",
            components=[
                discord.ui.TextInput(
                    label="New User Limit",
                    custom_id="new_user_limit",
                    style=discord.TextStyle.short,
                    max_length=2,
                )
            ],
        )

    async def permit(self, channel: discord.VoiceChannel, interaction: discord.Interaction):
        """Permit a user to join the voice channel."""
        await interaction.response.send_modal(
            title="Permit User",
            custom_id=f"permit_user_modal_{channel.id}",
            components=[
                discord.ui.TextInput(
                    label="User ID or Mention",
                    custom_id="permit_user_id",
                    style=discord.TextStyle.short,
                )
            ],
        )

    async def claim(self, channel: discord.VoiceChannel, interaction: discord.Interaction):
        """Claim ownership of the voice channel."""
        owner_id = await self.config.channel(channel).owner()
        if owner_id and owner_id != interaction.user.id:
            await interaction.response.send_message("This channel already has an owner.")
            return
        await self.config.channel(channel).owner.set(interaction.user.id)
        await interaction.response.send_message("Channel claimed.")

    async def reject(self, channel: discord.VoiceChannel, interaction: discord.Interaction):
        """Reject a user from the voice channel."""
        await interaction.response.send_modal(
            title="Reject User",
            custom_id=f"reject_user_modal_{channel.id}",
            components=[
                discord.ui.TextInput(
                    label="User ID or Mention",
                    custom_id="reject_user_id",
                    style=discord.TextStyle.short,
                )
            ],
        )

    @commands.Cog.listener()
    async def on_modal_submit(self, interaction: discord.Interaction):
        """Handle modal submissions."""
        if "change_name_modal" in interaction.custom_id:
            new_name = interaction.data['components'][0]['components'][0]['value']
            channel_id = int(interaction.custom_id.split('_')[-1])
            channel = self.bot.get_channel(channel_id)
            if channel:
                await channel.edit(name=new_name)
                await interaction.response.send_message(f"Channel name changed to {new_name}.")
        elif "set_limit_modal" in interaction.custom_id:
            new_limit = interaction.data['components'][0]['components'][0]['value']
            channel_id = int(interaction.custom_id.split('_')[-1])
            channel = self.bot.get_channel(channel_id)
            if channel:
                await channel.edit(user_limit=int(new_limit))
                await interaction.response.send_message(f"Channel user limit set to {new_limit}.")
        elif "permit_user_modal" in interaction.custom_id:
            user_input = interaction.data['components'][0]['components'][0]['value']
            channel_id = int(interaction.custom_id.split('_')[-1])
            channel = self.bot.get_channel(channel_id)
            user = await self._get_user_from_input(interaction.guild, user_input)
            if user and channel:
                await channel.set_permissions(user, connect=True)
                await interaction.response.send_message(f"{user.display_name} has been permitted to join the channel.")
            else:
                await interaction.response.send_message("User not found.", ephemeral=True)
        elif "reject_user_modal" in interaction.custom_id:
            user_input = interaction.data['components'][0]['components'][0]['value']
            channel_id = int(interaction.custom_id.split('_')[-1])
            channel = self.bot.get_channel(channel_id)
            user = await self._get_user_from_input(interaction.guild, user_input)
            if user and channel:
                await channel.set_permissions(user, connect=False)
                await interaction.response.send_message(f"{user.display_name} has been rejected from joining the channel.")
            else:
                await interaction.response.send_message("User not found.", ephemeral=True)

    async def _get_user_from_input(self, guild, user_input):
        """Helper method to get a user object from an ID or mention."""
        if user_input.isdigit():
            return guild.get_member(int(user_input))
        elif user_input.startswith("<@") and user_input.endswith(">"):
            user_id = user_input[2:-1]
            return guild.get_member(int(user_id))
        return None
