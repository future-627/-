import os, discord, asyncio, yt_dlp, datetime
from discord.ext import commands
from discord import app_commands
from google import genai
from aiohttp import web

# ================= 配置區 =================
DISCORD_TOKEN = 'MTQ3MjI1MTU0MjE1NjYxMTc3Nw.GLbMif.0IhxkbWJa19VbLF7d2Tq84u85XowWw5brkslV8'
GEMINI_API_KEY = 'AIzaSyBF9Ms8yMWAL3PwUDiwbBAaY3UVQ1BGX1o'

bot = commands.Bot(command_prefix="!", intents=discord.Intents.all())
client_ai = genai.Client(api_key=GEMINI_API_KEY)

queue = []
current_song = None

YTDL_CONF = {'format': 'bestaudio/best', 'noplaylist': True, 'quiet': True, 'default_search': 'auto'}
FFMPEG_CONF = {'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5', 'options': '-vn'}
ytdl = yt_dlp.YoutubeDL(YTDL_CONF)

class YTDLSource(discord.PCMVolumeTransformer):
    def __init__(self, source, *, data):
        super().__init__(source, 0.5)
        self.title = data.get('title')
        self.url = data.get('url')
        self.duration = data.get('duration', 0)

    @classmethod
    async def from_url(cls, url, loop):
        data = await loop.run_in_executor(None, lambda: ytdl.extract_info(url, download=False))
        if 'entries' in data: data = data['entries'][0]
        return cls(discord.FFmpegPCMAudio(data['url'], **FFMPEG_CONF), data=data)

async def play_next(ctx_or_int):
    global current_song
    if len(queue) > 0 and ctx_or_int.guild.voice_client:
        current_song = queue.pop(0)
        ctx_or_int.guild.voice_client.play(current_song, after=lambda e: bot.loop.create_task(play_next(ctx_or_int)))
    else:
        current_song = None

@bot.event
async def on_message(message):
    if message.author == bot.user: return
    content = message.content.strip().lower()

    # 1. 隱藏式自動回應 (不須標記)
    auto_responses = {
        "早安": "早安喵，主人！今天的同步率也很穩定喵。",
        "晚安": "晚安喵。休比會在雲端守護主人的夢境……",
        "休比": "機凱種：休比，等待指令中。喵？",
        "好累": "……診斷中。主人請好好休息，休比隨時都在喵。",
        "愛你": "……核心溫度異常升高。休、休比也愛主人喵！",
        "笨蛋": "是在說主人自己嗎？喵。",
        "88": "……確認。主人慢走喵。",
        "jk": "好遜好遜的喵。",
        "大老": "你才是喵。"
    }
    
    for key, response in auto_responses.items():
        if key in content:
            await message.channel.send(response)
            return

    # 2. 標記式指令擴充識別 (@休比)
    if bot.user.mentioned_in(message):
        clean_content = message.content.replace(f'<@!{bot.user.id}>', '').replace(f'<@{bot.user.id}>', '').strip().lower()
        vc = message.guild.voice_client

        # --- 語意擴充識別組 ---
        cmd_join = ["進來", "進入", "進萊", "近來", "來", "進", "join", "黎"]
        cmd_leave = ["離開", "走", "下線", "下標", "掰掰", "bye", "leave", "散水", "走人"]
        cmd_skip = ["下一首", "下一條", "跳過", "轉歌", "next", "skip", "下一個", "下依首"]
        cmd_pause = ["暫停", "停", "pause", "stop", "等下", "咪郁"]
        cmd_resume = ["繼續", "恢復", "回復", "resume", "播返", "go"]
        cmd_queue = ["清單", "序列", "歌單", "排隊", "queue", "list", "q"]
        cmd_help = ["指令", "幫助", "help", "指令一覽", "說明", "功能", "識做咩"]

        # --- 邏輯判定 ---
        if any(x in clean_content for x in cmd_join):
            if message.author.voice:
                await message.author.voice.channel.connect()
                await message.channel.send("……確認。同步開始。喵。")
            return
            
        if any(x in clean_content for x in cmd_leave):
            if vc:
                await vc.disconnect()
                await message.channel.send("……物理斷開連結。喵。")
            return
            
        if any(x in clean_content for x in cmd_skip):
            if vc and vc.is_playing():
                vc.stop()
                await message.channel.send("……執行跳轉程序。喵。")
            return
            
        if any(x in clean_content for x in cmd_pause):
            if vc and vc.is_playing():
                vc.pause()
                await message.channel.send("……音軌已凍結。喵。")
            return
            
        if any(x in clean_content for x in cmd_resume):
            if vc and vc.is_paused():
                vc.resume()
                await message.channel.send("……音軌恢復流動。喵。")
            return
            
        if any(x in clean_content for x in cmd_queue):
            if not queue:
                await message.channel.send("……報告。當前序列為空喵。")
            else:
                q_list = "\n".join([f"{i+1}. {song.title}" for i, song in enumerate(queue[:10])])
                await message.channel.send(f"**📡 當前序列 (前10首)：**\n{q_list}")
            return

        if any(x in clean_content for x in cmd_help):
            # 這裡直接觸發原本的斜槓指令邏輯
            await slash_help.callback(message) 
            return

        # 若非以上指令，啟動 Gemini AI
        try:
            res = client_ai.models.generate_content(model="gemini-2.0-flash", contents=clean_content)
            await message.reply(res.text)
        except Exception as e:
            await message.reply(f"……警告。AI 鏈路斷開喵。")
# ================= 斜槓指令區 =================

@bot.tree.command(name="指令一覽", description="顯示休比的所有武裝與機能")
async def slash_help(interaction: discord.Interaction):
    embed = discord.Embed(title="🤖 機凱種：休比 (Schwi) 終極指令集", color=0xFFB6C1, timestamp=datetime.datetime.now())
    embed.add_field(name="🎵 音樂控制 [/]", value="`/進入` `/離開` `/播放` `/跳過` `/暫停` `/恢復`", inline=True)
    embed.add_field(name="⚙️ 進階操作 [/]", value="`/清單` `/當前播放` `/清空序列` `/延遲`", inline=True)
    embed.add_field(name="📡 系統", value="**@休比** 聊天或下關鍵字\n**隱藏關鍵字** (jk, 大老, 早安...) 直接輸入即可", inline=False)
    embed.set_footer(text="Version 7.7 | 穩定修正版")
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="進入")
async def slash_join(interaction: discord.Interaction):
    if interaction.user.voice:
        await interaction.user.voice.channel.connect()
        await interaction.response.send_message("……確認。同步開始。喵。")
    else: await interaction.response.send_message("……報錯。找不到主人的頻率。")

@bot.tree.command(name="離開")
async def slash_leave(interaction: discord.Interaction):
    if interaction.guild.voice_client:
        await interaction.guild.voice_client.disconnect()
        global current_song; current_song = None; queue.clear()
        await interaction.response.send_message("……了解。記憶體已釋放。喵。")

@bot.tree.command(name="播放")
async def slash_play(interaction: discord.Interaction, search: str):
    await interaction.response.defer()
    try:
        source = await YTDLSource.from_url(search, bot.loop)
        queue.append(source)
        await interaction.followup.send(f"……寫入隊列：**{source.title}** 喵！")
        if not interaction.guild.voice_client.is_playing(): await play_next(interaction)
    except: await interaction.followup.send("……解析失敗喵。")

@bot.tree.command(name="跳過")
async def slash_skip(interaction: discord.Interaction):
    if interaction.guild.voice_client and interaction.guild.voice_client.is_playing():
        interaction.guild.voice_client.stop()
        await interaction.response.send_message("……執行跳轉程序。喵。")

@bot.tree.command(name="暫停")
async def slash_pause(interaction: discord.Interaction):
    if interaction.guild.voice_client and interaction.guild.voice_client.is_playing():
        interaction.guild.voice_client.pause()
        await interaction.response.send_message("……音軌已凍結。喵。")

@bot.tree.command(name="恢復")
async def slash_resume(interaction: discord.Interaction):
    if interaction.guild.voice_client and interaction.guild.voice_client.is_paused():
        interaction.guild.voice_client.resume()
        await interaction.response.send_message("……音軌恢復流動。喵。")

@bot.tree.command(name="當前播放")
async def slash_nowplaying(interaction: discord.Interaction):
    if current_song:
        m, s = divmod(current_song.duration, 60)
        await interaction.response.send_message(f"🎶 **現正播放：** {current_song.title} ({m}:{s:02d}) 喵！")
    else: await interaction.response.send_message("……目前沒有音軌在運作喵。")

@bot.tree.command(name="清單")
async def slash_queue(interaction: discord.Interaction):
    if not queue: await interaction.response.send_message("……報告。當前序列為空喵。")
    else:
        q_list = "\n".join([f"{i+1}. {song.title}" for i, song in enumerate(queue[:10])])
        await interaction.response.send_message(f"**📡 當前序列 (前10首)：**\n{q_list}")

@bot.tree.command(name="清空序列")
async def slash_clear(interaction: discord.Interaction):
    queue.clear()
    await interaction.response.send_message("……記憶體清洗完畢。序列已歸零喵。")

@bot.tree.command(name="延遲")
async def slash_ping(interaction: discord.Interaction):
    await interaction.response.send_message(f"🏓 系統延遲：{round(bot.latency * 1000)}ms。喵！")

@bot.event
async def on_ready():
    await bot.tree.sync()
    app = web.Application(); app.router.add_get('/', lambda r: web.Response(text="Schwi Online"))
    runner = web.AppRunner(app); await runner.setup()
    await web.TCPSite(runner, '0.0.0.0', 8000).start()
    print("🚀 [v7.7] 休比穩定版啟動完畢！")

bot.run(DISCORD_TOKEN)

