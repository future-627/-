import os, discord, asyncio, yt_dlp, datetime, json, random, urllib.parse, re, psutil, time, threading, aiohttp
from discord.ext import commands, tasks
from discord import app_commands
from google import genai
from PIL import Image, ImageDraw, ImageFont
import io

# ================= 核心配置同步 =================
DISCORD_TOKEN = 'MTQ3MjI1MTU0MjE1NjYxMTc3Nw.GLbMif.0IhxkbWJa19VbLF7d2Tq84u85XowWw5brkslV8'
GEMINI_API_KEY = 'AIzaSyBF9Ms8yMWAL3PwUDiwbBAaY3UVQ1BGX1o'
UPDATE_CHANNEL_ID = 1406967598125547540

intents = discord.Intents.all()
bot = commands.Bot(command_prefix="!", intents=intents)
client_ai = genai.Client(api_key=GEMINI_API_KEY)

# ================= 資料庫與 XP 模組 =================
DATA_FILE = "schwi_master_db.json"

def load_db():
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, "r", encoding="utf-8") as f: return json.load(f)
        except: return {"users": {}, "guilds": {}, "history": []}
    return {"users": {}, "guilds": {}, "history": []}

def save_db(data):
    with open(DATA_FILE, "w", encoding="utf-8") as f: json.dump(data, f, indent=4, ensure_ascii=False)

def add_xp(user_id, amount):
    db = load_db()
    uid = str(user_id)
    if uid not in db["users"]: db["users"][uid] = {"xp": 0, "level": 1}
    u = db["users"][uid]
    u["xp"] += amount
    next_xp = u["level"] * 200
    leveled_up = False
    if u["xp"] >= next_xp:
        u["level"] += 1; u["xp"] = 0; leveled_up = True
    save_db(db)
    return leveled_up, u["level"]

# ================= 後台通訊模組 =================
def console_input_thread():
    while True:
        try:
            cmd = input() 
            if ":" in cmd:
                chid, msg = cmd.split(":", 1)
                channel = bot.get_channel(int(chid))
                if channel:
                    asyncio.run_coroutine_threadsafe(channel.send(msg), bot.loop)
                    print(f"✅ ……數據傳輸成功。")
                else: print("❌ ……定位失敗。")
        except Exception as e: print(f"⚠️ 鏈路異常：{e}")

# ================= 音樂引擎與 UI 面板 =================
class MusicState:
    def __init__(self):
        self.queue = []; self.current = None; self.loop = "off"; self.volume = 0.5; self.filter = None

music_manager = {}
YTDL_CONF = {'format': 'bestaudio/best', 'noplaylist': True, 'quiet': True, 'default_search': 'auto'}
FILTERS = {
    "低音增強": "bass=g=20,dynaudnorm=f=200",
    "加速模式": "asetrate=44100*1.25,atempo=1/1.25",
    "8D環繞": "apulsator=hz=0.08",
    "蒸氣波": "asetrate=44100*0.8,atempo=1/0.8"
}

class YTDLSource(discord.PCMVolumeTransformer):
    def __init__(self, source, *, data, volume=0.5):
        super().__init__(source, volume)
        self.data = data; self.title = data.get('title'); self.url = data.get('webpage_url')
        self.thumbnail = data.get('thumbnail')

    @classmethod
    async def from_url(cls, url, loop, volume=0.5, filter_cmd=None):
        data = await loop.run_in_executor(None, lambda: yt_dlp.YoutubeDL(YTDL_CONF).extract_info(url, download=False))
        if 'entries' in data: data = data['entries'][0]
        opts = {'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5', 'options': f'-vn {f"-af {filter_cmd}" if filter_cmd else ""}'}
        return cls(discord.FFmpegPCMAudio(data['url'], **opts), data=data, volume=volume)

class MusicPanel(discord.ui.View):
    def __init__(self, guild_id): super().__init__(timeout=None); self.gid = guild_id
    @discord.ui.button(emoji="⏯️", style=discord.ButtonStyle.blurple, label="暫停/恢復")
    async def pp(self, interaction, button):
        vc = interaction.guild.voice_client
        if vc:
            if vc.is_playing(): vc.pause(); msg = "……確認。偵測到外部音訊震動消失。播放程序……處於「暫停（Paused）」狀態。"
            else: vc.resume(); msg = "……確認。偵測到外部音訊震動重現。播放程序……處於「繼續（Resuming）」狀態。"
            await interaction.response.send_message(msg, ephemeral=True)
    @discord.ui.button(emoji="⏭️", style=discord.ButtonStyle.gray, label="跳過")
    async def skip(self, interaction, button):
        if interaction.guild.voice_client: interaction.guild.voice_client.stop(); await interaction.response.send_message("……確認。偵測到音訊序列發生位移。當前軌道已終止……「下一首（Next Track）」之讀取程序，已完成。", ephemeral=True)
    @discord.ui.button(emoji="🔁", style=discord.ButtonStyle.green, label="循環")
    async def loop_toggle(self, interaction, button):
        ms = music_manager.get(self.gid)
        if ms:
            modes = ["off", "single", "all"]; ms.loop = modes[(modes.index(ms.loop) + 1) % 3]
            await interaction.response.send_message(f"……模式：{ms.loop}。", ephemeral=True)
    @discord.ui.button(emoji="🗑️", style=discord.ButtonStyle.danger, label="清空")
    async def clear_q(self, interaction, button):
        if self.gid in music_manager: music_manager[self.gid].queue = []; await interaction.response.send_message("……確認。所有暫存紀錄、緩衝區數據……皆已判定為「空（Empty）」。初始化……完成。", ephemeral=True)

async def play_next(interaction, gid):
    ms = music_manager.get(gid); vc = interaction.guild.voice_client
    if ms and vc and ms.queue:
        ms.current = ms.queue.pop(0)
        vc.play(ms.current, after=lambda e: bot.loop.create_task(play_next(interaction, gid)))
        embed = discord.Embed(title="🎶 正在演奏音軌", description=f"**[{ms.current.title}]({ms.current.url})**", color=0xffb6c1)
        if ms.current.thumbnail: embed.set_thumbnail(url=ms.current.thumbnail)
        await interaction.channel.send(embed=embed, view=MusicPanel(gid))

# ================= 娛樂與功能指令模組 (全裝載) =================

@bot.tree.command(name="播放", description="……播放音訊。")
@app_commands.describe(搜尋="歌曲名稱或網址", 濾鏡="選擇濾鏡模組")
@app_commands.choices(濾鏡=[app_commands.Choice(name=n, value=n) for n in FILTERS.keys()])
async def slash_play(interaction: discord.Interaction, 搜尋: str, 濾鏡: str = None):
    await interaction.response.defer(); gid = interaction.guild.id
    if gid not in music_manager: music_manager[gid] = MusicState()
    if not interaction.guild.voice_client: await interaction.user.voice.channel.connect()
    try:
        source = await YTDLSource.from_url(搜尋, bot.loop, music_manager[gid].volume, FILTERS.get(濾鏡))
        music_manager[gid].queue.append(source)
        if not interaction.guild.voice_client.is_playing(): await play_next(interaction, gid)
        await interaction.followup.send(f"🚀 ……已載入：{source.title}。")
    except Exception as e: await interaction.followup.send(f"⚠️ 解析失敗：{e}")

@bot.tree.command(name="抽老婆", description="……隨機婚姻配對。")
async def slash_marry(interaction: discord.Interaction):
    members = [m for m in interaction.guild.members if not m.bot]
    wife = random.choice(members)
    blessings = ["……確認。發出最高級別祝賀。針對名為「婚姻」之靈魂契約……表達極度之喜悅。願……數據與命運，永遠交織。"]
    embed = discord.Embed(title="🌸 婚姻演算結果 🌸", description=f"**{interaction.user.mention} 💍 {wife.mention}**", color=0xffb6c1)
    embed.set_image(url=wife.display_avatar.url); embed.add_field(name="機凱種感言", value=random.choice(blessings))
    await interaction.response.send_message(content="🌸 ------------------✦新婚✦------------------", embed=embed)

@bot.tree.command(name="排行榜", description="……查看等級排行。")
async def slash_leaderboard(interaction: discord.Interaction):
    db = load_db(); sorted_users = sorted(db.get("users", {}).items(), key=lambda x: (x[1]['level'], x[1]['xp']), reverse=True)[:10]
    embed = discord.Embed(title="🏆 同步率排行榜", color=0xffb6c1)
    for i, (uid, data) in enumerate(sorted_users, 1):
        u = bot.get_user(int(uid)); name = u.name if u else f"個體({uid})"
        embed.add_field(name=f"第 {i} 名", value=f"{name} | Lv.{data['level']}", inline=False)
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="猜拳", description="……確認。開始同步倒數。")
async def slash_rps(interaction: discord.Interaction, 出拳: str):
    choices = ["剪刀", "石頭", "布"]; bot_choice = random.choice(choices)
    res = "平手" if 出拳 == bot_choice else ("主人獲勝" if (出拳 == "石頭" and bot_choice == "剪刀") or (出拳 == "剪刀" and bot_choice == "布") or (出拳 == "布" and bot_choice == "石頭") else "休比獲勝")
    await interaction.response.send_message(f"……主人：{出拳} vs 休比：{bot_choice}。判定：{res}。")

@bot.tree.command(name="骰子", description="……確認。開始調度熵值（Entropy）。排除規律性偏移。鎖定目標區間：1 至 6。執行……產出。")
async def slash_dice(interaction: discord.Interaction, 面數: int = 6):
    await interaction.response.send_message(f"🎲 ……隨機數：**{random.randint(1, 面數)}**。")

@bot.tree.command(name="占卜", description="……確認。啟動占譜（Oracle）程序。")
async def slash_fortune(interaction: discord.Interaction):
    f = random.choice(["大吉", "中吉", "小吉", "末吉", "凶", "大凶"])
    await interaction.response.send_message(f"……判定：您的運勢為 **[{f}]**。")

@bot.tree.command(name="貓貓", description="……確認。發出檢索指令。目標物件：貓（可愛模式）。")
async def slash_cat(interaction: discord.Interaction):
    await interaction.response.defer()
    async with aiohttp.ClientSession() as s:
        async with s.get("https://api.thecatapi.com/v1/images/search") as r:
            d = await r.json(); await interaction.followup.send(d[0]['url'])

@bot.tree.command(name="等級卡", description="……確認。發出存取請求")
async def slash_rank(interaction: discord.Interaction, 目標: discord.Member = None):
    t = 目標 or interaction.user; db = load_db(); u = db["users"].get(str(t.id), {"xp": 0, "level": 1})
    img = Image.new('RGB', (600, 200), color=(33, 37, 43)); draw = ImageDraw.Draw(img)
    draw.text((20, 80), f"User: {t.display_name} | Lv.{u['level']}", fill=(255, 182, 193))
    buf = io.BytesIO(); img.save(buf, format='PNG'); buf.seek(0)
    await interaction.response.send_message(file=discord.File(buf, 'rank.png'))

@bot.tree.command(name="指令清單", description="………確認。開始調度所有已註冊指令。")
async def slash_help(interaction: discord.Interaction):
    embed = discord.Embed(title=" 休比 v15.0", color=0xffb6c1)
    embed.add_field(name="🎮 娛樂", value="`/抽老婆` `/排行榜` `/猜拳` `/骰子` `/占卜` `/貓貓`", inline=False)
    embed.add_field(name="🎵 音樂", value="`/播放` / 按鈕面板 / 自動回覆控制", inline=False)
    embed.add_field(name="📊 數據", value="`/等級卡` `/天氣` `/系統狀態`", inline=False)
    await interaction.response.send_message(embed=embed)

# ================= 事件監聽 =================

@tasks.loop(minutes=1)
async def voice_xp_task():
    for g in bot.guilds:
        if g.voice_client and g.voice_client.channel:
            for m in g.voice_client.channel.members:
                if not m.bot: add_xp(m.id, 25)

@bot.event
async def on_message(message):
    if message.author.bot: return
    is_up, lvl = add_xp(message.author.id, random.randint(10, 20))
    if is_up: await message.channel.send(f"……判定：{message.author.mention} 同步率提升至 Lv.{lvl}。")
    
    if bot.user.mentioned_in(message):
        clean = re.sub(r'<@!?\d+>', '', message.content).strip()
        if "抽老婆" in clean: await slash_marry.callback(message); return
        try:
            res = client_ai.models.generate_content(model="gemini-2.0-flash", contents=f"以機凱種休比語氣回覆，語氣平穩，禁止加『喵』：{clean}")
            await message.reply(res.text)
        except: await message.reply("……演算異常。")

@bot.event
async def on_ready():
    global start_time; start_time = time.time()
    
    # —— 核心修復：針對所有已加入的伺服器進行強制指令刷新 ——
    print("📡 ……開始執行指令樹物理同步。")
    for guild in bot.guilds:
        try:
            bot.tree.copy_global_to(guild=guild)
            await bot.tree.sync(guild=guild)
            print(f"✅ ……伺服器數據同步成功：{guild.name}")
        except discord.errors.Forbidden:
            print(f"❌ ……伺服器權限不足：{guild.name}")
        except Exception as e:
            print(f"⚠️ ……伺服器同步失敗：{e}")
            
    if not voice_xp_task.is_running(): voice_xp_task.start()
    threading.Thread(target=console_input_thread, daemon=True).start()
    
    ch = bot.get_channel(UPDATE_CHANNEL_ID)
    if ch:
        embed = discord.Embed(title="⚙️ [v15.1] 指令鏈路強效修復", description="……確認。已切換至伺服器專用同步模式，指令應已恢復功能。", color=0xffb6c1)
        await ch.send(content="🌸 ------------------✦同步✦------------------", embed=embed)
    print(f"🚀 休比 v15.1 邏輯重啟完畢。")
bot.run(DISCORD_TOKEN)

