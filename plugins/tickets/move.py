import discord

async def move_ticket(interaction: discord.Interaction, bot, db, config, category_id: int):
    """
    Moves the ticket to another category.
    """
    channel = interaction.channel
    guild = interaction.guild
    
    # Check if this is a ticket channel
    ticket = db.get_ticket_by_channel(channel.id)
    if not ticket:
        await interaction.response.send_message("❌ This is not a ticket channel.", ephemeral=True)
        return

    category = guild.get_channel(category_id)
    if not category or not isinstance(category, discord.CategoryChannel):
        await interaction.response.send_message("❌ Invalid category.", ephemeral=True)
        return
        
    try:
        await channel.edit(category=category)
        await interaction.response.send_message(f"✅ Ticket moved to {category.name}.", ephemeral=True)
    except discord.Forbidden:
        await interaction.response.send_message("❌ I don't have permission to move the channel.", ephemeral=True)
