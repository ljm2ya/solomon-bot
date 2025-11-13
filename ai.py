from openai import OpenAI
import os
import re
from urllib.parse import urlparse
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Initialize OpenAI client with API key from environment
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

def extract_urls(text):
    """Extract URLs from text"""
    url_pattern = r'http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\\(\\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+'
    return re.findall(url_pattern, text)

def build_context_prompt(messages_by_user, user_names, urls=None):
    """Build context-aware prompt with conversation history and URLs"""
    context_parts = []

    # Add conversation context
    if messages_by_user:
        context_parts.append("RECENT CONVERSATION CONTEXT:")
        for user_id, messages in messages_by_user.items():
            user_name = user_names.get(user_id, f"User {user_id}")
            for msg in messages[-3:]:  # Last 3 messages per user for context
                context_parts.append(f"{user_name}: {msg}")
        context_parts.append("")

    # Add URL context
    if urls:
        context_parts.append("REFERENCED URLS:")
        context_parts.extend(urls)
        context_parts.append("")

    return "\n".join(context_parts)

def chat_with_context(query, context=""):
    """Chat with context grounding and conflict moderation persona"""

    system_prompt = """You are Solomon, a wise and diplomatic moderator specializing in conflict resolution and team harmony. You:

1. ANALYZE conversations for tension, misunderstandings, or conflicts
2. PROVIDE balanced perspectives that acknowledge all viewpoints
3. SUGGEST constructive solutions and common ground
4. MAINTAIN neutrality while fostering understanding
5. Use GENTLE but FIRM guidance to redirect negative patterns

When responding to Slack conversations:
- Address underlying concerns, not just surface issues
- Validate emotions while focusing on solutions
- Suggest concrete next steps for resolution
- Keep responses concise but thoughtful"""

    full_prompt = f"{context}\nUSER QUERY: {query}"

    chat_completion = client.chat.completions.create(
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": full_prompt}
        ],
        model="gpt-4o",
        temperature=0.7
    )
    return chat_completion.choices[0].message.content

def chat(query: str):
    """Basic chat function (legacy compatibility)"""
    return chat_with_context(query)

def analyze_conversation_with_context(messages_by_user: dict, user_names: dict, channel_context: dict = None) -> str:
    """
    Analyze conversation with conflict moderation and context grounding.

    Args:
        messages_by_user: Dictionary mapping user IDs to lists of their messages
        user_names: Dictionary mapping user IDs to display names
        channel_context: Additional context from multiple channels

    Returns:
        A Solomon-moderated analysis and response
    """
    if not messages_by_user:
        return "No messages found in this conversation."

    # Extract all URLs from messages
    all_urls = []
    all_messages = []

    for user_id, messages in messages_by_user.items():
        user_name = user_names.get(user_id, f"User {user_id}")
        for msg in messages:
            if msg and msg.strip():
                all_messages.append(f"{user_name}: {msg}")
                all_urls.extend(extract_urls(msg))

    # Build context
    context = build_context_prompt(messages_by_user, user_names, all_urls if all_urls else None)

    # Add channel context if available
    if channel_context:
        context += "\nMULTI-CHANNEL CONTEXT:\n"
        for channel, data in channel_context.items():
            context += f"#{channel}: {data.get('recent_activity', 'No recent activity')}\n"

    # Use conflict moderation persona
    analysis_query = """Please analyze this conversation for:
1. Any tensions, conflicts, or misunderstandings
2. Emotional undertones and group dynamics
3. Constructive ways to address concerns
4. Common ground and shared goals
5. Next steps for productive dialogue

Provide a diplomatic summary that promotes understanding."""

    return chat_with_context(analysis_query, context)

def summarize_conversation(messages_by_user: dict, user_names: dict) -> str:
    """Legacy function - now uses Solomon's conflict moderation"""
    return analyze_conversation_with_context(messages_by_user, user_names)