# Memory

GuideAI remembers in a graph, not a log.

A list of past observations can only answer "what did I see". The questions
that actually help are relational: *what is usually here*, *what changed*,
*who was I with when that came up*. So memory is modelled as nodes (the things
worth remembering) and edges (how they relate), and recall returns a match
together with the context hanging off it.

## The model

**Nodes** carry a `kind` — `place`, `person`, `object`, `hazard`,
`conversation`, `sign`, `preference` — plus a label, when it was first and
last seen, and how many episodes it has appeared in.

**Edges** are typed:

| Relation | Meaning | Created when |
|---|---|---|
| `co_occurred` | seen in the same moment | two entities appear in one episode |
| `located_in` | this thing is at that place | an episode has a `place` |
| `said_by` | this turn was produced by that person | a Bridge turn has a speaker |
| `refers_to` | one is a more specific case of another | mapped from Supermemory parents/children |

An **episode** is everything noticed in one moment. Folding an episode in
links its entities to each other — that co-occurrence is where the graph comes
from. The place and the speaker are deliberately *not* folded into that
pairwise pass: they get their own typed edges, otherwise the same relationship
would be recorded twice and its weight inflated.

Edge weight decays with a 14-day half-life and is pruned below `0.05`, so a
link you stopped reinforcing fades instead of misleading recall forever. Nodes
are never auto-deleted; they are cheap, and a thing you saw once a year ago is
still worth recognising.

## Recall

`recall(graph, query, opts)` scores each node on three things: how well it
matches the words asked, how familiar it is (`log1p(mentions)`), and how
recently it was seen (7-day half-life). Passing `place` adds a bonus to nodes
linked to where the user is now. Each hit carries its strongest neighbours, so
a caller can say "the bin, by your front door, where you also pass the
postbox" rather than just "bin".

With a query, only genuine text matches survive. With an empty query, recall
browses — that is what the memory screen uses.

## Local first, sync second

The on-device graph is always written, and it is the only store unless the
user turns off **Keep memory on this device** in Settings. Sync is additive:
if the network or the backend is gone, recall still works from the phone.

Memory writes are fire-and-forget. A memory that did not reach the server is
never a reason to interrupt someone who is crossing a road.

## Supermemory

Sync uses [Supermemory](https://supermemory.ai) v5, whose own graph layer
returns related memories alongside each hit.

```
POST {base}/ns/{namespace}/document   ingest
POST {base}/ns/{namespace}/search     recall, with include.related
```

**The key never ships in the app.** A Supermemory Bearer key has write access
to every memory in the account, and anything in an app bundle can be extracted
from it. So `apps/api` proxies it:

```
GET  /v1/recall/status     is sync available at all
POST /v1/recall/remember   ingest one observation
POST /v1/recall/search     relationship-aware recall
```

The namespace is derived from the **device ID the API has already verified**,
never from the request body — that is what stops one device reading another's
memories. Unsafe characters are replaced and the result is capped at
Supermemory's documented 100-character limit, so a crafted device ID cannot
traverse out of its namespace.

Configure it with:

```bash
SUPERMEMORY_API_KEY=sm_...                      # blank = on-device only
SUPERMEMORY_BASE_URL=https://api.supermemory.ai # or a self-hosted instance
```

With no key set, `/v1/recall/status` reports `configured: false`, the app says
so plainly on the memory screen, and everything keeps working on-device.

> Supermemory's v3 and v4 APIs are deprecated and shut down on 2026-12-31.
> This integration targets v5.

### Measured behaviour

Tested against the live v5 API on 2026-11-19 with synthetic data. Three
findings changed the integration:

**Extraction is not immediate, and the default defers it a long way.** With
Supermemory's default `dreaming: "dynamic"`, documents were still unextracted
chunks eight minutes after ingest: search returned raw text, no memories and
no graph edges. `dreaming: "instant"` extracted within roughly a minute, at
the cost of one extra billed operation per document. GuideAI therefore sends
`instant` only for the kinds a user actually asks about later — `hazard`,
`conversation`, `person`, `preference` — and lets routine scenery batch
(`INSTANT_KINDS` in `supermemory_gateway.py`).

**The documented default threshold of 0.3 is too loose for speech.** A query
for "roadworks pavement" returned an unrelated conversation about a lift at
similarity 0.49. A sighted user skims past that; someone listening cannot.
The gateway defaults to `0.55`, which cut that query from three hits to one
relevant hit.

**Hybrid search returns a fact twice.** An extracted memory and the source
chunk it came from are separate results with near-identical text, so a brief
would state the same thing twice. `normalize_results` keeps the memory —
it is the cleaned-up statement and the one that carries relations — and drops
the chunk it restates.

**Relations were not observed forming.** `included.related` has exactly the
shape the gateway maps (`parents`, `children`, `siblings`), but stayed empty
across every test namespace, including minutes after extraction completed.
That appears to need a larger corpus or more time than a short test gives.
Until it fills, **the on-device graph is what supplies relationships**, which
is the arrangement this design already assumed: Supermemory is a background
memory layer, not a real-time one, and GuideAI's local-first path never waits
on it.

Ingest took roughly 700–850ms per document; search returned in about 200ms.

## What gets captured

| Source | What is recorded | Guard |
|---|---|---|
| Camera, scene mode | objects seen, with confidence and distance, at the current room | only when the *set* of labels changes, and at most every 30s |
| Camera, "confirm and share" | the confirmed labels, as `hazard` | user action, so no throttle |
| Bridge | each turn, linked to who signed or spoke it | per message |

Capture is sparse on purpose: the detector fires several times a second, but a
memory is only worth recording when the scene actually changed. Turning your
head should not write a memory; walking into another room should.

## Seeing and deleting it

`/memory` is the browser: search, filter by kind, see each entry's relations,
delete one entry or everything. Anything that remembers on a user's behalf has
to let them see and remove what it holds — especially when that user cannot
glance at a screen to check.

## Tests

```bash
npm run test:unit                              # graph behaviour (10 tests)
pytest apps/api/tests/test_supermemory_gateway.py   # gateway (24 tests)
```

The graph tests cover edge creation, strengthening without duplication, label
normalisation, decay and pruning, relationship-aware recall, place bias, and
cascade deletion. The gateway tests cover namespace isolation and traversal,
payload clamping, filter shaping, response mapping and misconfiguration.
