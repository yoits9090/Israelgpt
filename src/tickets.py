import discord
from discord.ext import commands

MARKETPLACE_CHANNEL_ID = 1441901428800229376
MARKETPLACE_STAFF_ROLE_IDS = [1441882323938316379, 1441878991370850335]


class MarketplaceTicketView(discord.ui.View):
    def __init__(self, bot: commands.Bot):
        super().__init__(timeout=None)
        self.bot = bot

    @discord.ui.button(
        label="Request Marketplace Listing",
        style=discord.ButtonStyle.primary,
        custom_id="gems:marketplace_ticket",
    )
    async def create_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.guild is None or interaction.channel is None:
            await interaction.response.send_message(
                "Nu, this only works in a server channel.", ephemeral=True,
            )
            return

        if interaction.channel.id != MARKETPLACE_CHANNEL_ID:
            await interaction.response.send_message(
                "Use this button in the marketplace channel, chaver.", ephemeral=True,
            )
            return

        thread_name = f"listing-{interaction.user.name}".replace(" ", "-")[:90]

        thread = await interaction.channel.create_thread(
            name=thread_name,
            type=discord.ChannelType.private_thread,
        )

        # Add requesting user
        await thread.add_user(interaction.user)

        guild = interaction.guild
        staff_members = set()
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
                # Ignore if we can't add a specific member
                pass

        role_mentions = []
        for role_id in MARKETPLACE_STAFF_ROLE_IDS:
            role = guild.get_role(role_id)
            if role:
                role_mentions.append(role.mention)

        mentions = " ".join(role_mentions)

        await thread.send(
            f"Shalom {interaction.user.mention}! This is your marketplace listing ticket.\n"
            f"{mentions} please take a look when you're free."
        )

        await interaction.response.send_message(
            "Your marketplace ticket has been created, check the new thread.",
            ephemeral=True,
        )


_ticket_view: MarketplaceTicketView | None = None


def setup_ticket_system(bot: commands.Bot) -> None:
    global _ticket_view
    if _ticket_view is None:
        _ticket_view = MarketplaceTicketView(bot)
        bot.add_view(_ticket_view)

    @bot.command(name="ticketpanel")
    @commands.has_permissions(manage_guild=True)
    async def ticketpanel(ctx: commands.Context):
        channel = ctx.guild.get_channel(MARKETPLACE_CHANNEL_ID) or ctx.channel

        embed = discord.Embed(
            title="Marketplace Listings",
            description=(
                "Click the button below to open a private ticket to request a marketplace listing.\n"
                "Staff will review your request b'karov (soon)."
            ),
            color=0x00BCD4,
        )

        await channel.send(embed=embed, view=_ticket_view)

        if channel.id != ctx.channel.id:
            await ctx.send(
                f"Ticket panel sent to {channel.mention}", delete_after=5,
            )
        else:
            await ctx.send("Ticket panel deployed, sababa.", delete_after=5)
