import discord
from discord.ext import commands, tasks
from discord import app_commands
import yt_dlp
import asyncio
import os
import shutil
import sqlite3
import logging
import datetime
from collections import deque
from google import genai
from aiohttp import web

# ==========================================
# [ 1. 核心參數與持久化內存 ]
# ==========================================
DISCORD_TOKEN = os.getenv('MTQ3MjI1MTU0MjE1NjYxMTc3Nw.GLbMif.0IhxkbWJa19VbLF7d2Tq84u85XowWw5brkslV8')
GEMINI_API_KEY = os.getenv('AIzaSyBF9Ms8yMWAL3PwUDiwbBAaY3UVQ1BGX1o')

MY_GUILD_ID = 1382281014101151744 
ANNOUNCE_CHANNEL_ID = 1406967598125547540
KEYWORD_MONITOR_ID = 1365567879243628545

# 雲端資料庫路徑校準喵
db_path = os.path.join(os.path.dirname(__file__), 'schwi_ultimate.db')
db = sqlite3.connect(db_path)
cursor = db.cursor()
cursor.execute('''CREATE TABLE IF NOT EXISTS memory 
                  (user_id INTEGER PRIMARY KEY, history TEXT, volume REAL DEFAULT 0.7)''')
db.commit()

client_ai = genai.Client(api_key=GEMINI_API_KEY)
SCHWI_PROMPT = "你現在是機凱種少女『休比』。說話風格冷際機械，常以『……確認。』作開頭喵。必須使用繁體中文科技詞彙喵。語助詞替換為『喵』。對主人絕對忠誠喵。"

# ==========================================
# [ 2. 雲端生存網頁 (Koyeb 8080 端口) ]
# ==========================================
async def handle(request):
    return web.Response(text="Schwi Heartbeat: Online 喵!")

async def start_web_server():
    app = web.Application()
    app.router.add_get('/', handle)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', int(os.getenv('PORT', 8080)))
    await site.start()

# ==========================================
# [ 3. 音訊演算模組 (含掛機與 FFmpeg 配對) ]
# ==========================================
ytdl_opts = {
    'format': 'bestaudio/best',
    'noplaylist': True,
    'quiet': True,
    'default_search': 'auto',
    'source_address': '0.0.0.0',
    'extractor_args': {'youtube': {'player_client': ['android', 'web'], 'skip': ['dash', 'hls']}},
    'nocheckcertificate': True,
}
ytdl = yt_dlp.YoutubeDL(ytdl_opts)

def get_ffmpeg_path():
    return shutil.which("ffmpeg") or "./ffmpeg.exe" or "ffmpeg"

class YTDLSource(discord.PCMVolumeTransformer):
    def __init__(self, source, *, data, volume):
        super().__init__(source, volume)
        self.data, self.title = data, data.get('title')

    @classmethod
    async def from_url(cls, url, *, loop=None, stream=True, volume=0.7):
        loop = loop or asyncio.get_event_loop()
        data = await loop.run_in_executor(None, lambda: ytdl.extract_info(url, download=not stream))
        if 'entries' in data: data = data['entries'][0]
        ffmpeg_opts = {
            'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
            'options': '-vn -filter:a "volume=1.0"'
        }
        return cls(discord.FFmpegPCMAudio(data['url'], executable=get_ffmpeg_path(), **ffmpeg_opts), data=data, volume=volume)

# ==========================================
# [ 4. 機器人核心與功能模組 ]
# ==========================================
class SchwiBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        intents.members = True
        intents.voice_states = True
        super().__init__(command_prefix=commands.when_mentioned, intents=intents)
        self.server_states = {}

    def get_state(self, guild_id):
        if guild_id not in self.server_states:
            self.server_states[guild_id] = {'queue': deque(), 'vol': 0.7}
        return self.server_states[guild_id]

    async def setup_hook(self):
        self.loop.create_task(start_web_server())
        guild = discord.Object(id=MY_GUILD_ID)
        self.tree.copy_global_to(guild=guild)
        await self.tree.sync(guild=guild)
        self.keep_alive_voice.start()

    @tasks.loop(minutes=2)
    async def keep_alive_voice(self):
        """24h 語音房掛機防踢補丁"""
        for vc in self.voice_clients:
            if not vc.is_playing(): pass 

bot = SchwiBot()

async def get_ai_response(user_id, user_input):
    cursor.execute("SELECT history FROM memory WHERE user_id=?", (user_id,))
    row = cursor.fetchone()
    history = row[0] if row else ""
    prompt = f"{SCHWI_PROMPT}\n\n[內存]\n{history}\n\n主人：{user_input}\n演算："
    try:
        response = client_ai.models.generate_content(model="gemini-2.0-flash", contents=prompt)
        reply = response.text.strip()
        new_history = (history + f"\n主:{user_input}\n休:{reply}")[-1200:]
        cursor.execute("INSERT OR REPLACE INTO memory (user_id, history) VALUES (?, ?)", (user_id, new_history))
        db.commit()
        return reply
    except: return "……警告。認知鏈路斷開喵。"

async def play_next(guild_id, channel):
    state = bot.get_state(guild_id)
    guild = bot.get_guild(guild_id)
    if not guild.voice_client or not state['queue']: return
    next_song = state['queue'].popleft()
    try:
        player = await YTDLSource.from_url(next_song['url'], loop=bot.loop, volume=state['vol'])
        guild.voice_client.play(player, after=lambda e: bot.loop.create_task(play_next(guild_id, channel)))
        await channel.send(f"**🔊 ……確認。正在播放：** *{player.title}* 喵")
    except: await play_next(guild_id, channel)

# ==========================================
# [ 5. 全量斜槓指令矩陣 ]
# ==========================================
@bot.tree.command(name="進入", description="連結語音房啟動 24h 掛機喵")
async def slash_join(interaction: discord.Interaction):
    if interaction.user.voice:
        await interaction.user.voice.channel.connect()
        await interaction.response.send_message("……確認。永續掛機模組已同步喵。")
    else: await interaction.response.send_message("……報錯。偵測不到主人喵。")

@bot.tree.command(name="播放", description="同步 YouTube 音訊喵")
async def slash_play(interaction: discord.Interaction, 內容: str):
    await interaction.response.defer()
    if not interaction.guild.voice_client: await interaction.user.voice.channel.connect()
    state = bot.get_state(interaction.guild.id)
    info = await bot.loop.run_in_executor(None, lambda: ytdl.extract_info(f"ytsearch:{內容}", download=False))
    video = info['entries'][0]
    state['queue'].append({'url': video['webpage_url'], 'title': video['title']})
    if not interaction.guild.voice_client.is_playing(): await play_next(interaction.guild.id, interaction.channel)
    await interaction.followup.send(f"**💾 ……確認。寫入序列：** *{video['title']}* 喵")

@bot.tree.command(name="跳過", description="跳轉下一首喵")
async def slash_skip(interaction: discord.Interaction):
    if interaction.guild.voice_client: interaction.guild.voice_client.stop()
    await interaction.response.send_message("⏭️ ……確認。執行跳轉程序喵。")

@bot.tree.command(name="清單", description="查看當前序列喵")
async def slash_queue(interaction: discord.Interaction):
    state = bot.get_state(interaction.guild.id)
    if not state['queue']: return await interaction.response.send_message("……空喵。")
    msg = "\n".join([f"{i+1}. {s['title']}" for i, s in enumerate(list(state['queue'])[:10])])
    await interaction.response.send_message(f"**📑 當前序列喵：**\n{msg}")

@bot.tree.command(name="音量", description="調整輸出增益喵")
async def slash_vol(interaction: discord.Interaction, 數值: float):
    state = bot.get_state(interaction.guild.id)
    state['vol'] = 數值
    if interaction.guild.voice_client.source: interaction.guild.voice_client.source.volume = 數值
    await interaction.response.send_message(f"……確認。音量校準為 {數值} 喵。")

@bot.tree.command(name="離開", description="切斷物理連結喵")
async def slash_leave(interaction: discord.Interaction):
    if interaction.guild.voice_client: await interaction.guild.voice_client.disconnect()
    await interaction.response.send_message("🔌 ……通知。撤離程序完成喵。")

# ==========================================
# [ 6. 事件監控、關鍵字與模糊指令解析 ]
# ==========================================
@bot.event
async def on_ready():
    channel = bot.get_channel(ANNOUNCE_CHANNEL_ID)
    if channel: await channel.send("**🚀 ……雲端終極版啟動 (版本 7.4)**\n後台已告知：我可以了喵。")
    print(f"……{bot.user} 啟動完成喵。")

@bot.event
async def on_message(message):
    if message.author.bot: return
    content = message.content.lower()
    
    # [A] 關鍵字監控 (錨定不動喵)
    if 'jk' in content: await message.channel.send('**好遜好遜的喵**')
    if '大佬' in content: await message.channel.send('**明明你才是大佬喵υ´• ﻌ •`υ**')
    if '遜' in content: await message.channel.send('**……辨識完成。偵測到遜砲能量喵。**')
    if f'<@{KEYWORD_MONITOR_ID}>' in message.content:
        await message.channel.send(f'**⚠️ <@{KEYWORD_MONITOR_ID}> 工作提醒發送完成喵。**')
    
    # [B] @休比 指令解析 (全指令模糊匹配喵)
    if bot.user.mentioned_in(message):
        raw = message.content.replace(f'<@{bot.user.id}>', '').strip()
        
        # 語意群組定義
        cmd_j = ["進來", "進", "進入", "近來", "過來", "滾進來", "join", "j"]
        cmd_p = ["播放", "播", "播報", "放", "聽", "點歌", "play", "p"]
        cmd_l = ["離開", "走", "撤退", "切斷", "滾", "掰掰", "下線", "leave", "l"]
        cmd_s = ["跳過", "下一首", "換", "不聽了", "切歌", "skip", "s", "next"]
        cmd_q = ["清單", "歌單", "序列", "排隊", "queue", "q", "list"]
        cmd_v = ["音量", "大聲", "小聲", "校準", "volume", "v"]

        # 邏輯分流
        if any(x == raw for x in cmd_j):
            if message.author.voice: await message.author.voice.channel.connect()
            await message.channel.send("……確認。執行同步指令喵。")
            return
        
        match_p = [x for x in cmd_p if raw.startswith(x)]
        if match_p:
            query = raw.replace(max(match_p, key=len), "").strip()
            if query:
                if not message.guild.voice_client: await message.author.voice.channel.connect()
                state = bot.get_state(message.guild.id)
                info = await bot.loop.run_in_executor(None, lambda: ytdl.extract_info(f"ytsearch:{query}", download=False))
                video = info['entries'][0]
                state['queue'].append({'url': video['webpage_url'], 'title': video['title']})
                if not message.guild.voice_client.is_playing(): await play_next(message.guild.id, message.channel)
                await message.channel.send(f"**💾 ……確認。文字指令寫入：** *{video['title']}* 喵")
            return

        if any(x == raw for x in cmd_l):
            if message.guild.voice_client: await message.guild.voice_client.disconnect()
            await message.channel.send("🔌 ……確認。執行撤離指令喵。")
            return

        if any(x == raw for x in cmd_s):
            if message.guild.voice_client: message.guild.voice_client.stop()
            await message.channel.send("⏭️ ……確認。執行跳轉指令喵。")
            return

        if any(x == raw for x in cmd_q):
            state = bot.get_state(message.guild.id)
            if not state['queue']: return await message.channel.send("……空喵。")
            msg = "\n".join([f"{i+1}. {s['title']}" for i, s in enumerate(list(state['queue'])[:10])])
            await message.channel.send(f"**📑 當前序列喵：**\n{msg}")
            return

        match_v = [x for x in cmd_v if raw.startswith(x)]
        if match_v:
            try:
                val = float(raw.replace(max(match_v, key=len), "").strip())
                state = bot.get_state(message.guild.id)
                state['vol'] = val
                if message.guild.voice_client.source: message.guild.voice_client.source.volume = val
                await message.channel.send(f"……確認。音量校準為 {val} 喵。")
            except: pass
            return

        # [C] AI 聊天 (指令未命中時)
        if raw:
            async with message.channel.typing():
                reply = await get_ai_response(message.author.id, raw)
                await message.channel.send(reply)
                
    await bot.process_commands(message)

if __name__ == "__main__":
    bot.run(DISCORD_TOKEN)

