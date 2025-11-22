import discord
from discord.ext import commands
import os
from dotenv import load_dotenv
import asyncio
import yt_dlp
import json
from datetime import datetime, timedelta
from collections import defaultdict

from tickets import setup_ticket_system

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

# Setup external systems (tickets, etc.)
setup_ticket_system(bot)

# Data storage
user_data = defaultdict(lambda: {"messages": 0, "level": 0, "xp": 0})
message_timestamps = defaultdict(list)  # Track message timestamps for anti-nuke
DATA_FILE = "data/user_data.json"

def load_data():
    """Load user data from file"""
    try:
        if os.path.exists(DATA_FILE):
            with open(DATA_FILE, 'r') as f:
                data = json.load(f)
                for user_id, info in data.items():
                    user_data[int(user_id)] = info
    except Exception as e:
        print(f"Error loading data: {e}")

def save_data():
    """Save user data to file"""
    try:
        os.makedirs("data", exist_ok=True)
        with open(DATA_FILE, 'w') as f:
            json.dump({str(k): v for k, v in user_data.items()}, f, indent=2)
    except Exception as e:
        print(f"Error saving data: {e}")

def calculate_level(xp):
    """Calculate level from XP (100 XP per level)"""
    return xp // 100

@bot.event
async def on_ready():
    print(f'{bot.user} has arrived! Shalom everyone!')
    await bot.change_presence(activity=discord.Game(name="Backgammon (Shesh Besh)"))
    load_data()

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

    # Track messages for leaderboard and leveling
    user_data[user_id]["messages"] += 1
    user_data[user_id]["xp"] += 5  # 5 XP per message
    
    old_level = user_data[user_id]["level"]
    new_level = calculate_level(user_data[user_id]["xp"])
    user_data[user_id]["level"] = new_level
    
    # Level up notification
    if new_level > old_level:
        await message.channel.send(
            f"Mazel tov {message.author.mention}! You leveled up to level {new_level}! 🎉"
        )
    
    # Grant Gem role at 150 messages
    if user_data[user_id]["messages"] == 150:
        gem_role = message.guild.get_role(GEM_ROLE_ID)
        if gem_role:
            try:
                await message.author.add_roles(gem_role)
                await message.channel.send(
                    f"Sababa! {message.author.mention} reached 150 messages and earned the {gem_role.name} role! 💎"
                )
            except Exception as e:
                print(f"Failed to assign gem role: {e}")
    
    # Save data periodically (every 10 messages)
    if user_data[user_id]["messages"] % 10 == 0:
        save_data()
    
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

# Leaderboard and Level Commands
@bot.command(name='leaderboard', aliases=['lb', 'top'])
async def leaderboard(ctx):
    sorted_users = sorted(user_data.items(), key=lambda x: x[1]["messages"], reverse=True)[:10]
    
    embed = discord.Embed(
        title="📊 Message Leaderboard",
        description="Top 10 members by message count",
        color=0x0000ff
    )
    
    for i, (user_id, data) in enumerate(sorted_users, 1):
        user = await bot.fetch_user(user_id)
        embed.add_field(
            name=f"{i}. {user.name}",
            value=f"Messages: {data['messages']} | Level: {data['level']}",
            inline=False
        )
    
    embed.set_footer(text="Keep chatting to climb the ranks!")
    await ctx.send(embed=embed)

@bot.command(name='rank', aliases=['level', 'stats'])
async def rank(ctx, member: discord.Member = None):
    member = member or ctx.author
    data = user_data[member.id]
    
    embed = discord.Embed(
        title=f"{member.display_name}'s Stats",
        color=0x0000ff
    )
    embed.add_field(name="Messages", value=data["messages"], inline=True)
    embed.add_field(name="Level", value=data["level"], inline=True)
    embed.add_field(name="XP", value=f"{data['xp']}/100", inline=True)
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
        try:
            bot.run(TOKEN)
        finally:
            save_data()
