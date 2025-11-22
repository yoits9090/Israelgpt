import os
import sqlite3
from datetime import datetime

import discord
from discord.ext import commands


MARKETPLACE_CHANNEL_ID = 1441901428800229376
MARKETPLACE_STAFF_ROLE_IDS = [1441882323938316379, 1441878991370850335]


BASE_DIR = os.path.dirname(os.path.dirname(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
os.makedirs(DATA_DIR, exist_ok=True)

DB_PATH = os.path.join(DATA_DIR, "tickets.db")

_conn = sqlite3.connect(DB_PATH, check_same_thread=False)
_conn.row_factory = sqlite3.Row

_conn.execute(
    """
    CREATE TABLE IF NOT EXISTS ticket_panels (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        guild_id INTEGER NOT NULL,
        channel_id INTEGER NOT NULL,
        message_id INTEGER NOT NULL UNIQUE,
        panel_type TEXT NOT NULL,
        handler_user_id INTEGER,
        created_by_user_id INTEGER NOT NULL,
        created_at TEXT NOT NULL
    )
    """
)
_conn.commit()


def _create_panel(
    guild_id: int,
    channel_id: int,
    message_id: int,
    panel_type: str,
    handler_user_id: int | None,
    created_by_user_id: int,
) -> None:
    _conn.execute(
        """
        INSERT INTO ticket_panels (
            guild_id, channel_id, message_id, panel_type, handler_user_id, created_by_user_id, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            guild_id,
            channel_id,
            message_id,
            panel_type,
            handler_user_id,
            created_by_user_id,
            datetime.utcnow().isoformat(),
        ),
    )
    _conn.commit()


def _get_panel(guild_id: int, message_id: int) -> sqlite3.Row | None:
    cur = _conn.execute(
        "SELECT * FROM ticket_panels WHERE guild_id=? AND message_id=?",
        (guild_id, message_id),
    )
    return cur.fetchone()


def _marketplace_panel_exists(guild_id: int) -> bool:
    cur = _conn.execute(
        "SELECT 1 FROM ticket_panels WHERE guild_id=? AND panel_type='marketplace' LIMIT 1",
        (guild_id,),
    )
    return cur.fetchone() is not None


class TicketView(discord.ui.View):
    """Generic ticket view used for all panels."""

    def __init__(self) -> None:
        super().__init__(timeout=None)  # persistent view

    @discord.ui.button(
        label="Open Ticket",
        style=discord.ButtonStyle.primary,
        custom_id="gems:ticket_panel_button",
    )
    async def open_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.guild is None or interaction.channel is None:
            await interaction.response.send_message(
                "Nu, this only works in a server channel.",
                ephemeral=True,
            )
            return

        panel = _get_panel(interaction.guild.id, interaction.message.id)
        if panel is None:
            await interaction.response.send_message(
                "Oy, I don't recognize this ticket panel anymore.",
                ephemeral=True,
            )
            return

        guild = interaction.guild
        base_name = "ticket"
        if panel["panel_type"] == "marketplace":
            base_name = "listing"

        thread_name = f"{base_name}-{interaction.user.name}".replace(" ", "-")[:90]

        thread = await interaction.channel.create_thread(
            name=thread_name,
            type=discord.ChannelType.private_thread,
        )

        # Add requesting user
        await thread.add_user(interaction.user)

        if panel["panel_type"] == "marketplace":
            staff_members: set[discord.Member] = set()
            for role_id in MARKETPLACE_STAFF_ROLE_IDS:
                role = guild.get_role(role_id)
                if role:
                    for member in role.members:
                        staff_members.add(member)

            # Add staff members with the given roles
            for member in staff_members:
                try:
                    await thread.add_user(member)
                except Exception:
                    pass

            role_mentions: list[str] = []
            for role_id in MARKETPLACE_STAFF_ROLE_IDS:
                role = guild.get_role(role_id)
                if role:
                    role_mentions.append(role.mention)

            mentions = " ".join(role_mentions)

            await thread.send(
                f"Shalom {interaction.user.mention}! This is your marketplace listing ticket.\n"
                f"{mentions} please take a look when you're free."
            )
        else:
            handler_id = panel["handler_user_id"]
            handler = guild.get_member(handler_id) if handler_id is not None else None
            if handler is not None:
                try:
                    await thread.add_user(handler)
                except Exception:
                    pass

            await thread.send(
                f"Shalom {interaction.user.mention}! This is your ticket."
                + (f" {handler.mention} will help you soon." if handler is not None else "")
            )

        await interaction.response.send_message(
            "Your ticket has been created, check the new thread.",
            ephemeral=True,
        )


_ticket_view: TicketView | None = None
_commands_registered: bool = False


def _get_view() -> TicketView:
    global _ticket_view
    if _ticket_view is None:
        _ticket_view = TicketView()
    return _ticket_view


def register_ticket_view(bot: commands.Bot) -> None:
    """Register the persistent view. Call from on_ready when loop is running."""
    view = _get_view()
    bot.add_view(view)


def setup_ticket_system(bot: commands.Bot) -> None:
    """Register ticket-related commands. Safe to call multiple times."""

    global _commands_registered
    if _commands_registered:
        return
    _commands_registered = True

    @bot.command(name="marketplacesetup")
    @commands.has_permissions(manage_guild=True)
    async def marketplacesetup(ctx: commands.Context):
        """One-time setup for the marketplace listing panel."""

        if _marketplace_panel_exists(ctx.guild.id):
            await ctx.send(
                "Marketplace panel is already configured for this server, chaver.",
                delete_after=10,
            )
            return

        channel = ctx.guild.get_channel(MARKETPLACE_CHANNEL_ID) or ctx.channel

        embed = discord.Embed(
            title="Marketplace Listings",
            description=(
                "Click the button below to open a private ticket to request a marketplace listing.\n"
                "Staff will review your request b'karov (soon)."
            ),
            color=0x00BCD4,
        )

        view = _get_view()
        msg = await channel.send(embed=embed, view=view)

        _create_panel(
            guild_id=ctx.guild.id,
            channel_id=channel.id,
            message_id=msg.id,
            panel_type="marketplace",
            handler_user_id=None,
            created_by_user_id=ctx.author.id,
        )

        if channel.id != ctx.channel.id:
            await ctx.send(
                f"Marketplace panel sent to {channel.mention}", delete_after=5,
            )
        else:
            await ctx.send("Marketplace panel deployed, sababa.", delete_after=5)

    @bot.command(name="ticketsetup")
    @commands.has_permissions(manage_guild=True)
    async def ticketsetup(ctx: commands.Context, handler: discord.Member):
        """Create a generic ticket panel in the current channel for a specific handler user."""

        channel = ctx.channel

        embed = discord.Embed(
            title="Support Tickets",
            description=(
                f"Click the button below to open a private ticket with {handler.mention}.\n"
                "They'll help you out, b'seder?"
            ),
            color=0x4CAF50,
        )

        view = _get_view()
        msg = await channel.send(embed=embed, view=view)

        _create_panel(
            guild_id=ctx.guild.id,
            channel_id=channel.id,
            message_id=msg.id,
            panel_type="generic",
            handler_user_id=handler.id,
            created_by_user_id=ctx.author.id,
        )

        await ctx.send(
            f"Ticket panel created for {handler.mention} in {channel.mention}",
            delete_after=5,
        )
