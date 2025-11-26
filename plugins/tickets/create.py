import discord
import asyncio
from .views import TicketControlsView

async def create_ticket(interaction: discord.Interaction, bot, db, config, category_name: str = None):
    """
    Creates a new ticket channel.
    """
    user = interaction.user
    guild = interaction.guild
    
    # Find category config
    categories = config.get("categories", [])
    cat_config = None
    if category_name:
        for cat in categories:
            if cat["name"] == category_name:
                cat_config = cat
                break
    
    if not cat_config and categories:
        cat_config = categories[0] # Fallback
    elif not cat_config:
        await interaction.response.send_message("❌ No ticket categories configured.", ephemeral=True)
        return

    # Check ticket limit
    open_tickets = db.get_open_tickets_count(user.id, guild.id)
    limit = cat_config.get("max_tickets", 1)
    
    if open_tickets >= limit:
        await interaction.response.send_message(f"❌ You have reached the limit of {limit} open tickets.", ephemeral=True)
        return

    # Get category channel
    category_id = cat_config.get("category_id")
    category = guild.get_channel(category_id) if category_id else None
    
    if not category:
        # Try to find a category named "Tickets" or create it
        category = discord.utils.get(guild.categories, name="Tickets")
        if not category:
            try:
                category = await guild.create_category("Tickets")
            except discord.Forbidden:
                await interaction.response.send_message("❌ I don't have permission to create the Tickets category.", ephemeral=True)
                return

    # Calculate ticket number
    prefix = cat_config.get("prefix", "ticket")
    ticket_num = db.get_next_ticket_number(guild.id, prefix)
    
    # Create channel
    channel_name = f"{prefix}-{ticket_num:04d}"
    
    overwrites = {
        guild.default_role: discord.PermissionOverwrite(read_messages=False),
        user: discord.PermissionOverwrite(read_messages=True, send_messages=True, attach_files=True),
        guild.me: discord.PermissionOverwrite(read_messages=True, send_messages=True, manage_channels=True)
    }
    
    # Add support role
    support_role_id = config.get("support_role_id")
    if support_role_id:
        support_role = guild.get_role(support_role_id)
        if support_role:
            overwrites[support_role] = discord.PermissionOverwrite(read_messages=True, send_messages=True)
    
    try:
        channel = await guild.create_text_channel(name=channel_name, category=category, overwrites=overwrites)
    except discord.Forbidden:
        await interaction.response.send_message("❌ I don't have permission to create the ticket channel.", ephemeral=True)
        return

    # Add to DB
    db.create_ticket(channel.id, user.id, guild.id, prefix, ticket_num)
    
    # Send welcome message
    welcome_msg = cat_config.get("welcome_message", "Support will be with you shortly.")
    embed_color_hex = config.get("embed_colors", {}).get("open", "#00FF00")
    embed_color = int(embed_color_hex.replace("#", ""), 16)
    
    embed = discord.Embed(
        title=f"{cat_config.get('emoji', '')} {cat_config.get('name', 'Ticket')} #{ticket_num:04d}", 
        description=welcome_msg, 
        color=embed_color
    )
    
    # Create View for controls
    view = TicketControlsView(claimed=False)
    
    await channel.send(content=f"{user.mention}", embed=embed, view=view)
    
    await interaction.response.send_message(f"✅ Ticket created: {channel.mention}", ephemeral=True)
