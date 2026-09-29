from pathlib import Path
import json
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
MODEL_ID = "openai/clip-vit-base-patch32"
REVISION = "3d74acf9a28c67741b2f4f2ea7635f0aaf6f0268"
ATTRIBUTES = {
    "modern": ("a photo of a modern contemporary apartment interior", "a photo of an outdated old-fashioned apartment interior"),
    "spacious": ("a photo of a spacious open apartment interior", "a photo of a cramped small apartment interior"),
    "clutter": ("a photo of a cluttered room full of furniture and objects", "a photo of a tidy uncluttered room"),
    "large_windows": ("an apartment room with large windows", "an apartment room with small windows or no windows"),
    "old_furniture": ("a room with old brown wooden furniture", "a room with modern contemporary furniture"),
    "renovated": ("a newly renovated apartment interior", "a worn apartment interior in need of renovation"),
    "natural_light": ("a sunlit room with abundant natural daylight", "a dark room without natural daylight"),
    "balcony": ("a photo of an apartment balcony, loggia or outdoor terrace", "a photo of an indoor apartment room"),
    "large_balcony": ("a large spacious balcony or loggia with plenty of open space", "a small narrow cramped balcony or loggia"),
    "sheltered_balcony": ("a covered sheltered balcony or enclosed loggia", "an exposed uncovered outdoor balcony"),
}
SEMANTIC_KEYS = ("brightness", *ATTRIBUTES)

class Vision:
    def __init__(self):
        self.model = None
        self.processor = None

    def load(self):
        if self.model is not None:
            return
        import torch
        from transformers import CLIPModel, CLIPProcessor
        torch.set_num_threads(4)
        self.processor = CLIPProcessor.from_pretrained(MODEL_ID, revision=REVISION, cache_dir=ROOT / "data/models")
        # Fixed official weights; transformers uses torch's weights_only deserializer.
        self.model = CLIPModel.from_pretrained(MODEL_ID, revision=REVISION, cache_dir=ROOT / "data/models",
                                              use_safetensors=False).eval()

    def encode(self, paths, on_embedding=None):
        """Attribute signals for every photo; `on_embedding(path, vector)` receives each
        L2-normalised CLIP image embedding (stored by content hash, not in the listing)."""
        if not paths:
            return None
        self.load()
        import torch
        from PIL import Image, ImageOps
        texts = [s for pair in ATTRIBUTES.values() for s in pair]
        per_photo=[]
        # Bound memory by encoding four images at a time, while processing every photo.
        for start in range(0,len(paths),4):
            images=[]
            for p in paths[start:start+4]:
                with Image.open(ROOT / p.removeprefix("/")) as im:
                    images.append(ImageOps.exif_transpose(im).convert("RGB").copy())
            inputs = self.processor(text=texts, images=images, return_tensors="pt", padding=True)
            with torch.inference_mode():
                output = self.model(**inputs)
                logits = output.logits_per_image
                if on_embedding:
                    for p, vector in zip(paths[start:start+4], output.image_embeds.numpy()):
                        on_embedding(p, vector)
                signals = logits.reshape(len(images), len(ATTRIBUTES), 2).softmax(dim=-1)[:, :, 0].numpy()
            for im,signal in zip(images,signals):
                retina=np.asarray(im.resize((8,8)),np.float32).ravel()/255
                attrs={"brightness":float(retina.mean()),**dict(zip(ATTRIBUTES,map(float,signal)))}
                # Qualities of a balcony matter only when the image resembles a balcony.
                for name in ("large_balcony", "sheltered_balcony"):
                    attrs[name] *= attrs["balcony"]
                per_photo.append({"retina":retina.tolist(),"semantic":list(attrs.values()),"attributes":attrs})
        attributes={name:float(np.mean([p["attributes"][name] for p in per_photo])) for name in per_photo[0]["attributes"]}
        return {"retina":np.mean([p["retina"] for p in per_photo],axis=0).tolist(),
                "semantic":list(attributes.values()), "attributes": attributes,"per_photo":per_photo,
                "encoder": MODEL_ID, "revision": REVISION, "algorithm":"all-photos-v2", "photos_analyzed":len(paths),
                "note": "CLIP similarity signals, not verified property attributes or calibrated probabilities."}

    def embed(self, paths):
        """L2-normalised CLIP image embeddings, identical to those produced by `encode`."""
        self.load()
        import torch
        from PIL import Image, ImageOps
        vectors = []
        for start in range(0, len(paths), 8):
            images = []
            for p in paths[start:start+8]:
                with Image.open(ROOT / p.removeprefix("/")) as im:
                    images.append(ImageOps.exif_transpose(im).convert("RGB").copy())
            inputs = self.processor(images=images, return_tensors="pt")
            with torch.inference_mode():
                features = self.model.get_image_features(**inputs)
                # transformers ≥ 5 returns model output with the projection in pooler_output.
                features = getattr(features, "pooler_output", features)
                vectors.extend((features / features.norm(dim=-1, keepdim=True)).numpy())
        return vectors

if __name__ == "__main__":
    Vision().load()
    print(json.dumps({"model": MODEL_ID, "revision": REVISION, "ready": True}), flush=True)
