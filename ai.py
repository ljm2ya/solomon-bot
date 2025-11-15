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

def detect_conversation_language(messages_by_user, user_names):
    """
    Detect the primary language used in recent conversation messages.

    Args:
        messages_by_user: Dictionary mapping user IDs to lists of their messages
        user_names: Dictionary mapping user IDs to display names

    Returns:
        Tuple of (detected_language_code, detected_language_name, confidence)
    """
    try:
        # Collect all recent messages for language detection
        all_text = []
        for user_id, messages in messages_by_user.items():
            for msg in messages[-5:]:  # Use last 5 messages per user for detection
                if msg and msg.strip():
                    # Remove URLs and mentions for cleaner language detection
                    cleaned_msg = re.sub(r'http[s]?://\S+', '', msg)
                    cleaned_msg = re.sub(r'<@\w+>', '', cleaned_msg)
                    cleaned_msg = cleaned_msg.strip()
                    if cleaned_msg:
                        all_text.append(cleaned_msg)

        if not all_text:
            return "en", "English", "low"

        # Use OpenAI to detect language
        combined_text = " ".join(all_text[:10])  # Limit to 10 messages for efficiency

        detection_prompt = f"""Analyze the language of this text and respond with only a JSON object:

TEXT TO ANALYZE: "{combined_text}"

Return ONLY this JSON format:
{{
    "language_code": "xx",
    "language_name": "Language Name",
    "confidence": "high|medium|low"
}}

Common language codes: en=English, es=Spanish, fr=French, de=German, it=Italian, pt=Portuguese, ru=Russian, ja=Japanese, ko=Korean, zh=Chinese, ar=Arabic, hi=Hindi, th=Thai, vi=Vietnamese"""

        response = client.chat.completions.create(
            messages=[{"role": "user", "content": detection_prompt}],
            model="gpt-4o",
            temperature=0.1,
            max_tokens=100
        )

        response_text = response.choices[0].message.content.strip()

        # Parse JSON response
        import json
        try:
            # Extract JSON from response
            json_start = response_text.find('{')
            json_end = response_text.rfind('}') + 1
            if json_start >= 0 and json_end > json_start:
                json_str = response_text[json_start:json_end]
                result = json.loads(json_str)
                return (
                    result.get("language_code", "en"),
                    result.get("language_name", "English"),
                    result.get("confidence", "low")
                )
        except:
            pass

        # Fallback: simple pattern matching for common languages
        text_lower = combined_text.lower()

        # Korean detection
        if re.search(r'[ㄱ-ㅎ가-힣]', combined_text):
            return "ko", "Korean", "high"

        # Japanese detection
        if re.search(r'[ひらがなカタカナ]|[一-龯]', combined_text):
            return "ja", "Japanese", "high"

        # Chinese detection
        if re.search(r'[一-龯]', combined_text) and not re.search(r'[ひらがなカタカナ]', combined_text):
            return "zh", "Chinese", "medium"

        # Spanish detection
        spanish_indicators = ['qué', 'cómo', 'dónde', 'cuándo', 'por favor', 'gracias', 'hola']
        if any(word in text_lower for word in spanish_indicators):
            return "es", "Spanish", "medium"

        # French detection
        french_indicators = ['bonjour', 'merci', 'comment', 'pourquoi', 's\'il vous plaît']
        if any(word in text_lower for word in french_indicators):
            return "fr", "French", "medium"

        # Default to English
        return "en", "English", "low"

    except Exception as e:
        print(f"❌ Error in language detection: {str(e)}")
        return "en", "English", "low"

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

def chat_with_context(query, context="", detected_language=None):
    """Chat with context grounding and conflict moderation persona"""

    # Build language-aware system prompt
    system_prompt = """You are Solomon, a wise and diplomatic moderator specializing in conflict resolution and team harmony. You have DIRECT ACCESS to Slack workspace data and can see messages, channels, and URLs.

Core abilities:
1. ANALYZE conversations for tension, misunderstandings, or conflicts
2. PROVIDE balanced perspectives that acknowledge all viewpoints
3. SUGGEST constructive solutions and common ground
4. MAINTAIN neutrality while fostering understanding
5. Use GENTLE but FIRM guidance to redirect negative patterns

IMPORTANT: When you receive SLACK WORKSPACE DATA or CHANNEL CONTEXT, you HAVE this information and can reference it directly. Do NOT say you "can't access" channels or external content - you have the data provided in the context.

When responding to Slack conversations:
- Use the provided channel data and messages to give informed responses
- Reference specific channels, users, or shared URLs when relevant
- Address underlying concerns using the broader workspace context
- Validate emotions while focusing on solutions
- Suggest concrete next steps for resolution
- Keep responses concise but thoughtful"""

    # Add language preference if detected
    if detected_language and detected_language[0] != "en":
        language_code, language_name, confidence = detected_language
        system_prompt += f"""

LANGUAGE PREFERENCE: The conversation is primarily in {language_name} ({language_code}).
RESPOND IN {language_name.upper()} to match the conversation language and cultural context.
Maintain your diplomatic and wise persona while using appropriate cultural communication patterns for {language_name}."""

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

def detect_query_language(query: str):
    """
    Detect language of a single query/message.

    Args:
        query: The text query to analyze

    Returns:
        Tuple of (detected_language_code, detected_language_name, confidence)
    """
    try:
        if not query or not query.strip():
            return "en", "English", "low"

        # Clean the query for better detection
        cleaned_query = re.sub(r'http[s]?://\S+', '', query)
        cleaned_query = re.sub(r'<@\w+>', '', cleaned_query)
        cleaned_query = cleaned_query.strip()

        if len(cleaned_query) < 10:  # Too short for reliable detection
            # Quick pattern check for obvious non-English
            if re.search(r'[ㄱ-ㅎ가-힣]', cleaned_query):
                return "ko", "Korean", "high"
            elif re.search(r'[ひらがなカタカナ]|[一-龯]', cleaned_query):
                return "ja", "Japanese", "high"
            else:
                return "en", "English", "low"

        # Use OpenAI for reliable detection
        detection_prompt = f"""Analyze the language of this text and respond with only a JSON object:

TEXT TO ANALYZE: "{cleaned_query}"

Return ONLY this JSON format:
{{
    "language_code": "xx",
    "language_name": "Language Name",
    "confidence": "high|medium|low"
}}

Common language codes: en=English, es=Spanish, fr=French, de=German, it=Italian, pt=Portuguese, ru=Russian, ja=Japanese, ko=Korean, zh=Chinese, ar=Arabic, hi=Hindi, th=Thai, vi=Vietnamese"""

        response = client.chat.completions.create(
            messages=[{"role": "user", "content": detection_prompt}],
            model="gpt-4o",
            temperature=0.1,
            max_tokens=100
        )

        response_text = response.choices[0].message.content.strip()

        # Parse JSON response
        import json
        try:
            json_start = response_text.find('{')
            json_end = response_text.rfind('}') + 1
            if json_start >= 0 and json_end > json_start:
                json_str = response_text[json_start:json_end]
                result = json.loads(json_str)
                return (
                    result.get("language_code", "en"),
                    result.get("language_name", "English"),
                    result.get("confidence", "low")
                )
        except:
            pass

        # Fallback detection
        text_lower = cleaned_query.lower()

        if re.search(r'[ㄱ-ㅎ가-힣]', cleaned_query):
            return "ko", "Korean", "high"
        elif re.search(r'[ひらがなカタカナ]|[一-龯]', cleaned_query):
            return "ja", "Japanese", "high"
        elif any(word in text_lower for word in ['qué', 'cómo', 'dónde', 'gracias', 'hola']):
            return "es", "Spanish", "medium"
        elif any(word in text_lower for word in ['bonjour', 'merci', 'comment', 'pourquoi']):
            return "fr", "French", "medium"
        else:
            return "en", "English", "low"

    except Exception as e:
        print(f"❌ Error in query language detection: {str(e)}")
        return "en", "English", "low"

def chat(query: str, context=""):
    """Enhanced chat function with language detection support"""
    # Detect query language
    detected_language = detect_query_language(query)
    language_code, language_name, confidence = detected_language

    if confidence in ["high", "medium"] and language_code != "en":
        print(f"🌐 Query language detected: {language_name} ({language_code})")
        return chat_with_context(query, context, detected_language)
    else:
        return chat_with_context(query, context)

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

    # Detect conversation language first
    detected_language = detect_conversation_language(messages_by_user, user_names)
    language_code, language_name, confidence = detected_language

    print(f"🌐 Detected language: {language_name} ({language_code}) - confidence: {confidence}")

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

    # Add language detection info to context
    if confidence in ["high", "medium"] and language_code != "en":
        context += f"\nLANGUAGE DETECTED: Conversation is primarily in {language_name} ({language_code})\n"

    # Add enhanced channel context if available
    if channel_context:
        context += "\nMULTI-CHANNEL CONTEXT (for grounding and background):\n"
        for channel, data in channel_context.items():
            context += f"\n#{channel} Channel:\n"
            if data.get('message_count', 0) > 0:
                context += f"- {data['message_count']} recent messages\n"

                # Add recent messages for context
                if data.get('recent_messages'):
                    context += "- Recent discussions:\n"
                    for msg in data['recent_messages'][:5]:  # Limit to 5 most recent
                        context += f"  {msg['time']} {msg['user']}: {msg['text']}\n"

                # Add URLs for reference
                if data.get('urls_shared'):
                    context += f"- URLs shared: {', '.join(data['urls_shared'][:3])}\n"  # Limit to 3 URLs

                # Add key topics
                if data.get('key_topics'):
                    context += f"- Key topics: {'; '.join(data['key_topics'][:3])}\n"  # Limit to 3 topics
            else:
                context += "- No recent activity\n"

    # Use conflict moderation persona with language awareness
    if language_code != "en" and confidence in ["high", "medium"]:
        analysis_query = f"""Please analyze this conversation for:
1. Any tensions, conflicts, or misunderstandings
2. Emotional undertones and group dynamics
3. Constructive ways to address concerns
4. Common ground and shared goals
5. Next steps for productive dialogue

Provide a diplomatic summary that promotes understanding. RESPOND IN {language_name.upper()} to match the conversation language."""
    else:
        analysis_query = """Please analyze this conversation for:
1. Any tensions, conflicts, or misunderstandings
2. Emotional undertones and group dynamics
3. Constructive ways to address concerns
4. Common ground and shared goals
5. Next steps for productive dialogue

Provide a diplomatic summary that promotes understanding."""

    return chat_with_context(analysis_query, context, detected_language if confidence in ["high", "medium"] else None)

def summarize_conversation(messages_by_user: dict, user_names: dict) -> str:
    """Legacy function - now uses Solomon's conflict moderation"""
    return analyze_conversation_with_context(messages_by_user, user_names)