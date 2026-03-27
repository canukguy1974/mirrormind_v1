import base64
import asyncio
import io
import json
import math
import os
import tempfile
import time
import wave
from typing import AsyncGenerator

import cv2
import librosa
import numpy as np
import torch
import torch.nn as nn
from diffusers import AutoencoderKL, UNet2DConditionModel
from transformers import AutoFeatureExtractor, WhisperModel


class PositionalEncoding(nn.Module):
    def __init__(self, d_model: int = 384, max_len: int = 5000):
        super().__init__()
        pe = torch.zeros(max_len, d_model)
        position = torch.arange(0, max_len, dtype=torch.float).unsqueeze(1)
        div_term = torch.exp(torch.arange(0, d_model, 2).float() * (-math.log(10000.0) / d_model))
        pe[:, 0::2] = torch.sin(position * div_term)
        pe[:, 1::2] = torch.cos(position * div_term)
        self.register_buffer("pe", pe.unsqueeze(0))

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return x + self.pe[:, : x.size(1), :].to(x.device)


class SimpleVAE:
    def __init__(self, model_path: str, device: torch.device, use_fp16: bool):
        self.vae = AutoencoderKL.from_pretrained(model_path)
        self.device = device
        self.vae.to(device)
        self.use_fp16 = use_fp16
        if self.use_fp16:
            self.vae = self.vae.half()
        self.scaling_factor = self.vae.config.scaling_factor

    def _preprocess(self, img_bgr: np.ndarray, half_mask: bool) -> torch.Tensor:
        img_rgb = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2RGB)
        img = cv2.resize(img_rgb, (256, 256), interpolation=cv2.INTER_LANCZOS4)
        x = img.astype(np.float32) / 255.0
        x = (x * 2.0) - 1.0
        x = np.transpose(x, (2, 0, 1))
        t = torch.from_numpy(x).unsqueeze(0).to(self.device)
        if half_mask:
            t[:, :, 128:, :] = 0
        if self.use_fp16:
            t = t.half()
        return t

    @torch.no_grad()
    def get_latents_for_unet(self, img_bgr: np.ndarray) -> torch.Tensor:
        masked = self._preprocess(img_bgr, half_mask=True)
        ref = self._preprocess(img_bgr, half_mask=False)
        masked_latents = self.scaling_factor * self.vae.encode(masked).latent_dist.sample()
        ref_latents = self.scaling_factor * self.vae.encode(ref).latent_dist.sample()
        return torch.cat([masked_latents, ref_latents], dim=1)

    @torch.no_grad()
    def decode_latents(self, latents: torch.Tensor) -> np.ndarray:
        x = (1.0 / self.scaling_factor) * latents
        image = self.vae.decode(x.to(self.vae.dtype)).sample
        image = (image / 2 + 0.5).clamp(0, 1)
        image = torch.nan_to_num(image, nan=0.5, posinf=1.0, neginf=0.0)
        image = image.detach().cpu().permute(0, 2, 3, 1).float().numpy()
        image = (image * 255).round().astype("uint8")
        return image[..., ::-1]


class MuseTalkWrapper:
    def __init__(self):
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        self.use_fp16 = self.device.type == "cuda"
        self.is_loaded = False
        self.use_fallback = False
        self.force_fallback = False
        self.avatar_img = None
        self.avatar_crop_bbox = None
        self.latent_cache = None
        if self.device.type == "cuda":
            try:
                vram_gb = torch.cuda.get_device_properties(0).total_memory / (1024 ** 3)
                # 4GB cards are not practical for stable MuseTalk inference in this stack.
                if vram_gb <= 6.0:
                    self.force_fallback = True
                    print(f"Detected {vram_gb:.1f}GB VRAM; forcing lightweight fallback animation mode.")
            except Exception:
                pass
        print(f"Initializing MuseTalk wrapper on {self.device}...")

    def load_models(self, models_dir: str):
        if self.is_loaded:
            return

        print(f"Loading MuseTalk models from {models_dir}...")
        try:
            unet_config = os.path.join(models_dir, "MuseTalk", "musetalkV15", "musetalk.json")
            unet_weights = os.path.join(models_dir, "MuseTalk", "musetalkV15", "unet.pth")
            vae_path = os.path.join(models_dir, "sd-vae-ft-mse")
            whisper_path = os.path.join(models_dir, "whisper-tiny")

            with open(unet_config, "r", encoding="utf-8") as f:
                cfg = json.load(f)

            self.unet = UNet2DConditionModel(**cfg)
            weights = torch.load(unet_weights, map_location=self.device)
            self.unet.load_state_dict(weights)
            self.unet.to(self.device)
            if self.use_fp16:
                self.unet = self.unet.half()
            self.unet.eval()

            self.vae = SimpleVAE(model_path=vae_path, device=self.device, use_fp16=self.use_fp16)
            self.pe = PositionalEncoding(d_model=384).to(self.device)
            if self.use_fp16:
                self.pe = self.pe.half()

            self.feature_extractor = AutoFeatureExtractor.from_pretrained(whisper_path)
            self.whisper = WhisperModel.from_pretrained(whisper_path)
            self.whisper.to(self.device)
            if self.use_fp16:
                self.whisper = self.whisper.half()
            self.whisper.eval()
            self.whisper.requires_grad_(False)

            self.timestep = torch.tensor([0], device=self.device)
            self.is_loaded = True
            print("MuseTalk models loaded successfully.")
        except Exception as e:
            print(f"MuseTalk load failed, switching to fallback: {repr(e)}")
            self.use_fallback = True
            self.is_loaded = True

    def prepare_avatar(self, image_path: str):
        if not os.path.exists(image_path):
            raise FileNotFoundError(f"Avatar image not found: {image_path}")
        self.avatar_img = cv2.imread(image_path)
        if self.avatar_img is None:
            raise RuntimeError(f"Failed to decode avatar image: {image_path}")

        h, w = self.avatar_img.shape[:2]
        x1 = int(w * 0.33)
        x2 = int(w * 0.67)
        y1 = int(h * 0.38)
        y2 = int(h * 0.76)
        self.avatar_crop_bbox = (x1, y1, x2, y2)

        if not self.use_fallback:
            crop = self.avatar_img[y1:y2, x1:x2]
            self.latent_cache = self.vae.get_latents_for_unet(crop)
            print("Avatar prepared with MuseTalk latent cache.")
        else:
            print("Avatar prepared in fallback mode.")

    @staticmethod
    def _estimate_duration_seconds(audio_data: bytes) -> float:
        try:
            with wave.open(io.BytesIO(audio_data), "rb") as wav:
                frame_count = wav.getnframes()
                frame_rate = wav.getframerate() or 22050
                return max(0.25, frame_count / float(frame_rate))
        except Exception:
            return 1.0

    @staticmethod
    def _extract_envelope(audio_data: bytes, num_frames: int) -> np.ndarray:
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
            peak = max(peak, 1e-6)
            norm = np.clip(rms / peak, 0.0, 1.0)

            if norm.size == num_frames:
                return norm
            x_old = np.linspace(0.0, 1.0, num=norm.size, endpoint=True)
            x_new = np.linspace(0.0, 1.0, num=num_frames, endpoint=True)
            return np.interp(x_new, x_old, norm)
        except Exception:
            x = np.linspace(0.0, np.pi * 4.0, num=num_frames, endpoint=True)
            return 0.5 + 0.5 * np.sin(x)

    async def _yield_fallback_animation(self, audio_data: bytes, fps: int = 24) -> AsyncGenerator[str, None]:
        duration_s = self._estimate_duration_seconds(audio_data)
        num_frames = max(12, int(duration_s * fps))
        envelope = self._extract_envelope(audio_data, num_frames)
        h, w = self.avatar_img.shape[:2]

        # Place fallback mouth effect higher so it aligns with lips, not chin.
        mouth_y = int(h * 0.53)
        mouth_x = int(w * 0.50)
        for i in range(num_frames):
            frame = self.avatar_img.copy()
            pulse = 0.5 + 0.5 * math.sin(i * 0.5)
            openness = float(np.clip(0.08 + 0.72 * envelope[i] + 0.20 * pulse, 0.0, 1.0))
            mouth_h = int(2 + openness * 15)
            mouth_w = int(16 + openness * 12)
            overlay = frame.copy()
            cv2.ellipse(
                overlay,
                (mouth_x, mouth_y),
                (mouth_w, mouth_h),
                0,
                0,
                360,
                (20, 18, 30),
                -1,
            )
            alpha = 0.10 + openness * 0.22
            frame = cv2.addWeighted(overlay, alpha, frame, 1.0 - alpha, 0)

            ok, buffer = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
            if not ok:
                continue
            yield base64.b64encode(buffer).decode("utf-8")
            await asyncio.sleep(1.0 / fps)

    def _extract_whisper_chunks(
        self,
        wav_path: str,
        fps: int = 24,
        audio_padding_length_left: int = 2,
        audio_padding_length_right: int = 2,
    ) -> torch.Tensor:
        samples, sr = librosa.load(wav_path, sr=16000)
        if samples.size == 0:
            return torch.empty((0, 50, 384), device=self.device)

        segment_length = 30 * sr
        segments = [samples[i : i + segment_length] for i in range(0, len(samples), segment_length)]

        whisper_feature_list = []
        dtype = self.unet.dtype
        for segment in segments:
            input_features = self.feature_extractor(
                segment,
                return_tensors="pt",
                sampling_rate=sr,
            ).input_features.to(self.device)
            input_features = input_features.to(dtype=dtype)
            audio_feats = self.whisper.encoder(input_features, output_hidden_states=True).hidden_states
            audio_feats = torch.stack(audio_feats, dim=2)
            whisper_feature_list.append(audio_feats)

        whisper_feature = torch.cat(whisper_feature_list, dim=1)

        audio_fps = 50
        whisper_idx_multiplier = audio_fps / int(fps)
        num_frames = max(1, math.floor((len(samples) / sr) * fps))
        actual_length = max(1, math.floor((len(samples) / sr) * audio_fps))
        whisper_feature = whisper_feature[:, :actual_length, ...]

        padding_nums = math.ceil(whisper_idx_multiplier)
        pad_left = torch.zeros_like(whisper_feature[:, : padding_nums * audio_padding_length_left])
        pad_right = torch.zeros_like(whisper_feature[:, : padding_nums * 3 * audio_padding_length_right])
        whisper_feature = torch.cat([pad_left, whisper_feature, pad_right], dim=1)

        audio_feature_length_per_frame = 2 * (audio_padding_length_left + audio_padding_length_right + 1)
        prompts = []
        for frame_index in range(num_frames):
            audio_index = math.floor(frame_index * whisper_idx_multiplier)
            clip = whisper_feature[:, audio_index : audio_index + audio_feature_length_per_frame]
            if clip.shape[1] != audio_feature_length_per_frame:
                break
            prompts.append(clip)

        if not prompts:
            return torch.empty((0, 50, 384), device=self.device)

        audio_prompts = torch.cat(prompts, dim=0)
        # [B, C, H, W] -> [B, C*H, W]
        b, c, h, w = audio_prompts.shape
        audio_prompts = audio_prompts.permute(0, 1, 2, 3).reshape(b, c * h, w)
        return audio_prompts

    async def generate_frames(self, audio_data: bytes) -> AsyncGenerator[str, None]:
        if not self.is_loaded:
            raise RuntimeError("Models not loaded. Call load_models() first.")
        if self.avatar_img is None:
            raise RuntimeError("Avatar image not prepared. Call prepare_avatar() first.")

        import asyncio

        if self.use_fallback or self.force_fallback:
            async for frame_b64 in self._yield_fallback_animation(audio_data, fps=24):
                yield frame_b64
            return

        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
            tmp.write(audio_data)
            wav_path = tmp.name

        try:
            start_ts = time.monotonic()
            realtime_deadline_s = 8.0
            audio_prompts = self._extract_whisper_chunks(wav_path, fps=24)
            if audio_prompts.numel() == 0:
                return
            if time.monotonic() - start_ts > realtime_deadline_s:
                print("MuseTalk inference setup exceeded realtime budget; using fallback animation.")
                async for frame_b64 in self._yield_fallback_animation(audio_data, fps=24):
                    yield frame_b64
                return

            x1, y1, x2, y2 = self.avatar_crop_bbox
            face_w = x2 - x1
            face_h = y2 - y1

            for i in range(audio_prompts.shape[0]):
                audio_prompt = audio_prompts[i : i + 1].to(self.device, dtype=self.unet.dtype)
                audio_feature = self.pe(audio_prompt)
                latent_batch = self.latent_cache.to(self.device, dtype=self.unet.dtype)

                pred_latents = self.unet(
                    latent_batch,
                    self.timestep,
                    encoder_hidden_states=audio_feature,
                ).sample
                pred_latents = torch.nan_to_num(pred_latents, nan=0.0, posinf=1.0, neginf=-1.0)

                recon = self.vae.decode_latents(pred_latents)
                face_patch = recon[0]
                face_patch = cv2.resize(face_patch, (face_w, face_h), interpolation=cv2.INTER_LINEAR)
                # Guard against degenerate outputs (flat gray/invalid patches on low VRAM).
                if float(np.std(face_patch)) < 4.0:
                    raise RuntimeError("MuseTalk patch variance too low")

                frame = self.avatar_img.copy()
                base_patch = frame[y1:y2, x1:x2].astype(np.float32)
                pred_patch = face_patch.astype(np.float32)

                # Blend only a feathered mouth region to avoid square artifacts.
                mask = np.zeros((face_h, face_w), dtype=np.float32)
                center = (face_w // 2, int(face_h * 0.68))
                axes = (max(8, int(face_w * 0.20)), max(8, int(face_h * 0.16)))
                cv2.ellipse(mask, center, axes, 0, 0, 360, 1.0, -1)
                mask = cv2.GaussianBlur(mask, (0, 0), sigmaX=8.0, sigmaY=8.0)
                mask = np.clip(mask, 0.0, 1.0)[:, :, None]

                blended = (base_patch * (1.0 - mask) + pred_patch * mask).astype(np.uint8)
                frame[y1:y2, x1:x2] = blended

                ok, buffer = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
                if not ok:
                    continue
                yield base64.b64encode(buffer).decode("utf-8")
                await asyncio.sleep(1.0 / 24)
        except Exception as e:
            print(f"MuseTalk inference failed for chunk; falling back to lightweight animation: {repr(e)}")
            async for frame_b64 in self._yield_fallback_animation(audio_data, fps=24):
                yield frame_b64
        finally:
            try:
                os.remove(wav_path)
            except OSError:
                pass


wrapper = MuseTalkWrapper()
