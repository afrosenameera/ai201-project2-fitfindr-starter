Run the app:
```bash
python app.py
```

---

## Tool Inventory

### 1. `search_listings(description, size, max_price)`

**Purpose:** Search the mock listings dataset for items matching a natural language description, with optional size and price filters. Returns results ranked by keyword relevance.

**Inputs:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `description` | `str` | Keywords describing the desired item (e.g. `"vintage graphic tee"`) |
| `size` | `str` or `None` | Size filter (e.g. `"M"`). `None` skips size filtering. |
| `max_price` | `float` or `None` | Maximum price in dollars. `None` skips price filtering. |

**Returns:** `list[dict]` — Listing dicts sorted by relevance score. Each dict contains: `id (str)`, `title (str)`, `description (str)`, `category (str)`, `style_tags (list[str])`, `size (str)`, `condition (str)`, `price (float)`, `colors (list[str])`, `brand (str)`, `platform (str)`. Returns `[]` if no matches — never raises an exception.

---

### 2. `suggest_outfit(new_item, wardrobe)`

**Purpose:** Generate 1–2 specific outfit combinations using a thrifted item and the user's existing wardrobe. If the wardrobe is empty, provides general styling advice instead.

**Inputs:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `new_item` | `dict` | A listing dict from `search_listings` for the item being considered |
| `wardrobe` | `dict` | Wardrobe dict with key `"items"` (list of wardrobe-item dicts). May be `{"items": []}`. |

**Returns:** `str` — Outfit suggestions up to ~100 words. General styling advice if wardrobe is empty. Template fallback string if LLM is unavailable.

---

### 3. `create_fit_card(outfit, new_item)`

**Purpose:** Generate a short Instagram/TikTok-style caption for the final outfit. Uses high LLM temperature and a random seed to ensure varied outputs across calls.

**Inputs:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `outfit` | `str` | Outfit suggestion string from `suggest_outfit` |
| `new_item` | `dict` | Listing dict for the thrifted piece (provides title, price, platform) |

**Returns:** `str` — A 2–4 sentence caption in lowercase with emojis. Returns a descriptive error string (not an exception) if `outfit` is empty or `new_item` is `None`.

---

## How the Planning Loop Works

`run_agent()` in `agent.py` uses a conditional planning loop — not a fixed pipeline. Here is the exact logic:

1. **Parse** the user's query with regex to extract `description`, `size`, and `max_price`. Store in `session["parsed"]`.

2. **Call `search_listings`** with the parsed parameters.
   - If results is empty → set `session["error"]` with an actionable message and **return immediately**. `suggest_outfit` and `create_fit_card` are never called.
   - If results is non-empty → set `session["selected_item"] = results[0]` and continue.

3. **Call `suggest_outfit`** with `session["selected_item"]` and the wardrobe.
   - If it returns an error string → set `session["error"]` and return early.
   - Otherwise continue.

4. **Call `create_fit_card`** with `session["outfit_suggestion"]` and `session["selected_item"]`. Store result and return.

The agent behaves differently for different inputs — it does not call all three tools unconditionally every time.

---

## State Management

All state lives in a single `session` dict created at the start of `run_agent()`:

| Key | Type | Set When | Used By |
|-----|------|----------|---------|
| `"query"` | `str` | Immediately | Logging |
| `"parsed"` | `dict` | After query parsing | `search_listings` inputs |
| `"search_results"` | `list[dict]` | After `search_listings` | Planning loop branch |
| `"selected_item"` | `dict or None` | After non-empty search | `suggest_outfit`, `create_fit_card` |
| `"wardrobe"` | `dict` | Immediately | `suggest_outfit` |
| `"outfit_suggestion"` | `str or None` | After `suggest_outfit` | `create_fit_card` |
| `"fit_card"` | `str or None` | After `create_fit_card` | UI display |
| `"error"` | `str or None` | On any failure | Displayed to user |

The user never re-enters data between steps. The item from `search_listings` passes directly into `suggest_outfit`, and the outfit from `suggest_outfit` passes directly into `create_fit_card` — all through the session dict without any re-entry.

---

## Error Handling

| Tool | Failure Mode | What the Agent Does |
|------|-------------|---------------------|
| `search_listings` | No listings match the query | Returns `[]`. Agent sets `session["error"]` = "No listings found for '[query]'... Try broadening your search — remove the size filter, raise the price limit, or use different keywords." Returns early, never calls other tools. |
| `suggest_outfit` | Empty wardrobe | Detects empty `wardrobe["items"]`, sends a different LLM prompt asking for general styling advice instead of wardrobe-specific combinations. Returns a useful string, never crashes. |
| `create_fit_card` | Empty outfit string | Returns `"[create_fit_card ERROR] Cannot generate a fit card — outfit description is empty."` immediately without calling the LLM. |

### Concrete examples from testing

**search_listings returns empty:**
```bash
python -c "from tools import search_listings; print(search_listings('designer ballgown', size='XXS', max_price=5))"
# Output: []
```
The agent responds: *"No listings found for 'designer ballgown' in size XXS under $5.0. Try broadening your search — remove the size filter, raise the price limit, or use different keywords."*

**create_fit_card with empty outfit:**
```bash
python -c "
from tools import search_listings, create_fit_card
results = search_listings('vintage graphic tee', size=None, max_price=50)
print(create_fit_card('', results[0]))
"
# Output: "[create_fit_card ERROR] Cannot generate a fit card — outfit description is empty."
```

**suggest_outfit with empty wardrobe:**
```bash
python -c "
from tools import search_listings, suggest_outfit
from utils.data_loader import get_empty_wardrobe
results = search_listings('vintage graphic tee', size=None, max_price=50)
print(suggest_outfit(results[0], get_empty_wardrobe()))
"
# Output: General styling advice string — not an error, not a crash
```

---

## Spec Reflection

**One way planning.md helped:** Writing the planning loop conditional logic before any code made it clear that `suggest_outfit` should never be called with empty input. Without that explicit branch in the spec, it would have been easy to accidentally pass `None` into the LLM and get a broken response.

**One divergence from spec:** The original spec described `suggest_outfit` returning an error string when the wardrobe was empty. During implementation it became clear that returning an error forces the agent to stop — but the user still found a great item and deserves a fit card. The better behavior was to return general styling advice instead, so the full flow can still complete. The spec was updated to reflect this after testing.

---

## AI Usage

### Instance 1: `search_listings` implementation

I gave Claude the Tool 1 spec block from `planning.md` (parameter names, types, return value, failure mode) and asked it to implement the function using `load_listings()` from `utils/data_loader.py`. Claude generated a keyword-scoring approach. Before using it I checked: does it filter by all three parameters? Does it return `[]` instead of raising on no results? I found the original raised a `ValueError` on no results — I revised it to return `[]` to match the spec.

### Instance 2: Planning loop (`run_agent`)

I gave Claude the Architecture diagram from `planning.md` and the Planning Loop and State Management sections. Claude generated a `run_agent()` that called all three tools unconditionally with no early return on empty results. I identified this by comparing against my spec's branch condition and revised the function to add the `if not results:` early-return branch before `suggest_outfit` is ever called.
