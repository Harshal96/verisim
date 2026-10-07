# AI-Training Datasets

[Verisim overview](../../../README.md) · [Package guide](../README.md)

Verisim generates instruction-response pairs, labeled classification examples,
NER sequences, and chat transcripts from coherent synthetic person, company,
product, and support-ticket context. The `verisim[ai]` tier exposes these offline
generators and a Python adapter protocol for user-supplied LLM generation:

```bash
uv add "verisim[ai]"
```

## Command Line Usage

Generate offline AI-training datasets:

```bash
uv run verisim ai instruction-pairs --count 100 --seed 7 --format jsonl --output instructions.jsonl
uv run verisim ai classification --count 100 --label positive=6 --label critical=4 --label-noise 0.05 --format jsonl
uv run verisim ai ner --count 100 --indent 2
uv run verisim ai chat --count 25 --min-turns 2 --max-turns 4 --format jsonl
```

`verisim ai` commands use deterministic offline generation. In Python, pass a
custom `AIGenerationAdapter` to `verisim.ai` generator functions when you want
to call an LLM provider from your own credential and retry boundary.

## Python API

```python
from verisim import Verisim
from verisim.ai import instruction_dataset

dataset = instruction_dataset(Verisim(seed=7), count=100)
print(dataset.model_dump_json(indent=2))
```

The materialized dataset functions are `instruction_dataset()`,
`classification_dataset()`, `ner_dataset()`, and `chat_dataset()`. Their iterator
counterparts are `iter_instruction_pairs()`, `iter_classification_examples()`,
`iter_ner_sequences()`, and `iter_chat_transcripts()`. Each accepts optional
`context` and `adapter` arguments; the default adapter is
`OfflineAIGenerationAdapter`, which performs no network calls. Provider-backed
adapters are extension points supplied by the caller.

See the [runnable AI-training example](../../../examples/ai_training.py) and
[examples guide](../../../examples/README.md). Implementation:
[generation functions](generation.py), [adapter protocol](adapters.py), and
[dataset models](models.py).
