# Product Categorization Example

Demonstrates using X-Ray Logger to instrument an automatic product categorization pipeline. This pipeline assigns products to categories from a multi-level taxonomy, capturing decision-making at each step.

## The Problem

When categorizing products into a large taxonomy (10,000+ categories), miscategorizations are common:
- **Phone chargers** end up in "office supplies" because they have "stand" in the name
- **Desk organizers** with phone holders get put in "mobile accessories"
- Ambiguous products match multiple categories equally well

Traditional logs tell you what category was assigned, but not **why** - which keywords matched? Which categories were considered? Where did the logic go wrong?

## What X-Ray Captures

This example shows how X-Ray captures:
1. **Attribute extraction** - Which keywords and signals were found?
2. **Candidate discovery** - Which categories matched the product?
3. **Filtering decisions** - Which candidates were eliminated and why?
4. **Ranking logic** - How were candidates scored?
5. **Ambiguity resolution** - When multiple categories match, how is the winner chosen?

## Quick Start

### 1. Start X-Ray Backend (Published Docker Image)

```bash
docker run -d --name xray-api -p 8000:8000 \
  -v /tmp/xray-data:/app/data \
  -e XRAY_DATABASE_URL=sqlite+aiosqlite:////app/data/xray.db \
  ghcr.io/mohit-nagaraj/xray-logger:latest
```

Verify it's running:
```bash
curl http://localhost:8000/docs
```

### 2. Install SDK from PyPI

```bash
pip install 'xray-logger[sdk]>=0.1.1'
```

### 3. Run the Example

```bash
python main.py
```

## Sample Output

```
[1/7] Categorizing: Wireless Phone Charger Stand with LED Light...
--------------------------------------------------------------------------------
  Category: Electronics > Mobile Accessories
  Category ID: elec-mobile-acc
  Confidence: 90%
  Expected: elec-mobile-acc
  Match: ✓

[2/7] Categorizing: Bamboo Desktop Organizer with Phone Holder...
--------------------------------------------------------------------------------
  Category: Office Supplies > Desk Organization
  Category ID: office-desk
  Confidence: 75%
  Expected: office-desk
  Match: ✓

...

Accuracy: 7/7 (100.0%)
Average Confidence: 85%
```

## Viewing the Data

### API Endpoints

```bash
# List all categorization runs
curl "http://localhost:8000/xray/runs?pipeline=product-categorization"

# Get a specific run with all steps
curl "http://localhost:8000/xray/runs/{run_id}"

# Query filter steps across all runs
curl "http://localhost:8000/xray/steps?step_type=filter"

# Find ambiguous categorizations (low confidence)
curl "http://localhost:8000/xray/steps?step_type=llm"
```

### Interactive API Docs

Open http://localhost:8000/docs in your browser to explore the API interactively.

## Pipeline Steps

| Step | Type | What It Captures |
|------|------|------------------|
| `extract_attributes` | `transform` | Keywords extracted, text analysis |
| `find_candidate_categories` | `retrieval` | All categories that matched, match counts |
| `filter_weak_candidates` | `filter` | Threshold used, candidates removed with scores |
| `score_categories` | `rank` | Scoring formula, weights, top 3 scores |
| `resolve_ambiguity` | `llm` | Confidence calculation, ambiguity detection |

## Debugging Example

**Scenario:** A "Wireless Phone Charger" is mis-categorized as "Desk Organization"

**Using X-Ray to debug:**

1. **Query for the run:**
   ```bash
   curl "http://localhost:8000/xray/runs?pipeline=product-categorization" | jq .
   ```

2. **Check the filter step - were good candidates eliminated?**
   ```bash
   curl "http://localhost:8000/xray/steps?step_type=filter&run_id={run_id}"
   ```
   Look at `reasoning.removed_candidates` - did we filter out "Mobile Accessories"?

3. **Check the ranking step - how were categories scored?**
   ```bash
   curl "http://localhost:8000/xray/steps?step_type=rank&run_id={run_id}"
   ```
   Look at `reasoning.top_3_scores` - what scored highest?

4. **Check the LLM step - was it ambiguous?**
   ```bash
   curl "http://localhost:8000/xray/steps?step_type=llm&run_id={run_id}"
   ```
   Look at `reasoning.ambiguous` and `reasoning.score_gap`

## Test Products

The example includes 7 test products with varying challenges:
- Simple cases (clear category match)
- Ambiguous cases (multiple categories apply)
- Edge cases (misleading keywords like "phone" in desk organizer)

Each product includes:
- `title` and `description`
- `expected_category` (ground truth)
- `challenge` (why this product is interesting to categorize)

## Files

- `data.py` - Category taxonomy and test products
- `pipeline.py` - Categorization pipeline with X-Ray instrumentation
- `main.py` - Entry point that runs the pipeline
- `requirements.txt` - Dependencies (just xray-logger[sdk])

## Clean Up

```bash
# Stop and remove X-Ray container
docker stop xray-api && docker rm xray-api

# Remove data
rm -rf /tmp/xray-data
```
