"""Minimal twikit demo — test login and search.

Usage:
    # Set env vars first:
    export TWIKIT_USERNAME=your_username
    export TWIKIT_EMAIL=your_email@example.com
    export TWIKIT_PASSWORD=your_password

    # Then run:
    python scripts/test_twikit.py
"""

import asyncio
import os
import sys
from pathlib import Path


async def main():
    try:
        from twikit import Client
    except ImportError:
        print("ERROR: twikit not installed. Run: pip install twikit")
        sys.exit(1)

    import twikit
    print(f"twikit version: {twikit.__version__}")

    username = os.environ.get("TWIKIT_USERNAME", "")
    email = os.environ.get("TWIKIT_EMAIL", "")
    password = os.environ.get("TWIKIT_PASSWORD", "")

    if not username or not password:
        print("ERROR: Set TWIKIT_USERNAME, TWIKIT_EMAIL, TWIKIT_PASSWORD env vars")
        sys.exit(1)

    print(f"Username: {username}")
    print(f"Email: {email[:3]}***")
    print()

    cookies_path = Path(".twikit_cookies.json")
    client = Client("en-US")

    # Step 1: Login or load cookies
    if cookies_path.exists():
        print("[1] Loading cookies from file...")
        client.load_cookies(str(cookies_path))
        print("    OK - cookies loaded")
    else:
        print("[1] Logging in with credentials...")
        try:
            await client.login(
                auth_info_1=username,
                auth_info_2=email,
                password=password,
            )
            client.save_cookies(str(cookies_path))
            print(f"    OK - logged in, cookies saved to {cookies_path}")
        except Exception as e:
            print(f"    FAILED: {type(e).__name__}: {e}")
            print()
            print("Possible fixes:")
            print("  1. pip install --upgrade twikit")
            print("  2. Disable 2FA on your X account")
            print("  3. Check username/email/password are correct")
            sys.exit(1)

    # Step 2: Search tweets
    print()
    print("[2] Searching tweets for 'AI Agent'...")
    try:
        results = await client.search_tweet("AI Agent", product="Top", count=5)
        print(f"    Found {len(results)} tweets:")
        print()
        for i, tweet in enumerate(results[:5], 1):
            user = tweet.user
            name = user.name if user else "Unknown"
            handle = user.screen_name if user else ""
            text = (tweet.full_text or tweet.text or "")[:100]
            likes = getattr(tweet, "favorite_count", 0) or 0
            rts = getattr(tweet, "retweet_count", 0) or 0
            print(f"    {i}. @{handle} ({name})")
            print(f"       {text}...")
            print(f"       ❤️ {likes}  🔁 {rts}")
            print()
    except Exception as e:
        print(f"    FAILED: {type(e).__name__}: {e}")
        sys.exit(1)

    print("✅ twikit is working! You can now run: python -m src.main --twitter")


if __name__ == "__main__":
    asyncio.run(main())
