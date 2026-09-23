"""Bounded, offline LoRA fitting with remote tokenizer code disabled."""
import json
import os
from pathlib import Path
from types import SimpleNamespace

from src.trivia_llm_worker import verify_model, sha256
from src.trivia_llm_dataset import JsonCompletionDataset


def main():
    os.environ.update(HF_HUB_OFFLINE='1', TRANSFORMERS_OFFLINE='1', HF_HUB_DISABLE_TELEMETRY='1')
    import mlx.core as mx
    import numpy as np
    from mlx_lm import load
    from mlx_lm.lora import CONFIG_DEFAULTS, build_parser, train_model

    values = vars(build_parser().parse_args())
    for key, default in CONFIG_DEFAULTS.items():
        if values.get(key) is None:
            values[key] = default
    args = SimpleNamespace(**values)
    if not args.train or args.test or args.report_to or args.config or args.fine_tune_type != 'lora':
        raise ValueError('Only local LoRA training without reporting is supported')
    training_path = Path(args.adapter_path) / 'training-manifest.json'
    training = json.loads(training_path.read_text()) if training_path.exists() else {}
    library_epoch = training.get('protocol') == 'library-one-epoch-v1'
    intent_epoch = training.get('protocol') == 'text-to-query-v1'
    if not 1 <= args.iters <= (2500 if library_epoch else 600 if intent_epoch else 200) or not 1 <= args.num_layers <= 4 or args.batch_size != 1:
        raise ValueError('Pilot memory/iteration budget exceeded')
    if args.resume_adapter_file:
        manifest = json.loads((Path(args.adapter_path) / 'training-manifest.json').read_text())
        parent = manifest['resume']
        if Path(args.resume_adapter_file).resolve() != Path(parent['weights']).resolve() or sha256(args.resume_adapter_file) != parent['sha256']:
            raise ValueError('Source adapter changed before continuation')
    verify_model(Path(args.model))
    mx.set_memory_limit(10 * 1024**3)
    mx.set_cache_limit(256 * 1024 * 1024)
    np.random.seed(args.seed)
    model, tokenizer = load(args.model, tokenizer_config={'trust_remote_code': False, 'local_files_only': True})
    datasets = []
    for split in ('train', 'valid'):
        records = [json.loads(line) for line in (Path(args.data) / f'{split}.jsonl').read_text().splitlines()]
        dataset = JsonCompletionDataset(records, tokenizer)
        for record in records:
            tokens, offset = dataset.process(record)
            if len(tokens) > args.max_seq_length or offset >= len(tokens):
                raise ValueError('Training would truncate a target or mask all its tokens')
        datasets.append(dataset)
    if (library_epoch or intent_epoch) and (args.iters != len(datasets[0]) or args.resume_adapter_file):
        raise ValueError('Corpus training must be one complete epoch from the base model')
    print('Train and validation only; test file is never loaded.', flush=True)
    train_model(args, model, datasets[0], datasets[1])


if __name__ == '__main__':
    main()
