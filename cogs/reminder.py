import sqlite3

from datetime import datetime, timezone, timedelta

import discord
from discord import app_commands
from discord.ext import commands, tasks


class Reminder(commands.GroupCog, group_name="reminder"):

    def __init__(self, bot):
        self.bot = bot

        self.db = sqlite3.connect("db/reminder.db")
        self.db.row_factory = sqlite3.Row

        self.db.execute("""
            CREATE TABLE IF NOT EXISTS reminders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                guild_id INTEGER,
                channel_id INTEGER,
                message TEXT NOT NULL,
                remind_at TEXT NOT NULL
            )
        """)

        self.db.commit()

        self.reminder_loop.start()

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

    @app_commands.command(
        name="remindme",
        description="Set a reminder"
    )
    @app_commands.describe(
        duration="How long until the reminder (e.g. 30m, 2h, 1d)",
        message="What you want to be reminded about"
    )
    async def remindme(
        self,
        interaction: discord.Interaction,
        duration: str,
        message: str
    ):

        seconds = self.parse_duration(duration)

        if seconds is None:
            await interaction.response.send_message(
                embed=self.error_embed(
                    "Invalid duration. Use formats like `30s`, `10m`, `2h`, or `1d`."
                ),
                ephemeral=True
            )
            return

        if seconds > 365 * 86400:
            await interaction.response.send_message(
                embed=self.error_embed(
                    "Reminder cannot be set more than 365 days in advance."
                ),
                ephemeral=True
            )
            return

        if not message.strip():
            await interaction.response.send_message(
                embed=self.error_embed(
                    "You need to provide something to be reminded about."
                ),
                ephemeral=True
            )
            return

        if len(message) > 2000:
            await interaction.response.send_message(
                embed=self.error_embed(
                    "The reminder message must be 2000 characters or fewer."
                ),
                ephemeral=True
            )
            return

        remind_at = datetime.now(timezone.utc) + timedelta(
            seconds=seconds
        )

        cursor = self.db.execute(
            """
            INSERT INTO reminders (
                user_id,
                guild_id,
                channel_id,
                message,
                remind_at
            )
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                interaction.user.id,
                interaction.guild.id if interaction.guild else None,
                interaction.channel.id if interaction.channel else None,
                message,
                remind_at.isoformat()
            )
        )

        self.db.commit()

        reminder_id = cursor.lastrowid

        embed = self.success_embed(
            f"I'll remind you <t:{int(remind_at.timestamp())}:R>."
        )

        embed.add_field(
            name="Reminder",
            value=message[:1024],
            inline=False
        )

        embed.add_field(
            name="Reminder ID",
            value=f"`#{reminder_id}`",
            inline=True
        )

        await interaction.response.send_message(
            embed=embed
        )

    @app_commands.command(
        name="list",
        description="View your reminders"
    )
    async def list_reminders(
        self,
        interaction: discord.Interaction
    ):

        rows = self.db.execute(
            """
            SELECT *
            FROM reminders
            WHERE user_id = ?
            ORDER BY remind_at ASC
            """,
            (interaction.user.id,)
        ).fetchall()

        if not rows:
            await interaction.response.send_message(
                embed=self.success_embed(
                    "You don't have any active reminders."
                ),
                ephemeral=True
            )
            return

        lines = []

        for row in rows[:20]:

            try:
                timestamp = int(
                    datetime.fromisoformat(
                        row["remind_at"]
                    ).timestamp()
                )
            except ValueError:
                continue

            message = row["message"]

            if len(message) > 70:
                message = message[:67] + "..."

            lines.append(
                f"**#{row['id']}** — {message}\n"
                f"<t:{timestamp}:R>"
            )

        embed = discord.Embed(
            title="Your reminders",
            description="\n\n".join(lines),
            color=discord.Color.orange()
        )

        if len(rows) > 20:
            embed.set_footer(
                text=f"Showing 20 of {len(rows)} reminders."
            )

        await interaction.response.send_message(
            embed=embed,
            ephemeral=True
        )

    @app_commands.command(
        name="cancel",
        description="Cancel one of your reminders"
    )
    @app_commands.describe(
        reminder_id="The reminder ID to cancel"
    )
    async def cancel(
        self,
        interaction: discord.Interaction,
        reminder_id: int
    ):

        cursor = self.db.execute(
            """
            DELETE FROM reminders
            WHERE id = ?
            AND user_id = ?
            """,
            (
                reminder_id,
                interaction.user.id
            )
        )

        self.db.commit()

        if cursor.rowcount == 0:
            await interaction.response.send_message(
                embed=self.error_embed(
                    "That reminder doesn't exist or doesn't belong to you."
                ),
                ephemeral=True
            )
            return

        await interaction.response.send_message(
            embed=self.success_embed(
                f"Reminder `#{reminder_id}` has been cancelled."
            ),
            ephemeral=True
        )

    @app_commands.command(
        name="clear",
        description="Cancel all of your reminders"
    )
    async def clear(
        self,
        interaction: discord.Interaction
    ):

        cursor = self.db.execute(
            """
            DELETE FROM reminders
            WHERE user_id = ?
            """,
            (interaction.user.id,)
        )

        self.db.commit()

        if cursor.rowcount == 0:
            await interaction.response.send_message(
                embed=self.success_embed(
                    "You don't have any active reminders."
                ),
                ephemeral=True
            )
            return

        await interaction.response.send_message(
            embed=self.success_embed(
                f"Cancelled {cursor.rowcount} reminder(s)."
            ),
            ephemeral=True
        )

    @app_commands.command(
        name="help",
        description="View reminder commands"
    )
    async def help_command(
        self,
        interaction: discord.Interaction
    ):

        embed = discord.Embed(
            title="reminder",
            description="Set reminders that Crumb will deliver for you.",
            color=discord.Color.orange()
        )

        embed.add_field(
            name="⏰ Reminders",
            value=(
                "`/reminder 1 remindme` — set a reminder\n"
                "`/reminder 1 list` — view your reminders\n"
                "`/reminder 1 cancel` — cancel a reminder\n"
                "`/reminder 1 clear` — cancel all reminders"
            ),
            inline=False
        )

        embed.add_field(
            name="🕐 Duration",
            value=(
                "Use `s` for seconds, `m` for minutes, "
                "`h` for hours, or `d` for days.\n\n"
                "Examples: `30s`, `10m`, `2h`, `3d`"
            ),
            inline=False
        )

        await interaction.response.send_message(
            embed=embed
        )

    @tasks.loop(seconds=5)
    async def reminder_loop(self):

        now = datetime.now(timezone.utc)

        rows = self.db.execute(
            """
            SELECT *
            FROM reminders
            WHERE remind_at <= ?
            ORDER BY remind_at ASC
            """,
            (now.isoformat(),)
        ).fetchall()

        for row in rows:

            self.db.execute(
                """
                DELETE FROM reminders
                WHERE id = ?
                """,
                (row["id"],)
            )

            self.db.commit()

            channel = None

            if row["channel_id"]:
                channel = self.bot.get_channel(
                    row["channel_id"]
                )

            if channel is not None:

                try:
                    await channel.send(
                        f"⏰ <@{row['user_id']}> — reminder:\n"
                        f"> {row['message']}"
                    )

                    continue

                except (
                    discord.Forbidden,
                    discord.HTTPException
                ):
                    pass

            try:

                user = self.bot.get_user(
                    row["user_id"]
                )

                if user is None:
                    user = await self.bot.fetch_user(
                        row["user_id"]
                    )

                await user.send(
                    "⏰ **Reminder**\n"
                    f"> {row['message']}"
                )

            except (
                discord.Forbidden,
                discord.HTTPException
            ):
                pass

    @reminder_loop.before_loop
    async def before_reminder_loop(self):

        await self.bot.wait_until_ready()

    def cog_unload(self):

        self.reminder_loop.cancel()
        self.db.close()


async def setup(bot):

    await bot.add_cog(Reminder(bot))