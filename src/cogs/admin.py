"""Admin and configuration commands cog."""

from __future__ import annotations

import discord
from discord.ext import commands

from config import (
    GuildSettings,
    guild_settings,
    get_guild_settings,
    save_guild_configs,
    get_voice_channel_ids,
    get_private_voice_lobby_id,
    GEM_TRIGGER_PHRASE,
)


class HelpPaginator(discord.ui.View):
    """Paginated help menu."""

    def __init__(self, ctx: commands.Context, pages: list[discord.Embed]):
        super().__init__(timeout=180)
        self.ctx = ctx
        self.pages = pages
        self.current_page = 0

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user != self.ctx.author:
            await interaction.response.send_message(
                "Only the person who requested help can use these buttons.",
                ephemeral=True,
            )
            return False
        return True

    def _update_footer(self) -> discord.Embed:
        embed = self.pages[self.current_page]
        embed.set_footer(
            text=f"Page {self.current_page + 1}/{len(self.pages)} • Use the buttons below to navigate"
        )
        return embed

    async def update_message(self, interaction: discord.Interaction):
        await interaction.response.edit_message(embed=self._update_footer(), view=self)

    @discord.ui.button(label="⏮️ Back", style=discord.ButtonStyle.secondary)
    async def previous_button(self, interaction: discord.Interaction, _: discord.ui.Button):
        self.current_page = (self.current_page - 1) % len(self.pages)
        await self.update_message(interaction)

    @discord.ui.button(label="🏠 Overview", style=discord.ButtonStyle.primary)
    async def home_button(self, interaction: discord.Interaction, _: discord.ui.Button):
        self.current_page = 0
        await self.update_message(interaction)

    @discord.ui.button(label="Next ⏭️", style=discord.ButtonStyle.secondary)
    async def next_button(self, interaction: discord.Interaction, _: discord.ui.Button):
        self.current_page = (self.current_page + 1) % len(self.pages)
        await self.update_message(interaction)


def build_help_pages(prefix: str) -> list[discord.Embed]:
    """Build the help menu embeds."""
    overview = discord.Embed(
        title="Guildest Command Guide",
        description=(
            "Interactive guide for every command. Navigate with the buttons to see detailed "
            "usage, permissions, and examples."
        ),
        color=0x3498DB,
    )
    overview.add_field(
        name="How to use",
        value=(
            f"Use `{prefix}command` with the arguments shown on each page. "
            "Only the user who requested this help can flip through the pages."
        ),
        inline=False,
    )
    overview.add_field(
        name="Need this guide again?",
        value=f"Type `{prefix}help` anytime to reopen the navigator.",
        inline=False,
    )
    overview.add_field(
        name="Navigation tips",
        value="⏮️ Back • 🏠 Overview • Next ⏭️",
        inline=False,
    )

    moderation = discord.Embed(title="Moderation & Safety", color=0xE74C3C)
    moderation.add_field(
        name=f"{prefix}ban <user> [reason]",
        value="Ban a member with an optional reason. Requires Ban Members permission.",
        inline=False,
    )
    moderation.add_field(
        name=f"{prefix}kick <user> [reason]",
        value="Kick a member from the server. Requires Kick Members permission.",
        inline=False,
    )
    moderation.add_field(
        name=f"{prefix}mute <user> <duration>",
        value="Timeout a user for a duration like `10m`, `2h`, or `1d`.",
        inline=False,
    )
    moderation.add_field(
        name=f"{prefix}clear <amount>",
        value="Bulk delete messages in the current channel.",
        inline=False,
    )
    moderation.add_field(
        name=f"{prefix}role <user> <role>",
        value="Toggle a role for a user by name or ID.",
        inline=False,
    )
    moderation.add_field(
        name=f"{prefix}slowmode <seconds>",
        value="Set channel slowmode (use 0 to disable).",
        inline=False,
    )
    moderation.add_field(
        name=f"{prefix}guildconfig",
        value="Show or adjust server-specific settings.",
        inline=False,
    )

    community = discord.Embed(title="Community & Utility", color=0x2ECC71)
    community.add_field(
        name=f"{prefix}leaderboard",
        value="Show the top 10 chatters by messages and level.",
        inline=False,
    )
    community.add_field(
        name=f"{prefix}rank [user]",
        value="See your own or another member's stats.",
        inline=False,
    )
    community.add_field(
        name=f"{prefix}info",
        value="Server overview including member count.",
        inline=False,
    )
    community.add_field(
        name=f"{prefix}avatar [user] / {prefix}banner [user]",
        value="Display avatars or banners.",
        inline=False,
    )
    community.add_field(
        name=f"{prefix}poll <question> | <options...>",
        value="Create a quick reaction poll.",
        inline=False,
    )
    community.add_field(
        name=f"{prefix}remind <duration> <message>",
        value="Set a reminder.",
        inline=False,
    )

    music = discord.Embed(title="Music & Media", color=0x9B59B6)
    music.add_field(
        name=f"{prefix}play <url/search>",
        value="Play audio from YouTube.",
        inline=False,
    )
    music.add_field(
        name=f"{prefix}pause / {prefix}resume",
        value="Pause or resume playback.",
        inline=False,
    )
    music.add_field(
        name=f"{prefix}skip",
        value="Skip the current track.",
        inline=False,
    )
    music.add_field(
        name=f"{prefix}stop",
        value="Stop playback and clear the queue.",
        inline=False,
    )
    music.add_field(
        name=f"{prefix}leave",
        value="Disconnect from voice.",
        inline=False,
    )

    ai = discord.Embed(title="AI & Tickets", color=0xF1C40F)
    ai.add_field(
        name="Mentioning Guildest",
        value="Mention the bot to get a concise, helpful AI reply.",
        inline=False,
    )
    ai.add_field(
        name="Ticket system",
        value="Use the configured ticket panel to reach staff.",
        inline=False,
    )

    return [overview, moderation, community, music, ai]


class AdminCog(commands.Cog, name="Admin"):
    """Administrative and configuration commands."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.hybrid_command(name="help")
    async def help_command(self, ctx: commands.Context):
        """Show the interactive help menu."""
        pages = build_help_pages(ctx.clean_prefix)
        view = HelpPaginator(ctx, pages)
        await ctx.send(embed=view._update_footer(), view=view)

    @commands.group(name="guildconfig", invoke_without_command=True)
    async def guildconfig(self, ctx: commands.Context):
        """Show current guild configuration."""
        if ctx.guild is None:
            return

        settings = get_guild_settings(ctx.guild.id)
        resolved_voice = get_voice_channel_ids(ctx.guild)
        resolved_lobby = get_private_voice_lobby_id(ctx.guild)

        embed = discord.Embed(
            title=f"Guild configuration for {ctx.guild.name}", color=0x1ABC9C
        )
        embed.add_field(
            name="Auto role",
            value=str(settings.auto_role_id or "Not set (inherit default)"),
            inline=False,
        )
        embed.add_field(
            name="Gem role",
            value=str(settings.gem_role_id or "Not set (inherit default)"),
            inline=False,
        )
        embed.add_field(
            name="Gem trigger phrase",
            value=settings.gem_trigger_phrase or "Not set",
            inline=False,
        )
        embed.add_field(
            name="Audit log channel",
            value=str(settings.audit_log_channel_id or "Not set (inherit default)"),
            inline=False,
        )
        embed.add_field(
            name="Voice monitor channels",
            value=", ".join(str(cid) for cid in sorted(resolved_voice))
            if resolved_voice
            else "None configured",
            inline=False,
        )
        embed.add_field(
            name="Private VC lobby",
            value=str(resolved_lobby or "None configured"),
            inline=False,
        )

        await ctx.send(embed=embed)

    @guildconfig.command(name="set")
    async def guildconfig_set(
        self, ctx: commands.Context, key: str | None = None, *, value: str | None = None
    ):
        """Set a guild configuration value."""
        if ctx.guild is None:
            return

        if not (
            ctx.author.guild_permissions.manage_guild
            or ctx.author.guild_permissions.administrator
        ):
            await ctx.send("You need Manage Server permissions to change this.")
            return

        if key is None or value is None:
            await ctx.send(
                "Usage: ,guildconfig set <auto_role|gem_role|audit_channel|voice_channels|lobby_channel|gem_phrase> <value>"
            )
            return

        key = key.lower()
        settings = guild_settings.setdefault(ctx.guild.id, GuildSettings())

        try:
            if key in {"auto_role", "gem_role"}:
                role = await commands.RoleConverter().convert(ctx, value)
                if key == "auto_role":
                    settings.auto_role_id = role.id
                else:
                    settings.gem_role_id = role.id
                await ctx.send(
                    f"Updated {key.replace('_', ' ')} to {role.mention} ({role.id})."
                )
            elif key == "audit_channel":
                channel = await commands.TextChannelConverter().convert(ctx, value)
                settings.audit_log_channel_id = channel.id
                await ctx.send(f"Audit log channel set to {channel.mention} ({channel.id}).")
            elif key == "voice_channels":
                converter = commands.VoiceChannelConverter()
                channel_ids: set[int] = set()
                for token in value.split():
                    channel = await converter.convert(ctx, token)
                    channel_ids.add(channel.id)
                settings.voice_channel_ids = channel_ids or None
                await ctx.send(
                    "Voice monitor channels updated to: "
                    + (", ".join(f"<#{cid}>" for cid in channel_ids) if channel_ids else "None")
                )
            elif key == "lobby_channel":
                channel = await commands.VoiceChannelConverter().convert(ctx, value)
                settings.private_voice_lobby_id = channel.id
                await ctx.send(f"Private VC lobby set to {channel.mention} ({channel.id}).")
            elif key == "gem_phrase":
                settings.gem_trigger_phrase = value.lower()
                await ctx.send(f"Gem trigger phrase updated to `{settings.gem_trigger_phrase}`.")
            else:
                await ctx.send(
                    "Unknown key. Valid options: auto_role, gem_role, audit_channel, voice_channels, lobby_channel, gem_phrase"
                )
                return

            save_guild_configs()
        except commands.BadArgument as e:
            await ctx.send(f"I couldn't parse that value: {e}")
        except Exception as e:
            await ctx.send(f"Something went wrong while updating config: {e}")

    @guildconfig.command(name="clear")
    async def guildconfig_clear(self, ctx: commands.Context, key: str | None = None):
        """Clear a guild configuration value."""
        if ctx.guild is None:
            return

        if not (
            ctx.author.guild_permissions.manage_guild
            or ctx.author.guild_permissions.administrator
        ):
            await ctx.send("You need Manage Server permissions to change this.")
            return

        if key is None:
            await ctx.send("Specify which key to clear.")
            return

        key = key.lower()
        settings = guild_settings.setdefault(ctx.guild.id, GuildSettings())

        if key == "auto_role":
            settings.auto_role_id = None
        elif key == "gem_role":
            settings.gem_role_id = None
        elif key == "audit_channel":
            settings.audit_log_channel_id = None
        elif key == "voice_channels":
            settings.voice_channel_ids = None
        elif key == "lobby_channel":
            settings.private_voice_lobby_id = None
        elif key == "gem_phrase":
            settings.gem_trigger_phrase = GEM_TRIGGER_PHRASE
        else:
            await ctx.send(
                "Unknown key. Valid options: auto_role, gem_role, audit_channel, voice_channels, lobby_channel, gem_phrase"
            )
            return

        save_guild_configs()
        await ctx.send(f"Cleared custom value for {key}; now using defaults.")


async def setup(bot: commands.Bot):
    await bot.add_cog(AdminCog(bot))
