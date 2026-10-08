# SPDX-FileCopyrightText: 2026 muntedcrocodile
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Persistent, CPU-only inference worker. JSON lines over private stdio, no network."""
import json
import re
import sys
from functools import lru_cache


def healing_prompt(prefix):
    """Replay the partial word so BPE can choose a longer whole-word token."""
    if prefix.endswith(" "):
        return prefix.rstrip(" "), b""
    match = re.search(r" ?[\w’'-]+$", prefix)
    if match:
        return prefix[:match.start()], match.group().encode("utf-8")
    return prefix, b""


def matching_tokens(remaining, vocabulary):
    return [index for index, piece in enumerate(vocabulary)
            if piece and (piece.startswith(remaining) or remaining.startswith(piece))]


def short_completion(prefix, generated):
    """Return one complete word (or word suffix), ending at any whitespace."""
    match = re.match(r"( *)(\S+)(?=\s)", generated)
    if not match:
        return ""
    word = match.group(2)
    if len(word) > 100 or any(ord(char) < 32 for char in word):
        return ""
    separator = " " if match.group(1) and prefix and not prefix[-1].isspace() else ""
    return separator + word


class Predictor:
    def __init__(self, model_path, context_tokens=128, max_tokens=12, threads=2):
        from llama_cpp import Llama
        self.context_tokens = context_tokens
        self.max_tokens = max_tokens
        self.model = Llama(model_path=model_path, n_ctx=context_tokens + max_tokens + 8,
                           n_batch=context_tokens, n_threads=threads, n_threads_batch=threads,
                           n_gpu_layers=0, verbose=False)
        self.vocabulary = [self.model.detokenize([token]) for token in range(self.model.n_vocab())]
        self.allowed = lru_cache(maxsize=128)(lambda remaining: matching_tokens(remaining, self.vocabulary))

    def predict(self, prefix):
        from llama_cpp import LogitsProcessorList, StoppingCriteriaList
        # Replaying an unfinished word lets "writ" become the token "writing",
        # instead of forcing the model to continue an unnatural token boundary.
        prompt, healing = healing_prompt(prefix)
        if len(healing) > 80:
            return ""
        tokens = self.model.tokenize(prompt.encode("utf-8"), add_bos=True)[-self.context_tokens:]
        if not tokens:
            if not healing or self.model.token_bos() < 0:
                return ""
            tokens = [self.model.token_bos()]

        def constrain(input_ids, scores):
            emitted = b"".join(self.vocabulary[int(token)] for token in input_ids[len(tokens):])
            remaining = healing[len(emitted):]
            if remaining:
                allowed = self.allowed(remaining)
                values = scores[allowed].copy()
                scores[:] = -float("inf")
                scores[allowed] = values
            return scores

        def word_finished(input_ids, _scores):
            # Leading token spaces and the replayed partial word are not the
            # boundary. Continue across subword tokens until new text ends a word.
            emitted = b"".join(self.vocabulary[int(token)]
                               for token in input_ids[len(tokens):self.model.n_tokens])
            if not emitted.startswith(healing):
                return False
            generated = emitted[len(healing):].decode("utf-8", errors="ignore")
            return bool(short_completion(prefix, generated))

        response = self.model.create_completion(prompt=tokens, max_tokens=self.max_tokens,
                                                temperature=0, repeat_penalty=1.05,
                                                stop=["\n", "\r"], echo=False,
                                                stopping_criteria=StoppingCriteriaList([word_finished]),
                                                logits_processor=LogitsProcessorList([constrain]) if healing else None)
        choice = response["choices"][0]
        generated = choice["text"].encode("utf-8")
        if not generated.startswith(healing):
            return ""
        generated = generated[len(healing):].decode("utf-8", errors="ignore")
        if choice["finish_reason"] == "stop":
            generated += " "  # EOS/newline is also a complete word boundary.
        return short_completion(prefix, generated)


def main():
    try:
        predictor = Predictor(sys.argv[1], *map(int, sys.argv[2:5]))
        # Warm up once, while the editor remains fully responsive.
        predictor.predict("The next word is")
        print(json.dumps({"ready": True}), flush=True)
        for line in sys.stdin:
            request = json.loads(line)
            result = predictor.predict(request["prefix"])
            print(json.dumps({"id": request["id"], "text": result}), flush=True)
    except Exception as exc:
        # Never put draft text or third-party exception messages in logs.
        print(json.dumps({"error": type(exc).__name__}), flush=True)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
