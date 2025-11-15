# Solomon Bot - AI Conflict Mediator for Slack

**🤝 Proactive Conversational Conflict Moderator**

Solomon Bot serves as your team's diplomatic mediator, automatically analyzing Slack conversations for tensions, misunderstandings, and conflicts. Using advanced AI reasoning and comprehensive context gathering, it provides balanced perspectives and constructive solutions to maintain team harmony.

## Core Conflict Moderation Capabilities

🤝 **Diplomatic Analysis**: Identifies tensions, misunderstandings, and communication breakdowns in real-time  
⚖️ **Balanced Mediation**: Provides neutral perspectives that acknowledge all viewpoints while fostering understanding  
🎯 **Solution-Oriented**: Suggests concrete next steps and common ground to resolve workplace conflicts  
🧠 **Context-Aware Intelligence**: Uses ReAct reasoning to gather comprehensive conversation history across all channels  
🔍 **Proactive Monitoring**: Automatically analyzes conversations when tagged to prevent conflicts from escalating  
💬 **Team Harmony Focus**: Maintains workplace relationships through gentle but firm diplomatic guidance  
🌐 **Multi-Language Support**: Automatically detects conversation language and responds in the same language for cultural alignment  

## Technical Features

🧠 **ReAct Architecture**: Reasoning-Acting loop determines context needs, executes search, integrates findings
🔍 **3-Phase Context Search**: Priority channels (72h) → All channels (72h) → Unlimited history + URL fetch
🌐 **Agentic URL Processing**: Autonomous GitHub README/web content extraction with summarization
📎 **Multi-Channel Indexing**: Message aggregation across accessible channels with relevance scoring
💬 **Dual Interface**: `@mention` triggers conversation analysis, `solomon [query]` enables direct interaction
🌐 **Language Detection**: Pattern matching + OpenAI classification with confidence-based switching  

## Quick Setup

```bash
# 1. Copy and configure environment
cp .env.example .env
# Edit .env with APP_TOKEN, BOT_TOKEN, OPENAI_API_KEY

# 2. Run bot
python main.py
```

### For Event Subscriptions (new channels support)
```bash
# Install ngrok: https://ngrok.com/download
# Run bot with ngrok:
python main.py  # terminal 1
ngrok http 3000  # terminal 2

# Configure Slack Event Subscriptions:
# URL: https://your-ngrok-url.ngrok.io/slack/events
# Events: app_mention, message.channels, channel_created
```

## Slack App Configuration

**Required OAuth Scopes:**
```
app_mentions:read, channels:history, channels:read, channels:join,
chat:write, reactions:read, reactions:write,
groups:read, users.read, conversations.read
```

**Event Subscriptions:** `app_mention`, `message.channels`, `channel_created`

## Conflict Moderation Commands

```bash
# Primary conflict analysis
@solomon                             # Analyze current conversation for tensions and conflicts
@solomon analyze this thread         # Deep analysis of specific discussion thread

# Workplace harmony support
solomon help mediate this conflict   # Request diplomatic intervention
solomon how to handle deadline conflicts        # Get guidance on specific conflict types
solomon best practices for team communication   # Proactive conflict prevention advice
solomon suggest meeting agenda       # Structure difficult conversations

# Context gathering (supports conflict analysis)
solomon summarize last link's readme # Fetch and analyze shared resources
solomon find any github links        # Search all channels for technical context
solomon what does that shared link do # Analyze URLs for project context
solomon help                         # Status and accessible channels
```

## How Conflict Moderation Works

### ReAct (Reasoning + Acting) Pipeline
1. **Query Analysis**: LLM classifies user intent and determines context requirements using keyword extraction
2. **Action Planning**: Selects search scope (priority channels/all channels/unlimited) based on query type
3. **Context Execution**: Parallel message retrieval, URL detection, and content fetching via HTTP requests
4. **Information Integration**: Aggregates channel data, URL summaries, and user history into structured context
5. **Response Generation**: GPT-4o processes integrated context using Solomon persona for conflict-aware output

### Solomon Persona Architecture
1. **System Prompt**: Diplomatic moderator specializing in conflict resolution with direct Slack data access
2. **Response Adaptation**: Language detection triggers culturally appropriate communication patterns
3. **Conflict Analysis**: Identifies tensions, emotional undertones, and misunderstandings in conversation threads
4. **Solution Framework**: Validates all perspectives while suggesting concrete resolution steps
5. **Context Grounding**: References specific channels, users, and shared URLs for informed mediation

## Troubleshooting

**Bot not responding in new channels:**
- Solution: Configure Event Subscriptions with ngrok (see setup above)
- Or manually `/invite @solomon` in each channel

**URL verification failed in ngrok:**
- Ensure bot is running AND ngrok is exposing port 3000
- Check Slack Event Subscriptions URL: `https://your-ngrok-url.ngrok.io/slack/events`
- Verify challenge parameter response in bot logs

**Missing scope errors:**
- Add required OAuth scopes in Slack App settings
- Reinstall app to workspace after scope changes

**ReAct search not finding content:**
- Content may be older than 72-hour limit
- Try specific queries like "find github links" to trigger unlimited search
- Check channel permissions with `solomon help`

## Architecture

**Conflict Mediation Pipeline:**
```
Conversation → Tension Analysis → Context Gathering → Multi-Perspective Understanding → Diplomatic Solution → Team Harmony
```

**Technical Flow:**
```
Query → AI Analysis → Smart Search (3-phase) → URL Fetching → Context Integration → Solomon Response
```

**Implementation:**
- `main.py` - Flask webhook + Socket Mode integration, ReAct query analysis, 3-phase context search (800+ lines)
- `ai.py` - OpenAI client wrapper, language detection algorithms, Solomon persona system prompt (320+ lines)
- `shell.nix` - Nix environment with ngrok tunneling for Event Subscriptions

**Technical Architecture:**
- **ReAct Loop**: Query → Intent Classification → Scope Selection → Data Retrieval → Context Integration → Response
- **Language Detection**: Regex patterns + OpenAI classification with confidence thresholds (high/medium/low)
- **URL Processing**: HTTP requests to GitHub/web APIs with content extraction and summarization
- **Context Indexing**: Message aggregation with timestamp filtering and relevance scoring
- **Persona Implementation**: System prompt engineering with dynamic language adaptation

## Language Support

**Detection Algorithm**: Regex pattern matching for character sets (Korean/Japanese/Chinese) + OpenAI classification for Latin scripts

**Implementation Process:**
1. **Message Preprocessing**: URL/mention removal, text cleaning for classification accuracy
2. **Dual Detection**: Pattern matching (high accuracy) + LLM classification (fallback) with confidence scoring
3. **Persona Adaptation**: Dynamic system prompt modification for language-specific cultural communication norms
4. **Fallback Logic**: English default when confidence below medium threshold or classification errors


