[README.md](https://github.com/user-attachments/files/30812482/README.md)
# Week 7 — Hybrid Recommendation Engine

## In one sentence

Once a user says *"I like this one,"* this module answers two questions:
**"What else is like it?"** and **"Is this one fairly priced?"**

## What problem it solves

Weeks 2–4 answer *"show me homes matching these filters."* But the moment a buyer
falls for a specific listing, the useful questions change. They stop asking for a
filtered list and start asking:

1. **What else should I look at?** — comparable homes they might like just as much.
2. **Am I overpaying?** — whether the asking price is backed by what similar homes
   actually sold for.

Week 7 does both. These are **two independent pieces of logic** that happen to live in
the same module because they both revolve around the listing the user picked.

| | Job 1: Recommend | Job 2: Validate the price |
|---|---|---|
| Answers | "What else is like it?" | "Is the asking price fair?" |
| Method | 100-point hybrid score | Comparable sold prices per sqft |
| Data source | `rets_property` (active listings) | `california_sold` (closed sales) |
| Output | Top 5 most similar homes | Above / below / in line with market |

---

## Job 1 — Recommending similar listings

Every candidate listing is scored **0–100**, blending two very different notions of
"similar." The point values below come from the project specification.

### Structured similarity — 60 points (hard facts)

| Signal | Points |
|--------|--------|
| Asking price within $50K | 20 (within $150K → 12, within $300K → 5) |
| Same number of bedrooms | 15 |
| Same city | 15 |
| Square footage within 300 | 10 (within 700 → 5) |

### Semantic similarity — 40 points (how it *reads*)

Reuses the Week 6 embeddings: the cosine similarity between the two listings'
descriptions, scaled to 0–40. Negative similarity is clamped to 0.

### Why blend the two

Hard facts alone miss character — two homes at identical price and size can feel
completely different (a renovated modern condo vs. a dated unit needing work).
Embeddings alone miss the practical constraints buyers actually filter on — no one
wants a "similar-feeling" home that costs twice as much. Weighting structure at 60%
reflects that buyers screen on hard constraints first; the semantic 40% captures the
character that specs can't express.

### Worked example

Target: **Irvine, $1.2M, 3 bed, 1500 sqft**

| Candidate | Score | Why |
|-----------|-------|-----|
| A — Irvine, $1.23M, 3bd, 1550 sqft | **60** | price close (20) + same beds (15) + same city (15) + size close (10) |
| C — San Jose, $1.21M, 3bd, 1490 sqft | **45** | same as A but different city (−15) |
| B — Irvine, $1.8M, 5bd, 3000 sqft | **15** | only the city matches |

Structured scoring is pure math, so recommendations still work (up to 60 points)
before embeddings are wired up — the semantic half simply contributes 0.

---

## Job 2 — Validating the asking price against comps

"Comps" is short for **comparable sales**: recently closed sales similar enough to the
target that their prices are a fair yardstick. This is how real appraisers value a home.

### The four steps

Target: **Irvine, 1500 sqft, asking $1,200,000**

**1. Pull comparable sold homes.** From `california_sold`, take residential sales in
the **same city** whose size is within **±20% of the target** — for a 1500 sqft home,
that's 1200–1800 sqft.

**2. Compute the average price per square foot.** Each comp's close price ÷ its living
area, then averaged:

```
$1,120,000 ÷ 1400 sqft = $800/sqft
$1,280,000 ÷ 1600 sqft = $800/sqft
$1,050,000 ÷ 1300 sqft = $808/sqft
...  average ≈ $800/sqft
```

**3. Estimate what the target should be worth.**

```
$800/sqft × 1500 sqft = $1,200,000
```

**4. Compare to the asking price.**

| Difference | Verdict |
|------------|---------|
| ≤ −5% | priced below comparable sales |
| −5% to +5% | in line with comparable sales |
| ≥ +5% | priced above comparable sales |

Here the asking price is $1.2M against a $1.2M estimate — 0% difference, **in line
with the market**. Asking $1.35M would be +12.5% (above market); asking $1.08M would
be −10% (below market, potentially a deal).

### Why restrict comps to ±20% of the target's size

Because **price per square foot is not constant across home sizes** — bigger homes
almost always sell for less per square foot, the same way buying in bulk lowers the
unit price:

```
small home:  $800,000 ÷ 1000 sqft = $800/sqft
large home: $3,000,000 ÷ 6000 sqft = $500/sqft   ← much lower per sqft
```

If a 6000 sqft estate were averaged in, it would drag the average down to, say,
$650/sqft, and the estimate for our 1500 sqft home would become $975,000. The system
would then wrongly claim the $1.2M asking price is 23% overpriced. Restricting comps to
a similar size range keeps the per-sqft average meaningful for *this* home.

---

## The files in this folder

| File | What it is |
|------|------------|
| `recommender.py` | Hybrid scoring, ranking, and comp-based price validation. |
| `README.md` | This explanation. |

## How to run it

```bash
python3 recommender.py
```

Prints a worked example: a target listing, three candidates ranked by hybrid score, and
a price assessment. No API key or database needed for the demo — structured scoring and
the price math run on their own. Supplying embeddings (Week 6) activates the semantic
40 points automatically, with no code changes.

## Where this fits

```
Week 5: sold-market data  ┐
                          ├─→  Week 7: comp-validated recommendations
Week 6: semantic search   ┘
```

Week 7 is the first module that **combines earlier weeks** rather than adding a
standalone capability: Week 6's embeddings supply the sense of "feel," Week 5's sold
data supplies the pricing reality check, and Week 3's query patterns supply the
candidates.

### In one line

> **Week 7 blends "how alike are the hard facts" (computed here) with "how alike do they
> feel" (Week 6) into a single 0–100 recommendation score, then uses Week 5's sold data
> to judge whether the asking price is fair. It is the first week that genuinely wires
> earlier modules together.**

```
Week 7 [integration]  user likes this home
                          -> recommend similar ones
                          -> validate the price against sold comps
                             ^ uses Week 6 semantics + Week 5 sold data
```

Job 1(推荐) 是代码级复用 Week 6——Week 7 自己写了一套硬指标打分(60 分),同时 import Week 6 的 cosine_similarity 来算语义相似度(40 分),两者相加得出 0–100 的推荐分。

Job 2(价格验证) 是数据级复用 Week 5——它用的是 Week 5 那张 california_sold 成交表和"每平尺价"的思路,但 SQL 是 Week 7 自己新写的(同城 + 面积 ±20%),因为 Week 5 算的是全城行情,粒度太粗,不适合给单套房估价。

更短的一句话版:

Job 1 真的调用了 Week 6 的代码;Job 2 只借用 Week 5 的数据和方法,查询是自己写的。

英文版(周会/面试用):

"Job 1 reuses Week 6 at the code level — it imports the cosine similarity function for the semantic 40 points, on top of the structured 60 points I wrote here. Job 2 reuses Week 5 at the data level — same sold-comps table and price-per-sqft approach, but a new query scoped to the same city and ±20% of the target's size, since Week 5's city-wide average is too coarse to value a single home."
