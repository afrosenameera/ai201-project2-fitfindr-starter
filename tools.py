"""
tools.py

The three required FitFindr tools. Each tool is a standalone function that
can be called and tested independently before being wired into the agent loop.

Complete and test each tool before moving to agent.py.

Tools:
    search_listings(description, size, max_price)  → list[dict]
    suggest_outfit(new_item, wardrobe)              → str
    create_fit_card(outfit, new_item)               → str
"""

import os
import random

from dotenv import load_dotenv
from groq import Groq

from utils.data_loader import load_listings

load_dotenv()


# ── Groq client ───────────────────────────────────────────────────────────────

def _get_groq_client():
    """Initialize and return a Groq client using GROQ_API_KEY from .env."""
    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        raise ValueError(
            "GROQ_API_KEY not set. Add it to a .env file in the project root."
        )
    return Groq(api_key=api_key)


def _call_llm(prompt: str, temperature: float = 0.85) -> str:
    """Call Groq LLM and return response text. Returns error string on failure."""
    try:
        client = _get_groq_client()
        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=512,
            temperature=temperature,
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        return f"[LLM ERROR] {e}"


# ── Tool 1: search_listings ───────────────────────────────────────────────────

def search_listings(
    description: str,
    size: str | None = None,
    max_price: float | None = None,
) -> list[dict]:
    """
    Search the mock listings dataset for items matching the description,
    optional size, and optional price ceiling.

    Args:
        description: Keywords describing what the user is looking for
                     (e.g., "vintage graphic tee").
        size:        Size string to filter by, or None to skip size filtering.
                     Matching is case-insensitive (e.g., "M" matches "S/M").
        max_price:   Maximum price (inclusive), or None to skip price filtering.

    Returns:
        A list of matching listing dicts, sorted by relevance (best match first).
        Returns an empty list if nothing matches — does NOT raise an exception.

    Each listing dict has the following fields:
        id, title, description, category, style_tags (list), size,
        condition, price (float), colors (list), brand, platform
    """
    try:
        listings = load_listings()
    except Exception as e:
        print(f"[search_listings] Failed to load listings: {e}")
        return []

    # 1. Extract keywords (words longer than 2 chars)
    keywords = [w.lower() for w in description.lower().split() if len(w) > 2]

    scored = []
    for item in listings:
        # 2. Filter by max_price
        if max_price is not None and item.get("price", 9999) > max_price:
            continue

        # 2. Filter by size (case-insensitive)
        if size is not None:
            item_size = item.get("size", "").upper()
            if size.upper() not in item_size:
                continue

        # 3. Score by keyword overlap against title, description, style_tags, category
        searchable = " ".join([
            item.get("title", ""),
            item.get("description", ""),
            " ".join(item.get("style_tags", [])),
            item.get("category", ""),
        ]).lower()

        score = sum(1 for kw in keywords if kw in searchable)

        # 4. Drop listings with score of 0
        if score > 0:
            scored.append((score, item))

    # 5. Sort by score descending, return dicts
    scored.sort(key=lambda x: x[0], reverse=True)
    return [item for _, item in scored]


# ── Tool 2: suggest_outfit ────────────────────────────────────────────────────

def suggest_outfit(new_item: dict, wardrobe: dict) -> str:
    """
    Given a thrifted item and the user's wardrobe, suggest 1–2 complete outfits.

    Args:
        new_item: A listing dict (the item the user is considering buying).
        wardrobe: A wardrobe dict with an 'items' key containing a list of
                  wardrobe item dicts. May be empty — handle this gracefully.

    Returns:
        A non-empty string with outfit suggestions.
        If the wardrobe is empty, offer general styling advice for the item
        rather than raising an exception or returning an empty string.
    """
    if not new_item:
        return "[suggest_outfit ERROR] No item provided. Cannot generate outfit suggestion."

    title = new_item.get("title", "the item")
    desc = new_item.get("description", "")
    tags = ", ".join(new_item.get("style_tags", []))
    colors = ", ".join(new_item.get("colors", []))

    # 1. Check whether wardrobe['items'] is empty
    wardrobe_items = wardrobe.get("items", [])

    # 2. Empty wardrobe — general styling advice
    if not wardrobe_items:
        prompt = f"""You are a creative thrift fashion stylist. A user just found this secondhand item and wants general styling advice.

Item: {title}
Description: {desc}
Style tags: {tags}
Colors: {colors}

The user hasn't shared their wardrobe. Give general styling advice — what kinds of bottoms, shoes, or layers pair well with this piece, and what overall vibe it suits. Be specific and conversational. Under 100 words."""

    # 3. Non-empty wardrobe — specific combinations using named pieces
    else:
        wardrobe_str = "\n".join(
            f"- {w.get('title', '?')} ({w.get('category', '?')}, colors: {', '.join(w.get('colors', []))})"
            for w in wardrobe_items
        )
        prompt = f"""You are a creative thrift fashion stylist. A user just found a secondhand item and wants outfit ideas using their existing wardrobe.

New item: {title}
Description: {desc}
Style tags: {tags}
Colors: {colors}

Their wardrobe includes:
{wardrobe_str}

Suggest 1–2 specific outfit combinations using the new item and named pieces from their wardrobe. Be concrete about how to style it and what vibe it creates. Under 100 words."""

    # 4. Call LLM and return response
    result = _call_llm(prompt, temperature=0.85)

    if result.startswith("[LLM ERROR]"):
        return (
            f"Style the {title} with high-waisted bottoms and chunky sneakers for "
            f"a relaxed, vintage-inspired look. The {colors} tones pair well with "
            f"neutral basics already in your wardrobe."
        )

    return result


# ── Tool 3: create_fit_card ───────────────────────────────────────────────────

def create_fit_card(outfit: str, new_item: dict) -> str:
    """
    Generate a short, shareable outfit caption for the thrifted find.

    Args:
        outfit:   The outfit suggestion string from suggest_outfit().
        new_item: The listing dict for the thrifted item.

    Returns:
        A 2–4 sentence string usable as an Instagram/TikTok caption.
        If outfit is empty or missing, return a descriptive error message
        string — do NOT raise an exception.

    The caption should:
    - Feel casual and authentic (like a real OOTD post, not a product description)
    - Mention the item name, price, and platform naturally (once each)
    - Capture the outfit vibe in specific terms
    - Sound different each time for different inputs (use higher LLM temperature)
    """
    # 1. Guard against empty or whitespace-only outfit string
    if not outfit or not outfit.strip():
        return "[create_fit_card ERROR] Cannot generate a fit card — outfit description is empty."

    if not new_item:
        return "[create_fit_card ERROR] Cannot generate a fit card — no item data provided."

    title = new_item.get("title", "this piece")
    price = new_item.get("price", "?")
    platform = new_item.get("platform", "a thrift app")
    condition = new_item.get("condition", "good condition")

    # Random seed so outputs vary across calls
    seed = random.randint(1000, 9999)

    # 2. Build prompt with item details and outfit context
    prompt = f"""Write an Instagram caption for a thrift fashion post. Make it sound authentic and casual — like a real person, not a brand. Use lowercase, 1–2 emojis, and thrift-culture language. Mention the item name, price, and platform naturally. 2–4 sentences max.

Item: {title}
Price: ${price}
Platform: {platform}
Condition: {condition}
Outfit: {outfit}

(variation seed: {seed})"""

    # 3. Call LLM with high temperature for variety
    result = _call_llm(prompt, temperature=1.0)

    if result.startswith("[LLM ERROR]"):
        return (
            f"thrifted this {title.lower()} for ${price} on {platform} and honestly "
            f"it's giving everything 🖤 full look on my stories"
        )

    return result