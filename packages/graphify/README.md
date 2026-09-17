# graphify

A knowledge graph over an indexed source tree, and the traversals an agent needs
from it.

```
chunks + links (from whoever indexed the tree)
   │
   ├── documents/  README, Makefile, *.toml -- text scan for mentions
   │                (drawn as `inferred` edges, never as structure)
   ▼
KnowledgeGraph ──► communities ──► subsystems
   │
   ├── near(x)          what this touches, within n hops
   ├── between(x, y)    the shortest relationship
   └── around(x)        what else belongs with it
```

## Why it exists

The agent verifies a claimed vulnerability by looking things up: what reaches
this function, whether the input really is attacker controlled, what else in the
tree would be affected. Those are graph questions, and answering them by
grepping is guesswork with extra steps. The MCP tools `graph_neighbours`,
`graph_path` and `graph_subsystem` are this package, exposed to the model.

It also decides how work is grouped: a community is a set of units that actually
depend on each other, which is a better batch than four functions that happened
to be adjacent in a queue.

## What it will not do

**Call a model.** The structural half is handed in already resolved. The other
half is a regex over the files a parser skips. Extraction that needs an LLM
would mean uploaded code leaving the machine, which is exactly what this tool
promises not to do.

**Pretend a mention is a call.** Every edge carries `extracted` or `inferred`,
and the second kind counts for less in the clustering and is labelled wherever
it surfaces. A README naming `handle_download` is a real relationship and is not
evidence of anything.

**Draw a hairball.** `graphify graph.json export --out map.html` writes a
self-contained page listing the subsystems and their members. A force-directed
picture of two thousand nodes is a screensaver.

## Using it

```bash
graphify artifacts/agent-runs/<run>/graph.json show
graphify artifacts/agent-runs/<run>/graph.json near handle_download --hops 2
graphify artifacts/agent-runs/<run>/graph.json between read_param fetch_firmware
graphify artifacts/agent-runs/<run>/graph.json export --out map.html
```

The document is written by `agent index`, and rebuilt on every re-index. From
Python, `agent.knowledge` is the adapter: it turns a `ChunkStore` into the
records this package takes, and is the only place the two meet.

## Clustering

Label propagation, sixteen lines, no dependencies. Only `extracted` edges vote:
weighting mentions down was tried and is not enough, because a README naming
forty symbols is a forty-edge hub that drags everything it names into one
community whatever the weight. Mentions stay in the graph and `graph_neighbours`
reports them; they are just not evidence about what belongs with what.

Ties break on the node id and the sweep order is fixed, so the same tree always
partitions the same way. That matters more than partition quality here: the
clustering decides how work is grouped, so a run that clustered differently on a
second pass would produce a report that could not be diffed against the first.
