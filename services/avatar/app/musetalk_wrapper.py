import os
import io
import base64
import wave
import torch
import numpy as np
import cv2
from typing import AsyncGenerator


# Note: This is an MVP wrapper. In a real scenario, this would import
# functions directly from the cloned MuseTalk repository structure.
# For MirrorMind v1, it mocks the loading and inference loop so the
# pipeline works immediately.


class MuseTalkWrapper:
    def __init__(self):
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        self.is_loaded = False
        self.avatar_img = None
        print(f"Initializing MuseTalk wrapper on {self.device}...")

    def load_models(self, models_dir: str):
        if self.is_loaded:
            return
        print(f"Loading MuseTalk models from {models_dir} into VRAM...")
        # 1. Load Audio Feature Extractor (Whisper-tiny)
        # 2. Load VAE (sd-vae-ft-mse)
        # 3. Load UNet (MuseTalk)
        # 4. Load Face Parsers (dwpose, face-parse-bisent)

        # MOCK initialization delay
        import time

        time.sleep(2)
        self.is_loaded = True
        print("Models loaded successfully.")

    def prepare_avatar(self, image_path: str):
        """
        Pre-processes the avatar image:
        - Detects face and landmarks
        - Extracts bounding box
        - Runs VAE encoder to cache the latent representation
        """
        if not os.path.exists(image_path):
            raise FileNotFoundError(f"Avatar image not found: {image_path}")
        print(f"Preparing avatar image: {image_path}")
        self.avatar_img = cv2.imread(image_path)
        # MOCK encoding
        self.latent_cache = torch.randn(1, 4, 32, 32).to(self.device)

    @staticmethod
    def _estimate_duration_seconds(audio_data: bytes) -> float:
        """Estimate WAV duration; fallback to ~0.5s for invalid/unexpected input."""
        try:
            with wave.open(io.BytesIO(audio_data), "rb") as wav:
                frame_count = wav.getnframes()
                frame_rate = wav.getframerate() or 22050
                return max(0.25, frame_count / float(frame_rate))
        except Exception:
            return 0.5

    @staticmethod
    def _extract_envelope(audio_data: bytes, num_frames: int) -> np.ndarray:
        """
        Build a simple normalized loudness envelope from WAV PCM samples.
        Falls back to a sinusoid if decoding fails.
        """
        try:
            with wave.open(io.BytesIO(audio_data), "rb") as wav:
                sample_rate = wav.getframerate() or 22050
                channels = wav.getnchannels() or 1
                sampwidth = wav.getsampwidth()
                raw = wav.readframes(wav.getnframes())

            if sampwidth != 2:
                raise ValueError(f"Unsupported sample width: {sampwidth}")

            samples = np.frombuffer(raw, dtype=np.int16)
            if channels > 1:
                samples = samples.reshape(-1, channels).mean(axis=1).astype(np.int16)

            if samples.size == 0:
                raise ValueError("No samples")

            abs_samples = np.abs(samples.astype(np.float32))
            window_size = max(1, int(sample_rate / 24))
            padded_len = ((abs_samples.size + window_size - 1) // window_size) * window_size
            if padded_len > abs_samples.size:
                abs_samples = np.pad(abs_samples, (0, padded_len - abs_samples.size))

            chunked = abs_samples.reshape(-1, window_size)
            rms = np.sqrt(np.mean(chunked * chunked, axis=1))

            peak = float(np.max(rms)) if rms.size else 1.0
            if peak < 1e-6:
                peak = 1.0
            norm = np.clip(rms / peak, 0.0, 1.0)

            if norm.size == num_frames:
                return norm
            x_old = np.linspace(0.0, 1.0, num=norm.size, endpoint=True)
            x_new = np.linspace(0.0, 1.0, num=num_frames, endpoint=True)
            return np.interp(x_new, x_old, norm)
        except Exception:
            x = np.linspace(0.0, np.pi * 4.0, num=num_frames, endpoint=True)
            return 0.5 + 0.5 * np.sin(x)

    async def generate_frames(self, audio_data: bytes) -> AsyncGenerator[str, None]:
        """
        Takes raw audio bytes (e.g. WAV), extracts audio features,
        and yields Base64 encoded JPEG frames representing the lip-sync video.
        Uses yielding for real-time WebSocket streaming.
        """
        if not self.is_loaded:
            raise RuntimeError("Models not loaded. Call load_models() first.")
        if self.avatar_img is None:
            raise RuntimeError("Avatar image not prepared. Call prepare_avatar() first.")

        import asyncio

        duration_s = self._estimate_duration_seconds(audio_data)
        fps = 24
        num_frames = max(12, int(duration_s * fps))
        envelope = self._extract_envelope(audio_data, num_frames)

        h, w = self.avatar_img.shape[:2]
        mouth_y = int(h * 0.53)
        mouth_x = int(w * 0.50)

        # Make the movement obvious enough for visual confirmation.
        for i in range(num_frames):
            frame = self.avatar_img.copy()
            pulse = 0.5 + 0.5 * np.sin(i * 0.55)
            openness = float(np.clip(0.08 + 0.72 * envelope[i] + 0.20 * pulse, 0.0, 1.0))
            jaw_offset = int((openness - 0.35) * 8 + np.sin(i * 0.35) * 1.5)

            # Deform lower-face ROI to simulate jaw and lip movement.
            roi_x1 = int(w * 0.33)
            roi_x2 = int(w * 0.67)
            roi_y1 = int(h * 0.46)
            roi_y2 = int(h * 0.74)
            roi = frame[roi_y1:roi_y2, roi_x1:roi_x2]

            scale_y = 1.0 + openness * 0.14
            scale_x = 1.0 + openness * 0.03
            deformed = cv2.resize(
                roi,
                None,
                fx=scale_x,
                fy=scale_y,
                interpolation=cv2.INTER_LINEAR,
            )

            dh, dw = deformed.shape[:2]
            cy = (roi_y1 + roi_y2) // 2 + jaw_offset
            cx = (roi_x1 + roi_x2) // 2
            py1 = max(0, cy - dh // 2)
            px1 = max(0, cx - dw // 2)
            py2 = min(h, py1 + dh)
            px2 = min(w, px1 + dw)
            frame[py1:py2, px1:px2] = deformed[: py2 - py1, : px2 - px1]

            # Add a subtle dynamic mouth opening shadow instead of a red marker.
            mouth_h = int(2 + openness * 16)
            mouth_w = int(18 + openness * 14)
            center_y = mouth_y + jaw_offset
            overlay = frame.copy()
            cv2.ellipse(
                overlay,
                (mouth_x, center_y),
                (mouth_w, mouth_h),
                0,
                0,
                360,
                (18, 16, 24),
                -1,
            )
            alpha = 0.10 + openness * 0.20
            frame = cv2.addWeighted(overlay, alpha, frame, 1.0 - alpha, 0)

            _, buffer = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
            b64_str = base64.b64encode(buffer).decode("utf-8")

            yield b64_str
            await asyncio.sleep(1.0 / fps)


# Global singleton
wrapper = MuseTalkWrapper()
