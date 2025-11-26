"""
Tickets Plugin
System for managing support tickets.
"""

import discord
from discord.ext import commands
from discord import app_commands
import json
import os
import sqlite3
import sys
from typing import Optional, Dict, List

# Add plugins directory to path to allow imports from tickets folder
sys.path.append(os.path.dirname(__file__))

from tickets import create_ticket, close_ticket, delete_ticket, claim_ticket, move_ticket
from tickets.views import TicketPanelView, TicketControlsView, ConfirmationView, ReasonModal

class TicketsDatabase:
    """Manages the SQLite database for the tickets system"""
    
    def __init__(self, db_path: str = "data/tickets.db"):
        self.db_path = db_path
        self._ensure_data_directory()
        self._initialize_database()
    
    def _ensure_data_directory(self):
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
    
    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn
    
    def _initialize_database(self):
        conn = self._get_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS tickets (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                channel_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                guild_id INTEGER NOT NULL,
                category_prefix TEXT,
                ticket_number INTEGER,
                status TEXT DEFAULT 'open',
                claimed_by INTEGER,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                closed_at DATETIME
            )
        """)
        
        conn.commit()
        conn.close()
        
    def create_ticket(self, channel_id: int, user_id: int, guild_id: int, category_prefix: str, ticket_number: int) -> int:
        conn = self._get_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            INSERT INTO tickets (channel_id, user_id, guild_id, category_prefix, ticket_number)
            VALUES (?, ?, ?, ?, ?)
        """, (channel_id, user_id, guild_id, category_prefix, ticket_number))
        
        ticket_id = cursor.lastrowid
        conn.commit()
        conn.close()
        return ticket_id

    def get_next_ticket_number(self, guild_id: int, category_prefix: str) -> int:
        conn = self._get_connection()
        cursor = conn.cursor()
        
        # Get max ticket number for this category
        cursor.execute("""
            SELECT MAX(ticket_number) as max_num FROM tickets 
            WHERE guild_id = ? AND category_prefix = ?
        """, (guild_id, category_prefix))
        
        result = cursor.fetchone()
        current_max = result['max_num'] if result['max_num'] is not None else 0
        
        conn.close()
        return current_max + 1

    def close_ticket(self, channel_id: int):
        conn = self._get_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            UPDATE tickets 
            SET status = 'closed', closed_at = CURRENT_TIMESTAMP 
            WHERE channel_id = ?
        """, (channel_id,))
        
        conn.commit()
        conn.close()

    def claim_ticket(self, channel_id: int, user_id: int):
        conn = self._get_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            UPDATE tickets 
            SET claimed_by = ? 
            WHERE channel_id = ?
        """, (user_id, channel_id))
        
        conn.commit()
        conn.close()

    def get_ticket_by_channel(self, channel_id: int) -> Optional[Dict]:
        conn = self._get_connection()
        cursor = conn.cursor()
        
        cursor.execute("SELECT * FROM tickets WHERE channel_id = ?", (channel_id,))
        row = cursor.fetchone()
        conn.close()
        return dict(row) if row else None

    def get_open_tickets_count(self, user_id: int, guild_id: int) -> int:
        conn = self._get_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT COUNT(*) as count FROM tickets 
            WHERE user_id = ? AND guild_id = ? AND status = 'open'
        """, (user_id, guild_id))
        
        count = cursor.fetchone()['count']
        conn.close()
        return count

class TicketsCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.db = TicketsDatabase()
        self.config_name = "tickets"
        self.config_path = os.path.join("config", f"{self.config_name}.json")
        self.default_config = {
            "panel_message": {
                "title": "Support Tickets",
                "description": "Select a category below to open a ticket.",
                "color": "#5865F2"
            },
            "categories": [
                {
                    "name": "Support",
                    "description": "General support",
                    "emoji": "❓",
                    "prefix": "support",
                    "category_id": 0,
                    "welcome_message": "Support will be with you shortly.",
                    "max_tickets": 1
                },
                {
                    "name": "Billing",
                    "description": "Billing inquiries",
                    "emoji": "💳",
                    "prefix": "billing",
                    "category_id": 0,
                    "welcome_message": "Please provide your transaction ID.",
                    "max_tickets": 1
                }
            ],
            "embed_colors": {
                "open": "#00FF00",
                "closed": "#FF0000",
                "deleted": "#000000",
                "claimed": "#0000FF"
            },
            "support_role_id": 0,
            "log_channel_id": 0
        }
        self.config = self._load_and_validate_config()

    def _load_and_validate_config(self):
        if not os.path.exists(self.config_path):
            os.makedirs(os.path.dirname(self.config_path), exist_ok=True)
            with open(self.config_path, 'w') as f:
                json.dump(self.default_config, f, indent=4)
            return self.default_config

        with open(self.config_path, 'r') as f:
            config = json.load(f)

        modified = False
        # Basic check for top level keys
        for key, value in self.default_config.items():
            if key not in config:
                config[key] = value
                modified = True

        if modified:
            with open(self.config_path, 'w') as f:
                json.dump(config, f, indent=4)

        return config

    async def cog_load(self):
        # Register persistent views
        # We need to reconstruct the view with categories from config
        categories = self.config.get("categories", [])
        self.bot.add_view(TicketPanelView(categories))
        self.bot.add_view(TicketControlsView(claimed=False))
        self.bot.add_view(TicketControlsView(claimed=True)) # Register both states if needed, though custom_id handles it
        # Actually, for dynamic views like ConfirmationView, we might not need persistent registration if we send them with timeout=None
        # But for the Panel and Controls (which sit in channels), we do.
        self.bot.add_view(ConfirmationView(action="close"))
        self.bot.add_view(ConfirmationView(action="delete"))

    # Listeners for persistent buttons and dropdowns
    @commands.Cog.listener()
    async def on_interaction(self, interaction: discord.Interaction):
        if interaction.type != discord.InteractionType.component:
            return
            
        custom_id = interaction.data.get("custom_id")
        if not custom_id:
            return

        # Dropdown
        if custom_id == "ticket_category_select":
            # Get selected value
            values = interaction.data.get("values", [])
            if not values:
                return
            category_name = values[0]
            await create_ticket(interaction, self.bot, self.db, self.config, category_name)
            
        # Buttons
        elif custom_id == "ticket_claim":
            await claim_ticket(interaction, self.bot, self.db, self.config)
        elif custom_id == "ticket_close":
            # Switch to confirmation view
            view = ConfirmationView(action="close")
            await interaction.response.edit_message(view=view)
        elif custom_id == "ticket_delete":
            # Switch to confirmation view
            view = ConfirmationView(action="delete")
            await interaction.response.edit_message(view=view)
            
        # Confirmation Actions
        elif custom_id == "ticket_confirm_close":
            await close_ticket(interaction, self.bot, self.db, self.config, confirmed=True)
        elif custom_id == "ticket_confirm_delete":
            await delete_ticket(interaction, self.bot, self.db, self.config, confirmed=True)
            
        # Cancel Actions (Return to controls)
        elif custom_id == "ticket_cancel_close" or custom_id == "ticket_cancel_delete":
            # We need to know if it was claimed to show the right button state
            ticket = self.db.get_ticket_by_channel(interaction.channel_id)
            claimed = ticket['claimed_by'] is not None if ticket else False
            view = TicketControlsView(claimed=claimed)
            await interaction.response.edit_message(view=view)
            
        # Reason Actions (Open Modal)
        elif custom_id == "ticket_reason_close":
            async def close_callback(inter, reason):
                await close_ticket(inter, self.bot, self.db, self.config, confirmed=True, reason=reason)
            await interaction.response.send_modal(ReasonModal(action="Close", callback_func=close_callback))
            
        elif custom_id == "ticket_reason_delete":
            async def delete_callback(inter, reason):
                await delete_ticket(inter, self.bot, self.db, self.config, confirmed=True, reason=reason)
            await interaction.response.send_modal(ReasonModal(action="Delete", callback_func=delete_callback))

    # Command Group
    ticket_group = app_commands.Group(name="ticket", description="Manage support tickets")

    @ticket_group.command(name="create", description="Create a new support ticket")
    async def create(self, interaction: discord.Interaction):
        await create_ticket(interaction, self.bot, self.db, self.config)

    @ticket_group.command(name="panel", description="Send the ticket panel")
    @app_commands.checks.has_permissions(administrator=True)
    async def panel(self, interaction: discord.Interaction):
        embed_config = self.config.get("panel_message", {})
        embed = discord.Embed(
            title=embed_config.get("title", "Support Tickets"),
            description=embed_config.get("description", "Select a category below to open a ticket."),
            color=int(embed_config.get("color", "#5865F2").replace("#", ""), 16)
        )
        
        categories = self.config.get("categories", [])
        view = TicketPanelView(categories)
        await interaction.channel.send(embed=embed, view=view)
        await interaction.response.send_message("✅ Panel sent!", ephemeral=True)

    @ticket_group.command(name="close", description="Close the current ticket")
    async def close(self, interaction: discord.Interaction):
        # Trigger the same flow as the button
        view = ConfirmationView(action="close")
        await interaction.response.send_message("Are you sure?", view=view, ephemeral=True)

    @ticket_group.command(name="claim", description="Claim the current ticket")
    @app_commands.checks.has_permissions(manage_messages=True) 
    async def claim(self, interaction: discord.Interaction):
        await claim_ticket(interaction, self.bot, self.db, self.config)

    @ticket_group.command(name="add", description="Add a user to the ticket")
    @app_commands.checks.has_permissions(manage_messages=True)
    async def add(self, interaction: discord.Interaction, user: discord.Member):
        ticket = self.db.get_ticket_by_channel(interaction.channel_id)
        if not ticket:
            await interaction.response.send_message("❌ This is not a ticket channel.", ephemeral=True)
            return
            
        await interaction.channel.set_permissions(user, read_messages=True, send_messages=True)
        await interaction.response.send_message(f"✅ Added {user.mention} to the ticket.")

    @ticket_group.command(name="remove", description="Remove a user from the ticket")
    @app_commands.checks.has_permissions(manage_messages=True)
    async def remove(self, interaction: discord.Interaction, user: discord.Member):
        ticket = self.db.get_ticket_by_channel(interaction.channel_id)
        if not ticket:
            await interaction.response.send_message("❌ This is not a ticket channel.", ephemeral=True)
            return
            
        await interaction.channel.set_permissions(user, overwrite=None)
        await interaction.response.send_message(f"✅ Removed {user.mention} from the ticket.")

    @ticket_group.command(name="move", description="Move the ticket to another category")
    @app_commands.checks.has_permissions(manage_channels=True)
    async def move(self, interaction: discord.Interaction, category: discord.CategoryChannel):
        await move_ticket(interaction, self.bot, self.db, self.config, category.id)

async def setup(bot):
    await bot.add_cog(TicketsCog(bot))
