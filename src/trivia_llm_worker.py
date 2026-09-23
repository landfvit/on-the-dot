"""Offline MLX subprocess. No database access, network fallback or publication."""
import argparse
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import time


def sha256(path):
    with Path(path).open('rb') as handle:
        return hashlib.file_digest(handle, 'sha256').hexdigest()


def verify_model(path):
    if not path.is_dir() or not (path / 'model.safetensors').is_file():
        raise ValueError('A downloaded local safetensors model is required')
    manifest = json.loads((path / 'points-model.json').read_text())
    for filename, digest in manifest['sha256'].items():
        file = (path / filename).resolve()
        if not file.is_relative_to(path.resolve()) or sha256(file) != digest:
            raise ValueError('Model files changed since download')
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--model', type=Path, required=True)
    parser.add_argument('--jobs', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--adapter', type=Path)
    parser.add_argument('--seed', type=int, default=42)
    args = parser.parse_args()
    os.environ.update(HF_HUB_OFFLINE='1', TRANSFORMERS_OFFLINE='1', HF_HUB_DISABLE_TELEMETRY='1')
    manifest = verify_model(args.model)
    if args.adapter:
        if not (args.adapter / 'adapters.safetensors').is_file() or (args.adapter / 'failure.json').exists():
            raise ValueError('Completed adapter not found; refusing base-model fallback')
        training = json.loads((args.adapter / 'training-manifest.json').read_text())
        if training['model_manifest'] != manifest:
            raise ValueError('Adapter was trained on another base model')
        if training.get('completion_required'):
            completion = json.loads((args.adapter / 'completion.json').read_text())
            if completion['adapter_sha256'] != sha256(args.adapter / 'adapters.safetensors'):
                raise ValueError('Adapter changed after training completed')
    import mlx.core as mx
    from mlx_lm import load, stream_generate
    from mlx_lm.sample_utils import make_sampler

    mx.set_cache_limit(256 * 1024 * 1024)
    mx.set_memory_limit(10 * 1024**3)
    model, tokenizer = load(str(args.model.resolve()),
                            adapter_path=str(args.adapter.resolve()) if args.adapter else None,
                            tokenizer_config={'trust_remote_code': False, 'local_files_only': True})
    jobs = [json.loads(line) for line in args.jobs.read_text().splitlines() if line.strip()]
    if not 1 <= len(jobs) <= 100:
        raise ValueError('Use 1-100 bounded jobs')
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open('x') as handle:
        for number, job in enumerate(jobs):
            mx.random.seed(args.seed + number)
            prompt = tokenizer.apply_chat_template(job['messages'], tokenize=True, add_generation_prompt=True)
            if len(prompt) > 4096:
                raise ValueError('Prompt exceeds pilot context limit')
            start = time.monotonic()
            parts = []
            response = None
            for response in stream_generate(model, tokenizer, prompt=prompt, max_tokens=256,
                                            sampler=make_sampler(temp=0.4, top_p=0.9)):
                parts.append(response.text)
                if time.monotonic() - start > 120:
                    raise TimeoutError('Question exceeded 120 seconds')
            record = {'id': job['id'], 'raw': ''.join(parts), 'seconds': time.monotonic() - start,
                      'model': manifest, 'adapter_sha256': sha256(args.adapter / 'adapters.safetensors') if args.adapter else None,
                      'jobs_sha256': sha256(args.jobs), 'seed': args.seed + number,
                      'mlx_lm_version': importlib.metadata.version('mlx-lm'),
                      'tokens': response.generation_tokens if response else 0,
                      'finish_reason': response.finish_reason if response else 'no_output'}
            handle.write(json.dumps(record) + '\n')
            handle.flush()
            print(f'Generated {number + 1}/{len(jobs)} in {record["seconds"]:.1f}s', flush=True)
            mx.clear_cache()


if __name__ == '__main__':
    main()
