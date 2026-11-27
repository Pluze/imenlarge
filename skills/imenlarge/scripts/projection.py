"""Apply a declared source-grid observation process to a downsampled RGB frame."""
import io
import math

import numpy as np
from PIL import Image, ImageFilter


def validate(profile):
    if not isinstance(profile, dict):
        raise ValueError("Supply a projection object.")
    allowed = {"status", "blur_radius", "noise_sigma", "seed", "jpeg_quality", "subsampling"}
    if set(profile) - allowed or profile.get("status") not in ("known", "assumed"):
        raise ValueError("Declare projection status as known or assumed and use documented fields.")
    for key in ("blur_radius", "noise_sigma"):
        val = profile.get(key, 0)
        if type(val) not in (float, int) or not math.isfinite(val) or val < 0:
            raise ValueError(f"Supply a finite nonnegative {key}.")
    if "seed" in profile or profile.get("noise_sigma"):
        if type(profile.get("seed")) is not int or profile["seed"] < 0:
            raise ValueError("Supply a nonnegative integer seed for the noise realization.")
    if "jpeg_quality" in profile or "subsampling" in profile:
        q = profile.get("jpeg_quality")
        sub = profile.get("subsampling", 2)
        if type(q) is not int or not 1 <= q <= 100 or type(sub) is not int or sub not in (0, 1, 2):
            raise ValueError("Use JPEG quality 1–100 and subsampling 0, 1 or 2.")


def project(down, profile):
    image = down
    if profile.get("blur_radius"):
        image = image.filter(ImageFilter.GaussianBlur(profile["blur_radius"]))
    if profile.get("noise_sigma"):
        values = np.asarray(image, dtype=float)
        noise = np.random.default_rng(profile["seed"]).normal(0, profile["noise_sigma"], values.shape)
        image = Image.fromarray(np.uint8(np.clip(np.rint(values + noise), 0, 255)))
    if "jpeg_quality" in profile:
        buf = io.BytesIO()
        image.save(buf, "JPEG", quality=profile["jpeg_quality"], subsampling=profile.get("subsampling", 2))
        buf.seek(0)
        with Image.open(buf) as encoded:
            image = encoded.convert("RGB")
    return image
