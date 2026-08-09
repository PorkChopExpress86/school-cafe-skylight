# Skylight Calendar API — Research Report

**Goal:** Write Python code that reads from and writes to a Skylight Calendar account, specifically to add items to the meal plan (e.g., a daily "lunch" entry from a school menu).

**Date of research:** 2026‑08.
**Sources (fetched directly, not paraphrased):**
- `github.com/aarons22/skylight-tools` — `API_REFERENCE.md` + `openapi.yaml` (HAR‑derived reference).
- `github.com/joshuaswarren/pyskylight` — Python client + CLI source (`auth.py`, `client.py`, `cli.py`, `constants.py`, `models.py`).
- `github.com/TheEagleByte/skylight-api` — HAR→OpenAPI generator; published Swagger / ReDoc at `theeaglebyte.github.io/skylight-api/`.
- `github.com/chrischall/skylight-mcp` — confirms `skylight-api-version` header requirement.
- Web search: Home Assistant community thread, kylebjordahl/skylight-calendar-home-assistant, kylejfrost/skylight-api-cli.

---

## 1. Official vs Unofficial status

### There is no official public API

- The Home Assistant community thread (April 2026) shows Skylight support explicitly telling users: *"At this time, Skylight does not offer a public Open API for third‑party smart home integrations."*
- All public libraries — `pyskylight`, `skylight-tools`, `kylejfrost/skylight-api-cli`, `mightybandito/Skylight`, `chrischall/skylight-mcp`, `TheEagleByte/skylight-api` — are **unofficial and reverse‑engineered** from network traffic captured by browsing the web app.
- No SDK, no partner program, no public docs from Skylight.

### Base URL

**Sole active host:** `https://app.ourskylight.com`

- Quoted from `aarons22/skylight-tools/openapi.yaml`:
  > `Note: api.ourskylight.com does not resolve. app.ourskylight.com is the sole active host.`
- The aarons22 reference still uses the older `https://api.ourskylight.com/api` form (left over from earlier community docs), but every actively‑maintained project (pyskylight, skylight-mcp, TheEagleByte) treats `app.ourskylight.com` as authoritative. The newer `chrischall/skylight-mcp` even defaults `SKYLIGHT_BASE_URL` to `https://app.ourskylight.com/api`.
- Data endpoints live under `/api/...` (the `/oauth/...` and `/auth/...` endpoints sit at the host root).

### Legal / ToS implications

- All reverse‑engineered clients include a "personal use only" legal notice. Quoting `pyskylight/README.md`:
  > *"Unofficial and not affiliated with, endorsed by, or supported by Skylight. The API can change without notice. Use only with your own account and data; do not build a multi‑tenant or commercial service on it."*
- For a personal automation script that drives your own account with your own email/password, you are acting like the official web app — there is no documented ToS prohibition on automation, but the API can break at any time and you should expect no support from Skylight.
- Don't distribute credentials or tokens; use `0600` token cache files (`pyskylight` already does this).

---

## 2. Authentication

### OAuth2 Authorization Code + PKCE (the only working login)

The legacy `POST /api/sessions` email‑password endpoint documented in the aarons22 reference (returning `{"data":{"id":..., "type":"users", "attributes":{"token":...}}}` with Basic auth on `user_id:token`) is **dead**.

`pyskylight`'s README states (verified 2026‑06 against the live API):
> *"The older `POST /api/sessions` email/password endpoint is version‑gated and effectively retired (it returns 'This version of Skylight is no longer supported'), which is why this client uses the OAuth flow."*

The flow uses the **same endpoints the mobile/web app uses**:

| Step | Method | URL | Purpose |
|------|--------|-----|---------|
| 1 | GET | `https://app.ourskylight.com/oauth/authorize?response_type=code&client_id=skylight-mobile&redirect_uri=skylight-family://welcome&scope=everything&state=...&code_challenge=...&code_challenge_method=S256&prompt=login` | Loads login page (carries CSRF `authenticity_token`). |
| 2 | POST | `https://app.ourskylight.com/auth/session` (form: `authenticity_token`, `email`, `password`) | Submits credentials. |
| 3 | (redirect) | Server responds 302 → eventually `Location: skylight-family://welcome?code=<auth_code>&state=<state>` | Carries the authorization code in the custom URL scheme. |
| 4 | POST | `https://app.ourskylight.com/oauth/token` (form: `grant_type=authorization_code`, `client_id=skylight-mobile`, `code`, `redirect_uri`, `code_verifier`) | Exchanges code for Bearer + Refresh tokens. |

**OAuth constants** (from `pyskylight/constants.py`):
```python
OAUTH_CLIENT_ID = "skylight-mobile"
OAUTH_SCOPE = "everything"
OAUTH_REDIRECT_URI = "skylight-family://welcome"
OAUTH_CODE_CHALLENGE_METHOD = "S256"
```

**The redirect scheme trick:** the app uses a custom URL scheme `skylight-family://welcome` — a browser normally intercepts this, but a programmatic client just reads the `Location` header of the 302 after the credential POST and parses the `code` from the query string. `pyskylight/auth.py` does exactly this:

```python
location = _chase_to_redirect(client, resp, base_url)
if not (location and location.startswith("skylight-family:")):
    raise SkylightAuthError("Invalid Skylight email or password")
query = parse_qs(urlparse(location).query)
code = query.get("code", [""])[0]
```

### Bearer token usage

All data requests after login:
```
Authorization: Bearer <access_token>
Accept: application/json
User-Agent: SkylightMobile (web)        # older clients; skylight-mcp uses an explicit version header instead
```

**Critical new requirement — `skylight-api-version` header.** From `chrischall/skylight-mcp/README.md`:
> *"Every API request carries the `skylight-api-version: 2026-05-01` header (matching the official mobile app); without it some features 422 with 'API version does not support …'."*

Known good values reported by community projects:
- `2026-05-01` — `chrischall/skylight-mcp`
- `2026-03-01` — `skylightctl` (PyPI)
- Older projects omit it (and may work for older endpoints).

**Practical advice:** send `skylight-api-version: 2026-05-01` (or whatever the latest mobile release is) on every request. If a 422 starts appearing, search for the latest known‑good value in the community.

### Token refresh

```
POST https://app.ourskylight.com/oauth/token
Content-Type: application/x-www-form-urlencoded

grant_type=refresh_token
&client_id=skylight-mobile
&refresh_token=<refresh_token>
```

From `pyskylight/auth.py`:
```python
token_resp = client.post(
    base_url + "/oauth/token",
    data={
        "grant_type": "refresh_token",
        "client_id": OAUTH_CLIENT_ID,
        "refresh_token": refresh_token,
    },
    headers={"User-Agent": BROWSER_UA},
)
```

Token response shape (`OAuthTokenResponse` in the OpenAPI spec):
```json
{
  "access_token": "...",
  "token_type": "Bearer",
  "expires_in": 7200,
  "refresh_token": "...",
  "scope": "everything",
  "created_at": 1717000000
}
```

- `expires_in`: 7200 seconds (2 hours) per the aarons22 OpenAPI spec. The `skylight-mcp` README also notes a **7‑day** refresh‑token lifetime.
- `pyskylight` caches the token at `${XDG_CACHE_HOME:-~/.cache}/pyskylight/token.json` (mode `0600`) and automatically refreshes if expired.

### Required headers summary

| Header | Required | Example / Notes |
|--------|----------|-----------------|
| `Authorization` | yes | `Bearer <access_token>` |
| `Accept` | recommended | `application/json` |
| `User-Agent` | depends on library | `SkylightMobile (web)` (legacy) — pyskylight uses its own UA; skylight-mcp sets `skylight-api-version` instead |
| `skylight-api-version` | strongly recommended for newer features | `2026-05-01` |
| `Content-Type` | for POST/PATCH/PUT | `application/json` |

### How to obtain `frame_id` (household ID) after login

```python
GET https://app.ourskylight.com/api/frames
Authorization: Bearer <access_token>
```

Response:
```json
{
  "data": [
    {
      "id": "12345",
      "type": "approved_viewer_frame",
      "attributes": {
        "name": "Smith Family Frame",
        "timezone": "America/New_York",
        "plus": false,
        ...
      }
    }
  ]
}
```

Use `data[0].id` as your `frame_id` (almost everyone has exactly one frame). `pyskylight` exposes this as `SkylightClient.list_frames()` returning `List[Frame]`. The `attributes.name` is the household name; `attributes.timezone` is the frame's IANA TZ (used by `events` queries).

---

## 3. Meal‑plan READ endpoints

All under `/api/frames/{frame_id}/meals/...`. JSON:API style: `{"data":[...], "included":[...], "meta":{...}}`.

### GET meal categories

```
GET /api/frames/{frame_id}/meals/categories
Authorization: Bearer <token>
```

Response (from `aarons22/skylight-tools/API_REFERENCE.md`):
```json
{
  "data": [
    {"id":"breakfast_category_id","type":"meal_category","attributes":{"label":"Breakfast","color":"#A8D4D3","enabled":true,"position":0}},
    {"id":"lunch_category_id",  "type":"meal_category","attributes":{"label":"Lunch",    "color":"#F66951","enabled":true,"position":1}},
    {"id":"dinner_category_id", "type":"meal_category","attributes":{"label":"Dinner",   "color":"#915EA1","enabled":true,"position":2}},
    {"id":"snack_category_id",  "type":"meal_category","attributes":{"label":"Snack",    "color":"#FDC36D","enabled":false,"position":3}}
  ]
}
```

Note: Snack is `enabled:false` by default — a basic account may not be able to assign meals to Snack. The four labels (`Breakfast`, `Lunch`, `Dinner`, `Snack`) are stable across accounts but the IDs are per‑account.

### GET recipes

```
GET /api/frames/{frame_id}/meals/recipes?include=meal_category
Authorization: Bearer <token>
```

Response:
```json
{
  "data": [
    {
      "id":"recipe_id_1","type":"meal_recipe",
      "attributes":{"summary":"Hot Dogs","description":"Ingredients:\n- Hot dogs\n- Hot dog buns\n\nInstructions:\n1. Grill and serve."},
      "relationships":{"meal_category":{"data":{"id":"dinner_category_id","type":"meal_category"}}}
    }
  ],
  "included":[
    {"id":"dinner_category_id","type":"meal_category","attributes":{"label":"Dinner","color":"#915EA1","enabled":true,"position":2}}
  ]
}
```

`type` is always `meal_recipe`. `attributes.summary` is the title; `attributes.description` is free‑form (often ingredients + instructions concatenated) and may be `null`.

### GET single recipe

```
GET /api/frames/{frame_id}/meals/recipes/{recipe_id}?include=meal_category
```

Returns the same shape as one element of the list, wrapped in `{"data": {...}}` plus optional `included`.

### GET meal sittings (date range)

```
GET /api/frames/{frame_id}/meals/sittings
    ?date_min=2026-03-01
    &date_max=2026-04-01
    &include=meal_category,meal_recipe
Authorization: Bearer <token>
```

Response:
```json
{
  "data": [
    {
      "id":"sitting123","type":"meal_sitting",
      "attributes":{
        "summary":"Pancakes and Eggs","description":"","note":"",
        "rrule":null,"recurring":false,
        "instances":["2026-03-01"]
      },
      "relationships":{
        "meal_category":{"data":{"id":"breakfast_category_id","type":"meal_category"}},
        "meal_recipe":{"data":{"id":"recipe456","type":"meal_recipe"}}
      }
    }
  ],
  "included":[
    {"id":"breakfast_category_id","type":"meal_category","attributes":{"label":"Breakfast","color":"#A8D4D3","enabled":true,"position":0}},
    {"id":"recipe456","type":"meal_recipe","attributes":{"summary":"Pancakes and Eggs Recipe"}}
  ],
  "meta":{"date_min":"2026-03-01","date_max":"2026-04-01"}
}
```

Key fields:
- `id` — the sitting ID (you need this + a date to delete).
- `attributes.summary` — display title; when the sitting is linked to a recipe, `summary` mirrors the recipe's `summary`.
- `attributes.instances[]` — the date(s) this sitting fires on, as `YYYY-MM-DD`.
- `attributes.rrule` / `attributes.recurring` — recurrence metadata (null/false for one‑offs).

### GET a single sitting's instances

```
GET /api/frames/{frame_id}/meals/sittings/{sitting_id}/instances
    ?date_min=2026-03-01
    &date_max=2026-04-01
    &include=meal_category,meal_recipe
Authorization: Bearer <token>
```

`pyskylight` exposes this as `client.list_sitting_instances(frame_id, sitting_id, date_min=..., date_max=..., include=...)`. The response is the `data` array unwrapped by the client (`_data()` helper).

---

## 4. Meal‑plan WRITE endpoints (the critical part)

### POST create recipe

```
POST /api/frames/{frame_id}/meals/recipes?include=meal_category
Authorization: Bearer <token>
Content-Type: application/json

{
  "meal_category_id": "lunch_category_id",
  "summary": "new recipe test",
  "description": "Ingredients:\n- pepper\n- salt\n- butter\n\nInstructions:\n1. Mix and cook."
}
```

Response (the recipe is returned inside `data`, with the meal_category sideloaded into `included`):
```json
{
  "data": {
    "id":"new_recipe_id","type":"meal_recipe",
    "attributes":{"summary":"new recipe test","description":"Ingredients:\n- pepper\n- salt\n- butter\n\nInstructions:\n1. Mix and cook."},
    "relationships":{"meal_category":{"data":{"id":"lunch_category_id","type":"meal_category"}}}
  },
  "included":[{"id":"lunch_category_id","type":"meal_category","attributes":{"label":"Lunch"}}]
}
```

**Required:** `meal_category_id`, `summary`. Optional: `description` (nullable). The recipe is *unlinked* from any sitting until you create one.

The OpenAPI spec for `CreateMealRecipeRequest`:
```yaml
required: [meal_category_id, summary]
properties:
  meal_category_id: { type: string }
  summary: { type: string }
  description: { type: string, nullable: true }
```

### POST create meal sitting

```
POST /api/frames/{frame_id}/meals/sittings
    ?date_min=2026-03-01
    &date_max=2026-04-01
    &include=meal_category,meal_recipe
Authorization: Bearer <token>
Content-Type: application/json

{
  "meal_recipe_id": "recipe456",
  "meal_category_id": "dinner_category_id",
  "add_to_grocery_list": false,
  "date": "2026-03-01",
  "note": null,
  "rrule": null,
  "description": null
}
```

**Response (real, from aarons22's HAR):**
```json
{
  "data": [
    {
      "id":"new_sitting_id","type":"meal_sitting",
      "attributes":{"summary":"Pancakes and Eggs","description":"","note":null,
                    "rrule":null,"recurring":false,"instances":["2026-03-01"]},
      "relationships":{
        "meal_category":{"data":{"id":"dinner_category_id","type":"meal_category"}},
        "meal_recipe":{"data":{"id":"recipe456","type":"meal_recipe"}}
      }
    }
  ],
  "included":[
    {"id":"dinner_category_id","type":"meal_category","attributes":{"label":"Dinner"}},
    {"id":"recipe456","type":"meal_recipe","attributes":{"summary":"Pancakes and Eggs Recipe"}}
  ],
  "meta":{"date_min":"2026-03-01","date_max":"2026-04-01"}
}
```

**Live‑validated behaviors** (from aarons22's notes, 2026‑03‑07):

- `data` may come back as an **array** even for a single create. `pyskylight` handles this: `data = (payload or {}).get("data"); if isinstance(data, list): data = data[0] if data else {}`.
- `attributes.instances` may be `[]` in the immediate POST response; a follow‑up GET shows the correct date.
- Multiple sittings with the same `(meal_category_id, date)` can coexist — they are separate records, not upserts. Tested with at least 25 simultaneous dinner entries on one day without API rejection.
- **If `meal_recipe_id` is set, `summary` must be blank (`null`)** or the API returns:
  ```
  422 {"errors":{"summary":["must be blank"]}}
  ```
  This is the famous **422 "summary must be blank" rule**. When linking a recipe, omit `summary` entirely from the body — `pyskylight` does this automatically by stripping `None`s via `_compact()`.

**`add_to_grocery_list` flag behavior:**
- `false` (default) — just creates the sitting.
- `true` — also queues the recipe's ingredients to be added to the grocery list (uses the same async `auto_creation_intent` flow as the recipe's `add_to_grocery_list` action). You don't get a synchronous grocery list write; the response shape from POST sittings does not include `meta.auto_creation_intent_id`.

**Required fields** (from OpenAPI `CreateMealSittingRequest`): `meal_category_id`, `date`. Optional: `meal_recipe_id`, `description`, `note`, `rrule`, `add_to_grocery_list`.

### DELETE a meal sitting instance (the working endpoint)

**This is the path that actually works:**

```
DELETE /api/frames/{frame_id}/meals/sittings/{sitting_id}/instances/{date}
    ?date_min=2026-03-01
    &date_max=2026-04-01
    &include=meal_category,meal_recipe
Authorization: Bearer <token>
```

Response:
```json
{
  "data": [],
  "included": [],
  "meta": {
    "date_min": "2026-03-01",
    "date_max": "2026-04-01",
    "deleted_sitting_ids": [28931735]
  }
}
```

`pyskylight/client.py:212` documents why this endpoint is the one to use:
> *"Deletes the instance (`.../meals/sittings/{id}/instances/{date}`) — this is how the app removes a planned meal. Deleting the sitting resource directly (`.../meals/sittings/{id}`) leaves a dangling entry in the plan view."*

This is the **opposite** of the broken list‑item pattern: for sittings the per‑instance DELETE works. For grocery list items, the per‑item DELETE is the one that's broken and you need `bulk_destroy` instead.

### Bulk create options

There is **no `bulk_create` endpoint for sittings or recipes.** You have to call `POST /meals/sittings` once per `(date, meal_category, recipe)` triple. For a 5‑day school lunch plan, that's 5 POSTs.

For chores, there *is* a bulk endpoint:
```
POST /api/frames/{frame_id}/chores/create_multiple
```
…but that doesn't help you with meals.

### `add_to_grocery_list` flag behavior — recap

- Set `add_to_grocery_list: true` on the sitting POST → ingredients get queued for grocery list creation.
- Or call `POST /api/frames/{frame_id}/meals/recipes/{recipe_id}/add_to_grocery_list` independently (empty body, `Content-Length: 0`).
- Both return `{meta: {auto_creation_intent_id: <int>}}`. The actual grocery items appear asynchronously — poll `/api/frames/{frame_id}/auto_creation_intents/{id}/created_items` if you need to confirm.

---

## 5. Required setup before writing

### 1. Discover meal_category_id values

```python
cats = client.list_meal_categories(frame_id)
labels = {c.label: c.id for c in cats}
# labels == {"Breakfast": "...", "Lunch": "...", "Dinner": "...", "Snack": "..."}
```

You do this **once** and cache the result by `label` — the IDs are stable for the life of the account.

### 2. Look up recipe_id by name (or create a new recipe first)

There is no name search endpoint; the only way to find an existing recipe is to enumerate:

```python
recipes = client.list_recipes(frame_id, include="meal_category")
by_summary = {r.summary: r.id for r in recipes}
```

If no match, create:
```python
recipe = client.create_recipe(
    frame_id,
    summary="School Lunch: Beef Tacos",
    description="Ground beef, taco shells, cheese, lettuce",
    meal_category_id=lunch_id,
)
recipe_id = recipe.id
```

### 3. Date format

- **Sitting date** (`POST /meals/sittings` body field `date`): **`YYYY-MM-DD`** (date only, no time). From the OpenAPI spec: `format: date, description: Date of the sitting (YYYY-MM-DD)`.
- **Date‑range query parameters** (`date_min`, `date_max` on `/meals/sittings` GET): also **`YYYY-MM-DD`**.
- **Calendar event timestamps** (`starts_at`, `ends_at`): ISO‑8601 datetime (`YYYY-MM-DDTHH:MM:SS`).
- The aarons22 reference sometimes shows `YYYY-MM-DD HH:MM:SS` for sitting dates — that is **wrong for current API**. The OpenAPI spec (`format: date`) and `pyskylight`'s create_sitting both use `YYYY-MM-DD`.

### 4. Resolve frame_id

```python
frame = client.list_frames()[0]
# or set SKYLIGHT_FRAME_ID env var
```

---

## 6. Known gotchas / sharp edges

### "Individual DELETE broken, bulk works" — applies to **list items**, NOT to sittings

- For **grocery list items**: `DELETE /lists/{listId}/list_items/{itemId}` returns 200 but does NOT delete. The working endpoint is `DELETE /lists/{listId}/list_items/bulk_destroy` with body `{"ids": [...]}`. Verified across all three sources.
- For **sittings**: the per‑instance DELETE *works* (`DELETE /meals/sittings/{sittingId}/instances/{date}`). Deleting the sitting resource directly (`DELETE /meals/sittings/{sittingId}`) is what leaves a dangling entry in the plan view — don't use that one.
- For **chores**: `DELETE /chores/{id}` works, with `?apply_to=one|all` to control single vs. series.
- For **task box items**: `DELETE /task_box/items/{id}` works.
- For **messages**: `DELETE /messages/{id}` works; `DELETE /messages/destroy_multiple` is the bulk version.

### Rate limits

No public rate‑limit docs. Empirically:
- `aarons22/skylight-tools` recommends **60+ seconds between requests** as a safe cadence for read loops.
- `pyskylight` exposes a `SkylightRateLimitError` (HTTP 429) that includes the `Retry-After` header.
- Be polite — this is an unofficial API against a small startup's servers. Cache aggressively.

### JSON:API envelope

All `/api/frames/{id}/...` responses are JSON:API:
- Reads: `{"data": [...], "included": [...], "meta": {...}}` or `{"data": {...}, ...}`.
- Writes: same shape, but POST/PATCH may return `data` as either a single object or a list (see sitting create).
- Use `?include=meal_category,meal_recipe` to sideload related resources into the `included` array; otherwise you only get `relationships.{type}.data.id` placeholders.
- `pyskylight`'s `Resource.from_jsonapi()` and `Sitting.from_jsonapi()` handle both shapes.

### The 422 "summary must be blank" rule

When you POST a sitting with `meal_recipe_id` set:
- Do **not** send `summary` in the body.
- If you send `summary: "anything"`, the server returns `422` with `{"errors":{"summary":["must be blank"]}}`.
- `pyskylight` avoids this by stripping `None` values before POST (`_compact()`).

### Skylight Plus requirement

From `pyskylight` README:
> *"Skylight Plus: some Meals features may require Skylight Plus. Where an endpoint is forbidden (HTTP 403) it surfaces as `SkylightPlusRequiredError`. (In practice the Meals/Recipes/Sittings endpoints work on a 'basic' account.)"*

The core read endpoints (`/meals/categories`, `/meals/recipes`, `/meals/sittings`) and the create‑sitting endpoint work on a basic account. The `Snack` category is shipped `enabled:false`; the AI Sidekick (`auto_creation_intents`) may be Plus‑gated.

### Other quirks

- **`/api/sessions` legacy endpoint is dead** — don't use it. Use OAuth PKCE.
- **POST `/meals/sittings` response shape variance**: `data` may be a list even for a single sitting creation. Always normalize.
- **Immediate‑POST `instances: []`**: the sitting date doesn't show up in the response array; you have to GET to confirm. Don't treat a successful POST as evidence the date is set — GET to verify.
- **`/api/frames/...` paths use the `frame_id` from `/api/frames`**, which is NOT the same as the `category_id` (family‑member profile). Don't confuse them.
- **Empty body for `add_to_grocery_list`**: the request must have `Content-Length: 0`. Don't send `null` or `{}`.
- **`User-Agent` quirks**: pyskylight uses its own UA (`pyskylight (+https://github.com/joshuaswarren/pyskylight)`); skylight-mcp uses `skylight-api-version` instead. Both work, but if you hit a 422 on a specific feature, try the official mobile UA: `SkylightMobile (web)`.
- **Custom redirect scheme**: `skylight-family://welcome` — make sure your HTTP client doesn't try to follow the redirect automatically (use `follow_redirects=False` during the `/auth/session` POST and parse the `Location` header manually).

---

## 7. Working Python code examples

### A. Login flow (raw, no library)

This is a minimal version of `pyskylight/auth.py`:

```python
import base64, hashlib, re, secrets, httpx
from urllib.parse import parse_qs, urlparse

BASE = "https://app.ourskylight.com"
CLIENT_ID = "skylight-mobile"
REDIRECT = "skylight-family://welcome"
SCOPE = "everything"
BROWSER_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)

def b64url(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode()

CSRF_RE = re.compile(r'name="authenticity_token"[^>]*value="([^"]+)"')

def login(email: str, password: str) -> dict:
    verifier  = b64url(secrets.token_bytes(32))
    challenge = b64url(hashlib.sha256(verifier.encode()).digest())
    state     = b64url(secrets.token_bytes(18))

    with httpx.Client(timeout=30) as c:
        # 1. GET /oauth/authorize -> follows redirects to login form
        r = c.get(
            f"{BASE}/oauth/authorize",
            params={
                "response_type":"code","client_id":CLIENT_ID,
                "redirect_uri":REDIRECT,"scope":SCOPE,"state":state,
                "code_challenge":challenge,"code_challenge_method":"S256",
                "prompt":"login",
            },
            headers={"User-Agent": BROWSER_UA},
            follow_redirects=False,
        )
        # follow the 302 chain until we hit the form
        hops = 0
        while r.status_code in (301,302,303,307,308) and r.headers.get("location") and hops < 10:
            loc = r.headers["location"]
            if loc.startswith("skylight-family:"):
                break
            r = c.get(loc if loc.startswith("http") else BASE+loc,
                      headers={"User-Agent":BROWSER_UA}, follow_redirects=False)
            hops += 1

        m = CSRF_RE.search(r.text)
        if not m:
            raise RuntimeError("could not find CSRF token")
        csrf = m.group(1)

        # 2. POST /auth/session
        r = c.post(
            f"{BASE}/auth/session",
            data={"authenticity_token":csrf, "email":email, "password":password},
            headers={"User-Agent":BROWSER_UA},
            follow_redirects=False,
        )

        # 3. Chase redirects to extract code from skylight-family://welcome?code=...
        loc = r.headers.get("location")
        hops = 0
        while loc and not loc.startswith("skylight-family:") and hops < 8:
            r = c.get(loc if loc.startswith("http") else BASE+loc,
                      headers={"User-Agent":BROWSER_UA}, follow_redirects=False)
            loc = r.headers.get("location"); hops += 1

        if not (loc and loc.startswith("skylight-family:")):
            raise RuntimeError("invalid email or password")

        q = parse_qs(urlparse(loc).query)
        if q.get("state",[""])[0] != state:
            raise RuntimeError("oauth state mismatch")
        code = q["code"][0]

        # 4. POST /oauth/token -> {access_token, refresh_token, expires_in, created_at}
        tok = c.post(
            f"{BASE}/oauth/token",
            data={
                "grant_type":"authorization_code","client_id":CLIENT_ID,
                "code":code,"redirect_uri":REDIRECT,"code_verifier":verifier,
            },
            headers={"User-Agent":BROWSER_UA},
        ).json()

    return tok  # {"access_token":..., "refresh_token":..., "expires_in":7200, "created_at":...}

def refresh(refresh_token: str) -> dict:
    return httpx.post(
        f"{BASE}/oauth/token",
        data={"grant_type":"refresh_token","client_id":CLIENT_ID,"refresh_token":refresh_token},
        headers={"User-Agent":BROWSER_UA},
    ).json()
```

### B. Complete "add recipe to dinner on this date" using `requests`

```python
import datetime as dt
import requests

BASE = "https://app.ourskylight.com"
HEAD = lambda tok: {
    "Authorization": f"Bearer {tok}",
    "Accept": "application/json",
    "skylight-api-version": "2026-05-01",
}

def get_or_create_frame(token):
    r = requests.get(f"{BASE}/api/frames", headers=HEAD(token), timeout=30)
    r.raise_for_status()
    return r.json()["data"][0]["id"]

def get_meal_categories(token, frame_id):
    r = requests.get(f"{BASE}/api/frames/{frame_id}/meals/categories",
                     headers=HEAD(token), timeout=30)
    r.raise_for_status()
    return {c["attributes"]["label"]: c["id"]
            for c in r.json()["data"]}

def list_recipes(token, frame_id):
    r = requests.get(f"{BASE}/api/frames/{frame_id}/meals/recipes",
                     params={"include":"meal_category"},
                     headers=HEAD(token), timeout=30)
    r.raise_for_status()
    return r.json()["data"]

def create_recipe(token, frame_id, *, meal_category_id, summary, description=None):
    r = requests.post(
        f"{BASE}/api/frames/{frame_id}/meals/recipes",
        params={"include":"meal_category"},
        headers={**HEAD(token), "Content-Type":"application/json"},
        json={"meal_category_id":meal_category_id,"summary":summary,"description":description},
        timeout=30,
    )
    r.raise_for_status()
    return r.json()["data"]   # {"id":..., "type":"meal_recipe", ...}

def plan_meal(token, frame_id, *, date_str, meal_category_id, meal_recipe_id=None,
              add_to_grocery_list=False):
    """Create a sitting for one (date, meal_category, [recipe]) triple."""
    body = {
        "meal_category_id": meal_category_id,
        "date": date_str,                # YYYY-MM-DD
        "add_to_grocery_list": add_to_grocery_list,
        # NOTE: do NOT send 'summary' when meal_recipe_id is set — 422 otherwise
    }
    if meal_recipe_id:
        body["meal_recipe_id"] = meal_recipe_id
    # description / note / rrule / description all optional; leaving out

    r = requests.post(
        f"{BASE}/api/frames/{frame_id}/meals/sittings",
        params={"include":"meal_category,meal_recipe"},
        headers={**HEAD(token), "Content-Type":"application/json"},
        json=body, timeout=30,
    )
    r.raise_for_status()
    payload = r.json()
    # POST response shape is variable: data may be a list of length 1
    data = payload.get("data")
    sitting = data[0] if isinstance(data, list) and data else data
    return sitting

def remove_meal(token, frame_id, sitting_id, date_str):
    r = requests.delete(
        f"{BASE}/api/frames/{frame_id}/meals/sittings/{sitting_id}/instances/{date_str}",
        headers=HEAD(token), timeout=30,
    )
    r.raise_for_status()
    return r.json()


# ---- Demo: read weekly menu, write each day as a Skylight lunch entry ----
if __name__ == "__main__":
    tok = login("you@example.com", "hunter2")["access_token"]
    frame_id = get_or_create_frame(tok)
    cats = get_meal_categories(tok, frame_id)
    lunch_id = cats["Lunch"]

    # 1. Find or create a recipe for Monday
    school_monday = next((r for r in list_recipes(tok, frame_id)
                         if r["attributes"]["summary"] == "School Lunch: Beef Tacos"), None)
    if not school_monday:
        school_monday = create_recipe(
            tok, frame_id,
            meal_category_id=lunch_id,
            summary="School Lunch: Beef Tacos",
            description="Ground beef, taco shells, cheese, lettuce",
        )
    recipe_id = school_monday["id"]

    # 2. Plan it for Monday
    today = dt.date.today()
    monday = today + dt.timedelta(days=(0 - today.weekday()))   # Monday of this week
    sitting = plan_meal(
        tok, frame_id,
        date_str=monday.isoformat(),
        meal_category_id=lunch_id,
        meal_recipe_id=recipe_id,
    )
    print("Created sitting:", sitting["id"], "for", sitting["attributes"]["instances"])

    # 3. Confirm by GET (POST may show instances=[])
    import time; time.sleep(0.5)
    r = requests.get(
        f"{BASE}/api/frames/{frame_id}/meals/sittings/{sitting['id']}",
        headers=HEAD(tok), timeout=30,
    )
    r.raise_for_status()
    print("Confirmed:", r.json()["data"]["attributes"]["instances"])
```

### C. Equivalent using `pyskylight` (recommended for production)

```python
from pyskylight import SkylightClient

with SkylightClient.login("you@example.com", "hunter2") as sky:
    frame = sky.list_frames()[0]
    cats  = {c.label: c.id for c in sky.list_meal_categories(frame.id)}
    lunch_id = cats["Lunch"]

    # ensure recipe
    recipe = next(
        (r for r in sky.list_recipes(frame.id)
         if r.summary == "School Lunch: Beef Tacos"),
        None,
    )
    if recipe is None:
        recipe = sky.create_recipe(
            frame.id,
            summary="School Lunch: Beef Tacos",
            description="Ground beef, taco shells, cheese, lettuce",
            meal_category_id=lunch_id,
        )

    # plan it
    sitting = sky.create_sitting(
        frame.id,
        date="2026-06-20",           # YYYY-MM-DD
        meal_category_id=lunch_id,
        meal_recipe_id=recipe.id,
        # extra={"add_to_grocery_list": True},   # optional
    )
    print(sitting.id, sitting.dates)

    # later, remove
    sky.delete_sitting(frame.id, sitting.id, "2026-06-20")
```

---

## 8. Comparison table of available client libraries

| Library | Language | Auth method | Meal-plan coverage | Status |
|---------|----------|-------------|--------------------|--------|
| [joshuaswarren/pyskylight](https://github.com/joshuaswarren/pyskylight) | Python (3.11+) | OAuth2 PKCE (email+pw) with token cache + auto-refresh | **Full**: categories, recipes (CRUD), sittings (CRUD + instances), add_to_grocery_list. 145+ CLI commands. | Alpha, MIT. Verified 2026-06. ⭐ recommended for Python. |
| [aarons22/skylight-tools](https://github.com/aarons22/skylight-tools) | Go (CLI) + Python (FastMCP) + OpenAPI spec | OAuth2 PKCE | Full (Go CLI + MCP server); ships an OpenAPI 3.0.3 spec you can code‑gen against. | Maintained as of 2026. ⭐ recommended for Go. |
| [chrischall/skylight-mcp](https://github.com/chrischall/skylight-mcp) | Node / TypeScript (MCP server) | OAuth2 PKCE (headless, no SSO/2FA) | 102 MCP tools incl. all meal reads/writes; AI meal‑plan generator (`auto_creation_intents`). Requires `skylight-api-version: 2026-05-01` header. | Active 2026‑05+. |
| [TheEagleByte/skylight-api](https://github.com/TheEagleByte/skylight-api) | OpenAPI 3.0.3 spec (from HAR) + TS HAR→OpenAPI tool | n/a (it IS the spec) | 38 endpoints, full Meals coverage including sittings, recipes, grocery integration. | Generates Swagger UI + ReDoc. |
| [skylightctl](https://pypi.org/project/skylightctl/) (PyPI) | Python CLI | Bearer (uses pre‑baked refresh_token) | Meals CRUD + chores + lists; ships `SKYLIGHT_API_VERSION=2026-03-01`. | v0.1.0; assumes you've already done OAuth once. |
| [kylejfrost/skylight-api-cli](https://github.com/kylejfrost/skylight-api-cli) | Node CLI | OAuth2 PKCE | Meals + calendar + chores. | Older but still functional. |
| [mightybandito/Skylight](https://github.com/mightybandito/Skylight) | Python | **Legacy Basic `user:token`** (broken now) | Reads only. | Dead — uses the retired `/api/sessions` endpoint. |
| [kylebjordahl/skylight-calendar-home-assistant](https://github.com/kylebjordahl/skylight-calendar-home-assistant) | Python (HA custom component) | Basic auth (older) | Calendar events only — no meals. | Reference for HA‑style code; auth path obsolete. |
| [sebrandon1/go-skylight](https://github.com/sebrandon1/go-skylight) | Go CLI | Bearer | Full meals incl. `meal plan --recipes ID,ID --start-date DATE`. | Active. |
| [bryanmig/skylight-calendar-api](https://github.com/bryanmig/skylight-calendar-api) | Python | Basic auth (legacy) | Calendar events only. | Mostly retired; cited as prior art. |

---

## 9. Recommended starting point for "read weekly SchoolCafé menu → write each day as a Skylight meal plan entry"

**Use `pyskylight` (pip install from git).** It is the only Python client that:

1. Implements the **current** OAuth2 PKCE flow (the Basic‑auth alternatives are all dead as of 2026‑06).
2. Covers the exact endpoints you need — `list_meal_categories`, `list_recipes`, `create_recipe`, `create_sitting`, `delete_sitting`.
3. Handles all the gotchas for you: strips `None` so you don't accidentally trigger `422 summary must be blank`, normalizes the variable `data` array shape from `POST /sittings`, uses the correct instance‑DELETE endpoint, caches and refreshes the Bearer token automatically.
4. Is a thin wrapper around `httpx`, so if you need a lower‑level escape hatch (raw POST with `skylight-api-version: 2026-05-01`, custom headers, etc.) the underlying client is still available.

**Concrete recipe (one‑time setup):**

```bash
pip install "git+https://github.com/joshuaswarren/pyskylight"
export SKYLIGHT_EMAIL=you@example.com
export SKYLIGHT_PASSWORD='…'
skylight login                          # caches token, prints frame id
export SKYLIGHT_FRAME_ID=<from above>
skylight meal-categories                # find lunch_id
```

**Then in your SchoolCafé→Skylight sync script:**

```python
import datetime as dt, os
from pyskylight import SkylightClient

with SkylightClient.from_env() as sky:        # reads SKYLIGHT_EMAIL/PASSWORD/FRAME_ID
    frame_id = int(os.environ["SKYLIGHT_FRAME_ID"])
    cats = {c.label: c.id for c in sky.list_meal_categories(frame_id)}
    lunch_id = cats["Lunch"]

    for date, item in school_cafe_menu_for_this_week():
        recipe = next(
            (r for r in sky.list_recipes(frame_id)
             if r.summary == item.title),
            None,
        ) or sky.create_recipe(
            frame_id,
            summary=item.title,
            description=item.description,
            meal_category_id=lunch_id,
        )
        sky.create_sitting(
            frame_id,
            date=date.isoformat(),          # YYYY-MM-DD
            meal_category_id=lunch_id,
            meal_recipe_id=recipe.id,
            # no 'summary' field — pyskylight drops None automatically
        )
```

**If you need to add the new `skylight-api-version` header** (e.g., for a future feature that 422s on the default), reach into the client:

```python
from pyskylight.client import SkylightClient
client = SkylightClient.from_env()
client._http.headers["skylight-api-version"] = "2026-05-01"
```

**If you'd rather avoid pyskylight entirely** (e.g., your environment can't `pip install` from git), the `requests`-based code in §7.B is a complete drop‑in replacement and is ~80 lines. Add the OAuth login function from §7.A on top, cache the token to disk (mode `0600`), and refresh when expired — that's the whole `pyskylight` library in essence.

---

## Appendix: URL/path cheatsheet

| Purpose | Method | Path |
|--------|--------|------|
| OAuth: load login form (PKCE) | GET | `/oauth/authorize?…` |
| OAuth: submit credentials | POST | `/auth/session` |
| OAuth: token exchange | POST | `/oauth/token` |
| List frames (households) | GET | `/api/frames` |
| List meal categories | GET | `/api/frames/{fid}/meals/categories` |
| List recipes | GET | `/api/frames/{fid}/meals/recipes?include=meal_category` |
| Get one recipe | GET | `/api/frames/{fid}/meals/recipes/{rid}?include=meal_category` |
| Create recipe | POST | `/api/frames/{fid}/meals/recipes?include=meal_category` |
| Update recipe | PATCH | `/api/frames/{fid}/meals/recipes/{rid}` |
| Delete recipe | DELETE | `/api/frames/{fid}/meals/recipes/{rid}` |
| Add recipe ingredients to grocery | POST | `/api/frames/{fid}/meals/recipes/{rid}/add_to_grocery_list` |
| List sittings (date range) | GET | `/api/frames/{fid}/meals/sittings?date_min=…&date_max=…&include=…` |
| Get one sitting | GET | `/api/frames/{fid}/meals/sittings/{sid}?include=…` |
| Create sitting | POST | `/api/frames/{fid}/meals/sittings` |
| Update sitting | PATCH | `/api/frames/{fid}/meals/sittings/{sid}` |
| **Delete sitting instance (works!)** | **DELETE** | **`/api/frames/{fid}/meals/sittings/{sid}/instances/{YYYY-MM-DD}`** |
| List sitting instances | GET | `/api/frames/{fid}/meals/sittings/{sid}/instances` |
| Update sitting instance | PATCH | `/api/frames/{fid}/meals/sittings/{sid}/instances/{YYYY-MM-DD}` |
