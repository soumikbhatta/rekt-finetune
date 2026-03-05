# rekt-finetune

Scrape every DeFi exploit post-mortem from [rekt.news](https://rekt.news) and fine-tune Qwen3.5-2B on Apple Silicon via MLX-LM LoRA.

## What this does

1. **Scrapes** ~200-300 exploit post-mortems from rekt.news (only `-rekt` slug articles)
2. **Extracts** metadata: title, date, tags, ETH addresses, tx hashes, dollar amount lost
3. **Prepares** a JSONL dataset for completion-style fine-tuning
4. **Fine-tunes** Qwen3.5-2B (or 4B) using LoRA on Apple Silicon via MLX-LM

**Mac safety note:** MLX runs on Apple Silicon's unified memory — it's the same as running a browser or Xcode. No overheating risk. Ctrl+C stops training at any point.

---

## Requirements

- macOS on Apple Silicon (M1/M2/M3/M4)
- Python 3.10+

---

## Setup (one time)

```bash
git clone <this-repo>
cd rekt-finetune
bash setup.sh
```

This creates a `.venv/` — nothing touches your global Python.

---

## Step 1 — Scrape

```bash
source .venv/bin/activate
python scraper/scrape_rekt.py
```

Progress output:
```
Phase 1 — Collecting exploit article links from 40 pages...
  Page 00/39 — 11 new exploit links (11 total)
  ...
Phase 2 — Scraping articles...
  [  1/241] Scraped poly-network-rekt (8,432 chars, 2 addresses found)
  [  2/241] Scraped ronin-rekt (12,104 chars, 5 addresses found)
  ...
Done. 238/241 articles scraped successfully.
```

Outputs:
- `data/raw/YYYY-MM-DD_slug.txt` — one file per article
- `data/all_addresses.csv`
- `data/all_tx_hashes.csv`
- `data/rekt_exploits_dataset.zip`

---

## Step 2 — Prepare training data

```bash
python prepare/convert_to_jsonl.py
```

Outputs:
- `data/finetune/train.jsonl` (90%)
- `data/finetune/valid.jsonl` (10%)

---

## Step 3 — Fine-tune

```bash
bash finetune/train.sh
```

Default config: `Qwen3.5-2B-4bit`, 1000 iterations, batch size 4, LoRA rank on 16 layers.

To use the 4B model instead, edit `finetune/lora_config.yaml`:
```yaml
model: mlx-community/Qwen3.5-4B-4bit
```

---

## Step 4 — Test inference

```bash
mlx_lm.generate \
  --model mlx-community/Qwen3.5-2B-4bit \
  --adapter-path adapters/ \
  --prompt "Title: Euler Finance Rekt

"
```

---

## Repo layout

```
rekt-finetune/
├── setup.sh                    # one-time setup
├── requirements.txt
├── scraper/
│   └── scrape_rekt.py          # Playwright scraper
├── data/
│   ├── raw/                    # .txt files (gitignored)
│   ├── finetune/               # JSONL (gitignored)
│   ├── all_addresses.csv       # gitignored
│   └── all_tx_hashes.csv       # gitignored
├── prepare/
│   └── convert_to_jsonl.py
└── finetune/
    ├── lora_config.yaml        # tweak model/iters here
    └── train.sh
```

---

## Tuning tips

| Want | Change |
|------|--------|
| Faster iteration | Drop `iters` to 200-500 |
| Better quality | Use `Qwen3.5-4B-4bit` |
| More expressiveness | Increase `lora_layers` to 32 |
| Resume training | Add `--resume-adapter-file adapters/adapters.npz` to train.sh |
