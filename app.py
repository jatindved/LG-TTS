from pathlib import Path
import textwrap, zipfile, os

app = r'''
import streamlit as st
import io
import json
import re
import hashlib
import zipfile
from datetime import datetime, timezone

from PIL import Image
from pydub import AudioSegment
from google import genai
from huggingface_hub import InferenceClient
from streamlit_local_storage import LocalStorage

APP_NAME = "Story Media Creator"

st.set_page_config(
    page_title=APP_NAME,
    page_icon="🎬",
    layout="wide",
)

# ---------------------------
# MODELS
# ---------------------------
PRIMARY_TTS_MODEL = "gemini-3.8-flash-tts"
FALLBACK_TTS_MODEL = "gemini-3.8-flash-lite-tts"

PRIMARY_IMAGE_MODEL = "Qwen/Qwen-Image"
FALLBACK_IMAGE_MODEL = "black-forest-labs/FLUX.1-schnell"

DEFAULT_VOICE = "Vindemiatrix"

VOICE_STYLE = (
    "A mature Indian female storyteller speaking natural Hindi to a child with "
    "maternal affection, devotional calm, warmth and dignity. Never sound like "
    "an announcer, advertisement, newsreader, or robotic assistant. Use natural "
    "breathing rhythm and meaningful pauses. Speak gently and unhurriedly. "
    "Recite the supplied transcript exactly. Do not sing. Do not add, remove, "
    "translate, paraphrase, summarize, or repeat words. Maintain the same narrator "
    "identity, vocal age, timbre, accent, pitch character, and speaking personality "
    "throughout the complete story."
)

VISUAL_STYLE = (
    "High-quality Indian devotional children's story illustration, cinematic "
    "composition, warm natural lighting, dignified expressive faces, coherent "
    "classical Indian costumes and architecture, detailed environment, painterly "
    "realism, family-friendly. No captions, no written text, no logos, no watermark."
)

# ---------------------------
# DEVICE STORAGE
# ---------------------------
storage = LocalStorage()

DEVICE_KEYS = {
    "g1": "smc_gemini_1",
    "g2": "smc_gemini_2",
    "g3": "smc_gemini_3",
    "h1": "smc_hf_1",
    "h2": "smc_hf_2",
    "h3": "smc_hf_3",
}

def read_device_value(storage_key, component_key):
    try:
        value = storage.getItem(storage_key, key=component_key)
        return value if isinstance(value, str) else ""
    except Exception:
        return ""

def save_device_value(storage_key, value):
    try:
        storage.setItem(storage_key, value)
    except Exception:
        pass

def delete_device_value(storage_key):
    try:
        storage.deleteItem(storage_key)
    except Exception:
        pass

for short, storage_key in DEVICE_KEYS.items():
    state_name = f"loaded_{short}"
    if state_name not in st.session_state:
        st.session_state[state_name] = read_device_value(
            storage_key, f"load_{short}"
        )

# ---------------------------
# HELPERS
# ---------------------------
def clean_keys(values):
    return [x.strip() for x in values if isinstance(x, str) and x.strip()]

def story_hash(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]

def split_sentences_exact(text):
    text = text.strip()
    if not text:
        return []
    pattern = re.compile(r".*?(?:[।!?…]+|\.(?=\s|$)|\n+|$)", re.S)
    pieces = [m.group(0) for m in pattern.finditer(text) if m.group(0)]
    return pieces if pieces else [text]

def make_dynamic_scenes(text, target_chars=420, max_chars=650):
    pieces = split_sentences_exact(text)
    scenes = []
    current = ""

    for piece in pieces:
        if not current:
            current = piece
            continue

        proposed = current + piece
        if len(proposed) <= target_chars:
            current = proposed
        elif len(proposed) <= max_chars and len(current) < int(target_chars * 0.65):
            current = proposed
        else:
            scenes.append(current.strip())
            current = piece

    if current.strip():
        scenes.append(current.strip())

    return scenes

def synthesize_one(api_key, model, voice, text, style):
    client = genai.Client(api_key=api_key)

    response = client.models.generate_content(
        model=model,
        contents=[{
            "role": "user",
            "parts": [{
                "text": text,
                "speech_metadata": {
                    "style": style
                }
            }]
        }],
        config={
            "response_modalities": ["AUDIO"],
            "speech_config": {
                "voice_config": {
                    "voice": voice
                }
            }
        }
    )

    try:
        return response.candidates[0].content.parts[0].inline_data.data
    except Exception as exc:
        raise RuntimeError("Gemini returned no audio.") from exc

def synthesize_with_rotation(api_keys, voice, text, style):
    attempts = []

    # Quality first: all accounts on Flash, then all accounts on Flash-Lite.
    for model in (PRIMARY_TTS_MODEL, FALLBACK_TTS_MODEL):
        for account_no, api_key in enumerate(api_keys, 1):
            try:
                audio = synthesize_one(
                    api_key=api_key,
                    model=model,
                    voice=voice,
                    text=text,
                    style=style,
                )
                return audio, model, account_no, attempts
            except Exception as exc:
                attempts.append({
                    "model": model,
                    "account": account_no,
                    "error": str(exc)[:700],
                })

    raise RuntimeError(json.dumps(attempts, ensure_ascii=False))

def image_dimensions(ratio):
    return {
        "9:16": (768, 1344),
        "16:9": (1344, 768),
        "1:1": (1024, 1024),
        "4:3": (1152, 864),
    }.get(ratio, (1024, 1024))

def make_image_prompt(scene_text, ratio, visual_style):
    framing = {
        "9:16": "vertical cinematic composition for mobile video",
        "16:9": "wide cinematic composition",
        "1:1": "balanced square composition",
        "4:3": "classic illustrated story composition",
    }.get(ratio, "cinematic composition")

    return f"""
Create one polished scene illustration for this exact story moment:

{scene_text}

Visual style:
{visual_style}

Composition:
{framing}.

Requirements:
- Show the correct people, action, place, mood, and period for this scene.
- Keep recurring characters visually consistent across the project.
- Preserve the same facial identity, approximate age, skin tone, hairstyle,
  ornaments and recognizable appearance whenever a character returns.
- Change pose, facial expression, costume or location only when required by the story.
- No captions.
- No subtitles.
- No text.
- No logo.
- No watermark.
""".strip()

def generate_image_once(token, model, prompt, ratio, seed):
    width, height = image_dimensions(ratio)
    client = InferenceClient(api_key=token)
    image = client.text_to_image(
        prompt=prompt,
        model=model,
        width=width,
        height=height,
        seed=seed,
    )

    if not isinstance(image, Image.Image):
        raise RuntimeError("Image provider returned an unexpected result.")
    return image

def generate_image_with_rotation(tokens, prompt, ratio, seed):
    attempts = []

    for model in (PRIMARY_IMAGE_MODEL, FALLBACK_IMAGE_MODEL):
        for account_no, token in enumerate(tokens, 1):
            try:
                image = generate_image_once(
                    token=token,
                    model=model,
                    prompt=prompt,
                    ratio=ratio,
                    seed=seed,
                )
                return image, model, account_no, attempts
            except Exception as exc:
                attempts.append({
                    "model": model,
                    "account": account_no,
                    "error": str(exc)[:700],
                })

    raise RuntimeError(json.dumps(attempts, ensure_ascii=False))

def png_bytes(image):
    out = io.BytesIO()
    image.save(out, format="PNG")
    return out.getvalue()

def wav_segment(wav):
    return AudioSegment.from_file(io.BytesIO(wav), format="wav")

def read_resume_package(upload, expected_story_hash, expected_voice):
    audio = {}
    images = {}
    metadata = {}
    state = None

    if upload is None:
        return audio, images, metadata, state

    with zipfile.ZipFile(io.BytesIO(upload.getvalue()), "r") as archive:
        if "project_state.json" not in archive.namelist():
            raise ValueError("This is not a Story Media Creator resume package.")

        state = json.loads(
            archive.read("project_state.json").decode("utf-8")
        )

        if state.get("story_hash") != expected_story_hash:
            raise ValueError("This resume package belongs to another story.")

        if state.get("voice") != expected_voice:
            raise ValueError("The narrator voice is different in this resume package.")

        for name in archive.namelist():
            a = re.fullmatch(r"audio/scene_(\d{3})\.wav", name)
            i = re.fullmatch(r"images/scene_(\d{3})\.png", name)
            m = re.fullmatch(r"metadata/scene_(\d{3})\.json", name)

            if a:
                audio[int(a.group(1))] = archive.read(name)
            elif i:
                images[int(i.group(1))] = archive.read(name)
            elif m:
                metadata[int(m.group(1))] = json.loads(
                    archive.read(name).decode("utf-8")
                )

    return audio, images, metadata, state

# ---------------------------
# UI
# ---------------------------
st.title("🎬 Story Media Creator")
st.caption(
    "Story text + matching narration audio + matching scene images"
)

st.info(
    "The number of scenes is dynamic. The app does not force the story into "
    "three scenes. Each scene keeps its matching text, audio and image together."
)

with st.expander("🔑 API Keys", expanded=True):
    remember = st.checkbox(
        "Remember API keys on this device",
        value=True,
        help=(
            "Keys are saved in this browser's local storage, not in the GitHub "
            "repository. Do not enable this on a shared/public computer."
        )
    )

    st.markdown("#### Gemini API keys")
    st.caption(
        "Up to three Google AI Studio keys. Gemini 3.8 Flash TTS is tried first."
    )

    g1 = st.text_input(
        "Gemini API Key 1",
        value=st.session_state.get("loaded_g1", ""),
        type="password",
        key="input_g1",
    )
    g2 = st.text_input(
        "Gemini API Key 2",
        value=st.session_state.get("loaded_g2", ""),
        type="password",
        key="input_g2",
    )
    g3 = st.text_input(
        "Gemini API Key 3",
        value=st.session_state.get("loaded_g3", ""),
        type="password",
        key="input_g3",
    )

    st.markdown("#### Hugging Face image tokens")
    st.caption(
        "Used only for image generation through available free Inference Provider credits."
    )

    h1 = st.text_input(
        "Hugging Face Token 1",
        value=st.session_state.get("loaded_h1", ""),
        type="password",
        key="input_h1",
    )
    h2 = st.text_input(
        "Hugging Face Token 2",
        value=st.session_state.get("loaded_h2", ""),
        type="password",
        key="input_h2",
    )
    h3 = st.text_input(
        "Hugging Face Token 3",
        value=st.session_state.get("loaded_h3", ""),
        type="password",
        key="input_h3",
    )

    b1, b2 = st.columns(2)

    with b1:
        if st.button("💾 Save keys on this device", use_container_width=True):
            if remember:
                values = {
                    "g1": g1, "g2": g2, "g3": g3,
                    "h1": h1, "h2": h2, "h3": h3,
                }
                for short, value in values.items():
                    save_device_value(DEVICE_KEYS[short], value.strip())
                    st.session_state[f"loaded_{short}"] = value.strip()

                st.success(
                    "Keys saved in this browser on this device. "
                    "Refresh once if a saved value does not appear immediately."
                )
            else:
                st.warning("Enable 'Remember API keys on this device' first.")

    with b2:
        if st.button("🗑️ Clear saved keys from this device", use_container_width=True):
            for short, storage_key in DEVICE_KEYS.items():
                delete_device_value(storage_key)
                st.session_state[f"loaded_{short}"] = ""
            st.success("Saved API keys cleared from this device.")

gemini_keys = clean_keys([g1, g2, g3])
hf_tokens = clean_keys([h1, h2, h3])

k1, k2 = st.columns(2)
with k1:
    st.write(f"Gemini keys detected: **{len(gemini_keys)}**")
with k2:
    st.write(f"Image tokens detected: **{len(hf_tokens)}**")

st.subheader("1. Story")
story = st.text_area(
    "Paste the complete story",
    height=280,
    placeholder="Paste the complete Hindi story here.",
)

st.subheader("2. Project Settings")
c1, c2, c3 = st.columns(3)

with c1:
    voice = st.selectbox(
        "Fixed narrator voice",
        ["Vindemiatrix", "Achernar", "Gacrux", "Despina", "Algieba", "Kore"],
        index=0,
        help="The narrator identity remains fixed throughout the complete story."
    )

with c2:
    ratio = st.selectbox(
        "Image aspect ratio",
        ["9:16", "16:9", "1:1", "4:3"],
        index=0,
    )

with c3:
    target_chars = st.slider(
        "Approximate scene length",
        220,
        700,
        420,
        20,
        help=(
            "This controls approximate scene size, not a fixed scene count. "
            "Longer stories automatically create more scenes."
        )
    )

voice_style = st.text_area(
    "Narrator direction",
    value=VOICE_STYLE,
    height=150,
)

visual_style = st.text_area(
    "Image direction",
    value=VISUAL_STYLE,
    height=150,
)

bgm = st.file_uploader(
    "Optional background music",
    type=["mp3", "wav"],
)

bgm_db = st.slider(
    "Background music level under narration (dB)",
    -36,
    -14,
    -27,
)

resume_zip = st.file_uploader(
    "Optional: resume an unfinished project ZIP",
    type=["zip"],
)

scenes = (
    make_dynamic_scenes(
        story,
        target_chars=target_chars,
        max_chars=max(450, target_chars + 180),
    )
    if story.strip()
    else []
)

if scenes:
    st.success(f"Dynamic scene plan: {len(scenes)} scenes")
    with st.expander("Preview scene text"):
        for n, scene in enumerate(scenes, 1):
            st.markdown(f"**Scene {n:03d}**")
            st.write(scene)

# ---------------------------
# RUN
# ---------------------------
if st.button(
    "🚀 Generate / Resume Story Media",
    type="primary",
    use_container_width=True,
):
    if not story.strip():
        st.error("Paste the story first.")
        st.stop()

    if not gemini_keys:
        st.error("Add at least one Gemini API key.")
        st.stop()

    if not hf_tokens:
        st.error("Add at least one Hugging Face token for image generation.")
        st.stop()

    s_hash = story_hash(story)

    old_audio, old_images, old_meta, old_state = {}, {}, {}, None

    if resume_zip:
        try:
            old_audio, old_images, old_meta, old_state = read_resume_package(
                resume_zip,
                expected_story_hash=s_hash,
                expected_voice=voice,
            )
            st.info(
                f"Resume package loaded: {len(old_audio)} audio scenes and "
                f"{len(old_images)} image scenes already available."
            )
        except Exception as exc:
            st.warning(f"Resume package could not be reused: {exc}")

    state = old_state or {
        "app": APP_NAME,
        "version": 1,
        "story_hash": s_hash,
        "voice": voice,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }

    state.update({
        "voice": voice,
        "total_scenes": len(scenes),
        "status": "RUNNING",
        "failed_scene": None,
        "last_error": None,
        "primary_tts_model": PRIMARY_TTS_MODEL,
        "fallback_tts_model": FALLBACK_TTS_MODEL,
    })

    progress = st.progress(0)
    status = st.empty()

    completed = []
    log = []
    paused = False

    for scene_no, scene_text in enumerate(scenes, 1):
        status.write(f"Processing Scene {scene_no} of {len(scenes)}…")

        audio = old_audio.get(scene_no)
        image_bytes = old_images.get(scene_no)
        meta = old_meta.get(scene_no, {})

        # Audio
        if audio is None:
            try:
                audio, tts_model, tts_account, tts_attempts = (
                    synthesize_with_rotation(
                        api_keys=gemini_keys,
                        voice=voice,
                        text=scene_text,
                        style=voice_style.strip(),
                    )
                )
                meta.update({
                    "tts_model": tts_model,
                    "tts_account": tts_account,
                    "tts_attempts_before_success": tts_attempts,
                })
            except Exception as exc:
                state.update({
                    "status": "PAUSED",
                    "failed_scene": scene_no,
                    "last_error": f"TTS: {str(exc)[:3000]}",
                })
                log.append({
                    "scene": scene_no,
                    "stage": "audio",
                    "status": "FAILED",
                    "error": str(exc)[:2000],
                })
                paused = True
                break
        else:
            meta.setdefault("tts_model", "RESUMED")
            meta.setdefault("tts_account", 0)

        # Image
        if image_bytes is None:
            prompt = make_image_prompt(
                scene_text=scene_text,
                ratio=ratio,
                visual_style=visual_style.strip(),
            )

            try:
                image, image_model, image_account, image_attempts = (
                    generate_image_with_rotation(
                        tokens=hf_tokens,
                        prompt=prompt,
                        ratio=ratio,
                        seed=10000 + scene_no,
                    )
                )
                image_bytes = png_bytes(image)
                meta.update({
                    "image_model": image_model,
                    "image_account": image_account,
                    "image_attempts_before_success": image_attempts,
                    "image_prompt": prompt,
                })
            except Exception as exc:
                # Preserve the already-created scene audio.
                completed.append({
                    "scene_no": scene_no,
                    "text": scene_text,
                    "audio": audio,
                    "image": None,
                    "meta": meta,
                })

                state.update({
                    "status": "PAUSED",
                    "failed_scene": scene_no,
                    "last_error": f"IMAGE: {str(exc)[:3000]}",
                })
                log.append({
                    "scene": scene_no,
                    "stage": "image",
                    "status": "FAILED",
                    "error": str(exc)[:2000],
                })
                paused = True
                break
        else:
            meta.setdefault("image_model", "RESUMED")
            meta.setdefault("image_account", 0)

        completed.append({
            "scene_no": scene_no,
            "text": scene_text,
            "audio": audio,
            "image": image_bytes,
            "meta": meta,
        })

        log.append({
            "scene": scene_no,
            "status": "DONE",
            "tts_model": meta.get("tts_model"),
            "tts_account": meta.get("tts_account"),
            "image_model": meta.get("image_model"),
            "image_account": meta.get("image_account"),
        })

        progress.progress(scene_no / len(scenes))

    if not paused and len(completed) == len(scenes):
        state.update({
            "status": "COMPLETE",
            "failed_scene": None,
            "last_error": None,
        })

    # Master narration
    master_voice = AudioSegment.empty()

    for item in completed:
        if item["audio"]:
            try:
                master_voice += wav_segment(item["audio"])
                master_voice += AudioSegment.silent(duration=850)
            except Exception:
                pass

    master = master_voice

    if len(master_voice) and bgm is not None:
        try:
            music = AudioSegment.from_file(io.BytesIO(bgm.getvalue()))
            music = (
                music.set_frame_rate(master_voice.frame_rate)
                .set_channels(master_voice.channels)
                + bgm_db
            )

            if len(music) < len(master_voice):
                music = music * ((len(master_voice) // len(music)) + 1)

            music = music[:len(master_voice)].fade_in(1000).fade_out(2500)
            master = music.overlay(master_voice)
        except Exception as exc:
            st.warning(f"Background music could not be mixed: {exc}")

    master_mp3 = io.BytesIO()

    if len(master):
        master.export(
            master_mp3,
            format="mp3",
            bitrate="192k",
        )

    # Package
    package = io.BytesIO()

    with zipfile.ZipFile(package, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(
            "project_state.json",
            json.dumps(state, ensure_ascii=False, indent=2).encode("utf-8"),
        )

        archive.writestr(
            "run_log.json",
            json.dumps(log, ensure_ascii=False, indent=2).encode("utf-8"),
        )

        archive.writestr(
            "story/full_story.txt",
            story.encode("utf-8"),
        )

        archive.writestr(
            "story/scenes.json",
            json.dumps(
                [
                    {"scene": n, "text": text}
                    for n, text in enumerate(scenes, 1)
                ],
                ensure_ascii=False,
                indent=2,
            ).encode("utf-8"),
        )

        if len(master):
            archive.writestr(
                "audio/full_story_master.mp3",
                master_mp3.getvalue(),
            )

        for item in completed:
            n = item["scene_no"]

            archive.writestr(
                f"story/scene_{n:03d}.txt",
                item["text"].encode("utf-8"),
            )

            if item["audio"]:
                archive.writestr(
                    f"audio/scene_{n:03d}.wav",
                    item["audio"],
                )

            if item["image"]:
                archive.writestr(
                    f"images/scene_{n:03d}.png",
                    item["image"],
                )

            archive.writestr(
                f"metadata/scene_{n:03d}.json",
                json.dumps(
                    item["meta"],
                    ensure_ascii=False,
                    indent=2,
                ).encode("utf-8"),
            )

    status.empty()

    if state["status"] == "COMPLETE":
        st.success(
            "Complete: story text, matching narration audio and matching scene "
            "images are ready."
        )
    else:
        st.warning(
            f"Generation paused at Scene {state.get('failed_scene')}. "
            "Download the ZIP now. Later upload that ZIP in the Resume field and "
            "the app will continue without recreating completed assets."
        )

    if len(master):
        st.subheader("Full narration")
        st.audio(
            master_mp3.getvalue(),
            format="audio/mp3",
        )

    st.download_button(
        "⬇️ Download Story Media Project ZIP",
        data=package.getvalue(),
        file_name="Story_Media_Creator_Project.zip",
        mime="application/zip",
        type="primary",
        use_container_width=True,
    )

    st.subheader("Completed scenes")

    for item in completed:
        n = item["scene_no"]

        with st.expander(
            f"Scene {n:03d}",
            expanded=(n <= 2),
        ):
            left, right = st.columns(2)

            with left:
                st.markdown("**Story text**")
                st.write(item["text"])

                if item["audio"]:
                    st.markdown("**Narration audio**")
                    st.audio(
                        item["audio"],
                        format="audio/wav",
                    )

            with right:
                st.markdown("**Scene image**")

                if item["image"]:
                    st.image(
                        item["image"],
                        use_container_width=True,
                    )
                else:
                    st.info(
                        "Image pending. Resume this package when free image "
                        "quota becomes available."
                    )
'''

requirements = """streamlit>=1.40
google-genai>=2.25.0
pydub>=0.25.1
Pillow>=10.0.0
huggingface_hub>=0.27.0
streamlit-local-storage==0.0.25
"""

readme = """# Story Media Creator

English Streamlit application for:
- Complete story text
- Matching narration audio
- Matching scene image
- Dynamic scene count
- Fixed narrator voice
- Gemini 3.8 Flash TTS first, Flash-Lite fallback
- Up to three Gemini API keys
- Hugging Face image generation fallback
- Browser/device local storage for API keys
- Resume ZIP when a free quota is exhausted
- Optional background music

## Run locally

```bash
pip install -r requirements.txt
streamlit run app.py
