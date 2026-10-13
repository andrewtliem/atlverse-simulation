# SIMAN coverage

Checklist of the SIMAN language blocks and elements.

Legend: **done**, *partial*, alt = covered differently, TODO

## Blocks

| Block | Status | Notes |
|---|---|---|
| ACCESS | **done** |  |
| ACTIVATE | **done** |  |
| ALLOCATE | **done** |  |
| ALTER | **done** |  |
| ASSIGN | **done** |  |
| BEGIN | alt | not needed |
| BLOCK | **done** | `BlockPoints` in Python, `block` in YAML |
| BRANCH | **done** |  |
| CAPTURE | **done** | vehicle size in zones |
| CLOSE | **done** |  |
| COMBINE | **done** |  |
| CONVEY | **done** |  |
| COPY | **done** |  |
| COUNT | **done** |  |
| CREATE | **done** |  |
| DELAY | **done** |  |
| DETECT | **done** |  |
| DISPOSE | **done** |  |
| DROPOFF | **done** |  |
| DUPLICATE | **done** |  |
| ELSE | **done** |  |
| ELSEIF | **done** |  |
| ENDIF | **done** |  |
| ENDWHILE | **done** |  |
| EVENT | alt | Call block (Python function) |
| EXIT | **done** |  |
| FINDJ | **done** |  |
| FREE | **done** |  |
| GROUP | **done** |  |
| HALT | **done** |  |
| IF | **done** |  |
| INCLUDE | alt | not needed (YAML/Python composition) |
| INSERT | **done** | wakes the owning hold block |
| MATCH | **done** |  |
| MOVE | **done** |  |
| PICKQ | **done** |  |
| PICKUP | **done** |  |
| PREEMPT | **done** | last-unit, priority and resume rules per spec |
| PROCEED | **done** |  |
| QPICK | **done** |  |
| QUEUE | **done** |  |
| READ | *partial* | free format only |
| RELEASE | **done** |  |
| RELINQUISH | **done** | vehicle size in zones |
| REMOVE | **done** |  |
| REQUEST | **done** |  |
| ROUTE | *partial* | no route-time by distance set |
| SCAN | **done** |  |
| SEARCH | **done** |  |
| SEIZE | *partial* | SELECT via select= option; no seize by expression list of sets |
| SELECT | **done** |  |
| SIGNAL | **done** |  |
| SPLIT | **done** |  |
| STACK | **done** |  |
| START | **done** |  |
| STATION | **done** |  |
| STOP | **done** |  |
| STORE | **done** |  |
| TALLY | **done** |  |
| TRACE | *partial* | basic |
| TRANSPORT | **done** |  |
| UNBLOCK | **done** |  |
| UNSTORE | **done** |  |
| VBA | alt | Call block (Python function) |
| WAIT | **done** |  |
| WHILE | **done** |  |
| WRITE | *partial* | python format strings |
| ZAP | **done** |  |
| ONCHANGE | **done** |  |

## Elements

| Element | Status | Notes |
|---|---|---|
| ARRIVALS | **done** | time / first / last / every; target block label or station |
| ATTRIBUTES | **done** |  |
| ActivityAreas | **done** | entered count and WIP, rolled up to parents |
| BEGIN | alt | not needed |
| BLOCKAGES | **done** |  |
| CONTINUOUS | **done** |  |
| CONVEYORS | **done** |  |
| COUNTERS | **done** |  |
| CSTATS | **done** |  |
| DISCRETE | alt | superseded |
| DISTANCES | **done** |  |
| DISTRIBUTIONS | alt | obsolete in SIMAN; use EXPRESSIONS |
| DSTATS | **done** |  |
| ENTITIES | **done** |  |
| EVENTS | alt | Call block |
| EXPRESSIONS | **done** |  |
| FAILURES | **done** |  |
| FILES | **done** |  |
| FREQUENCIES | **done** |  |
| INCLUDE | alt | not needed |
| INITIALIZE | alt | initial values on variables/attributes |
| INTERSECTIONS | **done** |  |
| LEVELS | **done** |  |
| LINKS | **done** | zones, uni/bi-directional, spur |
| NETWORKS | **done** | shortest paths; no REDIRECTS |
| NICKNAMES | alt | not needed |
| OUTPUTS | **done** |  |
| PARAMETERS | **done** |  |
| PICTURES | **done** | entity pictures (Entity module, Assign Entity Picture) drive the editor animation |
| PROJECT | **done** |  |
| QUEUES | **done** |  |
| RANKINGS | TODO | per-queue ranking done; RANKINGS element syntax TODO |
| RATES | **done** |  |
| RECIPES | **done** |  |
| REDIRECTS | TODO | TODO |
| REPLICATE | **done** |  |
| REPORTLINES | alt | custom reports via Python |
| REPORTS | alt | custom reports via Python |
| RESOURCES | **done** |  |
| RULES | TODO | TODO (rules inline) |
| SCHEDULES | **done** |  |
| SEEDS | **done** |  |
| SEGMENTS | **done** |  |
| SEQUENCES | **done** |  |
| SETS | **done** |  |
| STATESETS | **done** |  |
| STATICS | **done** | resolved via station recipe |
| STATIONS | **done** |  |
| STORAGES | **done** |  |
| TABLES | **done** |  |
| TALLIES | **done** |  |
| TASKS | TODO | TODO |
| TRACE | **done** |  |
| TRANSPORTERS | **done** | free-path and guided; no acceleration/turning factors |
| VARIABLES | **done** |  |

## Arena modules in the web editor

Dialog prompts follow the Basic Process / Advanced Process module conventions.

| Module | Status | Notes |
|---|---|---|
| Create, Dispose, Process, Decide, Batch, Separate, Assign, Record | **done** | all prompts, including Process Type Submodel (nested logic with Entry/Exit points) and Arena's process statistics (Number In/Out, time per entity by category) |
| Entity, Queue, Resource, Variable, Schedule, Set, Attribute (data) | *partial* | all prompts except Variable File Name/Recordset/File Read Time; Queue "Shared" is accepted and has no effect |
| Seize, Delay, Release, Hold, Signal, Remove | **done** | Queue Type Queue/Set/Internal/Attribute/Expression |
| Expression, Failure, StateSet (data) | **done** | Expression rows/columns (arrays) TODO |
| Statistic (data module) | **done** | Time-Persistent, Tally, Counter (Limit ends the run, Initial Value), Output, Frequency by Value or resource State with Constant/Range categories and Exclude (Restricted Percent); Output File not supported |
| Match, PickStation, Search, Store, Unstore, Adjust Variable, ReadWrite, Pickup, Dropoff, Advanced Set, File | TODO in the editor | the engine blocks exist (YAML / Python) |
