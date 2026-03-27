def embed(text: str) -> list[float]:
    return [float((sum(ord(c) for c in text) % 97))/97.0]
