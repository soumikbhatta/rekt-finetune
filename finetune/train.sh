#!/bin/bash
# Fine-tune Qwen3.5-2B on rekt.news exploit data via MLX-LM LoRA.
# Must be run from the repo root: bash finetune/train.sh
#
# Safe on Apple Silicon — MLX uses unified memory, not a discrete GPU.
# Press Ctrl+C at any time to stop; adapters are saved periodically.
# Resume later by adding: --resume-adapter-file adapters/adapters.npz

set -e

VENV=".venv"
if [ ! -d "$VENV" ]; then
    echo "Run setup.sh first: bash setup.sh"
    exit 1
fi

source "$VENV/bin/activate"

echo "Starting LoRA fine-tune..."
mlx_lm.lora --config finetune/lora_config.yaml

echo ""
echo "Training complete. Adapter saved to: adapters/"
echo ""
echo "Test inference:"
echo "  mlx_lm.generate --model mlx-community/Qwen3.5-2B-4bit --adapter-path adapters/ \\"
echo "    --prompt 'Title: [Protocol] Rekt\n\n'"
