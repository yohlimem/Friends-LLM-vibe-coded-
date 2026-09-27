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

The recommended tool for exporting Discord chats is the free, open-source **[DiscordChatExporter](https://github.com/Tyrrrz/DiscordChatExporter)**:

1. Download **`DiscordChatExporter.win-x64.zip`** (GUI version) from the [Releases page](https://github.com/Tyrrrz/DiscordChatExporter/releases).
2. Extract the archive and launch `DiscordChatExporter.exe`.

> 💡 **Tip:** When using the DiscordChatExporter GUI, simply follow the visual guide and prompts inside the application itself — it is often the simplest and most up-to-date method!

> ⚠️ **Important Warnings (from DiscordChatExporter):**
> - **Do not share your token!** A token grants full access to your Discord account. If your token is ever exposed, change your Discord account password immediately to reset it.
> - **Terms of Service:** Automating user accounts violates Discord's Terms of Service and carries a risk of account termination. Use at your own risk.

#### How to Fetch Your Discord User Token:

- **Method 1: Browser Console (Fastest)**
  1. Open [discord.com](https://discord.com) in your web browser and log in.
  2. Press <kbd>Ctrl</kbd> + <kbd>Shift</kbd> + <kbd>I</kbd> (<kbd>⌥</kbd> + <kbd>⌘</kbd> + <kbd>I</kbd> on macOS) to open Developer Tools.
  3. Go to the **Console** tab, paste the following line, and press <kbd>Enter</kbd>:
     ```javascript
     let m;webpackChunkdiscord_app.push([[Math.random()],{},e=>{for(let i in e.c){let x=e.c[i];if(x?.exports?.getToken){m=x;break}}}]);m&&console.log("Token:",m.exports.getToken());
     ```
  4. Copy your token from the output.

- **Method 2: Network Monitor (Alternative)**
  1. In DevTools, switch to the **Network** tab and refresh the page (<kbd>F5</kbd>).
  2. In the **Filter** box, type `messages` and select any matching request (click a chat if none appear).
  3. Under the **Headers** tab, locate `authorization:` in the request headers and copy its value.

#### Exporting the Chat:
3. Paste your token into DiscordChatExporter.
4. Select your friend's Direct Message (DM) or server channel.
5. Click the download icon (bottom right), select format **JSON** (or **Plain Text**), and click **Export**.

---

## 🛠️ Step-by-Step Training Workflow

1. **Upload Chats (Tab 1)**: Drag and drop your WhatsApp `.txt` file, Discord `.json` file, or both at once! The app will parse and merge all messages.
2. **Assign Participant Roles (Tab 1)**: For each person found in the chats, choose their role:
   - **🤖 Friend (AI)**: The persona the AI will learn to imitate and speak like (supports multiple aliases/handles across platforms).
   - **👤 Me (User)**: The conversational partner(s) whose questions and messages the AI learns to respond to.
   - **⚪ Ignore**: Non-relevant or third-party participants whose messages will be filtered out.
3. **Configure Dataset (Tab 2)**: Customize the system prompt and session gap settings, then click **Generate Dataset**.
4. **Train Model (Tab 3)**: Select your base model (recommended: `Qwen/Qwen2.5-7B-Instruct`) and start fine-tuning with live Loss tracking.
5. **Chat with Persona (Tab 4)**: Chat with your AI friend directly inside the app!
6. **Export (Tab 5)**: Download your trained LoRA adapter weights as a `.zip` or deploy to **Ollama**.
