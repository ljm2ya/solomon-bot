from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler
import os
import re
from dotenv import load_dotenv
from ai import chat, analyze_conversation_with_context
from collections import defaultdict
from datetime import datetime, timedelta

# Load environment variables from .env file
load_dotenv()

app_token = os.getenv("APP_TOKEN")
bot_token = os.getenv("BOT_TOKEN")
app = App(token=bot_token)

def get_multi_channel_context(client, limit_hours=24):
    """Gather recent activity from multiple channels for context"""
    try:
        context = {}
        cutoff_time = datetime.now() - timedelta(hours=limit_hours)
        cutoff_ts = cutoff_time.timestamp()

        # Try different approaches to get channels
        channels_to_check = []

        # Method 1: Get public channels bot is member of (works with current scopes)
        try:
            channels_response = client.conversations_list(
                types="public_channel",
                exclude_archived=True
            )
            if channels_response["ok"]:
                for channel in channels_response["channels"]:
                    if channel.get("is_member"):
                        channels_to_check.append((channel["id"], channel["name"]))
        except Exception as e:
            print(f"DEBUG: Error getting public channels: {str(e)}")

        # Method 2: Try user conversations (may work for some channels)
        try:
            user_convos = client.users_conversations(
                types="public_channel",
                exclude_archived=True
            )
            if user_convos["ok"]:
                for channel in user_convos["channels"]:
                    channel_tuple = (channel["id"], channel["name"])
                    if channel_tuple not in channels_to_check:
                        channels_to_check.append(channel_tuple)
        except Exception as e:
            print(f"DEBUG: Error getting user conversations: {str(e)}")
            pass

        # Process channels we found
        for channel_id, channel_name in channels_to_check:
            try:
                # Test access by trying to get history
                history = client.conversations_history(
                    channel=channel_id,
                    oldest=str(cutoff_ts),
                    limit=10
                )

                if history["ok"] and history["messages"]:
                    msg_count = len(history["messages"])
                    recent_activity = f"{msg_count} messages"

                    # Extract sample topics
                    topics = []
                    for msg in history["messages"][:3]:
                        if msg.get("text") and not msg.get("bot_id"):
                            clean_text = re.sub(r'<@[A-Z0-9]+>', '', msg["text"]).strip()
                            if clean_text:
                                topics.append(clean_text[:50])

                    if topics:
                        recent_activity += f" - Topics: {'; '.join(topics)}"

                    context[channel_name] = {"recent_activity": recent_activity}

            except Exception as e:
                # If we can't access the channel, skip it
                print(f"DEBUG: Can't access channel {channel_name}: {str(e)}")
                continue

        return context
    except Exception as e:
        print(f"DEBUG: Error in get_multi_channel_context: {str(e)}")
        return {}

def extract_user_messages(client, channel_id, bot_user_id):
    """Extract and clean user messages from a channel"""
    try:
        result = client.conversations_history(channel=channel_id, limit=50)
        if not result["ok"]:
            return [], set()

        user_messages = []
        user_ids = set()

        for msg in result["messages"]:
            # Skip bot messages, system messages, and empty messages
            if ("bot_id" in msg or "subtype" in msg or
                "text" not in msg or "user" not in msg):
                continue

            user_id = msg["user"]
            if bot_user_id and user_id == bot_user_id:
                continue

            text = re.sub(r'<@[A-Z0-9]+>', '', msg["text"]).strip()
            if text:
                user_messages.append((user_id, text))
                user_ids.add(user_id)

        return user_messages, user_ids
    except Exception:
        return [], set()

@app.event("app_mention")
def handle_app_mention_events(event, client, say):
    client.reactions_add(channel=event["channel"], timestamp=event["ts"], name="eyes")

    try:
        bot_info = client.auth_test()
        bot_user_id = bot_info["user_id"] if bot_info["ok"] else None
        channel_id = event["channel"]

        # Extract messages from current channel
        user_messages, user_ids = extract_user_messages(client, channel_id, bot_user_id)

        if not user_messages:
            response = "No user messages found in this conversation."
        else:
            # Get user names
            user_names = {}
            for user_id in user_ids:
                try:
                    user_info = client.users_info(user=user_id)
                    if user_info["ok"]:
                        user_names[user_id] = (user_info["user"].get("real_name") or
                                               user_info["user"].get("name", user_id))
                except:
                    user_names[user_id] = user_id

            # Group messages by user
            messages_by_user = defaultdict(list)
            for user_id, text in user_messages:
                messages_by_user[user_id].append(text)

            # Get multi-channel context for grounding
            channel_context = get_multi_channel_context(client)

            # Analyze with Solomon's conflict moderation and context
            response = analyze_conversation_with_context(
                messages_by_user, user_names, channel_context
            )

    except Exception as e:
        response = f"Error: {str(e)}"

    client.chat_postMessage(
        channel=event["channel"],
        thread_ts=event["ts"],
        text=response
    )
    client.reactions_remove(
        channel=event["channel"],
        timestamp=event["ts"],
        name="eyes"
    )

@app.message(re.compile(r"^solomon", re.IGNORECASE))
def handle_solomon_chat(message, client, say):
    """Direct chat with Solomon without need for @mention"""
    user_query = re.sub(r"^solomon\s*", "", message["text"], flags=re.IGNORECASE).strip()

    if not user_query:
        say(text="👋 Solomon here. Ask me anything or @mention me to analyze conversations for conflicts and solutions.", thread_ts=message["ts"])
        return

    if user_query.lower() in ["help", "status", "health"]:
        channel_context = get_multi_channel_context(client)
        channel_count = len(channel_context)
        if channel_count > 0:
            channel_names = ", ".join(channel_context.keys())
            say(text=f"🔍 Monitoring {channel_count} channels: {channel_names}\n🤝 Ready to mediate conflicts and provide diplomatic solutions", thread_ts=message["ts"])
        else:
            say(text=f"⚠️ Not detecting any accessible channels. Bot needs to be invited to channels with `/invite @botname`\n🤝 Ready to mediate conflicts when channels are accessible", thread_ts=message["ts"])
        return

    if user_query.lower() == "debug":
        try:
            # Try public channels only first
            channels_response = client.conversations_list(types="public_channel", exclude_archived=True)
            member_channels = []
            non_member_channels = []

            if channels_response["ok"]:
                for channel in channels_response["channels"]:
                    if channel.get("is_member"):
                        member_channels.append(channel["name"])
                    else:
                        non_member_channels.append(channel["name"])

                debug_info = f"📊 Channel Access Debug (Public Channels Only):\n"
                debug_info += f"✅ Member of: {', '.join(member_channels) if member_channels else 'None'}\n"
                debug_info += f"❌ Not member: {', '.join(non_member_channels[:5]) if non_member_channels else 'None'}"
                if len(non_member_channels) > 5:
                    debug_info += f" (and {len(non_member_channels)-5} more)"
                debug_info += f"\n\n💡 To add bot to channels: `/invite @botname`"
                debug_info += f"\n🔒 Private channels need `groups:read` scope"
            else:
                debug_info = f"❌ API Error: {channels_response.get('error', 'Unknown')}"

            say(text=debug_info, thread_ts=message["ts"])
        except Exception as e:
            say(text=f"Debug error: {str(e)}", thread_ts=message["ts"])
        return

    response = chat(user_query)
    say(text=response, thread_ts=message["ts"])

@app.event("message")
def handle_message_events(body, logger):
    """Handle regular messages to extract URLs and build context"""
    event = body.get("event", {})

    # Skip bot messages and messages we've already handled
    if (event.get("subtype") == "bot_message" or
        event.get("bot_id") or
        not event.get("text")):
        return

    # Extract URLs from messages for future context
    text = event.get("text", "")
    urls = re.findall(r'http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\\(\\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+', text)

    if urls:
        logger.info(f"URLs detected in channel {event.get('channel')}: {urls}")

    # Log for debugging (optional)
    # logger.info(f"Message received: {text[:50]}...")

handler = SocketModeHandler(app, app_token)
handler.start()
    