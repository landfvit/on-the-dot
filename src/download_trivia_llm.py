"""Explicit, pinned model download. Inference and training run offline afterwards."""
import argparse
import json
from pathlib import Path

from src.trivia_llm_worker import sha256

REPO = 'mlx-community/Qwen3-4B-Instruct-2507-4bit'
REVISION = '50d427756c6b1b2fe0c0a10f67fbda1fc8e82c1b'
FILES = ['config.json', 'generation_config.json', 'tokenizer.json', 'tokenizer_config.json',
         'special_tokens_map.json', 'added_tokens.json', 'chat_template.jinja',
         'merges.txt', 'vocab.json', 'model.safetensors', 'model.safetensors.index.json', 'README.md']


def main():
    from huggingface_hub import snapshot_download
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=Path('data/private/llm/models/qwen3-4b'))
    args = parser.parse_args()
    snapshot_download(REPO, revision=REVISION, local_dir=args.output, allow_patterns=FILES, max_workers=2)
    manifest = {'repository': REPO, 'revision': REVISION, 'license': 'Apache-2.0',
                'base_model': 'Qwen/Qwen3-4B-Instruct-2507',
                'sha256': {name: sha256(args.output / name) for name in FILES}}
    (args.output / 'points-model.json').write_text(json.dumps(manifest, indent=2) + '\n')
    print(json.dumps({'path': str(args.output.resolve()), 'revision': REVISION}, indent=2))


if __name__ == '__main__':
    main()
