import re
import sqlite3
import time
from collections import defaultdict, deque

import discord
from discord import app_commands
from discord.ext import commands

class Automod(commands.GroupCog, group_name="automod"):
    def __init__(self, bot):
        self.bot = bot

        self.db = sqlite3.connect("db/automod.db")
        self.db.row_factory = sqlite3.Row

        self.db.execute("""
            CREATE TABLE IF NOT EXISTS automod (
                guild_id INTEGER PRIMARY KEY,
                enabled INTEGER NOT NULL DEFAULT 0,
                log_channel_id INTEGER
            )
        """)

        self.db.execute("""
            CREATE TABLE IF NOT EXISTS blocked_words (
                guild_id INTEGER NOT NULL,
                word TEXT NOT NULL,
                PRIMARY KEY (guild_id, word)
            )
        """)

        self.db.execute("""
            CREATE TABLE IF NOT EXISTS whitelist (
                guild_id INTEGER NOT NULL,
                target_id INTEGER NOT NULL,
                target_type TEXT NOT NULL,
                PRIMARY KEY (guild_id, target_id, target_type)
            )
        """)

        self.db.execute("""
            CREATE TABLE IF NOT EXISTS automod_rules (
                guild_id INTEGER PRIMARY KEY,
                links INTEGER NOT NULL DEFAULT 0,
                invites INTEGER NOT NULL DEFAULT 0,
                spam INTEGER NOT NULL DEFAULT 0,
                mentions INTEGER NOT NULL DEFAULT 0,
                caps INTEGER NOT NULL DEFAULT 0
            )
        """)

        self.db.commit()

        self.message_history = defaultdict(
            lambda: deque(maxlen=10)
        )

    def error_embed(self, text):
        return discord.Embed(
            description=f"❌ {text}",
            color=discord.Color.red()
        )

    def success_embed(self, text):
        return discord.Embed(
            description=f"🟠 {text}",
            color=discord.Color.orange()
        )

    def get_config(self, guild_id):
        row = self.db.execute(
            """
            SELECT *
            FROM automod
            WHERE guild_id = ?
            """,
            (guild_id,)
        ).fetchone()

        if row is None:

            self.db.execute(
                """
                INSERT INTO automod (
                    guild_id,
                    enabled,
                    log_channel_id
                )
                VALUES (?, 0, NULL)
                """,
                (guild_id,)
            )

            self.db.commit()

            row = self.db.execute(
                """
                SELECT *
                FROM automod
                WHERE guild_id = ?
                """,
                (guild_id,)
            ).fetchone()

        return row

    def get_rules(self, guild_id):
        row = self.db.execute(
            """
            SELECT *
            FROM automod_rules
            WHERE guild_id = ?
            """,
            (guild_id,)
        ).fetchone()

        if row is None:

            self.db.execute(
                """
                INSERT INTO automod_rules (
                    guild_id
                )
                VALUES (?)
                """,
                (guild_id,)
            )

            self.db.commit()

            row = self.db.execute(
                """
                SELECT *
                FROM automod_rules
                WHERE guild_id = ?
                """,
                (guild_id,)
            ).fetchone()

        return row

    def set_rule(
        self,
        guild_id,
        rule,
        enabled
    ):

        self.get_rules(guild_id)

        allowed_rules = {
            "links",
            "invites",
            "spam",
            "mentions",
            "caps"
        }

        if rule not in allowed_rules:
            return

        self.db.execute(
            f"""
            UPDATE automod_rules
            SET {rule} = ?
            WHERE guild_id = ?
            """,
            (
                1 if enabled else 0,
                guild_id
            )
        )

        self.db.commit()

    def get_blocked_words(self, guild_id):
        rows = self.db.execute(
            """
            SELECT word
            FROM blocked_words
            WHERE guild_id = ?
            ORDER BY word ASC
            """,
            (guild_id,)
        ).fetchall()

        return [
            row["word"]
            for row in rows
        ]

    def is_whitelisted(
        self,
        guild_id,
        member,
        channel
    ):

        targets = [
            (
                member.id,
                "user"
            )
        ]

        for role in member.roles:
            targets.append(
                (
                    role.id,
                    "role"
                )
            )

        if channel is not None:
            targets.append(
                (
                    channel.id,
                    "channel"
                )
            )

        for target_id, target_type in targets:

            row = self.db.execute(
                """
                SELECT 1
                FROM whitelist
                WHERE guild_id = ?
                AND target_id = ?
                AND target_type = ?
                """,
                (
                    guild_id,
                    target_id,
                    target_type
                )
            ).fetchone()

            if row:
                return True

        return False

    @app_commands.command(
        name="enable",
        description="Enable automod"
    )
    @app_commands.checks.has_permissions(
        manage_guild=True
    )
    async def enable(
        self,
        interaction: discord.Interaction
    ):

        guild_id = interaction.guild.id

        self.get_config(guild_id)

        self.db.execute(
            """
            UPDATE automod
            SET enabled = 1
            WHERE guild_id = ?
            """,
            (guild_id,)
        )

        self.db.commit()

        await interaction.response.send_message(
            embed=self.success_embed(
                "Automod has been enabled."
            )
        )

    @app_commands.command(
        name="disable",
        description="Disable automod"
    )
    @app_commands.checks.has_permissions(
        manage_guild=True
    )
    async def disable(
        self,
        interaction: discord.Interaction
    ):

        guild_id = interaction.guild.id

        self.get_config(guild_id)

        self.db.execute(
            """
            UPDATE automod
            SET enabled = 0
            WHERE guild_id = ?
            """,
            (guild_id,)
        )

        self.db.commit()

        await interaction.response.send_message(
            embed=self.success_embed(
                "Automod has been disabled."
            )
        )

    @app_commands.command(
        name="config",
        description="View automod configuration"
    )
    @app_commands.checks.has_permissions(
        manage_guild=True
    )
    async def config(
        self,
        interaction: discord.Interaction
    ):

        guild_id = interaction.guild.id

        config = self.get_config(guild_id)
        rules = self.get_rules(guild_id)
        words = self.get_blocked_words(guild_id)

        if config["log_channel_id"]:

            channel = interaction.guild.get_channel(
                config["log_channel_id"]
            )

            log_channel = (
                channel.mention
                if channel
                else f"<#{config['log_channel_id']}>"
            )

        else:
            log_channel = "Not configured"

        embed = discord.Embed(
            title="Automod Configuration",
            color=discord.Color.orange()
        )

        embed.add_field(
            name="Status",
            value=(
                "Enabled"
                if config["enabled"]
                else "Disabled"
            ),
            inline=True
        )

        embed.add_field(
            name="Log channel",
            value=log_channel,
            inline=True
        )

        embed.add_field(
            name="Rules",
            value=(
                f"**Links:** "
                f"{'Enabled' if rules['links'] else 'Disabled'}\n"

                f"**Invites:** "
                f"{'Enabled' if rules['invites'] else 'Disabled'}\n"

                f"**Spam:** "
                f"{'Enabled' if rules['spam'] else 'Disabled'}\n"

                f"**Mentions:** "
                f"{'Enabled' if rules['mentions'] else 'Disabled'}\n"

                f"**Caps:** "
                f"{'Enabled' if rules['caps'] else 'Disabled'}"
            ),
            inline=False
        )

        embed.add_field(
            name="Blocked words",
            value=str(len(words)),
            inline=True
        )

        await interaction.response.send_message(
            embed=embed
        )

    @app_commands.command(
        name="words",
        description="Add or remove blocked words"
    )
    @app_commands.describe(
        action="Whether to add or remove a word",
        word="The word to manage"
    )
    @app_commands.choices(
        action=[
            app_commands.Choice(
                name="Add",
                value="add"
            ),
            app_commands.Choice(
                name="Remove",
                value="remove"
            )
        ]
    )
    @app_commands.checks.has_permissions(
        manage_guild=True
    )
    async def words(
        self,
        interaction: discord.Interaction,
        action: app_commands.Choice[str],
        word: str
    ):

        guild_id = interaction.guild.id

        word = word.lower().strip()

        if not word:

            await interaction.response.send_message(
                embed=self.error_embed(
                    "You need to provide a word."
                ),
                ephemeral=True
            )

            return

        if len(word) > 100:

            await interaction.response.send_message(
                embed=self.error_embed(
                    "The word must be 100 characters or fewer."
                ),
                ephemeral=True
            )

            return

        if action.value == "add":

            try:

                self.db.execute(
                    """
                    INSERT INTO blocked_words (
                        guild_id,
                        word
                    )
                    VALUES (?, ?)
                    """,
                    (
                        guild_id,
                        word
                    )
                )

                self.db.commit()

            except sqlite3.IntegrityError:

                await interaction.response.send_message(
                    embed=self.error_embed(
                        "That word is already blocked."
                    ),
                    ephemeral=True
                )

                return

            await interaction.response.send_message(
                embed=self.success_embed(
                    f"`{word}` has been added to the blocked word list."
                )
            )

        else:

            cursor = self.db.execute(
                """
                DELETE FROM blocked_words
                WHERE guild_id = ?
                AND word = ?
                """,
                (
                    guild_id,
                    word
                )
            )

            self.db.commit()

            if cursor.rowcount == 0:

                await interaction.response.send_message(
                    embed=self.error_embed(
                        "That word isn't blocked."
                    ),
                    ephemeral=True
                )

                return

            await interaction.response.send_message(
                embed=self.success_embed(
                    f"`{word}` has been removed from the blocked word list."
                )
            )

    @app_commands.command(
        name="links",
        description="Enable or disable link filtering"
    )
    @app_commands.describe(
        enabled="Whether links should be blocked"
    )
    @app_commands.choices(
        enabled=[
            app_commands.Choice(
                name="Enabled",
                value="true"
            ),
            app_commands.Choice(
                name="Disabled",
                value="false"
            )
        ]
    )
    @app_commands.checks.has_permissions(
        manage_guild=True
    )
    async def links(
        self,
        interaction: discord.Interaction,
        enabled: app_commands.Choice[str]
    ):

        value = enabled.value == "true"

        self.set_rule(
            interaction.guild.id,
            "links",
            value
        )

        status = (
            "enabled"
            if value
            else "disabled"
        )

        await interaction.response.send_message(
            embed=self.success_embed(
                f"Link filtering has been {status}."
            )
        )

    @app_commands.command(
        name="invites",
        description="Enable or disable Discord invite filtering"
    )
    @app_commands.describe(
        enabled="Whether Discord invites should be blocked"
    )
    @app_commands.choices(
        enabled=[
            app_commands.Choice(
                name="Enabled",
                value="true"
            ),
            app_commands.Choice(
                name="Disabled",
                value="false"
            )
        ]
    )
    @app_commands.checks.has_permissions(
        manage_guild=True
    )
    async def invites(
        self,
        interaction: discord.Interaction,
        enabled: app_commands.Choice[str]
    ):

        value = enabled.value == "true"

        self.set_rule(
            interaction.guild.id,
            "invites",
            value
        )

        status = (
            "enabled"
            if value
            else "disabled"
        )

        await interaction.response.send_message(
            embed=self.success_embed(
                f"Discord invite filtering has been {status}."
            )
        )

    @app_commands.command(
        name="spam",
        description="Enable or disable spam detection"
    )
    @app_commands.describe(
        enabled="Whether spam detection should be enabled"
    )
    @app_commands.choices(
        enabled=[
            app_commands.Choice(
                name="Enabled",
                value="true"
            ),
            app_commands.Choice(
                name="Disabled",
                value="false"
            )
        ]
    )
    @app_commands.checks.has_permissions(
        manage_guild=True
    )
    async def spam(
        self,
        interaction: discord.Interaction,
        enabled: app_commands.Choice[str]
    ):

        value = enabled.value == "true"

        self.set_rule(
            interaction.guild.id,
            "spam",
            value
        )

        status = (
            "enabled"
            if value
            else "disabled"
        )

        await interaction.response.send_message(
            embed=self.success_embed(
                f"Spam detection has been {status}."
            )
        )

    @app_commands.command(
        name="mentions",
        description="Enable or disable mention filtering"
    )
    @app_commands.describe(
        enabled="Whether excessive mentions should be blocked"
    )
    @app_commands.choices(
        enabled=[
            app_commands.Choice(
                name="Enabled",
                value="true"
            ),
            app_commands.Choice(
                name="Disabled",
                value="false"
            )
        ]
    )
    @app_commands.checks.has_permissions(
        manage_guild=True
    )
    async def mentions(
        self,
        interaction: discord.Interaction,
        enabled: app_commands.Choice[str]
    ):

        value = enabled.value == "true"

        self.set_rule(
            interaction.guild.id,
            "mentions",
            value
        )

        status = (
            "enabled"
            if value
            else "disabled"
        )

        await interaction.response.send_message(
            embed=self.success_embed(
                f"Mention filtering has been {status}."
            )
        )

    @app_commands.command(
        name="caps",
        description="Enable or disable excessive caps detection"
    )
    @app_commands.describe(
        enabled="Whether excessive caps should be blocked"
    )
    @app_commands.choices(
        enabled=[
            app_commands.Choice(
                name="Enabled",
                value="true"
            ),
            app_commands.Choice(
                name="Disabled",
                value="false"
            )
        ]
    )
    @app_commands.checks.has_permissions(
        manage_guild=True
    )
    async def caps(
        self,
        interaction: discord.Interaction,
        enabled: app_commands.Choice[str]
    ):

        value = enabled.value == "true"

        self.set_rule(
            interaction.guild.id,
            "caps",
            value
        )

        status = (
            "enabled"
            if value
            else "disabled"
        )

        await interaction.response.send_message(
            embed=self.success_embed(
                f"Caps filtering has been {status}."
            )
        )

    @app_commands.command(
        name="whitelist",
        description="Manage automod whitelist"
    )
    @app_commands.describe(
        action="Whether to add or remove a whitelist entry",
        target="The user, role, or channel to whitelist"
    )
    @app_commands.choices(
        action=[
            app_commands.Choice(
                name="Add",
                value="add"
            ),
            app_commands.Choice(
                name="Remove",
                value="remove"
            )
        ]
    )
    @app_commands.checks.has_permissions(
        manage_guild=True
    )
    async def whitelist(
        self,
        interaction: discord.Interaction,
        action: app_commands.Choice[str],
        target: str
    ):
        guild = interaction.guild

        if guild is None:

            await interaction.response.send_message(
                embed=self.error_embed(
                    "This command can only be used in a server."
                ),
                ephemeral=True
            )

            return

        target = target.strip()

        match = re.search(
            r"\d{17,20}",
            target
        )

        if not match:

            await interaction.response.send_message(
                embed=self.error_embed(
                    "Please provide a user, role, or channel mention/ID."
                ),
                ephemeral=True
            )

            return

        target_id = int(match.group())

        member = guild.get_member(target_id)

        if member is not None:

            target_type = "user"
            resolved_target = member

        else:
            role = guild.get_role(target_id)

            if role is not None:

                target_type = "role"
                resolved_target = role

            else:
                channel = guild.get_channel(target_id)

                if channel is not None:

                    target_type = "channel"
                    resolved_target = channel

                else:

                    await interaction.response.send_message(
                        embed=self.error_embed(
                            "I couldn't find that user, role, or channel in this server."
                        ),
                        ephemeral=True
                    )

                    return
                
        if action.value == "add":
            try:

                self.db.execute(
                    """
                    INSERT INTO whitelist (
                        guild_id,
                        target_id,
                        target_type
                    )
                    VALUES (?, ?, ?)
                    """,
                    (
                        guild.id,
                        target_id,
                        target_type
                    )
                )

                self.db.commit()

            except sqlite3.IntegrityError:

                await interaction.response.send_message(
                    embed=self.error_embed(
                        "That target is already whitelisted."
                    ),
                    ephemeral=True
                )

                return

            await interaction.response.send_message(
                embed=self.success_embed(
                    f"{resolved_target.mention} has been added to the automod whitelist."
                )
            )

        else:

            cursor = self.db.execute(
                """
                DELETE FROM whitelist
                WHERE guild_id = ?
                AND target_id = ?
                AND target_type = ?
                """,
                (
                    guild.id,
                    target_id,
                    target_type
                )
            )

            self.db.commit()

            if cursor.rowcount == 0:

                await interaction.response.send_message(
                    embed=self.error_embed(
                        "That target isn't whitelisted."
                    ),
                    ephemeral=True
                )

                return

            await interaction.response.send_message(
                embed=self.success_embed(
                    f"{resolved_target.mention} has been removed from the automod whitelist."
                )
            )

    @app_commands.command(
        name="log",
        description="Set the automod log channel"
    )
    @app_commands.describe(
        channel="The channel where automod actions should be logged"
    )
    @app_commands.checks.has_permissions(
        manage_guild=True
    )
    async def log(
        self,
        interaction: discord.Interaction,
        channel: discord.TextChannel
    ):

        self.get_config(
            interaction.guild.id
        )

        self.db.execute(
            """
            UPDATE automod
            SET log_channel_id = ?
            WHERE guild_id = ?
            """,
            (
                channel.id,
                interaction.guild.id
            )
        )

        self.db.commit()

        await interaction.response.send_message(
            embed=self.success_embed(
                f"Automod logs will now be sent to {channel.mention}."
            )
        )

    def contains_link(self, content):
        return bool(
            re.search(
                r"(https?://|www\.)",
                content,
                re.IGNORECASE
            )
        )

    def contains_invite(self, content):
        return bool(
            re.search(
                r"(discord\.gg/|discord\.com/invite/|discordapp\.com/invite/)",
                content,
                re.IGNORECASE
            )
        )

    def contains_blocked_word(
        self,
        content,
        words
    ):

        content_lower = content.lower()

        for word in words:

            if word.lower() in content_lower:
                return word

        return None

    def excessive_caps(self, content):
        letters = [
            character
            for character in content
            if character.isalpha()
        ]

        if len(letters) < 8:
            return False

        uppercase = sum(
            character.isupper()
            for character in letters
        )

        return (
            uppercase / len(letters)
        ) >= 0.75

    def excessive_mentions(self, message):
        total_mentions = (
            len(message.mentions)
            + len(message.role_mentions)
            + message.content.count("@everyone")
            + message.content.count("@here")
        )

        return total_mentions >= 5

    def is_spam(self, message):
        key = (
            message.guild.id,
            message.author.id
        )

        history = self.message_history[key]

        now = time.monotonic()

        history.append(
            (
                now,
                message.content
            )
        )

        recent = [
            item
            for item in history
            if now - item[0] <= 5
        ]

        if len(recent) >= 5:
            return True

        if len(recent) >= 3:

            contents = [
                item[1]
                for item in recent
            ]

            if len(set(contents)) == 1:
                return True

        return False

    async def automod_warn(
        self,
        member,
        reason
    ):
        moderation_db = None

        try:

            moderation_db = sqlite3.connect(
                "db/moderation.db"
            )

            moderation_db.row_factory = sqlite3.Row

            moderation_db.execute("""
                CREATE TABLE IF NOT EXISTS warning_counters (
                    guild_id INTEGER PRIMARY KEY,
                    next_id INTEGER NOT NULL DEFAULT 1
                )
            """)

            moderation_db.execute("""
                CREATE TABLE IF NOT EXISTS warnings (
                    id INTEGER NOT NULL,
                    guild_id INTEGER NOT NULL,
                    user_id INTEGER NOT NULL,
                    moderator_id INTEGER NOT NULL,
                    reason TEXT NOT NULL,
                    timestamp TEXT NOT NULL,
                    PRIMARY KEY (guild_id, id)
                )
            """)

            guild_id = member.guild.id

            row = moderation_db.execute(
                """
                SELECT next_id
                FROM warning_counters
                WHERE guild_id = ?
                """,
                (guild_id,)
            ).fetchone()

            if row is None:

                warning_id = 1

                moderation_db.execute(
                    """
                    INSERT INTO warning_counters (
                        guild_id,
                        next_id
                    )
                    VALUES (?, ?)
                    """,
                    (
                        guild_id,
                        2
                    )
                )

            else:
                warning_id = row["next_id"]

                moderation_db.execute(
                    """
                    UPDATE warning_counters
                    SET next_id = ?
                    WHERE guild_id = ?
                    """,
                    (
                        warning_id + 1,
                        guild_id
                    )
                )

            moderation_db.execute(
                """
                INSERT INTO warnings (
                    id,
                    guild_id,
                    user_id,
                    moderator_id,
                    reason,
                    timestamp
                )
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    warning_id,
                    guild_id,
                    member.id,
                    self.bot.user.id,
                    f"Automod: {reason}",
                    discord.utils.utcnow().isoformat()
                )
            )

            moderation_db.commit()

            return warning_id

        except (
            sqlite3.Error,
            AttributeError
        ):

            return None

        finally:

            if moderation_db is not None:
                moderation_db.close()

    async def send_automod_log(
        self,
        guild,
        member,
        reason,
        message
    ):

        config = self.get_config(
            guild.id
        )

        if not config["log_channel_id"]:
            return

        channel = guild.get_channel(
            config["log_channel_id"]
        )

        if channel is None:
            return

        embed = discord.Embed(
            title="Automod action",
            color=discord.Color.orange()
        )

        embed.add_field(
            name="User",
            value=f"{member.mention} (`{member.id}`)",
            inline=False
        )

        embed.add_field(
            name="Reason",
            value=reason,
            inline=True
        )

        content = message.content or "*No content*"

        if len(content) > 1000:
            content = content[:997] + "..."

        embed.add_field(
            name="Message",
            value=content,
            inline=False
        )

        embed.add_field(
            name="Channel",
            value=message.channel.mention,
            inline=True
        )

        try:

            await channel.send(
                embed=embed
            )

        except (
            discord.Forbidden,
            discord.HTTPException
        ):

            pass

    @commands.Cog.listener()
    async def on_message(
        self,
        message: discord.Message
    ):
        if message.guild is None:
            return
        
        if message.author.bot:
            return

        if not isinstance(
            message.author,
            discord.Member
        ):
            return

        config = self.get_config(
            message.guild.id
        )

        if not config["enabled"]:
            return

        if self.is_whitelisted(
            message.guild.id,
            message.author,
            message.channel
        ):
            return

        rules = self.get_rules(
            message.guild.id
        )

        blocked_reason = None

        if rules["invites"]:

            if self.contains_invite(
                message.content
            ):

                blocked_reason = "Discord invite"

        if (
            blocked_reason is None
            and rules["links"]
        ):

            if self.contains_link(
                message.content
            ):

                blocked_reason = "Link"

        if blocked_reason is None:

            blocked_word = self.contains_blocked_word(
                message.content,
                self.get_blocked_words(
                    message.guild.id
                )
            )

            if blocked_word:

                blocked_reason = (
                    f"Blocked word: `{blocked_word}`"
                )

        if (
            blocked_reason is None
            and rules["mentions"]
        ):

            if self.excessive_mentions(
                message
            ):

                blocked_reason = "Excessive mentions"

        if (
            blocked_reason is None
            and rules["caps"]
        ):

            if self.excessive_caps(
                message.content
            ):

                blocked_reason = "Excessive caps"

        if (
            blocked_reason is None
            and rules["spam"]
        ):

            if self.is_spam(
                message
            ):

                blocked_reason = "Spam"

        if blocked_reason is None:
            return

        deleted = False

        try:

            await message.delete()

            deleted = True

        except (
            discord.NotFound,
            discord.Forbidden,
            discord.HTTPException
        ):

            pass

        warning_id = await self.automod_warn(
            message.author,
            blocked_reason
        )

        blocked_type = {
            "Link": "link",
            "Discord invite": "Discord invite",
            "Excessive mentions": "excessive mentions",
            "Excessive caps": "excessive caps",
            "Spam": "spam"
        }.get(blocked_reason)

        if (
            blocked_type is None
            and blocked_reason.startswith("Blocked word:")
        ):

            blocked_type = "blocked word"

        elif blocked_type is None:

            blocked_type = "blocked content"

        try:

            action_message = await message.channel.send(
                f"{message.author.mention} sent a **{blocked_type}**, "
                f"their message has been deleted and they have been warned."
            )

            await action_message.delete(
                delay=5
            )

        except (
            discord.Forbidden,
            discord.HTTPException
        ):

            pass

        await self.send_automod_log(
            message.guild,
            message.author,
            blocked_reason,
            message
        )

    async def cog_app_command_error(
        self,
        interaction: discord.Interaction,
        error: app_commands.AppCommandError
    ):

        if isinstance(
            error,
            app_commands.MissingPermissions
        ):

            await interaction.response.send_message(
                embed=self.error_embed(
                    "You need the `Manage Server` permission "
                    "to use this command."
                ),
                ephemeral=True
            )

            return

        await interaction.response.send_message(
            embed=self.error_embed(
                "Something went wrong while running this command."
            ),
            ephemeral=True
        )

    def cog_unload(self):
        self.db.close()

async def setup(bot):
    await bot.add_cog(
        Automod(bot)
    )