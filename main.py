#!/usr/bin/env python3
"""
Simple Flask webhook server for Slack Event Subscriptions
Run this alongside your Socket Mode bot for development
"""

from flask import Flask, request, jsonify
import os
import json
import re
import requests
from dotenv import load_dotenv
from slack_bolt import App
from ai import chat, chat_with_solomon_persona, analyze_conversation_with_context
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
    "should_fetch_urls": true/false,
    "priority_keywords": ["keyword1", "keyword2"],
    "target_channels": ["channel1", "channel2"],
    "reasoning": "why context is/isn't needed"
}}

Guidelines:
- needs_context: true if query asks about workspace activity, shared content, recent discussions, or channel-specific info
- should_fetch_urls: true if query would benefit from external content (GitHub repos, documentation, articles, links)
- priority_keywords: extract key terms that might match channel names or content
- target_channels: max 3 most relevant channel names (without #)
- reasoning: brief explanation of decision

Examples:
- "what's been discussed lately?" -> needs_context: true, should_fetch_urls: false
- "explain this project" -> needs_context: true, should_fetch_urls: true (likely has GitHub links)
- "find github links" -> needs_context: true, should_fetch_urls: true
- "how to implement authentication" -> needs_context: true, should_fetch_urls: true (might find docs/tutorials)
- "hello" -> needs_context: false, should_fetch_urls: false"""

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

        should_fetch_urls = any(keyword in query_lower for keyword in [
            'github', 'link', 'url', 'readme', 'doc', 'tutorial', 'guide', 'explain', 'how', 'implement', 'project', 'repository'
        ])

        return {
            "needs_context": needs_context,
            "should_fetch_urls": should_fetch_urls,
            "priority_keywords": user_query.split()[:3],
            "target_channels": available_channels[:3],
            "reasoning": "fallback analysis"
        }

    except Exception as e:
        print(f"❌ Error in analyze_query_for_context: {str(e)}")
        return {"needs_context": False, "should_fetch_urls": False, "priority_keywords": [], "target_channels": [], "reasoning": "error occurred"}

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
    """Fetch and summarize content from URLs using LLM-based content analysis"""
    url_content = {}

    for url in urls[:5]:  # Increased limit to 5 URLs for better coverage
        try:
            print(f"🌐 Fetching: {url[:60]}...")

            # Create enhanced prompts based on URL type and user query
            url_lower = url.lower()
            query_lower = user_query.lower()

            if 'readme' in query_lower or '/readme' in url_lower:
                fetch_prompt = "Summarize this README: What does this project do? What are its key features and capabilities? How do users get started? Include any important technical details or requirements."
            elif 'github.com' in url_lower:
                if any(word in query_lower for word in ['explain', 'what', 'about']):
                    fetch_prompt = "Explain this GitHub repository: What is the project's purpose? What technology stack does it use? What problems does it solve? Include key features and use cases."
                else:
                    fetch_prompt = "Summarize this GitHub repository including its purpose, main features, technology used, and how to use it."
            elif any(word in query_lower for word in ['tutorial', 'guide', 'how to', 'implement']):
                fetch_prompt = "Summarize this tutorial/guide: What does it teach? What are the main steps or concepts? What will someone learn from following this?"
            elif any(word in query_lower for word in ['doc', 'documentation']):
                fetch_prompt = "Summarize this documentation: What does it explain? What are the key concepts, features, or procedures covered? Include important technical details."
            elif any(word in query_lower for word in ['explain', 'what', 'describe', 'tell me about']):
                fetch_prompt = "Explain what this content is about: What is its main purpose? What key information does it contain? What should someone know about this?"
            else:
                fetch_prompt = "Provide a comprehensive summary of this content including its main purpose, key points, and any important details that would be helpful to someone asking about it."

            # Detect if URL needs special handling
            url_lower = url.lower()
            if 'notion.so' in url_lower:
                print(f"📝 Detected Notion URL: {url[:50]}...")
                try:
                    # Use Node.js script to fetch Notion content
                    import subprocess
                    result = subprocess.run(['node', 'notion_fetcher.js', url],
                                          capture_output=True, text=True, timeout=30)

                    if result.returncode == 0:
                        import json
                        stdout_content = result.stdout.strip()
                        print(f"🔍 Node.js stdout: {stdout_content[:100]}...")  # Debug output
                        print(f"🔍 Node.js stderr: {result.stderr[:100]}...")  # Debug output

                        if stdout_content:
                            try:
                                notion_result = json.loads(stdout_content)
                                if notion_result.get('success'):
                                    notion_content = notion_result.get('content', '')
                                    print(f"✅ Fetched {len(notion_content)} characters from Notion")
                                    # Analyze the actual Notion content
                                    analysis_prompt = f"{fetch_prompt}\n\nNotion page content:\n{notion_content}"
                                    content = chat(analysis_prompt)
                                else:
                                    print(f"❌ Notion fetch failed: {notion_result.get('error', 'Unknown error')}")
                                    content = chat(f"I was unable to access the Notion page at {url}. {fetch_prompt.lower()}")
                            except json.JSONDecodeError as e:
                                print(f"❌ JSON decode error: {e}")
                                print(f"❌ Raw stdout: '{stdout_content}'")
                                content = chat(f"I encountered an error parsing the Notion page response. {fetch_prompt.lower()}")
                        else:
                            print("❌ Empty stdout from Node.js script")
                            content = chat(f"I was unable to access the Notion page at {url}. {fetch_prompt.lower()}")
                    else:
                        print(f"❌ Notion script failed with exit code {result.returncode}")
                        print(f"❌ stderr: {result.stderr}")
                        content = chat(f"I was unable to access the Notion page at {url}. {fetch_prompt.lower()}")

                except Exception as e:
                    print(f"❌ Error running Notion fetcher: {e}")
                    content = chat(f"I encountered an error accessing the Notion page at {url}. {fetch_prompt.lower()}")

            elif any(domain in url_lower for domain in ['docs.google.com', 'drive.google.com']):
                print(f"🔒 Detected Google Docs URL: {url[:50]}...")
                # For Google Docs, inform user that content can't be fetched
                content = chat(f"The user shared a Google Docs/Drive link: {url}. This appears to be a private document that requires authentication. Please provide helpful advice about working with shared documents and team collaboration, but acknowledge that you cannot access the specific content of the document. Focus on general conflict resolution and communication strategies that would apply to document collaboration scenarios.")

            else:
                # Fetch actual URL content using HTTP requests for regular web pages
                try:
                    print(f"📡 Requesting content from {url[:50]}...")
                    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
                    response = requests.get(url, headers=headers, timeout=10)
                    response.raise_for_status()

                    # Get the actual content
                    raw_content = response.text

                    # Extract meaningful text content
                    if 'text/html' in response.headers.get('content-type', ''):
                        # Enhanced text extraction without external dependencies
                        clean_content = raw_content

                        # Remove script tags and their content
                        clean_content = re.sub(r'<script[^>]*>.*?</script>', '', clean_content, flags=re.DOTALL | re.IGNORECASE)

                        # Remove style tags and their content
                        clean_content = re.sub(r'<style[^>]*>.*?</style>', '', clean_content, flags=re.DOTALL | re.IGNORECASE)

                        # Remove common non-content tags
                        clean_content = re.sub(r'<(nav|footer|header|aside|noscript)[^>]*>.*?</\1>', '', clean_content, flags=re.DOTALL | re.IGNORECASE)

                        # Extract content from main content areas preferentially
                        main_content_match = re.search(r'<(main|article|div[^>]*class="[^"]*content[^"]*")[^>]*>(.*?)</\1>', clean_content, flags=re.DOTALL | re.IGNORECASE)
                        if main_content_match:
                            clean_content = main_content_match.group(2)

                        # Remove all remaining HTML tags
                        clean_content = re.sub(r'<[^>]+>', ' ', clean_content)

                        # Clean up whitespace and decode HTML entities
                        clean_content = re.sub(r'&nbsp;', ' ', clean_content)
                        clean_content = re.sub(r'&[a-zA-Z]+;', ' ', clean_content)
                        clean_content = re.sub(r'\s+', ' ', clean_content).strip()

                    elif 'application/json' in response.headers.get('content-type', ''):
                        # For JSON content, extract text values
                        try:
                            import json
                            json_data = json.loads(raw_content)
                            clean_content = json.dumps(json_data, indent=2)[:2000]
                        except:
                            clean_content = raw_content
                    else:
                        clean_content = raw_content

                    # Limit content length for LLM processing
                    if len(clean_content) > 8000:
                        clean_content = clean_content[:8000] + "..."

                    # Analyze the actual content with LLM
                    analysis_prompt = f"{fetch_prompt}\n\nContent to analyze:\n{clean_content}"
                    content = chat(analysis_prompt)

                except Exception as fetch_error:
                    print(f"⚠️ HTTP fetch failed for {url[:30]}: {fetch_error}")
                    try:
                        # Fallback: just ask LLM about the URL
                        content = chat(f"Based on the URL {url}, {fetch_prompt.lower()}")
                    except:
                        content = f"Unable to access content from {url}"


            if content and len(content.strip()) > 30:  # Lowered threshold for valid content
                # Determine content type more accurately
                content_type = 'web'
                if 'github.com' in url_lower:
                    content_type = 'github'
                elif any(domain in url_lower for domain in ['docs.', 'documentation', 'api.']):
                    content_type = 'documentation'
                elif any(domain in url_lower for domain in ['blog', 'medium.', 'dev.to']):
                    content_type = 'article'

                url_content[url] = {
                    'summary': content.strip(),
                    'type': content_type
                }
                print(f"✅ Fetched content from {url[:40]}...")
            else:
                print(f"⚠️ Insufficient content from {url[:40]}...")

        except Exception as e:
            print(f"❌ Failed to fetch {url[:40]}: {str(e)}")
            continue

    if url_content:
        print(f"✅ Successfully processed {len(url_content)} URLs")
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
                # Skip messages that are also app mentions to prevent duplicates
                text = event.get('text', '')
                if not ('<@' in text and any(bot_id in text for bot_id in [os.getenv("BOT_USER_ID", ""), "U"])):
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

                # Step 1.5: Check for URLs directly in user's message first
                user_urls = re.findall(r'http[s]?://\S+', user_query)

                analysis_result = analyze_query_for_context(user_query, available_channels)

                # Step 2: Handle URLs in user's message first, then gather context if needed
                url_content = {}
                if user_urls and (analysis_result.get("should_fetch_urls", False) or
                                  any(word in user_query.lower() for word in ['explain', 'summarize', 'what', 'describe'])):
                    print(f"🔍 Found URLs in message, fetching content...")
                    url_content = fetch_url_content(user_urls, user_query)

                if analysis_result.get("needs_context"):
                    print(f"🧠 Context needed: {analysis_result.get('reasoning', 'relevant content search')}")
                    channel_context = get_targeted_channel_context(client, analysis_result)

                    # Step 3: Generate response with targeted context
                    if channel_context or url_content:
                        context_summary = ""

                        # Add URL content first if available (from user's message)
                        if url_content:
                            context_summary += "FETCHED URL CONTENT:\n"
                            for url, data in url_content.items():
                                context_summary += f"\n🔗 {url}:\n"
                                context_summary += f"{data['summary'][:800]}\n"

                        # Add channel context if available
                        if channel_context:
                            context_summary += "\nSLACK WORKSPACE DATA:\n"
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

                        # Step 3.5: Handle URL fetching based on AI analysis
                        should_fetch_urls = analysis_result.get("should_fetch_urls", False)
                        url_keywords = ['readme', 'summarize', 'content', 'explain', 'link', 'url', 'github', 'documentation']
                        explicit_url_request = any(keyword in user_query.lower() for keyword in url_keywords)

                        urls_to_fetch = []

                        if all_urls:
                            context_summary += f"\n\nFOUND URLS: {', '.join(list(set(all_urls))[:5])}"

                            if should_fetch_urls or explicit_url_request:
                                urls_to_fetch = list(set(all_urls))
                                print(f"🔍 Processing {len(urls_to_fetch)} URLs...")

                        elif should_fetch_urls or explicit_url_request:
                            # No URLs found but AI thinks we need them - proactive search
                            print(f"🔍 Searching for relevant URLs across workspace...")

                            # Search all accessible channels for URLs
                            try:
                                channels_response = client.conversations_list(types="public_channel", exclude_archived=True)
                                if channels_response["ok"]:
                                    accessible_channels = [(ch["id"], ch["name"]) for ch in channels_response["channels"] if ch.get("is_member")]

                                    # Look for URLs in recent messages across all channels
                                    extended_urls = []
                                    for channel_id, channel_name in accessible_channels[:10]:  # Limit to 10 channels for performance
                                        try:
                                            recent_messages = client.conversations_history(channel=channel_id, limit=20)
                                            if recent_messages["ok"]:
                                                for msg in recent_messages["messages"]:
                                                    if 'text' in msg:
                                                        msg_urls = re.findall(r'http[s]?://\S+', msg['text'])
                                                        extended_urls.extend(msg_urls)
                                        except:
                                            continue

                                    if extended_urls:
                                        urls_to_fetch = list(set(extended_urls))[:5]  # Limit to 5 most recent URLs
                                        context_summary += f"\n\nEXTENDED SEARCH URLS: {', '.join(urls_to_fetch)}"
                                        print(f"✅ Found {len(urls_to_fetch)} URLs")
                            except Exception as e:
                                print(f"❌ Extended URL search failed: {str(e)}")

                        # Fetch URL content if we have URLs to process
                        if urls_to_fetch:
                            url_content = fetch_url_content(urls_to_fetch, user_query)

                            if url_content:
                                context_summary += "\n\nFETCHED URL CONTENT:\n"
                                for url, data in url_content.items():
                                    context_summary += f"\n🔗 {url}:\n"
                                    context_summary += f"{data['summary'][:800]}\n"  # Remove type info, limit length

                        # Create enhanced query that prioritizes URL content
                        if url_content:
                            enhanced_query = f"SYSTEM: You have targeted Slack workspace data including fetched URL content below. PRIORITIZE the URL content in your response as it contains the most relevant information for the user's query.\n\n{context_summary}\n\nUSER QUESTION: {user_query}\n\nINSTRUCTION: Base your response primarily on the FETCHED URL CONTENT above. Reference specific information from the URLs and supplement with channel context where relevant. Be precise about what you found and where."
                        else:
                            enhanced_query = f"SYSTEM: You have targeted Slack workspace data below based on the user's query. Use this information to provide a specific, helpful response.\n\n{context_summary}\n\nUSER QUESTION: {user_query}\n\nINSTRUCTION: Reference specific findings from the channels above. Be precise about what you found and where."

                        print(f"💬 Generating response...")
                        response = chat_with_solomon_persona(enhanced_query, context_summary)
                    elif url_content:
                        # Only URL content available, no channel context
                        context_summary = "FETCHED URL CONTENT:\n"
                        for url, data in url_content.items():
                            context_summary += f"\n🔗 {url}:\n"
                            context_summary += f"{data['summary'][:800]}\n"

                        enhanced_query = f"SYSTEM: You have fetched URL content below. Base your response on this content.\n\n{context_summary}\n\nUSER QUESTION: {user_query}\n\nINSTRUCTION: Use the URL content to provide a helpful response."
                        print(f"💬 Generating response from URL content...")
                        response = chat_with_solomon_persona(enhanced_query, context_summary)
                    else:
                        response = chat_with_solomon_persona(f"No relevant information found in workspace channels for: {user_query}")
                elif url_content:
                    # Only URL content, no workspace context needed
                    context_summary = "FETCHED URL CONTENT:\n"
                    for url, data in url_content.items():
                        context_summary += f"\n🔗 {url}:\n"
                        context_summary += f"{data['summary'][:800]}\n"

                    enhanced_query = f"SYSTEM: You have fetched URL content below. Base your response on this content.\n\n{context_summary}\n\nUSER QUESTION: {user_query}\n\nINSTRUCTION: Use the URL content to provide a helpful response."
                    print(f"💬 Generating response from URL content...")
                    response = chat_with_solomon_persona(enhanced_query, context_summary)
                else:
                    print(f"💬 No context needed")
                    response = chat_with_solomon_persona(user_query)

            except Exception as e:
                print(f"❌ Error, using fallback")
                response = chat_with_solomon_persona(user_query)

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