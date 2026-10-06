# BUILD: Story Media Creator FULL Character Bank Python 3.14 — 2026-10-06

import io
import json
import re
import zipfile
import hashlib
import wave
import tempfile
import subprocess
import os
from datetime import datetime, timezone

import streamlit as st
from PIL import Image
# Optional dependencies are guarded so the UI can still load and show diagnostics.
GENAI_IMPORT_ERROR = None
LOCAL_STORAGE_IMPORT_ERROR = None

try:
    from google import genai
except Exception as exc:
    genai = None
    GENAI_IMPORT_ERROR = repr(exc)

try:
    from streamlit_local_storage import LocalStorage
except Exception as exc:
    LocalStorage = None
    LOCAL_STORAGE_IMPORT_ERROR = repr(exc)

APP_NAME = "Story Media Creator"

st.set_page_config(
    page_title=APP_NAME,
    page_icon="🎬",
    layout="wide",
)

PRIMARY_TTS_MODEL = "gemini-3.8-flash-tts"
FALLBACK_TTS_MODEL = "gemini-3.8-flash-lite-tts"
PRIMARY_IMAGE_MODEL = "gemini-3.1-flash-image"
FALLBACK_IMAGE_MODEL = "gemini-3-pro-image"

DEFAULT_VOICE_STYLE = (
    "A mature Indian female narrator speaking natural Hindi to a child with "
    "maternal affection, devotional calm, warmth and dignity. Never sound robotic, "
    "commercial, or like a formal announcer. Speak gently and clearly, with natural "
    "breathing and meaningful pauses. Recite the provided text exactly as given. "
    "Do not summarize, paraphrase, translate, omit or add anything. Maintain the "
    "same narrator identity, timbre, age impression, and speaking personality "
    "throughout the complete story."
)

DEFAULT_IMAGE_STYLE = (
    "High-quality Indian devotional children's story illustration, cinematic "
    "composition, dignified expressive faces, coherent classical Indian costumes "
    "and architecture, detailed environment, painterly realism, family-friendly, "
    "soft warm natural lighting. No captions, no subtitles, no written text."
)

storage = None
if LocalStorage is not None:
    try:
        storage = LocalStorage()
    except Exception as exc:
        LOCAL_STORAGE_IMPORT_ERROR = repr(exc)
        storage = None

DEVICE_KEYS = {"g1": "smc_gemini_1", "g2": "smc_gemini_2", "g3": "smc_gemini_3"}

# ---------------------------
# STATE INIT
# ---------------------------
if "character_bank" not in st.session_state:
    st.session_state.character_bank = []

if "bank_loaded_once" not in st.session_state:
    st.session_state.bank_loaded_once = False

# ---------------------------
# LOCAL STORAGE
# ---------------------------
def read_device_value(storage_key, component_key):
    if storage is None:
        return ""
    try:
        value = storage.getItem(storage_key, key=component_key)
        return value if isinstance(value, str) else ""
    except Exception:
        return ""

def save_device_value(storage_key, value):
    if storage is None:
        return False
    try:
        storage.setItem(storage_key, value)
        return True
    except Exception:
        return False

def delete_device_value(storage_key):
    if storage is None:
        return False
    try:
        storage.deleteItem(storage_key)
        return True
    except Exception:
        return False

for short, storage_key in DEVICE_KEYS.items():
    state_name = f"loaded_{short}"
    if state_name not in st.session_state:
        st.session_state[state_name] = read_device_value(storage_key, f"load_{short}")

# ---------------------------
# HELPERS
# ---------------------------
def clean_keys(values):
    return [x.strip() for x in values if isinstance(x, str) and x.strip()]

def story_hash(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]

def slugify(value):
    value = value.strip().lower()
    value = re.sub(r"[^a-z0-9]+", "_", value)
    return value.strip("_") or "character"

def split_sentences_exact(text):
    text = text.strip()
    if not text:
        return []
    pattern = re.compile(r".*?(?:[।!?…]+|\.(?=\s|$)|\n+|$)", re.S)
    pieces = [m.group(0).strip() for m in pattern.finditer(text) if m.group(0) and m.group(0).strip()]
    return pieces if pieces else [text]

def make_dynamic_scenes(text, target_chars=420, max_chars=650):
    pieces = split_sentences_exact(text)
    if not pieces:
        return []
    scenes = []
    current = ""
    for piece in pieces:
        if not current:
            current = piece
            continue
        proposed = current + " " + piece
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

def concatenate_wav_bytes(wav_parts, silence_ms=850):
    """
    Concatenate PCM WAV files using only Python's standard library.
    Compatible with Python 3.14; no pydub/audioop dependency.
    """
    if not wav_parts:
        return b""

    first_params = None
    frames_out = bytearray()

    for wav_bytes in wav_parts:
        with wave.open(io.BytesIO(wav_bytes), "rb") as wf:
            params = (
                wf.getnchannels(),
                wf.getsampwidth(),
                wf.getframerate(),
                wf.getcomptype(),
            )

            if first_params is None:
                first_params = params
            elif params != first_params:
                raise RuntimeError(
                    "Narration WAV formats differ between scenes. "
                    "Keep the same Gemini voice/model settings for all scenes."
                )

            frames_out.extend(wf.readframes(wf.getnframes()))

            channels, sample_width, frame_rate, _ = first_params
            silence_frames = int(frame_rate * silence_ms / 1000)
            frames_out.extend(
                b"\\x00" * silence_frames * channels * sample_width
            )

    channels, sample_width, frame_rate, _ = first_params

    output = io.BytesIO()
    with wave.open(output, "wb") as wf:
        wf.setnchannels(channels)
        wf.setsampwidth(sample_width)
        wf.setframerate(frame_rate)
        wf.setcomptype("NONE", "not compressed")
        wf.writeframes(bytes(frames_out))

    return output.getvalue()


def render_master_mp3(master_wav_bytes, bgm_upload=None, bgm_db=-27):
    """
    Convert narration WAV to MP3 and optionally mix looping BGM with ffmpeg.
    ffmpeg is installed on Streamlit Cloud from packages.txt.
    """
    if not master_wav_bytes:
        return b""

    with tempfile.TemporaryDirectory() as tmp:
        voice_path = os.path.join(tmp, "voice.wav")
        output_path = os.path.join(tmp, "full_story_master.mp3")

        with open(voice_path, "wb") as f:
            f.write(master_wav_bytes)

        if bgm_upload is None:
            cmd = [
                "ffmpeg", "-y",
                "-i", voice_path,
                "-codec:a", "libmp3lame",
                "-b:a", "192k",
                output_path,
            ]
        else:
            ext = ".wav" if bgm_upload.name.lower().endswith(".wav") else ".mp3"
            bgm_path = os.path.join(tmp, "bgm" + ext)

            with open(bgm_path, "wb") as f:
                f.write(bgm_upload.getvalue())

            cmd = [
                "ffmpeg", "-y",
                "-i", voice_path,
                "-stream_loop", "-1",
                "-i", bgm_path,
                "-filter_complex",
                (
                    f"[1:a]volume={bgm_db}dB[bg];"
                    f"[0:a][bg]amix=inputs=2:duration=first:dropout_transition=2[mix]"
                ),
                "-map", "[mix]",
                "-codec:a", "libmp3lame",
                "-b:a", "192k",
                output_path,
            ]

        result = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )

        if result.returncode != 0:
            raise RuntimeError(
                "ffmpeg audio processing failed: "
                + result.stderr.decode("utf-8", errors="ignore")[-1500:]
            )

        return Path(output_path).read_bytes()

def pil_to_png_bytes(image):
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()

def build_scene_image_prompt(scene_text, image_style, ratio, matched_names):
    framing = {
        "9:16": "vertical cinematic composition for mobile video framing",
        "16:9": "wide cinematic composition",
        "1:1": "balanced square composition",
        "4:3": "classic illustrated story composition",
    }.get(ratio, "cinematic composition")
    matched_text = ", ".join(matched_names) if matched_names else "use story context to determine characters"
    return (
        f"Create one finished illustration for this exact story moment:\n\n"
        f"{scene_text}\n\n"
        f"Visual style:\n{image_style}\n\n"
        f"Composition:\n{framing}\n\n"
        f"Matched recurring characters from the character bank:\n{matched_text}\n\n"
        f"Important requirements:\n"
        f"- show the correct characters, action, place, emotion and time period\n"
        f"- if reference images are supplied, preserve those same facial identities and recurring appearances\n"
        f"- keep recurring characters visually consistent across scenes\n"
        f"- change pose, expression, clothing or background only when the story requires it\n"
        f"- no text, no captions, no logo, no watermark"
    )

def collect_uploaded_refs(uploaded_files):
    refs = []
    if not uploaded_files:
        return refs
    for f in uploaded_files:
        try:
            data = f.getvalue()
            if not data:
                continue
            refs.append({"name": f.name, "bytes": data, "mime": f.type or "image/png"})
        except Exception:
            continue
    return refs

def reference_note(reference_files):
    if not reference_files:
        return ""
    names = ", ".join([r["name"] for r in reference_files[:8]])
    return f"Reference images provided: {names}."

# ---------------------------
# CHARACTER BANK
# ---------------------------
def add_character_to_bank(project_group, name, aliases, notes, uploaded_files):
    refs = collect_uploaded_refs(uploaded_files)
    if not name.strip():
        raise ValueError("Character name is required.")
    if not refs:
        raise ValueError("At least one reference image is required.")

    entry = {
        "id": slugify(name) + "_" + str(len(st.session_state.character_bank) + 1),
        "project_group": project_group.strip() or "Custom",
        "name": name.strip(),
        "aliases": [a.strip() for a in aliases.split(",") if a.strip()],
        "notes": notes.strip(),
        "references": refs,
    }
    st.session_state.character_bank.append(entry)

def export_character_bank_zip_bytes():
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as z:
        bank_meta = []
        for char in st.session_state.character_bank:
            entry = {
                "id": char["id"],
                "project_group": char["project_group"],
                "name": char["name"],
                "aliases": char["aliases"],
                "notes": char["notes"],
                "references": [],
            }
            slug = slugify(char["name"])
            for idx, ref in enumerate(char["references"], 1):
                ext = ".png"
                mime = ref.get("mime", "")
                if "jpeg" in mime or ref["name"].lower().endswith(".jpg") or ref["name"].lower().endswith(".jpeg"):
                    ext = ".jpg"
                elif "webp" in mime or ref["name"].lower().endswith(".webp"):
                    ext = ".webp"
                path = f"images/{slug}_{char['id']}_{idx}{ext}"
                z.writestr(path, ref["bytes"])
                entry["references"].append({
                    "name": ref["name"],
                    "mime": ref["mime"],
                    "path": path,
                })
            bank_meta.append(entry)
        z.writestr("character_bank.json", json.dumps(bank_meta, ensure_ascii=False, indent=2).encode("utf-8"))
    return buffer.getvalue()

def import_character_bank_zip(upload):
    with zipfile.ZipFile(io.BytesIO(upload.getvalue()), "r") as z:
        if "character_bank.json" not in z.namelist():
            raise ValueError("This ZIP does not contain character_bank.json.")
        bank_meta = json.loads(z.read("character_bank.json").decode("utf-8"))
        imported = []
        for entry in bank_meta:
            refs = []
            for ref in entry.get("references", []):
                path = ref.get("path")
                if path in z.namelist():
                    refs.append({
                        "name": ref.get("name", path),
                        "mime": ref.get("mime", "image/png"),
                        "bytes": z.read(path),
                    })
            imported.append({
                "id": entry.get("id", slugify(entry.get("name", "character"))),
                "project_group": entry.get("project_group", "Custom"),
                "name": entry.get("name", "").strip(),
                "aliases": entry.get("aliases", []),
                "notes": entry.get("notes", ""),
                "references": refs,
            })
        st.session_state.character_bank = imported

def matched_character_entries(scene_text):
    text = scene_text.lower()
    matches = []
    for char in st.session_state.character_bank:
        candidates = [char["name"]] + list(char.get("aliases", []))
        candidates = [c.strip().lower() for c in candidates if c.strip()]
        if any(c and c in text for c in candidates):
            matches.append(char)
    return matches

def character_refs_for_scene(scene_text, previous_scene_ref=None, limit=8):
    matched = matched_character_entries(scene_text)
    refs = []
    names = []
    for char in matched:
        names.append(char["name"])
        for ref in char["references"]:
            refs.append(ref)
            if len(refs) >= limit:
                break
        if len(refs) >= limit:
            break
    if previous_scene_ref is not None and len(refs) < limit:
        refs.append(previous_scene_ref)
    return refs[:limit], names

# ---------------------------
# GEMINI CALLS
# ---------------------------
def synthesize_one(api_key, model, voice, text, style):
    if genai is None:
        raise RuntimeError("google-genai is not available. Check requirements.txt.")
    client = genai.Client(api_key=api_key)
    response = client.models.generate_content(
        model=model,
        contents=[{
            "role": "user",
            "parts": [{
                "text": text,
                "speech_metadata": {"style": style}
            }]
        }],
        config={
            "response_modalities": ["AUDIO"],
            "speech_config": {"voice_config": {"voice": voice}}
        }
    )
    for cand in getattr(response, "candidates", []) or []:
        content = getattr(cand, "content", None)
        if not content:
            continue
        for part in getattr(content, "parts", []) or []:
            inline_data = getattr(part, "inline_data", None)
            if inline_data and getattr(inline_data, "data", None):
                return inline_data.data
    raise RuntimeError("Gemini returned no audio content.")

def synthesize_with_rotation(api_keys, voice, text, style):
    attempts = []
    for model in (PRIMARY_TTS_MODEL, FALLBACK_TTS_MODEL):
        for account_no, api_key in enumerate(api_keys, 1):
            try:
                audio = synthesize_one(api_key, model, voice, text, style)
                return audio, model, account_no, attempts
            except Exception as exc:
                attempts.append({"model": model, "account": account_no, "error": str(exc)[:700]})
    raise RuntimeError(json.dumps(attempts, ensure_ascii=False))

def image_response_to_pil(response):
    def try_open(image_bytes):
        return Image.open(io.BytesIO(image_bytes)).convert("RGB")

    output_image = getattr(response, "output_image", None)
    if output_image and getattr(output_image, "data", None):
        return try_open(output_image.data)

    for cand in getattr(response, "candidates", []) or []:
        content = getattr(cand, "content", None)
        if not content:
            continue
        for part in getattr(content, "parts", []) or []:
            inline_data = getattr(part, "inline_data", None)
            if inline_data and getattr(inline_data, "data", None):
                return try_open(inline_data.data)

    raise RuntimeError("Gemini returned no image content.")

def generate_image_one(api_key, model, prompt, reference_files):
    if genai is None:
        raise RuntimeError("google-genai is not available. Check requirements.txt.")
    client = genai.Client(api_key=api_key)
    input_parts = [{"type": "text", "text": prompt}]
    for ref in reference_files[:8]:
        input_parts.append({"type": "image", "mime_type": ref["mime"], "data": ref["bytes"]})
    response = client.interactions.create(model=model, input=input_parts)
    return image_response_to_pil(response)

def generate_image_with_rotation(api_keys, prompt, reference_files):
    attempts = []
    for model in (PRIMARY_IMAGE_MODEL, FALLBACK_IMAGE_MODEL):
        for account_no, api_key in enumerate(api_keys, 1):
            try:
                image = generate_image_one(api_key, model, prompt, reference_files)
                return image, model, account_no, attempts
            except Exception as exc:
                attempts.append({"model": model, "account": account_no, "error": str(exc)[:700]})
    raise RuntimeError(json.dumps(attempts, ensure_ascii=False))

def read_resume_package(upload, expected_story_hash, expected_voice):
    audio, images, metadata, state = {}, {}, {}, None
    if upload is None:
        return audio, images, metadata, state
    with zipfile.ZipFile(io.BytesIO(upload.getvalue()), "r") as archive:
        if "project_state.json" not in archive.namelist():
            raise ValueError("This is not a Story Media Creator resume package.")
        state = json.loads(archive.read("project_state.json").decode("utf-8"))
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
                metadata[int(m.group(1))] = json.loads(archive.read(name).decode("utf-8"))
    return audio, images, metadata, state

# ---------------------------
# UI
# ---------------------------
st.title("🎬 Story Media Creator")
st.caption("Story text + matching narration audio + matching scene images")

# Startup diagnostics: keep the app visible even if an optional dependency fails.
if GENAI_IMPORT_ERROR:
    st.error(
        "Google Gemini SDK could not be imported. "
        "Check requirements.txt and reboot the app."
    )
    with st.expander("Technical startup detail"):
        st.code(GENAI_IMPORT_ERROR)

if LOCAL_STORAGE_IMPORT_ERROR:
    st.warning(
        "Device key storage is unavailable in this session. "
        "The app will still work; enter Gemini keys manually."
    )
    with st.expander("Local-storage technical detail"):
        st.code(LOCAL_STORAGE_IMPORT_ERROR)

st.info(
    "This Gemini-only version includes a reusable Character Bank. "
    "Build one bank for Ramayan, Mahabharat, and other story projects."
)

with st.expander("🔑 Gemini API Keys", expanded=True):
    remember = st.checkbox(
        "Remember Gemini API keys on this device",
        value=True,
        help="Keys are saved in this browser's local storage on this device. Do not enable this on a shared/public computer."
    )
    g1 = st.text_input("Gemini API Key 1", value=st.session_state.get("loaded_g1", ""), type="password", key="input_g1")
    g2 = st.text_input("Gemini API Key 2", value=st.session_state.get("loaded_g2", ""), type="password", key="input_g2")
    g3 = st.text_input("Gemini API Key 3", value=st.session_state.get("loaded_g3", ""), type="password", key="input_g3")

    c1, c2 = st.columns(2)
    with c1:
        if st.button("💾 Save Gemini keys on this device", use_container_width=True):
            if storage is None:
                st.warning(
                    "Device storage is unavailable in this session. "
                    "You can still use the app with manually entered keys."
                )
            elif remember:
                values = {"g1": g1, "g2": g2, "g3": g3}
                saved_ok = True
                for short, value in values.items():
                    saved_ok = save_device_value(DEVICE_KEYS[short], value.strip()) and saved_ok
                    st.session_state[f"loaded_{short}"] = value.strip()
                if saved_ok:
                    st.success("Gemini keys saved in this browser on this device.")
                else:
                    st.warning("The browser did not confirm local key storage.")
            else:
                st.warning("Enable 'Remember Gemini API keys on this device' first.")
    with c2:
        if st.button("🗑️ Clear saved Gemini keys from this device", use_container_width=True):
            for short, storage_key in DEVICE_KEYS.items():
                delete_device_value(storage_key)
                st.session_state[f"loaded_{short}"] = ""
            st.success("Saved Gemini API keys cleared from this device.")

gemini_keys = clean_keys([g1, g2, g3])
st.write(f"Gemini keys detected: **{len(gemini_keys)}**")

st.subheader("1. Character Bank")

bank_col1, bank_col2 = st.columns([1.1, 0.9])

with bank_col1:
    with st.form("add_character_form", clear_on_submit=True):
        project_group = st.selectbox(
            "Project / Group",
            ["Ramayan", "Mahabharat", "Custom"],
            index=0,
        )
        char_name = st.text_input("Character name")
        char_aliases = st.text_input("Aliases (comma separated)")
        char_notes = st.text_area("Appearance / identity notes", height=100)
        char_images = st.file_uploader(
            "Reference images",
            type=["png", "jpg", "jpeg", "webp"],
            accept_multiple_files=True,
            key="char_images_uploader",
        )
        submitted = st.form_submit_button("Add character to bank", use_container_width=True)
        if submitted:
            try:
                add_character_to_bank(project_group, char_name, char_aliases, char_notes, char_images)
                st.success(f"Added {char_name.strip()} to the Character Bank.")
            except Exception as exc:
                st.error(str(exc))

with bank_col2:
    imported_bank = st.file_uploader(
        "Import Character Bank ZIP",
        type=["zip"],
        key="import_bank_zip",
    )
    if imported_bank is not None and not st.session_state.bank_loaded_once:
        try:
            import_character_bank_zip(imported_bank)
            st.session_state.bank_loaded_once = True
            st.success("Character Bank imported successfully.")
        except Exception as exc:
            st.error(f"Could not import Character Bank: {exc}")

    if st.button("Reload imported Character Bank ZIP", use_container_width=True):
        if imported_bank is not None:
            try:
                import_character_bank_zip(imported_bank)
                st.success("Character Bank reloaded.")
            except Exception as exc:
                st.error(f"Could not reload Character Bank: {exc}")
        else:
            st.warning("Upload a Character Bank ZIP first.")

    bank_zip_bytes = export_character_bank_zip_bytes() if st.session_state.character_bank else None
    if bank_zip_bytes:
        st.download_button(
            "⬇️ Download Character Bank ZIP",
            data=bank_zip_bytes,
            file_name="character_bank.zip",
            mime="application/zip",
            use_container_width=True,
        )

    if st.button("Clear entire Character Bank", use_container_width=True):
        st.session_state.character_bank = []
        st.success("Character Bank cleared.")

st.write(f"Characters in bank: **{len(st.session_state.character_bank)}**")

if st.session_state.character_bank:
    for idx, char in enumerate(st.session_state.character_bank):
        with st.expander(f"{idx+1}. {char['name']} — {char['project_group']}", expanded=False):
            st.write(f"**Aliases:** {', '.join(char['aliases']) if char['aliases'] else '—'}")
            st.write(f"**Notes:** {char['notes'] if char['notes'] else '—'}")
            st.write(f"**Reference images:** {len(char['references'])}")
            preview_cols = st.columns(min(3, max(1, len(char['references']))))
            for i, ref in enumerate(char["references"][:3]):
                with preview_cols[i % len(preview_cols)]:
                    st.image(ref["bytes"], use_container_width=True)
                    st.caption(ref["name"])
            if st.button(f"Delete {char['name']}", key=f"delete_char_{char['id']}"):
                st.session_state.character_bank.pop(idx)
                st.rerun()

st.subheader("2. Story")
story = st.text_area("Paste the complete story", height=280, placeholder="Paste the complete Hindi story here.")

st.subheader("3. Project Settings")
col1, col2, col3 = st.columns(3)
with col1:
    voice = st.selectbox("Fixed narrator voice", ["Vindemiatrix", "Achernar", "Gacrux", "Despina", "Algieba", "Kore"], index=0)
with col2:
    ratio = st.selectbox("Image aspect ratio", ["9:16", "16:9", "1:1", "4:3"], index=0)
with col3:
    target_chars = st.slider("Approximate scene length", 220, 700, 420, 20)

voice_style = st.text_area("Narrator direction", value=DEFAULT_VOICE_STYLE, height=150)
image_style = st.text_area("Image direction", value=DEFAULT_IMAGE_STYLE, height=150)
bgm = st.file_uploader("Optional background music", type=["mp3", "wav"])
bgm_db = st.slider("Background music level under narration (dB)", -36, -14, -27)
resume_zip = st.file_uploader("Optional: resume an unfinished project ZIP", type=["zip"])

scenes = make_dynamic_scenes(story, target_chars=target_chars, max_chars=max(450, target_chars + 180)) if story.strip() else []
if scenes:
    st.success(f"Dynamic scene plan: {len(scenes)} scenes")
    with st.expander("Preview scene text"):
        for n, scene in enumerate(scenes, 1):
            match_names = [c["name"] for c in matched_character_entries(scene)]
            st.markdown(f"**Scene {n:03d}**")
            st.write(scene)
            st.caption("Matched bank characters: " + (", ".join(match_names) if match_names else "none"))

if st.button("🚀 Generate / Resume Story Media", type="primary", use_container_width=True):
    if not story.strip():
        st.error("Paste the story first.")
        st.stop()
    if not gemini_keys:
        st.error("Add at least one Gemini API key.")
        st.stop()

    s_hash = story_hash(story)
    old_audio, old_images, old_meta, old_state = {}, {}, {}, None
    if resume_zip:
        try:
            old_audio, old_images, old_meta, old_state = read_resume_package(resume_zip, s_hash, voice)
            st.info(f"Resume package loaded: {len(old_audio)} audio scenes and {len(old_images)} image scenes already available.")
        except Exception as exc:
            st.warning(f"Resume package could not be reused: {exc}")

    state = old_state or {
        "app": APP_NAME,
        "version": 3,
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
        "primary_image_model": PRIMARY_IMAGE_MODEL,
        "fallback_image_model": FALLBACK_IMAGE_MODEL,
        "character_bank_count": len(st.session_state.character_bank),
    })

    progress = st.progress(0)
    status = st.empty()
    completed = []
    log = []
    paused = False
    previous_scene_ref = None

    for scene_no, scene_text in enumerate(scenes, 1):
        status.write(f"Processing Scene {scene_no} of {len(scenes)} …")
        audio = old_audio.get(scene_no)
        image_bytes = old_images.get(scene_no)
        meta = old_meta.get(scene_no, {})

        if audio is None:
            try:
                audio, tts_model, tts_account, tts_attempts = synthesize_with_rotation(gemini_keys, voice, scene_text, voice_style.strip())
                meta.update({"tts_model": tts_model, "tts_account": tts_account, "tts_attempts_before_success": tts_attempts})
            except Exception as exc:
                state.update({"status": "PAUSED", "failed_scene": scene_no, "last_error": f"TTS: {str(exc)[:3000]}"})
                log.append({"scene": scene_no, "stage": "audio", "status": "FAILED", "error": str(exc)[:2000]})
                paused = True
                break

        if image_bytes is None:
            scene_refs, matched_names = character_refs_for_scene(scene_text, previous_scene_ref=previous_scene_ref, limit=8)
            prompt = build_scene_image_prompt(scene_text, image_style.strip(), ratio, matched_names)
            prompt = prompt + "\n\n" + reference_note(scene_refs)

            try:
                image, image_model, image_account, image_attempts = generate_image_with_rotation(gemini_keys, prompt, scene_refs)
                image_bytes = pil_to_png_bytes(image)
                meta.update({
                    "image_model": image_model,
                    "image_account": image_account,
                    "image_attempts_before_success": image_attempts,
                    "image_prompt": prompt,
                    "matched_bank_characters": matched_names,
                })
            except Exception as exc:
                completed.append({"scene_no": scene_no, "text": scene_text, "audio": audio, "image": None, "meta": meta})
                state.update({"status": "PAUSED", "failed_scene": scene_no, "last_error": f"IMAGE: {str(exc)[:3000]}"})
                log.append({"scene": scene_no, "stage": "image", "status": "FAILED", "error": str(exc)[:2000]})
                paused = True
                break

        if image_bytes is not None:
            previous_scene_ref = {"name": f"scene_{scene_no:03d}.png", "bytes": image_bytes, "mime": "image/png"}

        completed.append({"scene_no": scene_no, "text": scene_text, "audio": audio, "image": image_bytes, "meta": meta})
        log.append({
            "scene": scene_no,
            "status": "DONE",
            "tts_model": meta.get("tts_model"),
            "tts_account": meta.get("tts_account"),
            "image_model": meta.get("image_model"),
            "image_account": meta.get("image_account"),
            "matched_bank_characters": meta.get("matched_bank_characters", []),
        })
        progress.progress(scene_no / len(scenes))

    if not paused and len(completed) == len(scenes):
        state.update({"status": "COMPLETE", "failed_scene": None, "last_error": None})

    master_wav_bytes = b""
    master_mp3_bytes = b""

    narration_parts = [
        item["audio"] for item in completed if item.get("audio")
    ]

    if narration_parts:
        try:
            master_wav_bytes = concatenate_wav_bytes(
                narration_parts,
                silence_ms=850,
            )
            master_mp3_bytes = render_master_mp3(
                master_wav_bytes,
                bgm_upload=bgm,
                bgm_db=bgm_db,
            )
        except Exception as exc:
            st.warning(f"Master audio could not be prepared: {exc}")

    package = io.BytesIO()
    with zipfile.ZipFile(package, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("project_state.json", json.dumps(state, ensure_ascii=False, indent=2).encode("utf-8"))
        archive.writestr("run_log.json", json.dumps(log, ensure_ascii=False, indent=2).encode("utf-8"))
        archive.writestr("story/full_story.txt", story.encode("utf-8"))
        archive.writestr("story/scenes.json", json.dumps([{"scene": n, "text": text} for n, text in enumerate(scenes, 1)], ensure_ascii=False, indent=2).encode("utf-8"))

        if master_mp3_bytes:
            archive.writestr("audio/full_story_master.mp3", master_mp3_bytes)
        elif master_wav_bytes:
            archive.writestr("audio/full_story_master.wav", master_wav_bytes)

        bank_bytes = export_character_bank_zip_bytes()
        archive.writestr("character_bank/character_bank_export.zip", bank_bytes)

        for item in completed:
            n = item["scene_no"]
            archive.writestr(f"story/scene_{n:03d}.txt", item["text"].encode("utf-8"))
            if item["audio"]:
                archive.writestr(f"audio/scene_{n:03d}.wav", item["audio"])
            if item["image"]:
                archive.writestr(f"images/scene_{n:03d}.png", item["image"])
            archive.writestr(f"metadata/scene_{n:03d}.json", json.dumps(item["meta"], ensure_ascii=False, indent=2).encode("utf-8"))

    status.empty()

    if state["status"] == "COMPLETE":
        st.success("Complete: story text, matching narration audio and matching scene images are ready.")
    else:
        st.warning(
            f"Generation paused at Scene {state.get('failed_scene')}. Download the ZIP now. "
            "Later upload that ZIP in the Resume field and the app will continue without recreating completed assets."
        )

    if master_mp3_bytes:
        st.subheader("Full narration")
        st.audio(master_mp3_bytes, format="audio/mp3")
    elif master_wav_bytes:
        st.subheader("Full narration")
        st.audio(master_wav_bytes, format="audio/wav")

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
        with st.expander(f"Scene {n:03d}", expanded=(n <= 2)):
            left, right = st.columns(2)
            with left:
                st.markdown("**Story text**")
                st.write(item["text"])
                if item["audio"]:
                    st.markdown("**Narration audio**")
                    st.audio(item["audio"], format="audio/wav")
                if item["meta"].get("matched_bank_characters"):
                    st.caption("Matched bank characters: " + ", ".join(item["meta"]["matched_bank_characters"]))
            with right:
                st.markdown("**Scene image**")
                if item["image"]:
                    st.image(item["image"], use_container_width=True)
                else:
                    st.info("Image pending. Resume this package later if free availability is exhausted.")
