# 🤖 Friends AI Studio (vibe coded)

Fine-tune a personal AI clone of your friend based on your actual **WhatsApp** and **Discord** chat history using **QLoRA** and modern open-source LLMs (Qwen 2.5, LLaMA 3.1).

---

## ✨ Features

- 💬 **Multi-Source Chat Support**: Seamlessly combines **WhatsApp** (`.txt`) and **Discord** (`.json` or `.txt`) chat exports into a unified dataset.
- 👥 **Multi-Platform Aliases**: Matches your friend's messages even if they use different names/nicknames on WhatsApp and Discord (e.g. `Alon` and `alon_pro`).
- ⏱️ **Session Gap Detection**: Identifies breaks in conversation (e.g. 60+ minutes of inactivity) so training contexts never leak across days or unrelated topics.
- ⚡ **Local QLoRA Training**: Optimized for consumer GPUs (RTX 4080 Super / 4090 / 3090) with 4-bit quantization, gradient accumulation, and live Loss charting.
- 🌐 **Interactive Web UI**: Clean dashboard to upload chats, configure datasets, train models, chat live with your cloned persona, and export adapters for **Ollama**.

---

## 🚀 Getting Started

### 1. Requirements
- Python 3.10+
- An NVIDIA GPU with CUDA support (e.g., RTX 3060 12GB, 3080, 4080, 4090)

### 2. Installation
```bash
git clone https://github.com/yohlimem/Friends-LLM-vibe-coded-.git
cd Friends-LLM-vibe-coded-
pip install -r requirements.txt
```

### 3. Running the App
Run the startup script:
```bash
.\start_app.bat
```
Or start via Python:
```bash
python app.py
```
Open your browser at: **`http://localhost:8000`**

---

## 📥 How to Export Chats

### 🟢 1. WhatsApp Chats

#### From WhatsApp Web & WhatsApp Windows App:
1. Open the chat with your friend.
2. Click on your friend's **profile name / contact info at the very top** of the chat window.
3. In the panel that opens on the right side, scroll all the way down and click **Export chat** (ייצא צ'אט).
4. Download the range that you think is most representative of your friend
5. The `.txt` file will be downloaded directly to your PC!

#### From Mobile (iOS / Android):
1. Open the WhatsApp chat with your friend.
2. Tap the **3 dots** (Android) or the **contact name at the top** (iOS).
3. Select **More** → **Export chat** → **Without Media**.
4. Save or send the `.txt` file to your computer.

---

### 🟣 2. Discord Chats (DMs or Channels)

The easiest and fastest method is using the free, open-source tool **DiscordChatExporter**:

1. Download **`DiscordChatExporter.win-x64.zip`** (GUI version) from the [DiscordChatExporter Releases page](https://github.com/Tyrrrz/DiscordChatExporter/releases).
2. Extract and run `DiscordChatExporter.exe`.
3. Retrieve your Discord token:
   - In Discord (desktop or web at [discord.com/app](https://discord.com/app)), press <kbd>Ctrl</kbd> + <kbd>Shift</kbd> + <kbd>I</kbd> to open Developer Tools.
   - Click the **Network** tab.
   - Click on any channel or send a message.
   - Click on any request to `api/v9/...` (e.g. `messages`), look at the **Request Headers** on the right, and copy the `Authorization` token.
4. Paste the token into DiscordChatExporter.
5. Select your friend's Direct Message (DM) or server channel.
6. Click the download icon (bottom right), select format **JSON** (or **Plain Text**), and click **Export**.

---

## 🛠️ Step-by-Step Training Workflow

1. **Upload Chats (Tab 1)**: Drag and drop your WhatsApp `.txt` file, Discord `.json` file, or both at once! The app will parse and merge all messages.
2. **Select Friend & Aliases (Tab 1)**: Choose your friend's name from the dropdown. If their username is different on Discord, add their Discord handle in the **Aliases** field separated by a comma (e.g., `אלון, alon_pro`).
3. **Configure Dataset (Tab 2)**: Customize the system prompt and session gap settings, then click **Generate Dataset**.
4. **Train Model (Tab 3)**: Select your base model (recommended: `Qwen/Qwen2.5-7B-Instruct`) and start fine-tuning with live Loss tracking.
5. **Chat with Persona (Tab 4)**: Chat with your AI friend directly inside the app!
6. **Export (Tab 5)**: Download your trained LoRA adapter weights as a `.zip` or deploy to **Ollama**.
