# Solomon Bot - AI Conflict Mediator

A compact Slack bot that provides diplomatic conflict resolution and conversation analysis with intelligent context grounding.

## Features

🤝 **Conflict Mediation**: Wise diplomatic moderator persona that analyzes tensions and suggests constructive solutions
🧠 **ReAct Intelligence**: AI-powered query analysis that determines when and where to gather context
🔍 **Smart Context Search**: 3-phase adaptive search (priority → all channels → unlimited history)
🌐 **URL Content Fetching**: Automatically fetches and summarizes GitHub READMEs and web content
📎 **Multi-Channel Grounding**: Gathers conversation context from all accessible channels
💬 **Dual Commands**: `@mention` for full analysis or `solomon [question]` for direct chat

## Quick Setup

### Option 1: Socket Mode (Easiest)
```bash
# 1. Enter dev environment
nix-shell

# 2. Copy and configure environment
cp .env.example .env
# Edit .env with APP_TOKEN, BOT_TOKEN, OPENAI_API_KEY

# 3. Run bot
python main.py
```

### Option 2: Webhooks with ngrok
```bash
# 1. Enter dev environment
nix-shell

# 2. Start webhook server
python webhook_server.py

# 3. Expose with ngrok (new terminal)
ngrok http 3000

# 4. Configure Slack Event Subscriptions
# Use: https://your-ngrok-url.ngrok.io/slack/events
```

## Slack App Configuration

**Required OAuth Scopes:**
```
app_mentions:read, channels:history, channels:read, channels:join,
chat:write, reactions:read, reactions:write,
groups:read, users.read, conversations.read
```

**Event Subscriptions:** `app_mention`, `message`, `channel_created`
**Choose:** Socket Mode OR Webhook Events (not both)

## Usage Commands

```bash
# Basic commands
solomon help                          # Status and accessible channels
@solomon                             # Analyze conversation for conflicts

# Content analysis (with URL fetching)
solomon summarize last link's readme  # Fetch and summarize GitHub README
solomon find any github links         # Search all channels + fetch content
solomon what does that shared link do # Analyze URLs in context

# General questions (no context needed)
solomon how to handle deadline conflicts
solomon best practices for team communication
```

## How It Works

### ReAct Intelligence Pattern
1. **Query Analysis**: AI determines if context gathering is needed
2. **Smart Search**: 3-phase adaptive search strategy
   - Phase 1: Priority channels (recent 72h)
   - Phase 2: All channels (recent 72h)
   - Phase 3: Unlimited history search (if URLs/links requested)
3. **URL Fetching**: Automatically fetches and summarizes web content
4. **Context Integration**: Combines channel data with fetched content
5. **Diplomatic Response**: Solomon persona provides balanced solutions

## Example Interactions

**Smart Content Analysis:**
```
solomon can you summarize last link's readme?

🧠 Context needed: summarizing README content
🎯 Searching 4 priority channels...
✅ Found 1 URLs in 1 channels
🔍 Query requests content analysis, fetching URLs...
🌐 Fetching: https://github.com/ljm2ya/solomon-bot...
✅ Fetched 1847 chars from https://github.com/ljm2ya...

Solomon: Based on the README from the GitHub repository shared in #info:

**Solomon Bot** is an AI conflict mediator for Slack that provides diplomatic
conflict resolution. Key features include:
- ReAct intelligence for smart context gathering
- 3-phase adaptive search across all channels
- Automatic URL content fetching and summarization
- Multi-channel conversation grounding

Setup requires Slack OAuth scopes and either Socket Mode or webhook configuration
with ngrok. The bot responds to @mentions for conflict analysis and 'solomon'
commands for direct questions.
```

**Conflict Resolution with Context:**
```
User1: This approach won't work, it's too risky
User2: We need to move fast, no time for perfect solutions
@solomon

Solomon: I see valid concerns from both perspectives. User1 raises important
risk considerations that shouldn't be dismissed, while User2 highlights
delivery pressures. Based on recent discussions in #project-alpha about
similar trade-offs, consider a phased approach: start with a minimal viable
version to address timing constraints, while building in safeguards to
mitigate the identified risks...
```

## Troubleshooting

**Bot not responding in new channels:**
- Solution: Use webhook mode with Event Subscriptions instead of Socket Mode
- Or manually `/invite @solomon` in each channel for Socket Mode

**URL verification failed in ngrok:**
- Ensure both `webhook_server.py` is running AND ngrok is exposing port 3000
- Check Slack Event Subscriptions URL: `https://your-ngrok-url.ngrok.io/slack/events`

**Missing scope errors:**
- Add required OAuth scopes in Slack App settings
- Reinstall app to workspace after scope changes

**ReAct search not finding content:**
- Content may be older than 72-hour limit
- Try specific queries like "find github links" to trigger unlimited search
- Check channel permissions with `solomon help`

## Architecture

**Enhanced ReAct Flow:**
```
Query → AI Analysis → Smart Search (3-phase) → URL Fetching → Context Integration → Solomon Response
```

**Files:**
- `webhook_server.py` - Main webhook server with ReAct intelligence (800+ lines)
- `main.py` - Legacy Socket Mode server (500+ lines)
- `ai.py` - OpenAI integration + Solomon persona (121 lines)
- `shell.nix` - Nix development environment with ngrok
- `WEBHOOK_SETUP.md` - Detailed webhook configuration guide


