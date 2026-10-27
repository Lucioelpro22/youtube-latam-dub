"""Local English -> Spanish caption translation using the Argos model.

Model source and hash: models/SOURCE.json. No translation HTTP requests.
"""
from pathlib import Path
import importlib.util
import threading

MODEL_DIR = Path(__file__).resolve().parent / "models" / "en_es"
_ENGINE = None
_TOKENIZER = None
_LOCK = threading.Lock()


def available():
    return (MODEL_DIR.joinpath("model", "model.bin").is_file()
            and MODEL_DIR.joinpath("sentencepiece.model").is_file()
            and importlib.util.find_spec("ctranslate2") is not None
            and importlib.util.find_spec("sentencepiece") is not None)


def warmup():
    global _ENGINE, _TOKENIZER
    with _LOCK:
        if _ENGINE is None:
            import ctranslate2
            import sentencepiece
            tokenizer = sentencepiece.SentencePieceProcessor(model_file=str(MODEL_DIR / "sentencepiece.model"))
            engine = ctranslate2.Translator(str(MODEL_DIR / "model"), device="cpu",
                compute_type="int8", intra_threads=2, inter_threads=1)
            _TOKENIZER, _ENGINE = tokenizer, engine


def translate(text):
    warmup()
    # Caption chunks are small. Split unusually large API inputs to avoid truncation.
    with _LOCK:
        tokens = _TOKENIZER.encode(text, out_type=str)
        if not tokens:
            return ""
        batches = [tokens[i:i + 160] for i in range(0, len(tokens), 160)]
        results = _ENGINE.translate_batch(batches, beam_size=2,
            max_decoding_length=512, replace_unknowns=True)
        return " ".join(_TOKENIZER.decode(result.hypotheses[0]).strip() for result in results).strip()
