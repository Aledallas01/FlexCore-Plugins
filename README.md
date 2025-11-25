# 🔌 FlexCore-Plugins

> Modular plugin system for Discord bots based on discord.py

FlexCore-Plugins is a collection of flexible and reusable plugins for Discord bots, designed with a modular architecture that allows you to easily extend your bot's functionality.

---

## 📋 Table of Contents

- [Features](#-features)
- [Project Structure](#-project-structure)
- [Installation](#-installation)
- [Available Plugins](#-available-plugins)
- [Creating a Plugin](#-creating-a-plugin)
- [Configuration](#-configuration)
- [Usage](#-usage)
- [Contributing](#-contributing)
- [License](#-license)

---

## ✨ Features

- **🔧 Modular System**: Each feature is an independent plugin that can be loaded/unloaded at runtime
- **⚙️ Auto-Config**: Plugins automatically create and validate their own configurations
- **🛡️ Config Checker**: Automatic validation and repair system for configurations
- **📊 Integrated Database**: SQLite support for persistent data storage
- **📝 Advanced Logging**: Complete logging system with rotating files
- **🔐 Permission Management**: Granular permission control for commands and features
- **⏱️ Rate Limiting**: Built-in anti-spam protection

---

## 📁 Project Structure

```
FlexCore-Plugins/
│
├── plugins/                 # Plugin directory
│   └── example.py          # Example plugin with best practices
│
├── config/                  # Configuration files (auto-generated)
│   └── *.json
│
├── data/                    # Database and persistent data
│   └── example.db
│
├── logs/                    # Log files
│   └── example.log
│
└── README.md               # This file
```

---

## 🚀 Installation

### Prerequisites

- Python 3.8 or higher
- discord.py 2.0+

### Setup

1.  **Clone the bot**
    ```bash
    git clone https://github.com/Aledallas01/FlexCore-Discord-Bot.git
    cd FlexCore-Discord-Bot
    ```

2.  **Install dependencies**
    ```bash
    pip install -r requirements.txt
    ```

3.  **Configure your bot**
    Open config/config.json and configure the Bot

4.  **Start the bot**
    ```bash
    python bot.py
    ```

5. **Download Plugin**
    1. Download the plugin from the [FlexCore-Plugins](https://github.com/Aledallas01/FlexCore-Plugins) repository
    2. Place the plugin in the `plugins` directory
    3. Restart the bot

    or

    1. Open the UI
    2. Click on **PLUGIN STORE**
    3. Choose the plugin
    4. Click **Download**
    5. Restart the bot

---

## 🎯 Available Plugins

### 📌 Example Plugin (`example.py`)

Demonstration plugin showcasing best practices for creating new plugins.

**Features:**
- ✅ Auto-config creation
- ✅ Config validation and repair
- ✅ Example commands
- ✅ Role-based permission management

**Commands:**
- `!example` - Shows a personalized welcome message
- `!ping` - Shows the bot latency
- `!echo` - Echoes a message
- `!serverinfo` - Shows the server info
- `/hello` - Sends a hello message
- `/userinfo` - Shows a user info
- `/chooseslash` - DropDown
- `/secret` - Sends ephemeral message
- `/kick_slash` - Kicks a user
- `/reload_config` - Reloads and verifies configuration (requires admin permissions)

**Configuration:**
```json
{
    "welcome_message": "Hello {user}, welcome to the server!",
    "admin_role_id": 0,
    "log_channel_id": 0
}
```

---

### 🛡️ Moderation Plugin (`moderation.py`)

Complete moderation system with SQLite database, automatic logging, and advanced management of warns, bans, mutes, and kicks.

**Features:**
- ⚠️ Warning system with counter
- 🔨 Temporary and permanent bans
- 🔇 Temporary and permanent mutes
- 👢 Kick system
- 📊 SQLite database for complete history
- 📝 Automatic logging of all actions
- ⏰ Automatic cleanup of expired punishments
- 🌍 Multilingual support
- ⏱️ Integrated rate limiting
- 🔐 Granular permission system

**Slash Commands:**

| Command | Description | Required Permissions |
|---------|-------------|-------------------|
| `/warn` | Warns a user | `moderate_members` |
| `/unwarn` | Removes the last warning | `moderate_members` |
| `/ban` | Bans a user | `ban_members` |
| `/unban` | Removes a ban | `ban_members` |
| `/mute` | Mutes a user | `moderate_members` |
| `/unmute` | Removes a mute | `moderate_members` |
| `/kick` | Kicks a user | `kick_members` |

**Database Schema:**

The plugin uses an SQLite database with the following tables:
- `warns` - User warnings
- `bans` - Temporary and permanent bans
- `mutes` - Mutes
- `kicks` - Kicks
- `mod_logs` - Complete log of all actions

**Configuration:**
```json
{
    "mute_role_name": "Muted",
    "log_channel_id": 0,
    "max_warns_before_action": 3,
    "auto_action_on_max_warns": "mute",
    "auto_mute_duration": 3600,
    "language": "en"
}
```

---

## 🛠️ Creating a Plugin

To create a new plugin, follow these steps:

### 1. Create the plugin file

Create a new Python file in the `plugins/` folder:

```python
import discord
from discord.ext import commands
import json
import os

class YourPlugin(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.config_name = "your_plugin"
        self.config_path = os.path.join("config", f"{self.config_name}.json")

        # Default configuration
        self.default_config = {
            "enabled": True,
            "setting_1": "default_value"
        }

        # Load and validate configuration
        self.config = self._load_and_validate_config()

    def _load_and_validate_config(self):
        """Manages the configuration lifecycle"""
        # Auto-Create
        if not os.path.exists(self.config_path):
            os.makedirs(os.path.dirname(self.config_path), exist_ok=True)
            with open(self.config_path, 'w') as f:
                json.dump(self.default_config, f, indent=4)
            return self.default_config

        # Load
        with open(self.config_path, 'r') as f:
            config = json.load(f)

        # Validate & Repair
        modified = False
        for key, value in self.default_config.items():
            if key not in config:
                config[key] = value
                modified = True

        if modified:
            with open(self.config_path, 'w') as f:
                json.dump(config, f, indent=4)

        return config

    @commands.command()
    async def your_command(self, ctx):
        """Command description"""
        await ctx.send("Your output here!")

async def setup(bot):
    await bot.add_cog(YourPlugin(bot))
```

### 2. Best Practices

- ✅ **Auto-Config**: The plugin must automatically create its own configuration
- ✅ **Validation**: Always validate configuration data
- ✅ **Logging**: Use logging for debugging and monitoring
- ✅ **Error Handling**: Always handle exceptions
- ✅ **Documentation**: Document commands and functions with docstrings
- ✅ **Permissions**: Implement appropriate permission checks
- ✅ **Rate Limiting**: Prevent spam and abuse

### 3. Slash Commands vs Text Commands

**Text Commands** (prefix commands):
```python
@commands.command()
async def ping(self, ctx):
    await ctx.send("Pong!")
```

**Slash Commands**:
```python
@app_commands.command(name="ping", description="Responds with Pong!")
async def ping_slash(self, interaction: discord.Interaction):
    await interaction.response.send_message("Pong!")
```

---

## ⚙️ Configuration

### Configuration Files

Each plugin automatically creates its own configuration file in `config/plugin_name.json`.

### Config Auto-Repair Example

If the configuration file is corrupted or missing fields:

```
⚙️ [ExamplePlugin] Creating default config at config/example_plugin.json...
✅ [ExamplePlugin] Config loaded and validated successfully.
```

If errors are detected:

```
⚠️ [ExamplePlugin] Missing key 'welcome_message', adding default.
❌ [ExamplePlugin] 'admin_role_id' must be an integer! Resetting to 0.
✅ [ExamplePlugin] Config repaired and saved.
```

---

## 📖 Usage

### Load a Plugin

```python
await bot.load_extension('plugins.plugin_name')
```

### Unload a Plugin

```python
await bot.unload_extension('plugins.plugin_name')
```

### Reload a Plugin

```python
await bot.reload_extension('plugins.plugin_name')
```

### Hot-Reload (during runtime)

You can implement an admin command to reload plugins without restarting the bot:

```python
@bot.command()
@commands.is_owner()
async def reload(ctx, extension):
    await bot.reload_extension(f'plugins.{extension}')
    await ctx.send(f'✅ Plugin {extension} reloaded!')
```

---

## 🤝 Contributing

Contributions, bug reports, and feature requests are welcome!

1.  Fork the project
2.  Create a branch for your feature (`git checkout -b feature/AmazingFeature`)
3.  Commit your changes (`git commit -m 'Add some AmazingFeature'`)
4.  Push to the branch (`git push origin feature/AmazingFeature`)
5.  Open a Pull Request

---

## 📄 License

This project is distributed under the MIT license. See the `LICENSE` file for more information.

---

## 🙏 Credits

Developed with ❤️ using:
- [discord.py](https://github.com/Rapptz/discord.py) - Discord bot framework
- [SQLite](https://www.sqlite.org/) - Database engine

---

<div align="center">

**[⬆ Back to top](#-flexcore-plugins)**

Made with 🔌 by Aledallas

</div>
