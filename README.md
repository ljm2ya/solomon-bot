# Solomon Bot - AI Conflict Mediator

A compact Slack bot that provides diplomatic conflict resolution and conversation analysis with multi-channel context grounding.

## Features

🤝 **Conflict Mediation**: Wise diplomatic moderator persona that analyzes tensions and suggests constructive solutions
🔍 **Multi-Channel Context**: Gathers conversation context from all accessible channels for grounded responses
📎 **URL Extraction**: Automatically detects and includes URLs from messages for enhanced context
💬 **Dual Commands**: `@mention` for full analysis or `solomon [question]` for direct chat
⚡ **Compact Code**: 112 lines of core logic with minimal dependencies

## Quick Setup

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Create .env file with your tokens
cat > .env << EOF
OPENAI_API_KEY=sk-your-openai-key
BOT_TOKEN=xoxb-your-bot-token
APP_TOKEN=xapp-your-app-token
EOF

# 3. Run bot
python main.py
```

## Slack App Configuration

**Required OAuth Scopes:**
```
app_mentions:read, channels:history, channels:read,
chat:write, reactions:read, reactions:write,
groups:read, users.read, conversations.read
```

**Event Subscriptions:** `app_mention`, `message`
**Socket Mode:** Enable for real-time events

## Usage Commands

```bash
# Add bot to channels
/invite @solomon

# Check status and accessible channels
solomon help

# Debug channel access issues
solomon debug

# Conflict analysis - mention in any conversation
@solomon

# Direct questions without @mention
solomon how should we handle this deadline conflict?
solomon what's the best approach for team communication?
```

## How It Works

1. **Multi-Channel Context**: Monitors all accessible channels for recent activity and topics
2. **URL Grounding**: Extracts URLs from messages to provide additional context
3. **Conflict Detection**: Analyzes conversations for tensions, emotional undertones, and misunderstandings
4. **Diplomatic Response**: Provides balanced perspectives and constructive solutions using Solomon persona
5. **Contextual Grounding**: Combines current conversation with broader team context

## Example Interactions

**Team Conflict Resolution:**
```
User1: This approach won't work, it's too risky
User2: We need to move fast, no time for perfect solutions
@solomon

Solomon: I see valid concerns from both perspectives. User1 raises important
risk considerations that shouldn't be dismissed, while User2 highlights
delivery pressures. Consider a phased approach: start with a minimal viable
version to address timing constraints, while building in safeguards to
mitigate the identified risks...
```

**Direct Consultation:**
```
solomon how do we handle conflicting priorities between teams?

Solomon: Conflicting priorities often reflect different success metrics.
Try: 1) Map each team's core objectives 2) Find shared goals 3) Establish
transparent communication channels 4) Create joint decision-making frameworks
5) Regular alignment check-ins. The key is shifting from competitive to
collaborative mindset...
```

## Troubleshooting

**"Monitoring 0 channels" issue:**
1. Use `/invite @solomon` in each channel
2. Check OAuth scopes include `groups:read` for private channels
3. Run `solomon debug` to see channel access status

**Missing scope errors:**
- Add required scopes in Slack App settings
- Reinstall app to workspace after scope changes

**Bot not responding:**
- Check `.env` file has correct tokens
- Verify Socket Mode is enabled
- Ensure Event Subscriptions include `app_mention` and `message`

## Architecture

**Context Grounding Flow:**
```
Message → Multi-channel scan → URL extraction → Context building → Solomon analysis → Diplomatic response
```

**Files:**
- `main.py` - Slack event handlers + multi-channel gathering (65 lines)
- `ai.py` - OpenAI integration + Solomon persona (47 lines)
- `requirements.txt` - Dependencies (3 packages)
- `.env.example` - Configuration template


