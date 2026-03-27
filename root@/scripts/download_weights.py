import os
from huggingface_hub import hf_hub_download


def _ensure_file(repo_id: str, filename: str, out_dir: str) -> None:
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, filename)

    # Remove stale/broken symlinks from older runs so existence checks are reliable.
    if os.path.islink(out_path) and not os.path.exists(out_path):
        os.unlink(out_path)

    if os.path.isfile(out_path) and os.path.getsize(out_path) > 0:
        print(f"{filename} already present; skipping.")
        return

    print(f"Downloading {repo_id}/{filename} -> {out_path}")
    hf_hub_download(
        repo_id=repo_id,
        filename=filename,
        local_dir=out_dir,
        local_dir_use_symlinks=False,
        resume_download=True,
    )


def download() -> None:
    models_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "models")
    os.makedirs(models_dir, exist_ok=True)

    print("Ensuring MuseTalk weights...")
    musetalk_dir = os.path.join(models_dir, "MuseTalk", "musetalkV15")
    _ensure_file("TMElyralab/MuseTalk", "musetalkV15/musetalk.json", os.path.join(models_dir, "MuseTalk"))
    _ensure_file("TMElyralab/MuseTalk", "musetalkV15/unet.pth", os.path.join(models_dir, "MuseTalk"))

    print("Ensuring sd-vae-ft-mse weights...")
    vae_dir = os.path.join(models_dir, "sd-vae-ft-mse")
    _ensure_file("stabilityai/sd-vae-ft-mse", "config.json", vae_dir)
    _ensure_file("stabilityai/sd-vae-ft-mse", "diffusion_pytorch_model.safetensors", vae_dir)

    print("Ensuring whisper-tiny weights...")
    whisper_dir = os.path.join(models_dir, "whisper-tiny")
    whisper_files = [
        "config.json",
        "generation_config.json",
        "preprocessor_config.json",
        "tokenizer.json",
        "tokenizer_config.json",
        "vocab.json",
        "merges.txt",
        "normalizer.json",
        "pytorch_model.bin",
    ]
    for fname in whisper_files:
        _ensure_file("openai/whisper-tiny", fname, whisper_dir)

    print("Ensuring dwpose weights...")
    dwpose_dir = os.path.join(models_dir, "dwpose")
    _ensure_file("yzd-v/DWPose", "dw-ll_ucoco_384.pth", dwpose_dir)

    print("Ensuring face-parse-bisent weights...")
    face_parse_dir = os.path.join(models_dir, "face-parse-bisent")
    _ensure_file("ManyOtherFunctions/face-parse-bisent", "resnet18-5c106cde.pth", face_parse_dir)
    _ensure_file("ManyOtherFunctions/face-parse-bisent", "79999_iter.pth", face_parse_dir)

    print("All weights ready.")


if __name__ == "__main__":
    download()
