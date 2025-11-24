import discord
from discord.ext import commands
import os
from dotenv import load_dotenv
import asyncio
import yt_dlp
from datetime import datetime, timedelta
from collections import defaultdict
import re

from tickets import setup_ticket_system, register_ticket_view
from db.levels import increment_activity, get_user_stats, get_top_users
from db.users import record_message
from llm_client import generate_israeli_reply

# Load environment variables
load_dotenv()

# Configuration
TOKEN = os.getenv('DISCORD_TOKEN')
AUTO_ROLE_ID = int(os.getenv('AUTO_ROLE_ID', '0'))  # Unpolished role
GEM_ROLE_ID = 1441889921102118963  # Gem role granted at 150 messages

# Intents
intents = discord.Intents.default()
intents.message_content = True
intents.members = True

# Bot setup
bot = commands.Bot(command_prefix=',', intents=intents)
bot.remove_command("help")

# Setup external systems (tickets, etc.)
setup_ticket_system(bot)

# In-memory tracking only for anti-nuke
message_timestamps = defaultdict(list)  # Track message timestamps for anti-nuke


def parse_duration(duration: str) -> timedelta | None:
    match = re.match(r"^(\d+)([smhdw])$", duration)
    if not match:
        return None

    value, unit = match.groups()
    value = int(value)

    multipliers = {
        "s": 1,
        "m": 60,
        "h": 60 * 60,
        "d": 60 * 60 * 24,
        "w": 60 * 60 * 24 * 7,
    }

    seconds = value * multipliers[unit]
    return timedelta(seconds=seconds)


class HelpPaginator(discord.ui.View):
    def __init__(self, ctx, pages: list[discord.Embed]):
        super().__init__(timeout=180)
        self.ctx = ctx
        self.pages = pages
        self.current_page = 0

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user != self.ctx.author:
            await interaction.response.send_message(
                "Only the person who asked for help can use these buttons, chaver!",
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

    overview = discord.Embed(
        title="IsraelGPT Command Guide",
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
        value=(
            "Timeout a user for a duration like `10m`, `2h`, or `1d`. You can also reply "
            "to a user's message instead of mentioning them."
        ),
        inline=False,
    )
    moderation.add_field(
        name=f"{prefix}clear <amount>",
        value="Bulk delete the given number of messages in the current channel.",
        inline=False,
    )
    moderation.add_field(
        name=f"{prefix}role <user> <role>",
        value="Toggle a role for a user by name or ID. Requires Manage Roles permission.",
        inline=False,
    )
    moderation.add_field(
        name=f"{prefix}slowmode <seconds>",
        value=(
            "Set channel slowmode in seconds (use 0 to disable). Great for calming a chat "
            "without full lockdown. Requires Manage Channels permission."
        ),
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
        value="See your own or another member's message, XP, and level stats.",
        inline=False,
    )
    community.add_field(
        name=f"{prefix}info",
        value="Server overview including member count and region.",
        inline=False,
    )
    community.add_field(
        name=f"{prefix}avatar [user] / {prefix}banner [user]",
        value="Display avatars or banners for yourself or a mentioned user.",
        inline=False,
    )
    community.add_field(
        name=f"{prefix}servericon / {prefix}serverbanner",
        value="Preview the guild's icon or banner if available.",
        inline=False,
    )
    community.add_field(
        name=f"{prefix}poll <question> | <option 1> | <option 2> ...",
        value=(
            "Create a quick reaction poll with up to 10 options. Separate options using `|` "
            "and I'll add number emojis automatically."
        ),
        inline=False,
    )
    community.add_field(
        name=f"{prefix}remind <duration> <message>",
        value=(
            "Set a reminder like `,remind 15m Drink water`. I'll ping you in this channel "
            "when time's up."
        ),
        inline=False,
    )

    music = discord.Embed(title="Music & Media", color=0x9B59B6)
    music.add_field(
        name=f"{prefix}play <url/search>",
        value="Join your voice channel and start playing audio from YouTube.",
        inline=False,
    )
    music.add_field(
        name=f"{prefix}pause / {prefix}resume",
        value="Pause or resume the current track.",
        inline=False,
    )
    music.add_field(
        name=f"{prefix}skip",
        value="Skip the current track and move to the next queued song if available.",
        inline=False,
    )
    music.add_field(
        name=f"{prefix}stop",
        value="Stop playback and clear the queue for this server.",
        inline=False,
    )
    music.add_field(
        name=f"{prefix}leave",
        value="Disconnect the bot from voice and clear the queue.",
        inline=False,
    )

    ai = discord.Embed(title="AI & Tickets", color=0xF1C40F)
    ai.add_field(
        name="Mentioning IsraelGPT",
        value=(
            "Mention the bot to get a friendly AI reply tailored to your server. "
            "Great for quick answers or conversation starters."
        ),
        inline=False,
    )
    ai.add_field(
        name="Ticket system",
        value=(
            "Use the configured ticket panel to reach staff. Replies are routed through the "
            "ticket tools once you set them up (see server setup)."
        ),
        inline=False,
    )

    return [overview, moderation, community, music, ai]

@bot.event
async def on_ready():
    print(f'{bot.user} has arrived! Shalom everyone!')
    await bot.change_presence(activity=discord.Game(name="Backgammon (Shesh Besh)"))
    register_ticket_view(bot)


@bot.command(name='help')
async def help_command(ctx):
    pages = build_help_pages(ctx.clean_prefix)
    view = HelpPaginator(ctx, pages)
    await ctx.send(embed=view._update_footer(), view=view)

@bot.event
async def on_member_join(member):
    # Auto Role - Assign "unpolished" role
    if AUTO_ROLE_ID:
        role = member.guild.get_role(AUTO_ROLE_ID)
        if role:
            try:
                await member.add_roles(role)
                print(f"Assigned role {role.name} ({role.id}) to {member.name}")
            except Exception as e:
                print(f"Failed to assign role: {e}")
        else:
            print(f"Role with ID {AUTO_ROLE_ID} not found")

    # Welcome Message
    channel = member.guild.system_channel
    if channel:
        await channel.send(f"What's up! Welcome to Gems! {member.mention}")

@bot.event
async def on_message(message):
    if message.author.bot:
        return

    # Anti-nuke detection
    user_id = message.author.id
    now = datetime.now()
    
    # Clean old timestamps (older than 10 seconds)
    message_timestamps[user_id] = [
        ts for ts in message_timestamps[user_id] 
        if now - ts < timedelta(seconds=10)
    ]
    
    message_timestamps[user_id].append(now)
    
    # If more than 20 messages in 10 seconds, start deleting
    if len(message_timestamps[user_id]) > 20:
        try:
            await message.delete()
            if len(message_timestamps[user_id]) == 21:  # Only warn once
                await message.channel.send(
                    f"Oy vey {message.author.mention}, slow down! Anti-spam triggered.",
                    delete_after=5
                )
        except:
            pass
        await bot.process_commands(message)
        return
    # Track messages for leaderboard, leveling, and user activity
    if message.guild is not None:
        record_message(message.guild.id, user_id, now)
        messages, xp, level, leveled_up = increment_activity(
            message.guild.id,
            user_id,
            xp_gain=5,
        )

        # Level up notification
        if leveled_up:
            await message.channel.send(
                f"Mazel tov {message.author.mention}! You leveled up to level {level}! 🎉"
            )

        # Grant Gem role at 150 messages
        if messages == 150:
            gem_role = message.guild.get_role(GEM_ROLE_ID)
            if gem_role:
                try:
                    await message.author.add_roles(gem_role)
                    await message.channel.send(
                        f"Sababa! {message.author.mention} reached 150 messages and earned the {gem_role.name} role! 💎"
                    )
                except Exception as e:
                    print(f"Failed to assign gem role: {e}")

    # LLM response when the bot is mentioned (but not when running a command)
    try:
        mentioned_bot = bot.user is not None and bot.user in message.mentions
    except Exception:
        mentioned_bot = False

    if mentioned_bot and not message.content.startswith(str(bot.command_prefix)):
        content = message.content
        if message.guild is not None and message.guild.me is not None:
            content = content.replace(message.guild.me.mention, "").strip()
        if not content:
            content = "Say something helpful and friendly."

        reply = await generate_israeli_reply(
            user_message=content,
            username=message.author.display_name,
            guild_name=message.guild.name if message.guild else None,
            guild_id=message.guild.id if message.guild else None,
            user_id=message.author.id,
            channel_id=message.channel.id,
        )
        if reply:
            await message.reply(reply)

    await bot.process_commands(message)

# Moderation Commands
@bot.command(name='ban', aliases=['b'])
@commands.has_permissions(ban_members=True)
async def ban(ctx, member: discord.Member, *, reason=None):
    try:
        await member.ban(reason=reason)
        await ctx.send(f"Oy vey! {member.mention} has been banned! \nReason: {reason if reason else 'No reason given'}")
    except Exception as e:
        await ctx.send(f"Nu? I couldn't ban them. Error: {e}")

@bot.command(name='kick', aliases=['k'])
@commands.has_permissions(kick_members=True)
async def kick(ctx, member: discord.Member, *, reason=None):
    try:
        await member.kick(reason=reason)
        await ctx.send(f"Yalla bye! {member.mention} has been kicked out.")
    except Exception as e:
        await ctx.send(f"Problem kicking this guy: {e}")


@bot.command(name='mute', aliases=['timeout'])
@commands.has_permissions(moderate_members=True)
async def mute(ctx, member: discord.Member | None = None, duration: str | None = None):
    target = member

    if ctx.message.reference and target is None:
        try:
            referenced_message = await ctx.channel.fetch_message(ctx.message.reference.message_id)
            target = referenced_message.author
        except Exception:
            pass

    if target is None:
        await ctx.send("Nu? Who should I mute? Mention someone or reply to their message.")
        return

    if target == ctx.author:
        await ctx.send("You can't mute yourself, chaver!")
        return

    if duration is None:
        await ctx.send("How long? Add a duration like 10m, 1h, or 2d.")
        return

    parsed_duration = parse_duration(duration.lower())
    if parsed_duration is None:
        await ctx.send("I don't understand that duration. Use s, m, h, d, or w (e.g., 10m).")
        return

    if ctx.guild and target.top_role >= ctx.author.top_role and ctx.guild.owner_id != ctx.author.id:
        await ctx.send("Their hat is taller than yours—I can't mute them.")
        return

    timeout_until = discord.utils.utcnow() + parsed_duration

    try:
        await target.edit(timeout=timeout_until, reason=f"Muted by {ctx.author} for {duration}")
        await ctx.send(f"Shhhh {target.mention} has been muted for {duration}.")
    except discord.Forbidden:
        await ctx.send("I don't have permission to mute this member, bubbeleh.")
    except Exception as e:
        await ctx.send(f"Couldn't apply the mute: {e}")

@bot.command(name='clear', aliases=['c', 'purge'])
@commands.has_permissions(manage_messages=True)
async def clear(ctx, amount: int):
    await ctx.channel.purge(limit=amount + 1)
    msg = await ctx.send(f"Cleaned up the balagan! Removed {amount} messages.")
    await asyncio.sleep(3)
    await msg.delete()

# Role toggle command
@bot.command(name='role', aliases=['r'])
@commands.has_permissions(manage_roles=True)
async def toggle_role(ctx, member: discord.Member, *, role_input: str):
    # Try to find role by ID or name
    role = None
    
    # Check if it's an ID
    if role_input.isdigit():
        role = ctx.guild.get_role(int(role_input))
    
    # If not found, search by name
    if not role:
        role = discord.utils.get(ctx.guild.roles, name=role_input)
    
    if not role:
        await ctx.send(f"Oy, I couldn't find that role!")
        return
    
    try:
        if role in member.roles:
            await member.remove_roles(role)
            await ctx.send(f"Removed {role.name} from {member.mention}")
        else:
            await member.add_roles(role)
            await ctx.send(f"Added {role.name} to {member.mention}")
    except discord.Forbidden:
        await ctx.send(f"Oy vey! I don't have permission to manage that role, chaver!")
    except Exception as e:
        await ctx.send(f"Nu? Something went wrong: {e}")


@bot.command(name='slowmode')
@commands.has_permissions(manage_channels=True)
async def slowmode(ctx, seconds: int | None = None):
    if seconds is None:
        await ctx.send(
            f"Current slowmode is set to {ctx.channel.slowmode_delay} seconds. "
            "Provide a number to update it (use 0 to disable)."
        )
        return

    if seconds < 0 or seconds > 21600:
        await ctx.send("Use a value between 0 seconds and 6 hours (21600 seconds).")
        return

    try:
        await ctx.channel.edit(slowmode_delay=seconds)
        if seconds == 0:
            await ctx.send("Slowmode disabled. Keep it civil, chaverim!")
        else:
            await ctx.send(f"Slowmode updated to {seconds} seconds. Breathe and type slowly.")
    except discord.Forbidden:
        await ctx.send("I don't have permission to change slowmode here.")
    except Exception as e:
        await ctx.send(f"Couldn't adjust slowmode: {e}")

# Leaderboard and Level Commands
@bot.command(name='leaderboard', aliases=['lb', 'top'])
async def leaderboard(ctx):
    rows = get_top_users(ctx.guild.id, limit=10)

    embed = discord.Embed(
        title="📊 Message Leaderboard",
        description="Top 10 members by message count",
        color=0x0000ff
    )

    for i, row in enumerate(rows, 1):
        user = await bot.fetch_user(row["user_id"])
        embed.add_field(
            name=f"{i}. {user.name}",
            value=f"Messages: {row['messages']} | Level: {row['level']}",
            inline=False
        )

    embed.set_footer(text="Keep chatting to climb the ranks!")
    await ctx.send(embed=embed)

@bot.command(name='rank', aliases=['level', 'stats'])
async def rank(ctx, member: discord.Member = None):
    member = member or ctx.author
    stats = get_user_stats(ctx.guild.id, member.id)
    
    embed = discord.Embed(
        title=f"{member.display_name}'s Stats",
        color=0x0000ff
    )
    embed.add_field(name="Messages", value=stats["messages"], inline=True)
    embed.add_field(name="Level", value=stats["level"], inline=True)
    embed.add_field(name="XP", value=f"{stats['xp']}/100", inline=True)
    embed.set_thumbnail(url=member.display_avatar.url)
    
    await ctx.send(embed=embed)

# Info Commands
@bot.command(name='info')
async def info(ctx):
    embed = discord.Embed(title=f"Info for {ctx.guild.name}", description="Here is the situation...", color=0x0000ff)
    embed.add_field(name="Server Name", value=ctx.guild.name, inline=True)
    embed.add_field(name="Member Count", value=ctx.guild.member_count, inline=True)
    embed.add_field(name="Region", value="The Middle East (probably)", inline=True)
    embed.set_footer(text="Developed with chutzpah")
    await ctx.send(embed=embed)


@bot.command(name='poll')
async def poll(ctx, *, question_and_options: str | None = None):
    if question_and_options is None:
        await ctx.send("Provide a question and at least two options using `|` as a separator.")
        return

    segments = [segment.strip() for segment in question_and_options.split("|") if segment.strip()]
    if len(segments) < 3:
        await ctx.send("Format: `,poll What do we eat? | Pizza | Falafel | Sushi`")
        return

    question, options = segments[0], segments[1:]
    if len(options) > 10:
        await ctx.send("Easy there! Maximum of 10 options.")
        return

    emoji_numbers = ["1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣", "9️⃣", "🔟"]
    embed = discord.Embed(title=f"📊 {question}", color=0x1ABC9C)
    description_lines = [f"{emoji_numbers[i]} {option}" for i, option in enumerate(options)]
    embed.description = "\n".join(description_lines)
    embed.set_footer(text="React below to vote! Votes update live.")

    message = await ctx.send(embed=embed)
    for i in range(len(options)):
        await message.add_reaction(emoji_numbers[i])


@bot.command(name='remind', aliases=['reminder'])
async def remind(ctx, duration: str | None = None, *, reminder: str | None = None):
    if duration is None or reminder is None:
        await ctx.send("Usage: `,remind <duration> <message>` e.g. `,remind 15m Drink water`")
        return

    parsed = parse_duration(duration.lower())
    if parsed is None:
        await ctx.send("I couldn't parse that time. Use values like 10m, 2h, or 1d.")
        return

    await ctx.send(f"Reminder set for {duration}. I'll ping you when time's up!")

    await asyncio.sleep(parsed.total_seconds())

    try:
        await ctx.send(f"{ctx.author.mention} ⏰ Reminder: {reminder}")
    except Exception as e:
        print(f"Failed to send reminder: {e}")

@bot.command(name='avatar', aliases=['av', 'pfp'])
async def avatar(ctx, member: discord.Member = None):
    member = member or ctx.author
    embed = discord.Embed(title=f"{member.display_name}'s Avatar", color=0x0000ff)
    embed.set_image(url=member.display_avatar.url)
    embed.set_footer(text="Sababa!")
    await ctx.send(embed=embed)

@bot.command(name='banner')
async def banner(ctx, member: discord.Member = None):
    member = member or ctx.author
    user = await bot.fetch_user(member.id)
    if user.banner:
        embed = discord.Embed(title=f"{member.display_name}'s Banner", color=0x0000ff)
        embed.set_image(url=user.banner.url)
        await ctx.send(embed=embed)
    else:
        await ctx.send(f"Oy, {member.display_name} doesn't have a banner!")

@bot.command(name='servericon', aliases=['guildicon'])
async def servericon(ctx):
    if ctx.guild.icon:
        embed = discord.Embed(title=f"{ctx.guild.name}'s Icon", color=0x0000ff)
        embed.set_image(url=ctx.guild.icon.url)
        await ctx.send(embed=embed)
    else:
        await ctx.send("This server has no icon, bubbeleh!")

@bot.command(name='serverbanner', aliases=['guildbanner'])
async def serverbanner(ctx):
    if ctx.guild.banner:
        embed = discord.Embed(title=f"{ctx.guild.name}'s Banner", color=0x0000ff)
        embed.set_image(url=ctx.guild.banner.url)
        await ctx.send(embed=embed)
    else:
        await ctx.send("This server has no banner, chaver!")

# Music commands
music_queue = {}

YTDL_OPTIONS = {
    'format': 'bestaudio/best',
    'noplaylist': True,
    'quiet': True,
    'no_warnings': True,
    'default_search': 'auto',
    'source_address': '0.0.0.0'
}

FFMPEG_OPTIONS = {
    'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
    'options': '-vn'
}

@bot.command(name='play', aliases=['p'])
async def play(ctx, *, url):
    if not ctx.author.voice:
        await ctx.send("Chaver, you need to be in a voice channel!")
        return

    channel = ctx.author.voice.channel
    
    if ctx.voice_client is None:
        await channel.connect()
    elif ctx.voice_client.channel != channel:
        await ctx.voice_client.move_to(channel)

    await ctx.send(f"Nu, searching for: {url}...")
    
    try:
        with yt_dlp.YoutubeDL(YTDL_OPTIONS) as ydl:
            info = ydl.extract_info(url, download=False)
            if 'entries' in info:
                info = info['entries'][0]
            
            url2 = info['url']
            title = info.get('title', 'Unknown')
            
            source = discord.FFmpegPCMAudio(url2, **FFMPEG_OPTIONS)
            
            if ctx.voice_client.is_playing():
                if ctx.guild.id not in music_queue:
                    music_queue[ctx.guild.id] = []
                music_queue[ctx.guild.id].append((url2, title))
                await ctx.send(f"Added to queue: **{title}**")
            else:
                ctx.voice_client.play(source, after=lambda e: play_next(ctx))
                await ctx.send(f"Now playing: **{title}** 🎵")
    except Exception as e:
        await ctx.send(f"Oy vey, error playing audio: {e}")

def play_next(ctx):
    if ctx.guild.id in music_queue and music_queue[ctx.guild.id]:
        url2, title = music_queue[ctx.guild.id].pop(0)
        source = discord.FFmpegPCMAudio(url2, **FFMPEG_OPTIONS)
        ctx.voice_client.play(source, after=lambda e: play_next(ctx))
        asyncio.run_coroutine_threadsafe(
            ctx.send(f"Now playing: **{title}** 🎵"),
            bot.loop
        )

@bot.command(name='pause')
async def pause(ctx):
    if ctx.voice_client and ctx.voice_client.is_playing():
        ctx.voice_client.pause()
        await ctx.send("Paused the music, hold on...")
    else:
        await ctx.send("Nothing is playing, chaver!")

@bot.command(name='resume')
async def resume(ctx):
    if ctx.voice_client and ctx.voice_client.is_paused():
        ctx.voice_client.resume()
        await ctx.send("Yalla, resuming!")
    else:
        await ctx.send("Nothing is paused!")

@bot.command(name='skip')
async def skip(ctx):
    if ctx.voice_client and ctx.voice_client.is_playing():
        ctx.voice_client.stop()
        await ctx.send("Skipping this one...")
    else:
        await ctx.send("Nothing is playing!")

@bot.command(name='stop')
async def stop(ctx):
    if ctx.voice_client:
        if ctx.guild.id in music_queue:
            music_queue[ctx.guild.id].clear()
        ctx.voice_client.stop()
        await ctx.send("Stopped the music.")
    else:
        await ctx.send("I'm not in a voice channel!")

@bot.command(name='leave', aliases=['disconnect', 'dc'])
async def leave(ctx):
    if ctx.voice_client:
        if ctx.guild.id in music_queue:
            music_queue[ctx.guild.id].clear()
        await ctx.voice_client.disconnect()
        await ctx.send("Shalom, I'm leaving!")
    else:
        await ctx.send("I'm not in a voice channel, bubbeleh!")

@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.MissingPermissions):
        await ctx.send("Chaver, you don't have permissions for this!")
    elif isinstance(error, commands.MissingRequiredArgument):
        await ctx.send("Nu? You forgot something in the command.")
    else:
        print(f"Error: {error}")

if __name__ == "__main__":
    if not TOKEN:
        print("Error: DISCORD_TOKEN not found in .env")
    else:
        bot.run(TOKEN)
