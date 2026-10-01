"""Offline MockTransport handler with repeatable text-based or fixed responses."""
import hashlib
import json
import random
from copy import deepcopy

import httpx


class FakeJev:
    def __init__(self, answer=None):
        self.answer = deepcopy(answer)

    def __call__(self, request: httpx.Request) -> httpx.Response:
        if self.answer is not None:
            return httpx.Response(200, json=deepcopy(self.answer))
        body = json.loads(request.content)
        rng = random.Random(hashlib.sha256(body['state'].encode()).digest())
        answers = {}
        for name, question in body['questions'].items():
            if question['type'] == 'noul':
                answers[name] = {'type': 'noul', 'noul': rng.random()}
            else:
                weights = {key: rng.random() for key in question['criteria']}
                total = sum(weights.values())
                probabilities = {key: value / total for key, value in weights.items()}
                choice = max(probabilities, key=probabilities.get)
                answers[name] = {'type': 'choice', 'choice': choice, 'probabilities': probabilities, 'confidence': probabilities[choice]}
        return httpx.Response(200, json={'model': 'fake-jev-q1', 'answers': answers, 'usage': {'input_tokens': 0, 'output_tokens': 0}})
