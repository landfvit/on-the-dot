"""Exact JSON completion targets; chat templates format the prompt only."""


class JsonCompletionDataset:
    def __init__(self, records, tokenizer):
        self.records = records
        self.tokenizer = tokenizer

    def __len__(self):
        return len(self.records)

    def __getitem__(self, index):
        return self.records[index]

    def process(self, record):
        messages = record['messages']
        if messages[-1]['role'] != 'assistant':
            raise ValueError('Missing supervised completion')
        # Qwen chat templates can insert reasoning tags when formatting assistant
        # messages. Never teach those tags as part of our JSON-only protocol.
        prompt = self.tokenizer.apply_chat_template(messages[:-1], tokenize=True, add_generation_prompt=True)
        target = self.tokenizer.encode(messages[-1]['content'], add_special_tokens=False)
        return prompt + target + [self.tokenizer.eos_token_id], len(prompt)
