"""
Convert data/raw/*.txt files → JSONL for mlx-lm fine-tuning.

Output format (completion style):
    {"text": "Title: ...\n...\n====\n[article body]"}

Writes:
    data/finetune/train.jsonl   (90%)
    data/finetune/valid.jsonl   (10%)

Usage:
    python prepare/convert_to_jsonl.py
"""

import json
import random
from pathlib import Path

SEED = 42
SPLIT = 0.9  # 90% train, 10% val

DATA_DIR = Path(__file__).parent.parent / "data"
RAW_DIR = DATA_DIR / "raw"
FT_DIR = DATA_DIR / "finetune"


def load_article(path: Path) -> str | None:
    text = path.read_text(encoding="utf-8").strip()
    if not text or len(text) < 200:
        return None
    return text


def main():
    FT_DIR.mkdir(parents=True, exist_ok=True)

    txt_files = sorted(RAW_DIR.glob("*.txt"))
    print(f"Found {len(txt_files)} .txt files in {RAW_DIR}")

    samples = []
    skipped = 0
    for f in txt_files:
        text = load_article(f)
        if text is None:
            skipped += 1
            continue
        samples.append({"text": text})

    print(f"Loaded {len(samples)} samples ({skipped} skipped — too short or empty)")

    random.seed(SEED)
    random.shuffle(samples)

    split_idx = int(len(samples) * SPLIT)
    train = samples[:split_idx]
    valid = samples[split_idx:]

    def write_jsonl(path: Path, data: list[dict]):
        with open(path, "w", encoding="utf-8") as f:
            for item in data:
                f.write(json.dumps(item, ensure_ascii=False) + "\n")

    train_path = FT_DIR / "train.jsonl"
    valid_path = FT_DIR / "valid.jsonl"
    write_jsonl(train_path, train)
    write_jsonl(valid_path, valid)

    print(f"Wrote {len(train)} train samples → {train_path}")
    print(f"Wrote {len(valid)} valid samples → {valid_path}")
    print("Done.")


if __name__ == "__main__":
    main()
