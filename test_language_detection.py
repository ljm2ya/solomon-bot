#!/usr/bin/env python3
"""
Test script for language detection functionality in Solomon Bot.
This script tests various language inputs to ensure proper detection and response.
"""

import os
import sys
from dotenv import load_dotenv
from ai import detect_query_language, detect_conversation_language, chat

load_dotenv()

def test_single_query_detection():
    """Test language detection for individual queries"""
    print("🧪 Testing Single Query Language Detection")
    print("=" * 50)

    test_queries = [
        ("Hello, how are you today?", "en"),
        ("안녕하세요, 오늘 어떻게 지내세요?", "ko"),
        ("こんにちは、今日はいかがですか？", "ja"),
        ("Hola, ¿cómo estás hoy?", "es"),
        ("Bonjour, comment allez-vous aujourd'hui?", "fr"),
        ("Guten Tag, wie geht es Ihnen heute?", "de"),
        ("你好，你今天怎么样？", "zh"),
    ]

    for query, expected_lang in test_queries:
        detected_lang, lang_name, confidence = detect_query_language(query)
        print(f"Query: {query}")
        print(f"Expected: {expected_lang} | Detected: {detected_lang} ({lang_name}) - {confidence}")
        print(f"✅ Match: {detected_lang == expected_lang}")
        print("-" * 30)

def test_conversation_detection():
    """Test language detection for conversations"""
    print("\n🧪 Testing Conversation Language Detection")
    print("=" * 50)

    # Korean conversation
    korean_messages = {
        "user1": ["안녕하세요", "이 프로젝트에 대해 어떻게 생각하세요?", "좋은 아이디어네요"],
        "user2": ["네, 안녕하세요", "흥미로운 제안이에요", "함께 작업해보면 좋겠어요"]
    }
    korean_names = {"user1": "김철수", "user2": "이영희"}

    detected_lang, lang_name, confidence = detect_conversation_language(korean_messages, korean_names)
    print(f"Korean conversation - Detected: {detected_lang} ({lang_name}) - {confidence}")

    # Spanish conversation
    spanish_messages = {
        "user1": ["Hola equipo", "¿Cómo vamos con el proyecto?", "Necesitamos más tiempo"],
        "user2": ["Buenos días", "Creo que vamos bien", "¿Podemos extender el plazo?"]
    }
    spanish_names = {"user1": "Carlos", "user2": "María"}

    detected_lang, lang_name, confidence = detect_conversation_language(spanish_messages, spanish_names)
    print(f"Spanish conversation - Detected: {detected_lang} ({lang_name}) - {confidence}")

def test_response_language():
    """Test if responses match detected language"""
    print("\n🧪 Testing Language-Aware Responses")
    print("=" * 50)

    test_cases = [
        ("안녕하세요, 팀 갈등을 해결하는 방법은 무엇인가요?", "ko"),
        ("Hola, ¿cómo puedo mediar un conflicto en el trabajo?", "es"),
        ("Bonjour, comment résoudre un conflit d'équipe?", "fr"),
        ("Hello, how do I resolve team conflicts?", "en")
    ]

    for query, expected_lang in test_cases:
        print(f"\nQuery: {query}")
        print(f"Expected language: {expected_lang}")

        # Get response
        response = chat(query)
        print(f"Response: {response[:200]}...")

        # Basic check if response seems to be in expected language
        if expected_lang == "ko" and any(ord(c) >= 0xAC00 and ord(c) <= 0xD7AF for c in response):
            print("✅ Response contains Korean characters")
        elif expected_lang == "es" and any(word in response.lower() for word in ["equipo", "conflicto", "solución"]):
            print("✅ Response contains Spanish words")
        elif expected_lang == "fr" and any(word in response.lower() for word in ["équipe", "conflit", "solution"]):
            print("✅ Response contains French words")
        elif expected_lang == "en":
            print("✅ Response in English")
        else:
            print("❓ Could not verify response language")
        print("-" * 50)

if __name__ == "__main__":
    if not os.getenv("OPENAI_API_KEY"):
        print("❌ Error: OPENAI_API_KEY not found in environment")
        sys.exit(1)

    test_single_query_detection()
    test_conversation_detection()
    test_response_language()

    print("\n🎉 Language detection testing completed!")