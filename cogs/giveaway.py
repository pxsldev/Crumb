import random
import sqlite3

from datetime import datetime, timezone, timedelta

import discord
from discord import app_commands
from discord.ext import commands, tasks


class GiveawayView(discord.ui.View):

    def __init__(self, cog, giveaway_id):
        super().__init__(timeout=None)

        self.cog = cog
        self.giveaway_id = giveaway_id

        button = discord.ui.Button(
            label="Enter Giveaway",
            emoji="🎉",
            style=discord.ButtonStyle.primary,
            custom_id=f"giveaway:enter:{giveaway_id}"
        )

        button.callback = self.enter
        self.add_item(button)

    async def enter(
        self,
        interaction: discord.Interaction
    ):

        giveaway = self.cog.get_giveaway(
            self.giveaway_id
        )

        if giveaway is None:
            await interaction.response.send_message(
                embed=self.cog.error_embed(
                    "That giveaway no longer exists."
                ),
                ephemeral=True
            )
            return

        if giveaway["ended"]:
            await interaction.response.send_message(
                embed=self.cog.error_embed(
                    "This giveaway has already ended."
                ),
                ephemeral=True
            )
            return

        if interaction.guild is None:
            await interaction.response.send_message(
                embed=self.cog.error_embed(
                    "Giveaways can only be entered inside a server."
                ),
                ephemeral=True
            )
            return

        if giveaway["guild_id"] != interaction.guild.id:
            await interaction.response.send_message(
                embed=self.cog.error_embed(
                    "That giveaway belongs to another server."
                ),
                ephemeral=True
            )
            return

        existing = self.cog.db.execute(
            """
            SELECT 1
            FROM giveaway_entries
            WHERE giveaway_id = ?
            AND user_id = ?
            """,
            (
                self.giveaway_id,
                interaction.user.id
            )
        ).fetchone()

        if existing:
            await interaction.response.send_message(
                embed=self.cog.error_embed(
                    "You're already entered in this giveaway."
                ),
                ephemeral=True
            )
            return

        self.cog.db.execute(
            """
            INSERT INTO giveaway_entries (
                giveaway_id,
                user_id
            )
            VALUES (?, ?)
            """,
            (
                self.giveaway_id,
                interaction.user.id
            )
        )

        self.cog.db.commit()

        await interaction.response.send_message(
            embed=self.cog.success_embed(
                "You're now entered in the giveaway! 🎉"
            ),
            ephemeral=True
        )

        await self.cog.update_giveaway_message(
            giveaway
        )


class Giveaway(commands.GroupCog, group_name="giveaway"):

    def __init__(self, bot):

        self.bot = bot

        self.db = sqlite3.connect("db/giveaway.db")
        self.db.row_factory = sqlite3.Row

        self.db.execute("""
            CREATE TABLE IF NOT EXISTS giveaways (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id INTEGER NOT NULL,
                channel_id INTEGER NOT NULL,
                message_id INTEGER NOT NULL,
                prize TEXT NOT NULL,
                winners INTEGER NOT NULL,
                ends_at TEXT NOT NULL,
                ended INTEGER NOT NULL DEFAULT 0,
                cancelled INTEGER NOT NULL DEFAULT 0
            )
        """)

        self.db.execute("""
            CREATE TABLE IF NOT EXISTS giveaway_entries (
                giveaway_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                PRIMARY KEY (giveaway_id, user_id)
            )
        """)

        self.db.commit()

        self.giveaway_loop.start()

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

    def parse_duration(self, duration):

        duration = duration.lower().strip()

        units = {
            "s": 1,
            "m": 60,
            "h": 3600,
            "d": 86400
        }

        if len(duration) < 2:
            return None

        unit = duration[-1]

        if unit not in units:
            return None

        try:
            amount = int(duration[:-1])
        except ValueError:
            return None

        if amount <= 0:
            return None

        return amount * units[unit]

    def get_giveaway(self, giveaway_id):

        return self.db.execute(
            """
            SELECT *
            FROM giveaways
            WHERE id = ?
            """,
            (giveaway_id,)
        ).fetchone()

    def get_entries(self, giveaway_id):

        return self.db.execute(
            """
            SELECT user_id
            FROM giveaway_entries
            WHERE giveaway_id = ?
            """,
            (giveaway_id,)
        ).fetchall()

    async def update_giveaway_message(
        self,
        giveaway,
        ended=False,
        cancelled=False
    ):

        channel = self.bot.get_channel(
            giveaway["channel_id"]
        )

        if channel is None:
            return

        try:

            message = await channel.fetch_message(
                giveaway["message_id"]
            )

        except (
            discord.NotFound,
            discord.Forbidden,
            discord.HTTPException
        ):
            return

        entries = self.get_entries(
            giveaway["id"]
        )

        if cancelled:

            embed = discord.Embed(
                title="🎉 Giveaway Cancelled",
                description=(
                    f"**Prize:** {giveaway['prize']}\n\n"
                    "This giveaway has been cancelled."
                ),
                color=discord.Color.orange()
            )

            embed.set_footer(
                text=f"Giveaway ID: #{giveaway['id']}"
            )

            await message.edit(
                embed=embed,
                view=None
            )

            return

        if ended:

            embed = discord.Embed(
                title="🎉 Giveaway Ended",
                description=(
                    f"**Prize:** {giveaway['prize']}\n\n"
                    f"**Entries:** {len(entries)}"
                ),
                color=discord.Color.orange()
            )

            embed.set_footer(
                text=f"Giveaway ID: #{giveaway['id']}"
            )

            await message.edit(
                embed=embed,
                view=None
            )

            return

        ends_at = int(
            datetime.fromisoformat(
                giveaway["ends_at"]
            ).timestamp()
        )

        embed = discord.Embed(
            title="🎉 Giveaway",
            description=(
                f"**Prize:** {giveaway['prize']}\n\n"
                "Click the button below to enter!\n\n"
                f"🏆 **Winners:** {giveaway['winners']}\n"
                f"⏰ **Ends:** <t:{ends_at}:R>\n"
                f"👥 **Entries:** {len(entries)}"
            ),
            color=discord.Color.orange()
        )

        embed.set_footer(
            text=f"Giveaway ID: #{giveaway['id']}"
        )

        await message.edit(
            embed=embed,
            view=GiveawayView(
                self,
                giveaway["id"]
            )
        )

    @app_commands.command(
        name="start",
        description="Start a giveaway"
    )
    @app_commands.describe(
        channel="The channel for the giveaway",
        duration="How long it should last (e.g. 30m, 2h, 1d)",
        prize="The giveaway prize",
        winners="Number of winners"
    )
    @app_commands.checks.has_permissions(
        manage_guild=True
    )
    async def start(
        self,
        interaction: discord.Interaction,
        channel: discord.TextChannel,
        duration: str,
        prize: str,
        winners: int = 1
    ):

        if interaction.guild is None:
            await interaction.response.send_message(
                embed=self.error_embed(
                    "This command can only be used in a server."
                ),
                ephemeral=True
            )
            return

        seconds = self.parse_duration(duration)

        if seconds is None:
            await interaction.response.send_message(
                embed=self.error_embed(
                    "Invalid duration. Use formats like `30m`, `2h`, or `1d`."
                ),
                ephemeral=True
            )
            return

        if seconds > 30 * 86400:
            await interaction.response.send_message(
                embed=self.error_embed(
                    "Giveaway cannot last longer than 30 days."
                ),
                ephemeral=True
            )
            return

        if winners < 1 or winners > 20:
            await interaction.response.send_message(
                embed=self.error_embed(
                    "You can have between 1 and 20 winners."
                ),
                ephemeral=True
            )
            return

        if len(prize) > 256:
            await interaction.response.send_message(
                embed=self.error_embed(
                    "The prize must be 256 characters or fewer."
                ),
                ephemeral=True
            )
            return

        if not prize.strip():
            await interaction.response.send_message(
                embed=self.error_embed(
                    "You need to provide a prize."
                ),
                ephemeral=True
            )
            return

        me = interaction.guild.me

        if me is None:
            await interaction.response.send_message(
                embed=self.error_embed(
                    "I couldn't verify my permissions in this server."
                ),
                ephemeral=True
            )
            return

        permissions = channel.permissions_for(me)

        if not permissions.send_messages:
            await interaction.response.send_message(
                embed=self.error_embed(
                    f"I don't have permission to send messages in {channel.mention}."
                ),
                ephemeral=True
            )
            return

        if not permissions.embed_links:
            await interaction.response.send_message(
                embed=self.error_embed(
                    f"I don't have permission to embed links in {channel.mention}."
                ),
                ephemeral=True
            )
            return

        ends_at = datetime.now(
            timezone.utc
        ) + timedelta(
            seconds=seconds
        )

        cursor = self.db.execute(
            """
            INSERT INTO giveaways (
                guild_id,
                channel_id,
                message_id,
                prize,
                winners,
                ends_at,
                ended,
                cancelled
            )
            VALUES (?, ?, ?, ?, ?, ?, 0, 0)
            """,
            (
                interaction.guild.id,
                channel.id,
                0,
                prize,
                winners,
                ends_at.isoformat()
            )
        )

        self.db.commit()

        giveaway_id = cursor.lastrowid

        embed = discord.Embed(
            title="🎉 Giveaway",
            description=(
                f"**Prize:** {prize}\n\n"
                "Click the button below to enter!\n\n"
                f"🏆 **Winners:** {winners}\n"
                f"⏰ **Ends:** <t:{int(ends_at.timestamp())}:R>\n"
                f"👥 **Entries:** 0"
            ),
            color=discord.Color.orange()
        )

        embed.set_footer(
            text=f"Giveaway ID: #{giveaway_id}"
        )

        try:

            message = await channel.send(
                embed=embed,
                view=GiveawayView(
                    self,
                    giveaway_id
                )
            )

        except (
            discord.Forbidden,
            discord.HTTPException
        ):

            self.db.execute(
                """
                DELETE FROM giveaways
                WHERE id = ?
                """,
                (giveaway_id,)
            )

            self.db.commit()

            await interaction.response.send_message(
                embed=self.error_embed(
                    "I couldn't create the giveaway in that channel."
                ),
                ephemeral=True
            )

            return

        self.db.execute(
            """
            UPDATE giveaways
            SET message_id = ?
            WHERE id = ?
            """,
            (
                message.id,
                giveaway_id
            )
        )

        self.db.commit()

        await interaction.response.send_message(
            embed=self.success_embed(
                f"Giveaway `#{giveaway_id}` started in {channel.mention}."
            ),
            ephemeral=True
        )

    @app_commands.command(
        name="end",
        description="End a giveaway and pick winners"
    )
    @app_commands.describe(
        giveaway_id="The giveaway ID"
    )
    @app_commands.checks.has_permissions(
        manage_guild=True
    )
    async def end(
        self,
        interaction: discord.Interaction,
        giveaway_id: int
    ):

        giveaway = self.get_giveaway(
            giveaway_id
        )

        if giveaway is None:
            await interaction.response.send_message(
                embed=self.error_embed(
                    "That giveaway doesn't exist."
                ),
                ephemeral=True
            )
            return

        if interaction.guild is None or giveaway["guild_id"] != interaction.guild.id:
            await interaction.response.send_message(
                embed=self.error_embed(
                    "That giveaway doesn't belong to this server."
                ),
                ephemeral=True
            )
            return

        if giveaway["ended"]:
            await interaction.response.send_message(
                embed=self.error_embed(
                    "That giveaway has already ended."
                ),
                ephemeral=True
            )
            return

        await self.finish_giveaway(
            giveaway
        )

        await interaction.response.send_message(
            embed=self.success_embed(
                f"Giveaway `#{giveaway_id}` has ended."
            ),
            ephemeral=True
        )

    @app_commands.command(
        name="reroll",
        description="Reroll a giveaway winner"
    )
    @app_commands.describe(
        giveaway_id="The giveaway ID"
    )
    @app_commands.checks.has_permissions(
        manage_guild=True
    )
    async def reroll(
        self,
        interaction: discord.Interaction,
        giveaway_id: int
    ):

        giveaway = self.get_giveaway(
            giveaway_id
        )

        if giveaway is None:
            await interaction.response.send_message(
                embed=self.error_embed(
                    "That giveaway doesn't exist."
                ),
                ephemeral=True
            )
            return

        if interaction.guild is None or giveaway["guild_id"] != interaction.guild.id:
            await interaction.response.send_message(
                embed=self.error_embed(
                    "That giveaway doesn't belong to this server."
                ),
                ephemeral=True
            )
            return

        if not giveaway["ended"]:
            await interaction.response.send_message(
                embed=self.error_embed(
                    "That giveaway hasn't ended yet."
                ),
                ephemeral=True
            )
            return

        if giveaway["cancelled"]:
            await interaction.response.send_message(
                embed=self.error_embed(
                    "You can't reroll a cancelled giveaway."
                ),
                ephemeral=True
            )
            return

        entries = self.get_entries(
            giveaway_id
        )

        if not entries:
            await interaction.response.send_message(
                embed=self.error_embed(
                    "That giveaway had no entries."
                ),
                ephemeral=True
            )
            return

        winner = random.choice(entries)

        await interaction.response.send_message(
            embed=self.success_embed(
                f"🎉 New winner: <@{winner['user_id']}>"
            )
        )

    @app_commands.command(
        name="cancel",
        description="Cancel a giveaway"
    )
    @app_commands.describe(
        giveaway_id="The giveaway ID"
    )
    @app_commands.checks.has_permissions(
        manage_guild=True
    )
    async def cancel(
        self,
        interaction: discord.Interaction,
        giveaway_id: int
    ):

        giveaway = self.get_giveaway(
            giveaway_id
        )

        if giveaway is None:
            await interaction.response.send_message(
                embed=self.error_embed(
                    "That giveaway doesn't exist."
                ),
                ephemeral=True
            )
            return

        if interaction.guild is None or giveaway["guild_id"] != interaction.guild.id:
            await interaction.response.send_message(
                embed=self.error_embed(
                    "That giveaway doesn't belong to this server."
                ),
                ephemeral=True
            )
            return

        if giveaway["ended"]:
            await interaction.response.send_message(
                embed=self.error_embed(
                    "That giveaway has already ended."
                ),
                ephemeral=True
            )
            return

        self.db.execute(
            """
            UPDATE giveaways
            SET ended = 1,
                cancelled = 1
            WHERE id = ?
            """,
            (giveaway_id,)
        )

        self.db.commit()

        await self.update_giveaway_message(
            giveaway,
            cancelled=True
        )

        await interaction.response.send_message(
            embed=self.success_embed(
                f"Giveaway `#{giveaway_id}` has been cancelled."
            ),
            ephemeral=True
        )

    @app_commands.command(
        name="list",
        description="View active giveaways"
    )
    @app_commands.checks.has_permissions(
        manage_guild=True
    )
    async def list_giveaways(
        self,
        interaction: discord.Interaction
    ):

        rows = self.db.execute(
            """
            SELECT *
            FROM giveaways
            WHERE guild_id = ?
            AND ended = 0
            ORDER BY ends_at ASC
            """,
            (interaction.guild.id,)
        ).fetchall()

        if not rows:
            await interaction.response.send_message(
                embed=self.success_embed(
                    "There are no active giveaways."
                ),
                ephemeral=True
            )
            return

        lines = []

        for row in rows[:20]:

            timestamp = int(
                datetime.fromisoformat(
                    row["ends_at"]
                ).timestamp()
            )

            lines.append(
                f"**#{row['id']}** — {row['prize']}\n"
                f"Ends <t:{timestamp}:R> in <#{row['channel_id']}>"
            )

        embed = discord.Embed(
            title="Active giveaways",
            description="\n\n".join(lines),
            color=discord.Color.orange()
        )

        if len(rows) > 20:
            embed.set_footer(
                text=f"Showing 20 of {len(rows)} giveaways."
            )

        await interaction.response.send_message(
            embed=embed,
            ephemeral=True
        )

    @app_commands.command(
        name="help",
        description="View giveaway commands"
    )
    async def help_command(
        self,
        interaction: discord.Interaction
    ):

        embed = discord.Embed(
            title="giveaway",
            description="Create and manage server giveaways.",
            color=discord.Color.orange()
        )

        embed.add_field(
            name="🎉 Management",
            value=(
                "`/giveaway 1 start` — start a giveaway\n"
                "`/giveaway 1 end` — end a giveaway\n"
                "`/giveaway 1 reroll` — reroll a winner\n"
                "`/giveaway 1 cancel` — cancel a giveaway\n"
                "`/giveaway 1 list` — view active giveaways"
            ),
            inline=False
        )

        embed.add_field(
            name="🕐 Duration",
            value=(
                "Use `s`, `m`, `h`, or `d`.\n"
                "Examples: `30m`, `2h`, `7d`"
            ),
            inline=False
        )

        embed.set_footer(
            text="You need the Manage Server permission to manage giveaways."
        )

        await interaction.response.send_message(
            embed=embed
        )

    async def finish_giveaway(
        self,
        giveaway
    ):

        current = self.get_giveaway(
            giveaway["id"]
        )

        if current is None or current["ended"]:
            return

        entries = self.get_entries(
            giveaway["id"]
        )

        winners_count = min(
            giveaway["winners"],
            len(entries)
        )

        winners = (
            random.sample(
                entries,
                winners_count
            )
            if winners_count
            else []
        )

        cursor = self.db.execute(
            """
            UPDATE giveaways
            SET ended = 1
            WHERE id = ?
            AND ended = 0
            """,
            (giveaway["id"],)
        )

        self.db.commit()

        if cursor.rowcount == 0:
            return

        channel = self.bot.get_channel(
            giveaway["channel_id"]
        )

        if channel is None:
            return

        try:

            message = await channel.fetch_message(
                giveaway["message_id"]
            )

            embed = discord.Embed(
                title="🎉 Giveaway Ended",
                description=(
                    f"**Prize:** {giveaway['prize']}\n\n"
                    f"**Entries:** {len(entries)}"
                ),
                color=discord.Color.orange()
            )

            if winners:

                winner_text = "\n".join(
                    f"🏆 <@{winner['user_id']}>"
                    for winner in winners
                )

                embed.add_field(
                    name="Winner(s)",
                    value=winner_text,
                    inline=False
                )

            else:

                embed.add_field(
                    name="Winner(s)",
                    value="No valid entries.",
                    inline=False
                )

            embed.set_footer(
                text=f"Giveaway ID: #{giveaway['id']}"
            )

            await message.edit(
                embed=embed,
                view=None
            )

            if winners:

                mentions = " ".join(
                    f"<@{winner['user_id']}>"
                    for winner in winners
                )

                await channel.send(
                    f"🎉 Congratulations {mentions}! "
                    f"You won **{giveaway['prize']}**!"
                )

        except (
            discord.NotFound,
            discord.Forbidden,
            discord.HTTPException
        ):
            pass

    @tasks.loop(seconds=5)
    async def giveaway_loop(self):

        now = datetime.now(
            timezone.utc
        ).isoformat()

        rows = self.db.execute(
            """
            SELECT *
            FROM giveaways
            WHERE ended = 0
            AND ends_at <= ?
            ORDER BY ends_at ASC
            """,
            (now,)
        ).fetchall()

        for giveaway in rows:

            await self.finish_giveaway(
                giveaway
            )

    @giveaway_loop.before_loop
    async def before_giveaway_loop(self):

        await self.bot.wait_until_ready()

    async def restore_giveaway_views(self):

        rows = self.db.execute(
            """
            SELECT id
            FROM giveaways
            WHERE ended = 0
            """
        ).fetchall()

        for row in rows:

            self.bot.add_view(
                GiveawayView(
                    self,
                    row["id"]
                )
            )

    def cog_unload(self):

        self.giveaway_loop.cancel()
        self.db.close()


async def setup(bot):

    cog = Giveaway(bot)

    await bot.add_cog(cog)

    await cog.restore_giveaway_views()