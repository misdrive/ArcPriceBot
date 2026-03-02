import os
import re
import json
import asyncio
import pathlib
import discord
from discord.ext import commands, tasks
from discord import app_commands, ui
from playwright.async_api import async_playwright
from dotenv import load_dotenv

load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN").strip() if os.getenv("DISCORD_TOKEN") else None

# ── PERMISSIONS LOGIC ──
auth_raw = os.getenv("AUTHORIZED_USERS", "")
AUTHORIZED_IDS = [int(uid.strip()) for uid in auth_raw.split(",") if uid.strip().isdigit()]

THEME_COLOR = 0xBF9DA4 
BASE_DIR = pathlib.Path(__file__).parent.resolve()
ALIAS_FILE = BASE_DIR / "aliases.json"
LINKS_FILE = BASE_DIR / "links.txt"
PRICE_ARCHIVE = BASE_DIR / "prices.txt"

# ── DATA HANDLING ──────────────────────────────────────────────────
def load_aliases():
    if ALIAS_FILE.exists():
        try:
            with open(ALIAS_FILE, "r") as f: return json.load(f)
        except: return {}
    return {}

def save_alias(trigger, slug):
    aliases = load_aliases()
    aliases[trigger.lower().strip()] = slug.lower().strip()
    with open(ALIAS_FILE, "w") as f: json.dump(aliases, f, indent=4)

def load_links_from_file():
    """Returns a dict of categories and their lists of links."""
    if not LINKS_FILE.exists():
        LINKS_FILE.write_text("")
        return {}
    
    categories = {}
    current_cat = "General"
    with open(LINKS_FILE, "r") as f:
        for line in f:
            line = line.strip()
            if not line: continue
            if line.startswith("[") and line.endswith("]"):
                current_cat = line[1:-1]
                continue
            if "metaforge.app" in line.lower():
                if current_cat not in categories: categories[current_cat] = []
                categories[current_cat].append(line)
    return categories

def get_archived_price(slug):
    if not PRICE_ARCHIVE.exists(): return None
    with open(PRICE_ARCHIVE, "r") as f:
        for line in f:
            if line.startswith(f"{slug}:"):
                try: return int(line.split(":")[1].strip())
                except: continue
    return None

def update_price_archive(slug, price):
    prices = {}
    if PRICE_ARCHIVE.exists():
        with open(PRICE_ARCHIVE, "r") as f:
            for line in f:
                if ":" in line:
                    parts = line.strip().split(":")
                    prices[parts[0]] = parts[1]
    prices[slug] = str(price)
    with open(PRICE_ARCHIVE, "w") as f:
        for k, v in prices.items():
            f.write(f"{k}:{v}\n")

# ── UI COMPONENTS ──────────────────────────────────────────────────
class AliasModal(ui.Modal, title='Neural Link Configuration'):
    trigger = ui.TextInput(label='Shorthand', placeholder='e.g. bp', min_length=1)
    slug = ui.TextInput(label='Metaforge Slug', placeholder='e.g. tempest-i-recipe', min_length=1)

    async def on_submit(self, interaction: discord.Interaction):
        save_alias(str(self.trigger), str(self.slug))
        await interaction.response.send_message(f"✅ Linked: **{self.trigger}** ➔ **{self.slug}**", ephemeral=True)

# ── BOT CORE ───────────────────────────────────────────────────────
class ArcRaidersBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True 
        super().__init__(command_prefix="!", intents=intents, help_command=None)
        self.playwright = None
        self.browser = None
        self.context = None

    async def setup_hook(self):
        self.playwright = await async_playwright().start()
        self.browser = await self.playwright.chromium.launch(headless=True)
        self.context = await self.browser.new_context(user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36")
        self.update_prices_loop.start()
        await self.tree.sync()
        print(f"✅ {self.user} Online | Auto-updating with Categories")

    @tasks.loop(minutes=5)
    async def update_prices_loop(self):
        print("🔄 Background Update: Refreshing prices...")
        cat_data = load_links_from_file()
        slugs = []
        for links in cat_data.values():
            slugs.extend([u.split("/")[-1] for u in links])
        
        aliases = load_aliases()
        slugs.extend(aliases.values())
        slugs = list(set(slugs))

        for slug in slugs:
            url = f"https://metaforge.app/arc-raiders/database/item/{slug}"
            page = await self.context.new_page()
            try:
                await page.goto(url, wait_until="domcontentloaded", timeout=15000)
                content = await page.inner_text("body")
                match = re.search(r"([\d,]+)\s*Seeds", content, re.IGNORECASE)
                if match:
                    price = int(match.group(1).replace(",", ""))
                    update_price_archive(slug, price)
                await asyncio.sleep(2)
            except Exception as e:
                print(f"⚠️ Failed background scrape for {slug}: {e}")
            finally:
                await page.close()
        print("✅ Background Update: Prices synchronized.")

bot = ArcRaidersBot()

# ── FEATURE 1: VALUE COMMAND ───────────────────────────────────────
@bot.tree.command(name="value", description="Instantly look up item value from local cache.")
@app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
@app_commands.allowed_installs(guilds=True, users=True)
async def value(interaction: discord.Interaction, item: str):
    aliases = load_aliases()
    item_slug = aliases.get(item.lower(), item.lower().replace(" ", "-"))
    url = f"https://metaforge.app/arc-raiders/database/item/{item_slug}"
    
    seeds = get_archived_price(item_slug)
    
    if seeds:
        display_title = item_slug.replace("-", " ").title()
        if "-i-recipe" in item_slug.lower():
            display_title = display_title.replace("I Recipe", "Blueprint").replace(" i Recipe", " Blueprint")
            
        embed = discord.Embed(title=f"📊 {display_title}", url=url, color=THEME_COLOR)
        embed.add_field(name="Market Value", value=f"💰 **{seeds:,} Seeds**", inline=True)
        embed.add_field(name="Stash Value", value=f"💵 **${seeds*100:,}**", inline=True)
        embed.set_footer(text="Data updated automatically every 5 minutes")
        
        await interaction.response.send_message(embed=embed)
    else:
        await interaction.response.send_message(f"❌ No data found for `{item_slug}`. Pending next update.", ephemeral=True)

# ── FEATURE 2: ALIAS SYSTEM ────────────────────────────────────────
@bot.tree.command(name="alias", description="[AUTH ONLY] Create a shorthand for a Metaforge slug.")
@app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
@app_commands.allowed_installs(guilds=True, users=True)
async def alias(interaction: discord.Interaction):
    if interaction.user.id not in AUTHORIZED_IDS:
        return await interaction.response.send_message("⚠️ Unauthorized.", ephemeral=True)
    await interaction.response.send_modal(AliasModal())

@bot.tree.command(name="aliases", description="Display all saved shorthands.")
@app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
@app_commands.allowed_installs(guilds=True, users=True)
async def aliases_list(interaction: discord.Interaction):
    aliases = load_aliases()
    if not aliases: return await interaction.response.send_message("📭 Archive empty.", ephemeral=True)
    manifest = "```ascii\nSHORTHAND    | SLUG\n" + "─" * 25 + "\n"
    for k, v in dict(sorted(aliases.items())).items(): manifest += f"{k:<12} | {v}\n"
    manifest += "```"
    embed = discord.Embed(title="📂 Neural Manifest", color=THEME_COLOR)
    embed.add_field(name="Active Links", value=manifest)
    await interaction.response.send_message(embed=embed)

# ── FEATURE 3: LIST SYSTEM (CATEGORIZED) ───────────────────────────
@bot.tree.command(name="list", description="Show values categorized by links.txt headers.")
@app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
@app_commands.allowed_installs(guilds=True, users=True)
async def list_items(interaction: discord.Interaction):
    categories = load_links_from_file()
    if not categories:
        return await interaction.response.send_message("📭 `links.txt` is empty.")

    embeds = []
    for category_name, urls in categories.items():
        results = []
        for url in urls:
            item_slug = url.split("/")[-1]
            seeds = get_archived_price(item_slug)
            
            name_val = item_slug.replace("-", " ").title()
            if "-i-recipe" in item_slug.lower():
                name_val = name_val.replace("I Recipe", "Blueprint").replace(" i Recipe", " Blueprint")
                
            if seeds:
                results.append(f"**{name_val}**\n💰 {seeds:,} Seeds | 💵 ${seeds*100:,}")
            else:
                results.append(f"❌ **{name_val}** (Pending)")
        
        embed = discord.Embed(title=f"📋 {category_name}", color=THEME_COLOR)
        embed.description = "\n\n".join(results)
        embeds.append(embed)

    # Discord allows sending up to 10 embeds in one message
    await interaction.response.send_message(embeds=embeds[:10])

bot.run(TOKEN)