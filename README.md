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

🧠 **ReAct Intelligence**: AI-powered query analysis that determines when and where to gather context
🔍 **Smart Context Search**: 3-phase adaptive search (priority → all channels → unlimited history)
🌐 **URL Content Fetching**: Automatically fetches and summarizes GitHub READMEs and web content
📎 **Multi-Channel Grounding**: Gathers conversation context from all accessible channels
💬 **Dual Commands**: `@mention` for full conflict analysis or `solomon [question]` for direct chat
🌐 **Language Detection**: Automatically identifies language used in channels and responds appropriately

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

### AI-Powered Diplomatic Mediation
1. **Conversation Analysis**: Solomon analyzes messages for emotional undertones, tensions, and misunderstandings
2. **Context Gathering**: Uses ReAct intelligence to search relevant channels for background and history
3. **Multi-Perspective Understanding**: Identifies all viewpoints and validates each person's concerns
4. **Solution Synthesis**: Suggests constructive approaches that address underlying issues
5. **Diplomatic Communication**: Delivers guidance with wisdom, neutrality, and respect for all parties

### ReAct Grounding for Context
1. **Query Analysis**: AI determines if workspace context gathering is needed for effective mediation
2. **Smart Search**: 3-phase adaptive search strategy across conversation history
   - Phase 1: Priority channels (recent 72h)
   - Phase 2: All channels (recent 72h)
   - Phase 3: Unlimited history search (if URLs/links requested)
3. **URL Fetching**: Automatically fetches and summarizes shared resources
4. **Context Integration**: Combines channel data with fetched content for comprehensive understanding

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

**Key Components:**
- `main.py` - Slack integration + ReAct intelligence for context gathering (800+ lines)
- `ai.py` - OpenAI integration + Solomon conflict mediation persona (144 lines)
- `shell.nix` - Nix development environment with ngrok

**Solomon Persona Design:**
- **Diplomatic Core**: Wise, neutral moderator specializing in workplace conflict resolution
- **Multi-Perspective Validation**: Acknowledges all viewpoints while identifying common ground
- **Solution-Oriented**: Focuses on constructive next steps rather than blame
- **Context-Aware**: Uses comprehensive workspace history for informed mediation
- **Culturally Adaptive**: Responds in detected language with appropriate cultural communication patterns

## Language Support

**Auto-Detection**: Solomon automatically detects the primary language in conversations and responds accordingly

**Detection Process:**
1. **Conversation Analysis**: Scans recent messages for language patterns
2. **Confidence Assessment**: High/medium confidence triggers language switching
3. **Cultural Adaptation**: Adjusts diplomatic style for cultural appropriateness
4. **Fallback Protection**: Defaults to English if detection is uncertain


