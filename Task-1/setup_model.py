"""
One-time helper: downloads the local AI model into  models/all-MiniLM-L6-v2
so the portal runs fully offline afterwards (no internet, no API key).

The model is already bundled in this project. Only run this if the models/
folder is missing or you want to refresh it.

Run:  python setup_model.py
"""
import os

from sentence_transformers import SentenceTransformer


def main():
    target = os.path.join(os.path.dirname(__file__), "models", "all-MiniLM-L6-v2")
    if os.path.isdir(target):
        print("Model already present at:", target)
        return
    print("Downloading all-MiniLM-L6-v2 (~80 MB) ...")
    model = SentenceTransformer("all-MiniLM-L6-v2")
    model.save(target)
    print("Saved to:", target)


if __name__ == "__main__":
    main()
