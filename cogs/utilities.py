import aiohttp
from discord import app_commands, Interaction
from discord.ext import commands
from datetime import datetime, timezone
import random
import discord
import json

class Utilities(commands.GroupCog, group_name="utilities"):
    def __init__(self, bot):
        self.bot = bot
        self.bot_start_time = datetime.now(timezone.utc)

    @app_commands.command(
        name="ping",
        description="get bot's latency"
    )
    async def ping(
        self,
        interaction: Interaction
    ):
        embed = discord.Embed(
            title="Pong! 🏓",
            description=f"Ping: {round(self.bot.latency * 1000)} ms",
            color=discord.Color.orange()
        )

        await interaction.response.send_message(embed=embed)

    @app_commands.command(
    name="avatar",
    description="show a user's avatar"
    )
    @app_commands.describe(
        user="the user whose avatar you want to see"
    )
    async def avatar(
        self,
        interaction: Interaction,
        user: discord.User | None = None
    ):
        user = user or interaction.user

        embed = discord.Embed(
            title=f"{user.display_name}'s Avatar",
            color=discord.Color.orange()
        )

        embed.set_image(url=user.display_avatar.url)

        view = discord.ui.View()
        view.add_item(
            discord.ui.Button(
                label="View Full Avatar",
                url=user.display_avatar.url
            )
        )

        await interaction.response.send_message(
            embed=embed,
            view=view
        )

    @app_commands.command(
        name="banner",
        description="show a user's banner"
    )
    @app_commands.describe(
        user="the user whose banner you want to see"
    )
    async def banner(
        self,
        interaction: Interaction,
        user: discord.User | None = None
    ):
        user = user or interaction.user

        user = await self.bot.fetch_user(user.id)

        if not user.banner:
            embed = discord.Embed(
                title="No Banner",
                description=f"**{user.display_name}** doesn't have a profile banner.",
                color=discord.Color.red()
            )

            await interaction.response.send_message(
                embed=embed,
                ephemeral=True
            )
            return

        embed = discord.Embed(
            title=f"{user.display_name}'s Banner",
            color=discord.Color.orange()
        )

        embed.set_image(url=user.banner.url)

        view = discord.ui.View()
        view.add_item(
            discord.ui.Button(
                label="View Full Banner",
                url=user.banner.url
            )
        )

        await interaction.response.send_message(
            embed=embed,
            view=view
        )

    @app_commands.command(
    name="serverinfo",
    description="show information about the server"
    )
    async def serverinfo(
        self,
        interaction: Interaction
    ):
        guild = interaction.guild

        if guild is None:
            embed = discord.Embed(
                title="Server Info",
                description="This command can only be used inside a server.",
                color=discord.Color.red()
            )

            await interaction.response.send_message(
                embed=embed,
                ephemeral=True
            )
            return

        owner = guild.owner
        owner_text = owner.mention if owner else f"<@{guild.owner_id}>"

        humans = sum(
            1 for member in guild.members
            if not member.bot
        )

        bots = sum(
            1 for member in guild.members
            if member.bot
        )

        text_channels = len(guild.text_channels)
        voice_channels = len(guild.voice_channels)
        category_channels = len(guild.categories)
        forum_channels = len(guild.forums)

        embed = discord.Embed(
            title=guild.name,
            color=discord.Color.orange()
        )

        if guild.icon:
            embed.set_thumbnail(url=guild.icon.url)

        embed.add_field(
            name="👑 Owner",
            value=owner_text,
            inline=True
        )

        embed.add_field(
            name="🆔 Server ID",
            value=f"`{guild.id}`",
            inline=True
        )

        embed.add_field(
            name="📅 Created",
            value=discord.utils.format_dt(
                guild.created_at,
                style="F"
            ),
            inline=True
        )

        embed.add_field(
            name="👥 Members",
            value=(
                f"**{guild.member_count:,}** total\n"
                f"👤 {humans:,} humans\n"
                f"🤖 {bots:,} bots"
            ),
            inline=True
        )

        embed.add_field(
            name="💬 Channels",
            value=(
                f"💬 {text_channels} text\n"
                f"🔊 {voice_channels} voice\n"
                f"📁 {category_channels} categories\n"
                f"📝 {forum_channels} forums"
            ),
            inline=True
        )

        embed.add_field(
            name="🎭 Roles",
            value=f"{len(guild.roles):,}",
            inline=True
        )

        embed.add_field(
            name="😀 Emojis",
            value=f"{len(guild.emojis):,}",
            inline=True
        )

        embed.add_field(
            name="🏷️ Stickers",
            value=f"{len(guild.stickers):,}",
            inline=True
        )

        embed.add_field(
            name="🚀 Boosts",
            value=(
                f"Level **{guild.premium_tier}**\n"
                f"{guild.premium_subscription_count or 0} boosts"
            ),
            inline=True
        )

        embed.add_field(
            name="🔐 Verification",
            value=guild.verification_level.name.replace(
                "_", " "
            ).title(),
            inline=True
        )

        if guild.features:
            features = [
                feature.replace("_", " ").title()
                for feature in guild.features
            ]

            embed.add_field(
                name="✨ Features",
                value=", ".join(features),
                inline=False
            )

        embed.set_footer(
            text=f"Server ID: {guild.id}"
        )

        await interaction.response.send_message(
            embed=embed
        )

    @app_commands.command(
    name="info",
    description="view information about Clanker"
    )
    async def info(
        self,
        interaction: discord.Interaction
    ):
        with open("data.json", "r") as f:
            data = json.load(f)

        version = data.get(
            "version",
            "Unknown"
        )

        ping = round(
            self.bot.latency * 1000
        )

        users = sum(
            g.member_count or 0
            for g in self.bot.guilds
        )

        servers = len(self.bot.guilds)

        commands = sum(
            1
            for cmd in self.bot.tree.walk_commands()
            if not isinstance(cmd, app_commands.Group)
        )

        embed = discord.Embed(
            title="🤖 Info",
            color=discord.Color.orange()
        )

        embed.add_field(
            name="🏷️ Version",
            value=f"v{version}",
            inline=True
        )

        embed.add_field(
            name="📡 Ping",
            value=f"{ping} ms",
            inline=True
        )

        embed.add_field(
            name="🤖 Commands",
            value=str(commands),
            inline=True
        )

        embed.add_field(
            name="👤 Users",
            value=f"{users:,}",
            inline=True
        )

        embed.add_field(
            name="🖥️ Servers",
            value=f"{servers:,}",
            inline=True
        )

        await interaction.response.send_message(embed=embed)

    @app_commands.command(
    name="membercount",
    description="show the server's member count"
    )
    async def membercount(
        self,
        interaction: Interaction
    ):
        guild = interaction.guild

        if guild is None:
            embed = discord.Embed(
                title="Member Count",
                description="This command can only be used inside a server.",
                color=discord.Color.red()
            )
            await interaction.response.send_message(
                embed=embed,
                ephemeral=True
            )
            return

        humans = sum(
            1 for member in guild.members
            if not member.bot
        )

        bots = sum(
            1 for member in guild.members
            if member.bot
        )

        embed = discord.Embed(
            title=f"{guild.name} Member Count",
            color=discord.Color.orange()
        )

        if guild.icon:
            embed.set_thumbnail(url=guild.icon.url)

        embed.add_field(
            name="👥 Total",
            value=f"**{guild.member_count:,}**",
            inline=True
        )

        embed.add_field(
            name="👤 Humans",
            value=f"**{humans:,}**",
            inline=True
        )

        embed.add_field(
            name="🤖 Bots",
            value=f"**{bots:,}**",
            inline=True
        )

        await interaction.response.send_message(
            embed=embed
        )

    @app_commands.command(
    name="userinfo",
    description="show information about a user"
    )
    @app_commands.describe(
        user="the user you want information about"
    )
    async def userinfo(
        self,
        interaction: Interaction,
        user: discord.Member | None = None
    ):
        user = user or interaction.user

        embed = discord.Embed(
            title=f"{user.display_name}",
            color=discord.Color.orange()
        )

        embed.set_thumbnail(url=user.display_avatar.url)

        embed.add_field(
            name="👤 Username",
            value=f"`{user.name}`",
            inline=True
        )

        embed.add_field(
            name="🆔 User ID",
            value=f"`{user.id}`",
            inline=True
        )

        embed.add_field(
            name="🤖 Bot",
            value="Yes" if user.bot else "No",
            inline=True
        )

        embed.add_field(
            name="📅 Account Created",
            value=discord.utils.format_dt(
                user.created_at,
                style="F"
            ),
            inline=False
        )

        if isinstance(user, discord.Member):
            embed.add_field(
                name="📥 Joined Server",
                value=discord.utils.format_dt(
                    user.joined_at,
                    style="F"
                ) if user.joined_at else "Unknown",
                inline=False
            )

            roles = [
                role.mention
                for role in reversed(user.roles)
                if role != interaction.guild.default_role
            ]

            embed.add_field(
                name=f"🎭 Roles ({len(roles)})",
                value=", ".join(roles[:20]) if roles else "None",
                inline=False
            )

        embed.set_footer(
            text=f"User ID: {user.id}"
        )

        await interaction.response.send_message(
            embed=embed
        )

    @app_commands.command(
        name="roleinfo",
        description="show information about a role"
    )
    @app_commands.describe(
        role="the role you want information about"
    )
    async def roleinfo(
        self,
        interaction: Interaction,
        role: discord.Role
    ):
        embed = discord.Embed(
            title=f"{role.name}",
            color=role.color if role.color.value else discord.Color.orange()
        )

        embed.add_field(
            name="🆔 Role ID",
            value=f"`{role.id}`",
            inline=True
        )

        embed.add_field(
            name="🎨 Color",
            value=f"`{role.color}`",
            inline=True
        )

        embed.add_field(
            name="📊 Position",
            value=str(role.position),
            inline=True
        )

        embed.add_field(
            name="👥 Members",
            value=f"{len(role.members):,}",
            inline=True
        )

        embed.add_field(
            name="🔔 Mentionable",
            value="Yes" if role.mentionable else "No",
            inline=True
        )

        embed.add_field(
            name="📌 Hoisted",
            value="Yes" if role.hoist else "No",
            inline=True
        )

        embed.add_field(
            name="🔗 Managed",
            value="Yes" if role.managed else "No",
            inline=True
        )

        embed.add_field(
            name="📅 Created",
            value=discord.utils.format_dt(
                role.created_at,
                style="F"
            ),
            inline=False
        )

        await interaction.response.send_message(
            embed=embed
        )

    @app_commands.command(
        name="channelinfo",
        description="show information about a channel"
    )
    @app_commands.describe(
        channel="the channel you want information about"
    )
    async def channelinfo(
        self,
        interaction: Interaction,
        channel: discord.abc.GuildChannel | None = None
    ):
        channel = channel or interaction.channel

        embed = discord.Embed(
            title=f"#{channel.name}",
            color=discord.Color.orange()
        )

        embed.add_field(
            name="🆔 Channel ID",
            value=f"`{channel.id}`",
            inline=True
        )

        embed.add_field(
            name="📁 Type",
            value=channel.type.name.replace("_", " ").title(),
            inline=True
        )

        embed.add_field(
            name="📅 Created",
            value=discord.utils.format_dt(
                channel.created_at,
                style="F"
            ),
            inline=True
        )

        if channel.category:
            embed.add_field(
                name="📂 Category",
                value=channel.category.mention,
                inline=True
            )

        if isinstance(channel, discord.TextChannel):
            embed.add_field(
                name="🐌 Slowmode",
                value=(
                    f"{channel.slowmode_delay}s"
                    if channel.slowmode_delay
                    else "Disabled"
                ),
                inline=True
            )

        if isinstance(channel, discord.VoiceChannel):
            embed.add_field(
                name="🔊 Bitrate",
                value=f"{channel.bitrate // 1000} kbps",
                inline=True
            )

            embed.add_field(
                name="👥 User Limit",
                value=(
                    str(channel.user_limit)
                    if channel.user_limit
                    else "Unlimited"
                ),
                inline=True
            )

        embed.set_footer(
            text=f"Channel ID: {channel.id}"
        )

        await interaction.response.send_message(
            embed=embed
        )

    @app_commands.command(
        name="permissions",
        description="show a user's server permissions"
    )
    @app_commands.describe(
        user="the user whose permissions you want to see"
    )
    async def permissions(
        self,
        interaction: Interaction,
        user: discord.Member | None = None
    ):
        user = user or interaction.user

        permissions = user.guild_permissions

        enabled = [
            permission.replace("_", " ").title()
            for permission, value in permissions
            if value
        ]

        embed = discord.Embed(
            title=f"{user.display_name}'s Permissions",
            color=discord.Color.orange()
        )

        if enabled:
            embed.description = "\n".join(
                f"✅ {permission}"
                for permission in enabled
            )
        else:
            embed.description = "No permissions."

        embed.set_footer(
            text=f"User ID: {user.id}"
        )

        await interaction.response.send_message(
            embed=embed,
            ephemeral=True
        )

    @app_commands.command(
        name="emoji",
        description="show information about an emoji"
    )
    @app_commands.describe(
        emoji="the custom emoji you want information about"
    )
    async def emoji(
        self,
        interaction: Interaction,
        emoji: str
    ):
        try:
            converted = await commands.PartialEmojiConverter().convert(
                await commands.Context.from_interaction(interaction),
                emoji
            )
        except commands.BadArgument:
            embed = discord.Embed(
                title="Invalid Emoji",
                description="I couldn't find a valid custom emoji in that input.",
                color=discord.Color.red()
            )

            await interaction.response.send_message(
                embed=embed,
                ephemeral=True
            )
            return

        embed = discord.Embed(
            title=f"{converted.name}",
            color=discord.Color.orange()
        )

        embed.set_image(url=converted.url)

        embed.add_field(
            name="🆔 Emoji ID",
            value=f"`{converted.id}`",
            inline=True
        )

        embed.add_field(
            name="🎞️ Animated",
            value="Yes" if converted.animated else "No",
            inline=True
        )

        view = discord.ui.View()

        view.add_item(
            discord.ui.Button(
                label="View Full Emoji",
                url=converted.url
            )
        )

        await interaction.response.send_message(
            embed=embed,
            view=view
        )

    @app_commands.command(
        name="sticker",
        description="show information about a sticker"
    )
    @app_commands.describe(
        sticker="the sticker ID you want information about"
    )
    async def sticker(
        self,
        interaction: Interaction,
        sticker: str
    ):
        guild = interaction.guild

        if guild is None:
            embed = discord.Embed(
                title="Sticker Info",
                description="This command can only be used inside a server.",
                color=discord.Color.red()
            )

            await interaction.response.send_message(
                embed=embed,
                ephemeral=True
            )
            return

        try:
            sticker_id = int(sticker)
        except ValueError:
            embed = discord.Embed(
                title="Invalid Sticker",
                description="Please provide a valid sticker ID.",
                color=discord.Color.red()
            )

            await interaction.response.send_message(
                embed=embed,
                ephemeral=True
            )
            return

        sticker_obj = discord.utils.get(
            guild.stickers,
            id=sticker_id
        )

        if sticker_obj is None:
            embed = discord.Embed(
                title="Sticker Not Found",
                description="I couldn't find that sticker in this server.",
                color=discord.Color.red()
            )

            await interaction.response.send_message(
                embed=embed,
                ephemeral=True
            )
            return

        embed = discord.Embed(
            title=sticker_obj.name,
            color=discord.Color.orange()
        )

        embed.set_image(url=sticker_obj.url)

        embed.add_field(
            name="🆔 Sticker ID",
            value=f"`{sticker_obj.id}`",
            inline=True
        )

        embed.add_field(
            name="📝 Description",
            value=sticker_obj.description or "None",
            inline=False
        )

        embed.add_field(
            name="🏷️ Format",
            value=sticker_obj.format.name.title(),
            inline=True
        )

        view = discord.ui.View()

        view.add_item(
            discord.ui.Button(
                label="View Full Sticker",
                url=sticker_obj.url
            )
        )

        await interaction.response.send_message(
            embed=embed,
            view=view
        )

    @app_commands.command(
        name="timestamp",
        description="create a Discord timestamp"
    )
    @app_commands.describe(
        timestamp="Unix timestamp to convert"
    )
    async def timestamp(
        self,
        interaction: Interaction,
        timestamp: int
    ):
        try:
            dt = datetime.fromtimestamp(
                timestamp,
                tz=timezone.utc
            )
        except (ValueError, OverflowError, OSError):
            embed = discord.Embed(
                title="Invalid Timestamp",
                description="That isn't a valid Unix timestamp.",
                color=discord.Color.red()
            )

            await interaction.response.send_message(
                embed=embed,
                ephemeral=True
            )
            return

        embed = discord.Embed(
            title="Discord Timestamp",
            color=discord.Color.orange()
        )

        embed.add_field(
            name="📅 Date",
            value=discord.utils.format_dt(
                dt,
                style="F"
            ),
            inline=False
        )

        embed.add_field(
            name="⏰ Relative",
            value=discord.utils.format_dt(
                dt,
                style="R"
            ),
            inline=False
        )

        embed.add_field(
            name="💻 Timestamp",
            value=f"`<t:{timestamp}:F>`",
            inline=False
        )

        embed.add_field(
            name="🕐 Short",
            value=f"`<t:{timestamp}:f>`",
            inline=False
        )

        await interaction.response.send_message(
            embed=embed
        )

    @app_commands.command(
        name="snowflake",
        description="get information from a Discord ID"
    )
    @app_commands.describe(
        id="the Discord ID you want to decode"
    )
    async def snowflake(
        self,
        interaction: Interaction,
        id: str
    ):
        try:
            snowflake = int(id)

            if snowflake < 0:
                raise ValueError

            timestamp = (
                (snowflake >> 22)
                + 1420070400000
            ) / 1000

            created_at = datetime.fromtimestamp(
                timestamp,
                tz=timezone.utc
            )

        except (ValueError, OverflowError, OSError):
            embed = discord.Embed(
                title="Invalid Snowflake",
                description="Please provide a valid Discord snowflake.",
                color=discord.Color.red()
            )

            await interaction.response.send_message(
                embed=embed,
                ephemeral=True
            )
            return

        embed = discord.Embed(
            title="Discord Snowflake",
            color=discord.Color.orange()
        )

        embed.add_field(
            name="🆔 ID",
            value=f"`{snowflake}`",
            inline=False
        )

        embed.add_field(
            name="📅 Created",
            value=discord.utils.format_dt(
                created_at,
                style="F"
            ),
            inline=True
        )

        embed.add_field(
            name="⏱️ Relative",
            value=discord.utils.format_dt(
                created_at,
                style="R"
            ),
            inline=True
        )

        embed.set_footer(
            text="Discord Snowflake"
        )

        await interaction.response.send_message(
            embed=embed
        )

    @app_commands.command(
    name="cmdcount",
    description="how many commands Crumb has"
    )
    async def cmdcount(
        self,
        interaction: Interaction
    ):
        total = 0
        category_counts = {}

        for cmd in self.bot.tree.walk_commands():
            if isinstance(cmd, app_commands.Group):
                continue

            total += 1

            cog_name = (
                cmd.binding.__class__.__name__
                if getattr(cmd, "binding", None)
                else "No Category"
            )

            if cog_name not in category_counts:
                category_counts[cog_name] = 0

            category_counts[cog_name] += 1

        desc = f"**Total Commands:** {total}\n\n"

        for category, count in category_counts.items():
            desc += f"- **{category}**: {count}\n"

        embed = discord.Embed(
            title="Command Count 🤖",
            description=desc,
            color=discord.Color.orange()
        )

        await interaction.response.send_message(embed=embed)

    def get_all_commands(self):
        cmds = []

        for cmd in self.bot.tree.walk_commands():

            if isinstance(cmd, app_commands.Group):
                continue

            cmds.append(cmd)

        return cmds

    @app_commands.command(
        name="help",
        description="get help with the bot"
    )
    async def help(
        self,
        interaction: discord.Interaction
    ):

        def is_admin(user_id):
            return (
                user_id in self.bot.data.get("admins", [])
                or
                user_id in self.bot.data.get("owners", [])
            )

        categories = {}
        admin_commands = []

        for cmd in self.get_all_commands():

            cog_name = (
                cmd.binding.__class__.__name__
                if getattr(cmd, "binding", None)
                else "Other"
            )

            if cog_name == "Admin":

                if is_admin(interaction.user.id):
                    admin_commands.append(cmd)

                continue

            categories.setdefault(
                cog_name,
                []
            ).append(cmd)

        if is_admin(interaction.user.id) and admin_commands:
            categories["Admin"] = admin_commands

        pages = []

        for category, cmds in categories.items():

            cmds = sorted(
                cmds,
                key=lambda c: c.name
            )

            chunk_size = 5

            for i in range(
                0,
                len(cmds),
                chunk_size
            ):
                chunk = cmds[
                    i:i + chunk_size
                ]

                description = "\n".join(
                    f"{getattr(cmd, 'mention', f'/{cmd.name}')} "
                    f"- {cmd.description}"
                    for cmd in chunk
                )

                page_num = (
                    i // chunk_size
                ) + 1

                total_pages = (
                    len(cmds) + chunk_size - 1
                ) // chunk_size

                embed = discord.Embed(
                    title=(
                        f"Help - {category} "
                        f"({page_num}/{total_pages})"
                    ),
                    description=description,
                    color=discord.Color.orange()
                )

                pages.append(embed)

        if not pages:
            pages.append(
                discord.Embed(
                    title="Help",
                    description="No commands found.",
                    color=discord.Color.red()
                )
            )


        class HelpView(discord.ui.View):

            def __init__(self):
                super().__init__(timeout=120)
                self.current = 0


            @discord.ui.button(
                label="◀️",
                style=discord.ButtonStyle.gray
            )
            async def previous(
                self,
                interaction: discord.Interaction,
                button: discord.ui.Button
            ):
                self.current = (
                    self.current - 1
                ) % len(pages)

                await interaction.response.edit_message(
                    embed=pages[self.current],
                    view=self
                )


            @discord.ui.button(
                label="▶️",
                style=discord.ButtonStyle.gray
            )
            async def next(
                self,
                interaction: discord.Interaction,
                button: discord.ui.Button
            ):
                self.current = (
                    self.current + 1
                ) % len(pages)

                await interaction.response.edit_message(
                    embed=pages[self.current],
                    view=self
                )


        view = HelpView()

        await interaction.response.send_message(
            embed=pages[0],
            view=view,
            ephemeral=True
        )

async def setup(bot):
    await bot.add_cog(Utilities(bot))