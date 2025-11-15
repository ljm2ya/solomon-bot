#!/usr/bin/env python3
"""
Simple Flask webhook server for Slack Event Subscriptions
Run this alongside your Socket Mode bot for development
"""

from flask import Flask, request, jsonify
import os
import json
import re
from dotenv import load_dotenv
from slack_bolt import App
from ai import chat, analyze_conversation_with_context
from collections import defaultdict
from datetime import datetime, timedelta

load_dotenv()

app = Flask(__name__)
slack_app = App(token=os.getenv("BOT_TOKEN"))

# Track processed messages to prevent duplicates
processed_events = set()

def analyze_query_for_context(user_query, available_channels):
    """Use AI to determine if context gathering is needed and which channels to prioritize"""
    try:
        channels_list = ", ".join([f"#{ch}" for ch in available_channels])

        analysis_prompt = f"""Analyze this user query to determine context gathering strategy:

USER QUERY: "{user_query}"

AVAILABLE CHANNELS: {channels_list}

Return a JSON response with:
{{
    "needs_context": true/false,
    "priority_keywords": ["keyword1", "keyword2"],
    "target_channels": ["channel1", "channel2"],
    "reasoning": "why context is/isn't needed"
}}

Guidelines:
- needs_context: true if query asks about workspace activity, shared content, recent discussions, or channel-specific info
- priority_keywords: extract key terms that might match channel names or content
- target_channels: max 3 most relevant channel names (without #)
- reasoning: brief explanation of decision

Examples:
- "what's been discussed lately?" -> needs_context: true, keywords: ["discuss", "recent"], channels: ["general", "project-*"]
- "find github links" -> needs_context: true, keywords: ["github", "link"], channels: channels with "project", "dev", "code" in name
- "hello" -> needs_context: false"""

        response = chat(analysis_prompt)

        # Try to parse JSON response
        import json
        try:
            # Extract JSON from response if wrapped in text
            json_start = response.find('{')
            json_end = response.rfind('}') + 1
            if json_start >= 0 and json_end > json_start:
                json_str = response[json_start:json_end]
                result = json.loads(json_str)
                return result
        except:
            pass

        # Fallback: simple keyword matching
        query_lower = user_query.lower()
        needs_context = any(keyword in query_lower for keyword in [
            'find', 'search', 'recent', 'discuss', 'share', 'link', 'url', 'github', 'channel', 'what', 'who', 'when', 'summary'
        ])

        return {
            "needs_context": needs_context,
            "priority_keywords": user_query.split()[:3],
            "target_channels": available_channels[:3],
            "reasoning": "fallback analysis"
        }

    except Exception as e:
        print(f"❌ Error in analyze_query_for_context: {str(e)}")
        return {"needs_context": False, "priority_keywords": [], "target_channels": [], "reasoning": "error occurred"}

def priority_score_channels(available_channels, target_channels, keywords):
    """Score channels by relevance to query"""
    scored_channels = []

    for channel_id, channel_name in available_channels:
        score = 0

        # Exact match with target channels
        for target in target_channels:
            if target.replace('#', '') == channel_name:
                score += 100
            elif target.replace('*', '').replace('#', '') in channel_name:
                score += 50

        # Keyword match in channel name
        for keyword in keywords:
            if keyword.lower() in channel_name.lower():
                score += 30

        # Default score for common channels
        if channel_name in ['general', 'random']:
            score += 10
        elif any(prefix in channel_name for prefix in ['project', 'dev', 'test']):
            score += 20

        scored_channels.append((score, channel_id, channel_name))

    # Sort by score (highest first) and return top channels
    scored_channels.sort(reverse=True)
    return scored_channels

def get_targeted_channel_context(client, analysis_result, limit_hours=72, max_messages_per_channel=20):
    """Smart context gathering based on AI analysis"""
    try:
        if not analysis_result.get("needs_context"):
            print("🚫 AI determined no context gathering needed")
            return {}

        print(f"🎯 Targeted context gathering: {analysis_result.get('reasoning')}")

        cutoff_time = datetime.now() - timedelta(hours=limit_hours)
        cutoff_ts = cutoff_time.timestamp()

        # Get all available channels
        available_channels = []
        try:
            channels_response = client.conversations_list(types="public_channel", exclude_archived=True)
            if channels_response["ok"]:
                for channel in channels_response["channels"]:
                    if channel.get("is_member"):
                        available_channels.append((channel["id"], channel["name"]))
        except Exception as e:
            print(f"❌ Error getting channels: {str(e)}")
            return {}

        # Score and prioritize channels
        target_channels = analysis_result.get("target_channels", [])
        keywords = analysis_result.get("priority_keywords", [])

        scored_channels = priority_score_channels(available_channels, target_channels, keywords)

        # Adaptive search: Start with priority channels, expand if needed
        priority_channels = scored_channels[:4]  # Try top 4 first
        context = {}
        found_relevant_content = False

        print(f"🎯 Searching {len(priority_channels)} priority channels...")

        for score, channel_id, channel_name in priority_channels:
            if score <= 0:
                continue  # Skip irrelevant channels

            try:
                history = client.conversations_history(
                    channel=channel_id,
                    oldest=str(cutoff_ts),
                    limit=max_messages_per_channel
                )

                if history["ok"] and history["messages"]:
                    channel_context = {
                        "message_count": len(history["messages"]),
                        "recent_messages": [],
                        "urls_shared": [],
                        "key_topics": [],
                        "relevance_score": score
                    }

                    # Extract messages, URLs, and topics with keyword priority
                    for msg in history["messages"]:
                        if msg.get("text") and not msg.get("bot_id"):
                            clean_text = re.sub(r'<@[A-Z0-9]+>', '@user', msg["text"]).strip()

                            if clean_text:
                                # Get user name
                                user_name = "unknown"
                                if msg.get("user"):
                                    try:
                                        user_info = client.users_info(user=msg["user"])
                                        if user_info["ok"]:
                                            user_name = user_info["user"].get("real_name", user_info["user"].get("name", "unknown"))
                                    except:
                                        pass

                                # Prioritize messages with keywords
                                keyword_match = any(kw.lower() in clean_text.lower() for kw in keywords)
                                if keyword_match or len(channel_context["recent_messages"]) < 5:
                                    timestamp = datetime.fromtimestamp(float(msg.get("ts", 0)))
                                    channel_context["recent_messages"].append({
                                        "user": user_name,
                                        "text": clean_text[:200],
                                        "time": timestamp.strftime("%H:%M"),
                                        "keyword_match": keyword_match
                                    })

                                # Extract URLs
                                urls = re.findall(r'http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\\(\\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+', clean_text)
                                channel_context["urls_shared"].extend(urls)

                                # Extract key topics
                                if len(clean_text) > 20:
                                    channel_context["key_topics"].append(clean_text[:100])

                    # Limit and deduplicate
                    channel_context["recent_messages"] = sorted(
                        channel_context["recent_messages"],
                        key=lambda x: x.get("keyword_match", False),
                        reverse=True
                    )[:8]
                    channel_context["urls_shared"] = list(set(channel_context["urls_shared"]))[:5]
                    channel_context["key_topics"] = channel_context["key_topics"][:5]

                    if channel_context["message_count"] > 0:
                        context[channel_name] = channel_context

                        # Check if we found relevant content (URLs, keyword matches, etc.)
                        if (len(channel_context.get('urls_shared', [])) > 0 or
                            any(msg.get('keyword_match', False) for msg in channel_context.get('recent_messages', []))):
                            found_relevant_content = True

            except Exception as e:
                continue

        # Phase 2: If priority search didn't find relevant content, expand to all channels
        if not found_relevant_content and len(scored_channels) > 4:
            print(f"🔍 Expanding to all {len(scored_channels)} channels...")

            remaining_channels = scored_channels[4:]  # Skip already searched channels

            for score, channel_id, channel_name in remaining_channels:
                try:
                    history = client.conversations_history(
                        channel=channel_id,
                        oldest=str(cutoff_ts),
                        limit=max_messages_per_channel
                    )

                    if history["ok"] and history["messages"]:
                        channel_context = {
                            "message_count": len(history["messages"]),
                            "recent_messages": [],
                            "urls_shared": [],
                            "key_topics": [],
                            "relevance_score": score
                        }

                        # Extract content with same logic as above
                        for msg in history["messages"]:
                            if msg.get("text") and not msg.get("bot_id"):
                                clean_text = re.sub(r'<@[A-Z0-9]+>', '@user', msg["text"]).strip()

                                if clean_text:
                                    # Get user name
                                    user_name = "unknown"
                                    if msg.get("user"):
                                        try:
                                            user_info = client.users_info(user=msg["user"])
                                            if user_info["ok"]:
                                                user_name = user_info["user"].get("real_name", user_info["user"].get("name", "unknown"))
                                        except:
                                            pass

                                    # Prioritize messages with keywords
                                    keyword_match = any(kw.lower() in clean_text.lower() for kw in keywords)
                                    if keyword_match or len(channel_context["recent_messages"]) < 5:
                                        timestamp = datetime.fromtimestamp(float(msg.get("ts", 0)))
                                        channel_context["recent_messages"].append({
                                            "user": user_name,
                                            "text": clean_text[:200],
                                            "time": timestamp.strftime("%H:%M"),
                                            "keyword_match": keyword_match
                                        })

                                    # Extract URLs
                                    urls = re.findall(r'http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\\(\\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+', clean_text)
                                    channel_context["urls_shared"].extend(urls)

                                    # Extract key topics
                                    if len(clean_text) > 20:
                                        channel_context["key_topics"].append(clean_text[:100])

                        # Process and check for relevant content
                        channel_context["recent_messages"] = sorted(
                            channel_context["recent_messages"],
                            key=lambda x: x.get("keyword_match", False),
                            reverse=True
                        )[:8]
                        channel_context["urls_shared"] = list(set(channel_context["urls_shared"]))[:5]
                        channel_context["key_topics"] = channel_context["key_topics"][:5]

                        if channel_context["message_count"] > 0:
                            # Check if this channel has the content we're looking for
                            has_relevant_content = (
                                len(channel_context.get('urls_shared', [])) > 0 or
                                any(msg.get('keyword_match', False) for msg in channel_context.get('recent_messages', []))
                            )

                            if has_relevant_content:
                                context[channel_name] = channel_context
                                print(f"💎 Found in #{channel_name}: {len(channel_context['urls_shared'])} URLs")
                                found_relevant_content = True
                                # Keep searching to find all relevant content, don't break early

                except Exception as e:
                    continue

        # Summary
        total_urls = sum(len(ch.get('urls_shared', [])) for ch in context.values())
        if total_urls > 0:
            print(f"✅ Found {total_urls} URLs in {len(context)} channels")
            return context
        else:
            print(f"🔍 No URLs found in recent messages, trying unlimited search...")

        # Phase 3: If still no URLs found, search without time limits
        if 'github' in ' '.join(analysis_result.get('priority_keywords', [])).lower() or 'link' in ' '.join(analysis_result.get('priority_keywords', [])).lower():
            print(f"🕰️ Searching all message history...")

            for score, channel_id, channel_name in scored_channels:
                try:
                    # Search all history (no time limit)
                    history = client.conversations_history(
                        channel=channel_id,
                        limit=50  # More messages for unlimited search
                    )

                    if history["ok"] and history["messages"]:
                        channel_context = {
                            "message_count": len(history["messages"]),
                            "recent_messages": [],
                            "urls_shared": [],
                            "key_topics": [],
                            "relevance_score": score,
                            "unlimited_search": True
                        }

                        # Extract content with same logic as above
                        for msg in history["messages"]:
                            if msg.get("text") and not msg.get("bot_id"):
                                clean_text = re.sub(r'<@[A-Z0-9]+>', '@user', msg["text"]).strip()

                                if clean_text:
                                    # Extract URLs
                                    urls = re.findall(r'http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\\(\\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+', clean_text)
                                    channel_context["urls_shared"].extend(urls)

                        # Check for URLs
                        channel_context["urls_shared"] = list(set(channel_context["urls_shared"]))[:10]

                        if len(channel_context["urls_shared"]) > 0:
                            context[channel_name] = channel_context
                            print(f"🎯 Found in #{channel_name}: {len(channel_context['urls_shared'])} URLs (all history)")
                            found_relevant_content = True

                except Exception as e:
                    continue

            # Final summary
            total_urls = sum(len(ch.get('urls_shared', [])) for ch in context.values())
            if total_urls > 0:
                print(f"✅ Found {total_urls} URLs in {len(context)} channels (including older messages)")
            else:
                print(f"❌ No URLs found in any messages")

        return context

    except Exception as e:
        print(f"❌ Error in get_targeted_channel_context: {str(e)}")
        return {}

def fetch_url_content(urls, user_query):
    """Fetch and summarize content from URLs using WebFetch"""
    url_content = {}

    for url in urls[:3]:  # Limit to 3 URLs for performance
        try:
            print(f"🌐 Fetching: {url[:50]}...")

            # Create a prompt based on user query
            if 'readme' in user_query.lower():
                fetch_prompt = "Extract and summarize the README content, focusing on: project purpose, key features, installation instructions, usage guidelines, and any important notes."
            elif 'github' in user_query.lower():
                fetch_prompt = "Summarize this GitHub repository: what it does, key features, and how to use it."
            elif 'summarize' in user_query.lower():
                fetch_prompt = "Provide a comprehensive summary of the main content, key points, and important information from this page."
            else:
                fetch_prompt = "Summarize the key content and main points from this page."

            # Use WebFetch to get content
            content = WebFetch(url=url, prompt=fetch_prompt)

            if content and len(content.strip()) > 50:  # Valid content
                url_content[url] = {
                    'summary': content,
                    'type': 'github' if 'github.com' in url else 'web'
                }
                print(f"✅ Fetched {len(content)} chars from {url[:30]}...")
            else:
                print(f"⚠️ No content fetched from {url[:30]}...")

        except Exception as e:
            print(f"❌ Failed to fetch {url[:30]}: {str(e)}")
            continue

    return url_content

def get_multi_channel_context(client, limit_hours=24, max_messages_per_channel=20):
    """Gather comprehensive context from multiple channels including messages and URLs"""
    try:
        context = {}
        cutoff_time = datetime.now() - timedelta(hours=limit_hours)
        cutoff_ts = cutoff_time.timestamp()

        channels_to_check = []

        # Get channels bot is member of
        try:
            channels_response = client.conversations_list(
                types="public_channel",
                exclude_archived=True
            )
            if channels_response["ok"]:
                for channel in channels_response["channels"]:
                    if channel.get("is_member"):
                        channels_to_check.append((channel["id"], channel["name"]))
        except Exception:
            pass

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
        except Exception:
            pass

        # Limit to top channels to prevent timeouts
        channels_to_check = channels_to_check[:8]  # Max 8 channels for speed

        for channel_id, channel_name in channels_to_check:
            try:
                history = client.conversations_history(
                    channel=channel_id,
                    oldest=str(cutoff_ts),
                    limit=max_messages_per_channel
                )

                if history["ok"] and history["messages"]:
                    channel_context = {
                        "message_count": len(history["messages"]),
                        "recent_messages": [],
                        "urls_shared": [],
                        "key_topics": []
                    }

                    # Extract messages, URLs, and topics
                    for msg in history["messages"]:
                        if msg.get("text") and not msg.get("bot_id"):
                            # Clean message text
                            clean_text = re.sub(r'<@[A-Z0-9]+>', '@user', msg["text"]).strip()

                            if clean_text:
                                # Get user name
                                user_name = "unknown"
                                if msg.get("user"):
                                    try:
                                        user_info = client.users_info(user=msg["user"])
                                        if user_info["ok"]:
                                            user_name = user_info["user"].get("real_name", user_info["user"].get("name", "unknown"))
                                    except:
                                        pass

                                # Store message with context
                                timestamp = datetime.fromtimestamp(float(msg.get("ts", 0)))
                                channel_context["recent_messages"].append({
                                    "user": user_name,
                                    "text": clean_text[:200],  # Truncate long messages
                                    "time": timestamp.strftime("%H:%M")
                                })

                                # Extract URLs
                                urls = re.findall(r'http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\\(\\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+', clean_text)
                                channel_context["urls_shared"].extend(urls)

                                # Extract key topics (meaningful phrases)
                                if len(clean_text) > 20:  # Skip very short messages
                                    channel_context["key_topics"].append(clean_text[:100])

                    # Limit and deduplicate
                    channel_context["recent_messages"] = channel_context["recent_messages"][:10]
                    channel_context["urls_shared"] = list(set(channel_context["urls_shared"]))[:5]
                    channel_context["key_topics"] = channel_context["key_topics"][:5]

                    if channel_context["message_count"] > 0:
                        context[channel_name] = channel_context

            except Exception as e:
                continue

        return context
    except Exception as e:
        print(f"❌ Error in get_multi_channel_context: {str(e)}")
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

@app.route('/slack/events', methods=['POST'])
def slack_events():
    """Handle Slack Events API"""
    try:
        data = request.get_json()
    except Exception as e:
        print(f"❌ JSON parsing error: {e}")
        return jsonify({'error': 'Invalid JSON'}), 400

    # Handle URL verification for Slack Event Subscriptions - PRIORITY
    if data and data.get('type') == 'url_verification':
        challenge = data.get('challenge')
        if challenge:
            print(f"🔗 URL verification ✅")
            return challenge, 200, {'Content-Type': 'text/plain'}
        else:
            print(f"❌ No challenge parameter")
            return jsonify({'error': 'No challenge parameter'}), 400

    # Handle actual events
    if data and data.get('type') == 'event_callback':
        event = data.get('event', {})
        event_type = event.get('type', 'unknown')
        event_id = data.get('event_id', '')

        # Check for duplicate events (Slack retries)
        if event_id in processed_events:
            print(f"⏭️ Duplicate ignored")
            return jsonify({'status': 'duplicate_ignored'}), 200

        # Add to processed set (keep last 100 events)
        processed_events.add(event_id)
        if len(processed_events) > 100:
            processed_events.pop()

        if event_type == 'app_mention':
            print("📡 @Mention")
        elif event_type == 'message':
            # Extract user query for context
            text = event.get('text', '')
            if text.startswith('solomon'):
                query = text[7:].strip()[:30]  # First 30 chars
                print(f"📡 Solomon: '{query}{'...' if len(text) > 37 else ''}'")
            else:
                print("📡 Message")
        elif event_type == 'channel_created':
            print("📡 Channel Created")
        else:
            print(f"📡 {event_type.title()}")

        # Process events through bot logic
        try:
            if event_type == 'app_mention':
                handle_app_mention(event)
            elif event_type == 'message' and event.get('text'):
                handle_message(event)
            elif event_type == 'channel_created':
                handle_channel_created(event)
        except Exception as e:
            print(f"❌ Error processing event: {str(e)}")

    return jsonify({'status': 'ok'}), 200

def handle_app_mention(event):
    """Handle @bot mentions"""
    try:
        client = slack_app.client
        client.reactions_add(channel=event["channel"], timestamp=event["ts"], name="eyes")

        bot_info = client.auth_test()
        bot_user_id = bot_info["user_id"] if bot_info["ok"] else None
        channel_id = event["channel"]

        user_messages, user_ids = extract_user_messages(client, channel_id, bot_user_id)

        if not user_messages:
            response = "No user messages found in this conversation."
        else:
            user_names = {}
            for user_id in user_ids:
                try:
                    user_info = client.users_info(user=user_id)
                    if user_info["ok"]:
                        user_names[user_id] = (user_info["user"].get("real_name") or
                                               user_info["user"].get("name", user_id))
                except:
                    user_names[user_id] = user_id

            messages_by_user = defaultdict(list)
            for user_id, text in user_messages:
                messages_by_user[user_id].append(text)

            channel_context = get_multi_channel_context(client, limit_hours=6, max_messages_per_channel=8)
            response = analyze_conversation_with_context(
                messages_by_user, user_names, channel_context
            )

        client.chat_postMessage(channel=event["channel"], text=response)
        client.reactions_remove(channel=event["channel"], timestamp=event["ts"], name="eyes")

    except Exception as e:
        print(f"❌ Error in handle_app_mention: {str(e)}")

def handle_message(event):
    """Handle regular messages"""
    try:
        # Skip bot messages and system messages
        if (event.get("subtype") == "bot_message" or
            event.get("bot_id") or
            not event.get("text") or
            not event.get("user")):
            return

        client = slack_app.client

        # Check if this is our own bot message
        bot_info = client.auth_test()
        if bot_info["ok"] and event.get("user") == bot_info["user_id"]:
            return

        text = event.get("text", "")

        # Check for solomon commands
        if re.match(r"^solomon\b", text, re.IGNORECASE):
            user_query = re.sub(r"^solomon\s*", "", text, flags=re.IGNORECASE).strip()

            if not user_query:
                client.chat_postMessage(
                    channel=event["channel"],
                    text="👋 Solomon here. Ask me anything or @mention me to analyze conversations for conflicts and solutions."
                )
                return

            if user_query.lower() in ["help", "status", "health"]:
                channel_context = get_multi_channel_context(client, limit_hours=6, max_messages_per_channel=5)
                channel_count = len(channel_context)
                if channel_count > 0:
                    channel_names = ", ".join(channel_context.keys())
                    response = f"🔍 Monitoring {channel_count} channels: {channel_names}\n🤝 Ready to mediate conflicts and provide diplomatic solutions"
                else:
                    response = f"⚠️ Not detecting any accessible channels. Bot needs to be invited to channels with `/invite @botname`\n🤝 Ready to mediate conflicts when channels are accessible"

                client.chat_postMessage(channel=event["channel"], text=response)
                return

            # ReAct Pattern: Reasoning + Acting for intelligent context gathering
            print(f"🤔 '{user_query}'")

            # Step 1: Analyze query to determine context strategy
            try:
                # Get available channels list for AI analysis
                available_channels = []
                try:
                    channels_response = client.conversations_list(types="public_channel", exclude_archived=True)
                    if channels_response["ok"]:
                        available_channels = [ch["name"] for ch in channels_response["channels"] if ch.get("is_member")]
                except:
                    available_channels = ["general", "random"]  # fallback

                analysis_result = analyze_query_for_context(user_query, available_channels)

                # Step 2: Gather targeted context if needed
                if analysis_result.get("needs_context"):
                    print(f"🧠 Context needed: {analysis_result.get('reasoning', 'relevant content search')}")
                    channel_context = get_targeted_channel_context(client, analysis_result)

                    # Step 3: Generate response with targeted context
                    if channel_context:
                        context_summary = "TARGETED SLACK WORKSPACE DATA:\n"
                        total_messages = 0
                        all_urls = []
                        channel_details = []

                        for channel, data in channel_context.items():
                            if data.get('message_count', 0) > 0:
                                total_messages += data['message_count']
                                all_urls.extend(data.get('urls_shared', []))

                                channel_detail = f"#{channel} (relevance: {data.get('relevance_score', 0)}):"
                                if data.get('recent_messages'):
                                    channel_detail += f" {len(data['recent_messages'])} recent messages"
                                    # Prioritize keyword-matching messages
                                    priority_messages = [msg for msg in data['recent_messages'] if msg.get('keyword_match')]
                                    regular_messages = [msg for msg in data['recent_messages'] if not msg.get('keyword_match')]

                                    for msg in (priority_messages + regular_messages)[:3]:
                                        channel_detail += f"\n  - {msg['user']} ({msg['time']}): {msg['text'][:120]}"

                                if data.get('urls_shared'):
                                    channel_detail += f"\n  - URLs: {', '.join(data['urls_shared'][:3])}"

                                channel_details.append(channel_detail)

                        context_summary += f"Found: {total_messages} messages from {len(channel_context)} relevant channels\n"
                        context_summary += f"Keywords matched: {', '.join(analysis_result.get('priority_keywords', []))}\n"
                        context_summary += "\nRELEVANT CHANNELS:\n" + "\n".join(channel_details)

                        if all_urls:
                            context_summary += f"\n\nFOUND URLS: {', '.join(list(set(all_urls))[:5])}"

                            # Step 3.5: Fetch URL content if query requests it
                            url_keywords = ['readme', 'summarize', 'content', 'what', 'explain']
                            should_fetch_urls = any(keyword in user_query.lower() for keyword in url_keywords)

                            if should_fetch_urls:
                                unique_urls = list(set(all_urls))
                                print(f"🔍 Query requests content analysis, fetching URLs...")
                                url_content = fetch_url_content(unique_urls, user_query)

                                if url_content:
                                    context_summary += "\n\nFETCHED URL CONTENT:\n"
                                    for url, data in url_content.items():
                                        context_summary += f"\n🔗 {url}:\n"
                                        context_summary += f"Type: {data['type'].upper()}\n"
                                        context_summary += f"Summary: {data['summary'][:800]}...\n"  # Limit length

                        enhanced_query = f"SYSTEM: You have targeted Slack workspace data below based on the user's query. Use this information to provide a specific, helpful response.\n\n{context_summary}\n\nUSER QUESTION: {user_query}\n\nINSTRUCTION: Reference specific findings from the channels above. Be precise about what you found and where."

                        print(f"💬 Generating response...")
                        response = chat(enhanced_query, context_summary)
                    else:
                        response = chat(f"No relevant information found in workspace channels for: {user_query}")
                else:
                    print(f"💬 No context needed")
                    response = chat(user_query)

            except Exception as e:
                print(f"❌ Error, using fallback")
                response = chat(user_query)

            client.chat_postMessage(channel=event["channel"], text=response)

    except Exception as e:
        print(f"❌ Error in handle_message: {str(e)}")

def handle_channel_created(event):
    """Auto-join new public channels"""
    try:
        client = slack_app.client
        channel_id = event["channel"]["id"]
        channel_name = event["channel"]["name"]

        # Try to join the channel
        result = client.conversations_join(channel=channel_id)
        if result["ok"]:
            print(f"✅ Auto-joined #{channel_name}")
        else:
            print(f"❌ Failed to join #{channel_name}")

    except Exception as e:
        print(f"❌ Error in handle_channel_created: {str(e)}")

@app.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    return jsonify({'status': 'healthy', 'service': 'solomon-bot-webhook'})

@app.route('/', methods=['GET'])
def root():
    """Root endpoint with instructions"""
    return """
    <h1>🤖 Solomon Bot Webhook Server</h1>
    <p><strong>Status:</strong> Running ✅</p>
    <p><strong>Slack Events Endpoint:</strong> <code>/slack/events</code></p>
    <p><strong>Health Check:</strong> <code>/health</code></p>

    <h2>📝 Setup Instructions:</h2>
    <ol>
        <li>Copy your ngrok HTTPS URL</li>
        <li>Add <code>/slack/events</code> to the end</li>
        <li>Paste in Slack App > Event Subscriptions > Request URL</li>
    </ol>

    <p><em>Example:</em> <code>https://abc123.ngrok.io/slack/events</code></p>
    """

if __name__ == '__main__':
    port = int(os.getenv('PORT', 3000))
    print(f"🚀 Starting webhook server on port {port}")
    print(f"📡 Slack events endpoint: http://localhost:{port}/slack/events")
    print(f"🔗 Use ngrok to expose this publicly")

    app.run(host='0.0.0.0', port=port, debug=True)