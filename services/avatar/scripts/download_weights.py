import os
from huggingface_hub import snapshot_download

def download():
    models_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "models")
    os.makedirs(models_dir, exist_ok=True)

    print("Downloading MuseTalk weights...")
    snapshot_download(
        repo_id="TMElyralab/MuseTalk",
        local_dir=os.path.join(models_dir, "MuseTalk"),
        ignore_patterns=["*.md", "*.pth.tar"], # Skip unnecessary files if any
        resume_download=True
    )

    print("Downloading sd-vae-ft-mse...")
    snapshot_download(
        repo_id="stabilityai/sd-vae-ft-mse",
        local_dir=os.path.join(models_dir, "sd-vae-ft-mse"),
        resume_download=True
    )

    print("Downloading whisper-tiny...")
    snapshot_download(
        repo_id="openai/whisper-tiny",
        local_dir=os.path.join(models_dir, "whisper-tiny"),
        resume_download=True
    )

    print("Downloading dwpose weights...")
    dwpose_dir = os.path.join(models_dir, "dwpose")
    os.makedirs(dwpose_dir, exist_ok=True)
    snapshot_download(
        repo_id="yzd-v/DWPose",
        local_dir=dwpose_dir,
        allow_patterns=["dw-ll_ucoco_384.pth"],
        resume_download=True
    )

    print("Downloading face-parse-bisent weights...")
    face_parse_dir = os.path.join(models_dir, "face-parse-bisent")
    os.makedirs(face_parse_dir, exist_ok=True)
    snapshot_download(
        repo_id="ManyOtherFunctions/face-parse-bisent",
        local_dir=face_parse_dir,
        allow_patterns=["resnet18-5c106cde.pth", "79999_iter.pth"],
        resume_download=True
    )

    print("All weights downloaded.")

if __name__ == "__main__":
    download()
