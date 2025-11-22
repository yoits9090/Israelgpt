import discord
from discord.ext import commands
import os
from dotenv import load_dotenv
import asyncio

# Load environment variables
load_dotenv()

# Configuration
TOKEN = os.getenv('DISCORD_TOKEN')
AUTO_ROLE_NAME = os.getenv('AUTO_ROLE_NAME', 'Member')

# Intents
intents = discord.Intents.default()
intents.message_content = True
intents.members = True

# Bot setup
bot = commands.Bot(command_prefix='!', intents=intents)

@bot.event
async def on_ready():
    print(f'{bot.user} has arrived! Shalom everyone!')
    await bot.change_presence(activity=discord.Game(name="Backgammon (Shesh Besh)"))

@bot.event
async def on_member_join(member):
    # Auto Role
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
        await channel.send(f"Shalom {member.mention}! Welcome to the mishpacha (family)!")

@bot.command(name='ban')
@commands.has_permissions(ban_members=True)
async def ban(ctx, member: discord.Member, *, reason=None):
    try:
        await member.ban(reason=reason)
        await ctx.send(f"Oy vey! {member.mention} has been banned! \nReason: {reason if reason else 'No reason given'}")
    except Exception as e:
        await ctx.send(f"Nu? I couldn't ban them. Error: {e}")

@bot.command(name='kick')
@commands.has_permissions(kick_members=True)
async def kick(ctx, member: discord.Member, *, reason=None):
    try:
        await member.kick(reason=reason)
        await ctx.send(f"Yalla bye! {member.mention} has been kicked out.")
    except Exception as e:
        await ctx.send(f"Problem kicking this guy: {e}")

@bot.command(name='clear')
@commands.has_permissions(manage_messages=True)
async def clear(ctx, amount: int):
    await ctx.channel.purge(limit=amount + 1)
    msg = await ctx.send(f"Cleaned up the balagan! Removed {amount} messages.")
    await asyncio.sleep(3)
    await msg.delete()

@bot.command(name='info')
async def info(ctx):
    embed = discord.Embed(title=f"Info for {ctx.guild.name}", description="Here is the situation...", color=0x0000ff)
    embed.add_field(name="Server Name", value=ctx.guild.name, inline=True)
    embed.add_field(name="Member Count", value=ctx.guild.member_count, inline=True)
    embed.add_field(name="Region", value="The Middle East (probably)", inline=True)
    embed.set_footer(text="Developed with chutzpah")
    await ctx.send(embed=embed)

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
