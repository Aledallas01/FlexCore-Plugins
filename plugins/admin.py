"""
Admin Utilities Plugin

Essential commands for bot administration:
- Dynamic help system (auto-generates from loaded plugins)
- Hot reload for plugins (no restart needed)
- Bot statistics and management

Owner-only commands for development and maintenance.
"""

import discord
from discord.ext import commands
from discord import app_commands
from typing import Optional
import traceback

class AdminCog(commands.Cog):
    """Administrative utilities for bot owners"""
    
    def __init__(self, bot):
        self.bot = bot
        print("✅ [Admin] Utilities loaded!")
    
    # ==================== RELOAD SYSTEM ====================
    
    @commands.command(name="reload")
    @commands.is_owner()
    async def reload_command(self, ctx, plugin: str):
        """Hot reload a plugin without restarting the bot (Owner Only)
        
        Usage: !reload <plugin_name>
        Example: !reload moderation
        """
        try:
            # Unload
            await self.bot.unload_extension(f"plugins.{plugin}")
            
            # Reload
            await self.bot.load_extension(f"plugins.{plugin}")
            
            embed = discord.Embed(
                title="🔄 Plugin Reloaded",
                description=f"✅ **{plugin}** has been reloaded successfully!",
                color=discord.Color.green()
            )
            await ctx.send(embed=embed)
            print(f"[Admin] Plugin '{plugin}' reloaded by {ctx.author}")
            
        except commands.ExtensionNotLoaded:
            await ctx.send(f"❌ Plugin **{plugin}** is not loaded!")
        except commands.ExtensionNotFound:
            await ctx.send(f"❌ Plugin **{plugin}** not found!\nMake sure the file exists in `plugins/{plugin}.py`")
        except Exception as e:
            error_embed = discord.Embed(
                title="❌ Reload Failed",
                description=f"**Plugin:** {plugin}\n\n**Error:**\n```py\n{str(e)}\n```",
                color=discord.Color.red()
            )
            await ctx.send(embed=error_embed)
            print(f"[Admin] Error reloading '{plugin}': {e}")
            traceback.print_exc()
    
    @app_commands.command(name="reload", description="Hot reload a plugin (Owner Only)")
    @app_commands.describe(plugin="Name of the plugin to reload")
    async def reload_slash(self, interaction: discord.Interaction, plugin: str):
        """Slash command version of reload"""
        # Check if user is owner
        if interaction.user.id != self.bot.owner_id:
            await interaction.response.send_message("❌ Only the bot owner can use this command!", ephemeral=True)
            return
        
        try:
            # Unload & Reload
            await self.bot.unload_extension(f"plugins.{plugin}")
            await self.bot.load_extension(f"plugins.{plugin}")
            
            embed = discord.Embed(
                title="🔄 Plugin Reloaded",
                description=f"✅ **{plugin}** has been reloaded successfully!",
                color=discord.Color.green()
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            print(f"[Admin] Plugin '{plugin}' reloaded by {interaction.user}")
            
        except commands.ExtensionNotLoaded:
            await interaction.response.send_message(f"❌ Plugin **{plugin}** is not loaded!", ephemeral=True)
        except commands.ExtensionNotFound:
            await interaction.response.send_message(f"❌ Plugin **{plugin}** not found!", ephemeral=True)
        except Exception as e:
            error_embed = discord.Embed(
                title="❌ Reload Failed",
                description=f"**Plugin:** {plugin}\n\n**Error:**\n```py\n{str(e)[:500]}\n```",
                color=discord.Color.red()
            )
            await interaction.response.send_message(embed=error_embed, ephemeral=True)
    
    @reload_command.error
    async def reload_error(self, ctx, error):
        if isinstance(error, commands.NotOwner):
            await ctx.send("❌ Only the bot owner can reload plugins!")
    
    # ==================== DYNAMIC HELP SYSTEM ====================
    
    @commands.command(name="help")
    async def help_command(self, ctx, *, command: Optional[str] = None):
        """Dynamic help system - Shows all commands from loaded plugins
        
        Usage: 
        - !help - Show all commands
        - !help <command> - Show detailed info about a command
        """
        if command:
            await self._show_command_help(ctx, command)
        else:
            await self._show_all_commands(ctx)
    
    @app_commands.command(name="help", description="Show bot commands and usage")
    @app_commands.describe(command="Specific command to get help for (optional)")
    async def help_slash(self, interaction: discord.Interaction, command: Optional[str] = None):
        """Slash command version of help"""
        if command:
            await self._show_command_help_slash(interaction, command)
        else:
            await self._show_all_commands_slash(interaction)
    
    async def _show_all_commands(self, ctx):
        """Show all commands grouped by plugin"""
        embed = discord.Embed(
            title="📚 Bot Commands",
            description=f"Prefix: `{self.bot.command_prefix}` | Use `!help <command>` for details",
            color=discord.Color.blue(),
            timestamp=discord.utils.utcnow()
        )
        
        # Group commands by cog
        for cog_name, cog in sorted(self.bot.cogs.items()):
            # Get text commands from this cog
            text_commands = [cmd for cmd in cog.get_commands() if not cmd.hidden]
            
            # Get slash commands from this cog
            slash_commands = []
            if hasattr(cog, '__cog_app_commands__'):
                slash_commands = cog.__cog_app_commands__
            
            if text_commands or slash_commands:
                # Build command list
                cmd_list = []
                
                # Add text commands
                for cmd in text_commands[:5]:  # Limit to 5 per plugin
                    cmd_list.append(f"`!{cmd.name}`")
                
                # Add slash commands
                for cmd in slash_commands[:5]:
                    if cmd.name not in [c.name for c in text_commands]:  # Avoid duplicates
                        cmd_list.append(f"`/{cmd.name}`")
                
                if cmd_list:
                    # Clean cog name (remove "Cog" suffix)
                    display_name = cog_name.replace("Cog", "")
                    
                    # Get cog description
                    description = cog.__doc__ or "No description"
                    if len(description) > 100:
                        description = description[:97] + "..."
                    
                    field_value = f"*{description}*\n" + " • ".join(cmd_list)
                    
                    if len(cmd_list) > 5:
                        field_value += f"\n*+{len(cmd_list) - 5} more*"
                    
                    embed.add_field(
                        name=f"🔌 {display_name}",
                        value=field_value,
                        inline=False
                    )
        
        # Footer
        total_commands = len(list(self.bot.walk_commands()))
        embed.set_footer(text=f"Total Commands: {total_commands} | Use /help for slash commands")
        
        await ctx.send(embed=embed)
    
    async def _show_all_commands_slash(self, interaction: discord.Interaction):
        """Show all slash commands grouped by plugin"""
        embed = discord.Embed(
            title="📚 Bot Slash Commands",
            description="All available slash commands organized by plugin",
            color=discord.Color.blue(),
            timestamp=discord.utils.utcnow()
        )
        
        # Group commands by cog
        for cog_name, cog in sorted(self.bot.cogs.items()):
            # Get slash commands from this cog
            if hasattr(cog, '__cog_app_commands__'):
                slash_commands = cog.__cog_app_commands__
                
                if slash_commands:
                    cmd_list = []
                    for cmd in slash_commands[:8]:
                        cmd_list.append(f"`/{cmd.name}`")
                    
                    # Clean cog name
                    display_name = cog_name.replace("Cog", "")
                    
                    field_value = " • ".join(cmd_list)
                    if len(slash_commands) > 8:
                        field_value += f"\n*+{len(slash_commands) - 8} more*"
                    
                    embed.add_field(
                        name=f"🔌 {display_name}",
                        value=field_value,
                        inline=False
                    )
        
        embed.set_footer(text="Use /help <command> for detailed info")
        await interaction.response.send_message(embed=embed)
    
    async def _show_command_help(self, ctx, command_name: str):
        """Show detailed help for a specific command"""
        # Find command
        cmd = self.bot.get_command(command_name)
        
        if not cmd:
            await ctx.send(f"❌ Command `{command_name}` not found!")
            return
        
        embed = discord.Embed(
            title=f"📖 Command: {cmd.name}",
            description=cmd.help or "No description available",
            color=discord.Color.green()
        )
        
        # Usage
        usage = f"{self.bot.command_prefix}{cmd.name}"
        if cmd.signature:
            usage += f" {cmd.signature}"
        embed.add_field(name="Usage", value=f"`{usage}`", inline=False)
        
        # Aliases
        if cmd.aliases:
            embed.add_field(name="Aliases", value=", ".join([f"`{a}`" for a in cmd.aliases]), inline=False)
        
        # Permissions
        if cmd.checks:
            perms = []
            for check in cmd.checks:
                if hasattr(check, '__name__'):
                    perms.append(check.__name__.replace('_', ' ').title())
            if perms:
                embed.add_field(name="Required Permissions", value=", ".join(perms), inline=False)
        
        await ctx.send(embed=embed)
    
    async def _show_command_help_slash(self, interaction: discord.Interaction, command_name: str):
        """Show detailed help for a specific slash command"""
        # Find slash command
        found_cmd = None
        for cog in self.bot.cogs.values():
            if hasattr(cog, '__cog_app_commands__'):
                for cmd in cog.__cog_app_commands__:
                    if cmd.name == command_name:
                        found_cmd = cmd
                        break
            if found_cmd:
                break
        
        if not found_cmd:
            await interaction.response.send_message(f"❌ Slash command `{command_name}` not found!", ephemeral=True)
            return
        
        embed = discord.Embed(
            title=f"📖 Slash Command: /{found_cmd.name}",
            description=found_cmd.description or "No description available",
            color=discord.Color.green()
        )
        
        # Parameters
        if found_cmd.parameters:
            params = []
            for param in found_cmd.parameters:
                required = "Required" if param.required else "Optional"
                param_desc = param.description or "No description"
                params.append(f"**{param.name}** ({required}): {param_desc}")
            
            embed.add_field(name="Parameters", value="\n".join(params), inline=False)
        
        await interaction.response.send_message(embed=embed, ephemeral=True)
    
    # ==================== BOT STATISTICS ====================
    
    @commands.command(name="botstats")
    async def botstats_command(self, ctx):
        """Show bot statistics and information"""
        embed = discord.Embed(
            title="📊 Bot Statistics",
            color=discord.Color.blue(),
            timestamp=discord.utils.utcnow()
        )
        
        # Server & User count
        total_users = sum(guild.member_count for guild in self.bot.guilds)
        embed.add_field(name="📊 Servers", value=len(self.bot.guilds), inline=True)
        embed.add_field(name="👥 Users", value=total_users, inline=True)
        embed.add_field(name="🏓 Ping", value=f"{round(self.bot.latency * 1000)}ms", inline=True)
        
        # Commands count
        text_cmds = len(list(self.bot.walk_commands()))
        slash_cmds = len([cmd for cog in self.bot.cogs.values() if hasattr(cog, '__cog_app_commands__') for cmd in cog.__cog_app_commands__])
        embed.add_field(name="📝 Text Commands", value=text_cmds, inline=True)
        embed.add_field(name="⚡ Slash Commands", value=slash_cmds, inline=True)
        embed.add_field(name="🔌 Plugins", value=len(self.bot.cogs), inline=True)
        
        if self.bot.user.avatar:
            embed.set_thumbnail(url=self.bot.user.avatar.url)
        
        embed.set_footer(text=f"Bot: {self.bot.user.name}")
        await ctx.send(embed=embed)


async def setup(bot):
    await bot.add_cog(AdminCog(bot))
