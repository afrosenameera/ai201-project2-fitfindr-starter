"""
agent.py

The FitFindr planning loop. Orchestrates the three tools in response to a
natural language user query, passing state between them via a session dict.

Complete tools.py and test each tool in isolation before implementing this file.

Usage (once implemented):
    from agent import run_agent
    from utils.data_loader import get_example_wardrobe

    result = run_agent(
        query="vintage graphic tee under $30, size M",
        wardrobe=get_example_wardrobe(),
    )
    print(result["fit_card"])
    print(result["error"])   # None on success
"""

import re

from tools import search_listings, suggest_outfit, create_fit_card


# ── session state ─────────────────────────────────────────────────────────────

def _new_session(query: str, wardrobe: dict) -> dict:
    """
    Initialize and return a fresh session dict for one user interaction.

    The session dict is the single source of truth for everything that happens
    during a run — it stores the original query, parsed parameters, tool results,
    and any error that caused early termination.

    You may add fields to this dict as needed for your implementation.
    """
    return {
        "query": query,              # original user query
        "parsed": {},                # extracted description / size / max_price
        "search_results": [],        # list of matching listing dicts
        "selected_item": None,       # top result, passed into suggest_outfit
        "wardrobe": wardrobe,        # user's wardrobe dict
        "outfit_suggestion": None,   # string returned by suggest_outfit
        "fit_card": None,            # string returned by create_fit_card
        "error": None,               # set if the interaction ended early
    }


def _parse_query(query: str) -> dict:
    """
    Parse the natural language query to extract description, size, and max_price
    using regex. Strips size/price tokens from the description so only clothing
    keywords remain for search_listings.

    Returns a dict with keys: description (str), size (str|None), max_price (float|None)
    """
    # Extract size — "size M", "size XL", or standalone S/M/L/XL/XXL
    size = None
    size_match = re.search(r'\bsize\s+([A-Z]{1,3})\b', query, re.IGNORECASE)
    if size_match:
        size = size_match.group(1).upper()
    else:
        standalone = re.search(r'\b(XS|S|M|L|XL|XXL)\b', query)
        if standalone:
            size = standalone.group(1).upper()

    # Extract max_price — "under $30", "under 30", "$30"
    max_price = None
    price_match = re.search(r'(?:under\s+)?\$?(\d+(?:\.\d+)?)\s*(?:dollars?)?', query, re.IGNORECASE)
    if price_match:
        max_price = float(price_match.group(1))

    # Build description by stripping size/price/filler words from query
    description = query
    description = re.sub(r'\bsize\s+[A-Z]{1,3}\b', '', description, flags=re.IGNORECASE)
    description = re.sub(r'(?:under\s+)?\$?\d+(?:\.\d+)?\s*(?:dollars?)?', '', description, flags=re.IGNORECASE)
    description = re.sub(r'\b(XS|S|M|L|XL|XXL)\b', '', description)
    description = re.sub(r'\b(looking for|i want|find me|i need)\b', '', description, flags=re.IGNORECASE)
    description = " ".join(description.split())

    return {
        "description": description,
        "size": size,
        "max_price": max_price,
    }


# ── planning loop ─────────────────────────────────────────────────────────────

def run_agent(query: str, wardrobe: dict) -> dict:
    """
    Main agent entry point. Runs the FitFindr planning loop for a single
    user interaction and returns the completed session dict.

    Args:
        query:    Natural language user request
                  (e.g., "vintage graphic tee under $30, size M")
        wardrobe: User's wardrobe dict — use get_example_wardrobe() or
                  get_empty_wardrobe() from utils/data_loader.py

    Returns:
        The session dict after the interaction completes. Check session["error"]
        first — if it is not None, the interaction ended early and the other
        output fields (outfit_suggestion, fit_card) will be None.
    """
    # Step 1: Initialize session
    session = _new_session(query, wardrobe)

    # Step 2: Parse query to extract description, size, max_price
    parsed = _parse_query(query)
    session["parsed"] = parsed
    description = parsed["description"]
    size = parsed["size"]
    max_price = parsed["max_price"]

    print(f"[agent] Parsed → description='{description}' size={size} max_price={max_price}")

    # Step 3: Call search_listings
    results = search_listings(description, size=size, max_price=max_price)
    session["search_results"] = results

    # BRANCH: no results → set error and return early, do NOT call suggest_outfit
    if not results:
        session["error"] = (
            f"No listings found for \"{description}\""
            + (f" in size {size}" if size else "")
            + (f" under ${max_price}" if max_price else "")
            + ". Try broadening your search — remove the size filter, "
            "raise the price limit, or use different keywords."
        )
        print(f"[agent] No results — returning early.")
        return session

    # Step 4: Select top result
    session["selected_item"] = results[0]
    print(f"[agent] Selected: {results[0]['title']} (${results[0]['price']})")

    # Step 5: Call suggest_outfit
    outfit = suggest_outfit(session["selected_item"], wardrobe)
    session["outfit_suggestion"] = outfit

    if outfit.startswith("[suggest_outfit ERROR]"):
        session["error"] = outfit
        print(f"[agent] suggest_outfit failed — returning early.")
        return session

    # Step 6: Call create_fit_card
    fit_card = create_fit_card(outfit, session["selected_item"])
    session["fit_card"] = fit_card

    if fit_card.startswith("[create_fit_card ERROR]"):
        session["error"] = fit_card

    # Step 7: Return session
    print(f"[agent] Complete.")
    return session


# ── CLI test ──────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    from utils.data_loader import get_example_wardrobe, get_empty_wardrobe

    print("=== Happy path: graphic tee ===\n")
    session = run_agent(
        query="looking for a vintage graphic tee under $30",
        wardrobe=get_example_wardrobe(),
    )
    if session["error"]:
        print(f"Error: {session['error']}")
    else:
        print(f"Found: {session['selected_item']['title']}")
        print(f"\nOutfit: {session['outfit_suggestion']}")
        print(f"\nFit card: {session['fit_card']}")

    print("\n\n=== No-results path ===\n")
    session2 = run_agent(
        query="designer ballgown size XXS under $5",
        wardrobe=get_example_wardrobe(),
    )
    print(f"Error message: {session2['error']}")