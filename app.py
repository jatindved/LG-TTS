import streamlit as st
import io
import json
import re
import time
import hashlib
import zipfile
from datetime import datetime, timezone
from pydub import AudioSegment
from google import genai

st.set_page_config(page_title="Hanuman Ansh Story Voice Studio", page_icon="🎙️", layout="wide")

PRIMARY_MODEL = "gemini-3.8-flash-tts"
FALLBACK_MODEL = "gemini-3.8-flash-lite-tts"
DEFAULT_VOICE = "Vindemiatrix"  # Gentle. Change once, then keep fixed for the whole project.
STATE_FILE = "project_state.json"

VOICE_STYLE = (
    "A mature Indian female storyteller speaking natural Hindi to a child with maternal affection, "
    "devotional calm, warmth and dignity. Never sound like an announcer, newsreader, commercial, or robot. "
    "Use natural breathing rhythm and meaningful pauses. Keep the delivery gentle, emotionally sincere and "
    "unhurried, while preserving every word exactly. Do not sing. Do not add, remove, paraphrase, translate, "
    "or repeat any words. Maintain the same narrator identity, vocal age, timbre, pitch character, accent, "
    "and speaking personality for the entire story."
)


def safe_secret(name: str, default=""):
    try:
        return st.secrets.get(name, default)
    except Exception:
        return default


def story_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def split_story_exact(text: str, max_chars: int = 850):
    """Split without rewriting. Every non-whitespace character stays in original order."""
    text = text.strip()
    if not text:
        return []

    # Keep punctuation attached. This only chooses boundaries; it does not regenerate text.
    sentence_pattern = re.compile(r".*?(?:[।!?…]+|\.(?=\s|$)|\n+|$)", re.S)
    pieces = [m.group(0) for m in sentence_pattern.finditer(text) if m.group(0)]

    chunks = []
    current = ""
    for piece in pieces:
        if len(current) + len(piece) <= max_chars or not current:
            current += piece
        else:
            chunks.append(current.strip())
            current = piece
    if current.strip():
        chunks.append(current.strip())

    return chunks


def get_audio_bytes(response):
    try:
        return response.candidates[0].content.parts[0].inline_data.data
    except Exception as exc:
        raise RuntimeError("Gemini returned no audio data.") from exc


def synthesize_once(api_key: str, model: str, voice: str, text: str, style: str):
    client = genai.Client(api_key=api_key)
    response = client.models.generate_content(
        model=model,
        contents=[{
            "role": "user",
            "parts": [{
                "text": text,
                "speech_metadata": {"style": style},
            }],
        }],
        config={
            "response_modalities": ["AUDIO"],
            "speech_config": {
                "voice_config": {"voice": voice}
            },
        },
    )
    return get_audio_bytes(response)


def looks_like_quota_error(exc: Exception) -> bool:
    s = str(exc).lower()
    quota_markers = [
        "429", "resource_exhausted", "quota", "rate limit", "rate_limit",
        "too many requests", "daily limit", "per day", "rpm", "rpd"
    ]
    return any(x in s for x in quota_markers)


def synthesize_with_rotation(api_keys, voice, text, style):
    """
    Quality-first order:
      key 1 Flash -> key 2 Flash -> key 3 Flash
      then key 1 Lite -> key 2 Lite -> key 3 Lite
    Narrator voice and style NEVER change.
    """
    attempts = []
    for model in (PRIMARY_MODEL, FALLBACK_MODEL):
        for key_index, key in enumerate(api_keys, start=1):
            if not key:
                continue
            try:
                audio = synthesize_once(key, model, voice, text, style)
                return audio, model, key_index, attempts
            except Exception as exc:
                attempts.append({
                    "model": model,
                    "account": key_index,
                    "quota_like": looks_like_quota_error(exc),
                    "error": str(exc)[:500],
                })
                continue
    raise RuntimeError(json.dumps(attempts, ensure_ascii=False))


def wav_to_segment(wav_bytes: bytes) -> AudioSegment:
    return AudioSegment.from_file(io.BytesIO(wav_bytes), format="wav")


def load_state(uploaded_state, current_hash, chunks):
    if uploaded_state is not None:
        try:
            state = json.load(uploaded_state)
            if state.get("story_hash") == current_hash:
                return state
        except Exception:
            pass

    return {
        "version": 1,
        "story_hash": current_hash,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "voice": DEFAULT_VOICE,
        "primary_model": PRIMARY_MODEL,
        "fallback_model": FALLBACK_MODEL,
        "status": "NEW",
        "total_chunks": len(chunks),
        "completed_chunks": [],
        "failed_chunk": None,
        "last_error": None,
    }


def state_bytes(state):
    return json.dumps(state, ensure_ascii=False, indent=2).encode("utf-8")


st.title("🎙️ Hanuman Ansh — Gemini 3.8 Story Voice Studio")
st.caption("Free-tier-first • Fixed narrator • Exact text • 3-account rotation • Resume checkpoint")

st.info(
    "Important: this app never switches to a paid model. However, an API key from a billing-enabled Google project "
    "can still incur provider-side charges. For strict ₹0 use, use API keys only from projects where billing is disabled."
)

with st.expander("🔑 Gemini API keys", expanded=True):
    st.write("Add up to three separate Google AI Studio project keys. Keys are used only as fallbacks when a request fails/quota-limits.")
    key1 = st.text_input("Account 1 API key", value=safe_secret("GEMINI_API_KEY_1"), type="password")
    key2 = st.text_input("Account 2 API key", value=safe_secret("GEMINI_API_KEY_2"), type="password")
    key3 = st.text_input("Account 3 API key", value=safe_secret("GEMINI_API_KEY_3"), type="password")
    free_only_confirm = st.checkbox(
        "I confirm these keys belong to projects where billing is disabled (₹0-only safety).",
        value=False,
    )

st.subheader("1. Story")
story = st.text_area(
    "Paste the complete Hindi story",
    height=260,
    placeholder="Paste the complete story here. The app will not rewrite it.",
)

col_a, col_b, col_c = st.columns(3)
with col_a:
    fixed_voice = st.selectbox(
        "Fixed narrator voice",
        ["Vindemiatrix", "Achernar", "Gacrux", "Despina", "Algieba", "Kore"],
        index=0,
        help="Pick once for a project. The same voice is used for every chunk and every fallback account/model.",
    )
with col_b:
    chunk_chars = st.slider("Chunk size", 450, 1200, 850, 50)
with col_c:
    pause_ms = st.slider("Pause between chunks (ms)", 300, 2500, 900, 100)

style_text = st.text_area("Narration direction (locked across story)", value=VOICE_STYLE, height=150)

bgm_file = st.file_uploader("Optional BGM (MP3/WAV)", type=["mp3", "wav"])
bgm_db = st.slider("BGM level under narration (dB)", -36, -14, -27, 1)
resume_zip = st.file_uploader("Optional: resume from a previous narration package ZIP", type=["zip"])
state_upload = st.file_uploader("Optional: resume from project_state.json only (audio parts will be regenerated)", type=["json"])

chunks = split_story_exact(story, chunk_chars) if story.strip() else []
if chunks:
    st.write(f"Exact-text chunks: **{len(chunks)}**")
    with st.expander("Preview exact chunks"):
        for i, chunk in enumerate(chunks, 1):
            st.markdown(f"**Part {i:02d}**")
            st.code(chunk, language="text")

api_keys = [key1.strip(), key2.strip(), key3.strip()]

if st.button("▶️ Generate / Resume narration", type="primary", use_container_width=True):
    if not story.strip():
        st.error("Paste the story first.")
        st.stop()
    if not any(api_keys):
        st.error("Add at least one Gemini API key.")
        st.stop()
    if not free_only_confirm:
        st.error("For this free-only build, confirm that billing is disabled on the API-key projects.")
        st.stop()

    s_hash = story_hash(story)
    state = load_state(state_upload, s_hash, chunks)
    state["voice"] = fixed_voice
    state["total_chunks"] = len(chunks)
    state["status"] = "RUNNING"

    completed_this_run = []
    audio_parts = []
    run_log = []
    prior_audio = {}

    # True resume: load already-generated WAV parts from a previous package ZIP.
    if resume_zip is not None:
        try:
            zbytes = io.BytesIO(resume_zip.getvalue())
            with zipfile.ZipFile(zbytes, "r") as zf:
                if "project_state.json" in zf.namelist():
                    prior_state = json.loads(zf.read("project_state.json").decode("utf-8"))
                    if prior_state.get("story_hash") == s_hash and prior_state.get("voice") == fixed_voice:
                        state = prior_state
                        state["status"] = "RUNNING"
                        for name in zf.namelist():
                            m = re.fullmatch(r"audio/part_(\d{3})\.wav", name)
                            if m:
                                part_no = int(m.group(1))
                                wav_b = zf.read(name)
                                prior_audio[part_no] = wav_b
                    else:
                        st.warning("Resume ZIP does not match this story hash and fixed voice, so it will not be reused.")
        except Exception as exc:
            st.warning(f"Could not read resume ZIP; starting clean. {exc}")

    progress = st.progress(0)
    status_box = st.empty()

    for idx, chunk in enumerate(chunks, start=1):
        if idx in prior_audio:
            wav_bytes = prior_audio[idx]
            segment = wav_to_segment(wav_bytes)
            audio_parts.append((idx, wav_bytes, segment, "RESUMED", 0))
            completed_this_run.append(idx)
            run_log.append({"part": idx, "status": "RESUMED_FROM_ZIP"})
            state["completed_chunks"] = completed_this_run.copy()
            progress.progress(min(idx / len(chunks), 1.0))
            continue

        status_box.write(f"Generating part {idx}/{len(chunks)} with fixed voice **{fixed_voice}**…")
        try:
            wav_bytes, used_model, used_account, attempts = synthesize_with_rotation(
                api_keys, fixed_voice, chunk, style_text.strip()
            )
            segment = wav_to_segment(wav_bytes)
            audio_parts.append((idx, wav_bytes, segment, used_model, used_account))
            completed_this_run.append(idx)
            run_log.append({
                "part": idx,
                "status": "DONE",
                "model": used_model,
                "account": used_account,
                "prior_failed_attempts": attempts,
            })
            state["completed_chunks"] = completed_this_run.copy()
            state["failed_chunk"] = None
            state["last_error"] = None
        except Exception as exc:
            state["status"] = "PAUSED_QUOTA_OR_ERROR"
            state["failed_chunk"] = idx
            state["last_error"] = str(exc)[:4000]
            run_log.append({"part": idx, "status": "FAILED", "error": str(exc)[:2000]})
            st.warning(
                f"Stopped at part {idx}. All configured Flash and Flash-Lite attempts failed. "
                "Download the checkpoint below. Do not restart the story manually."
            )
            break
        finally:
            progress.progress(min(idx / len(chunks), 1.0))

    if len(audio_parts) == len(chunks):
        state["status"] = "COMPLETE"

    # Build continuous narration from generated parts from this run.
    if audio_parts:
        narration = AudioSegment.empty()
        for _, _, seg, _, _ in audio_parts:
            narration += seg + AudioSegment.silent(duration=pause_ms)

        master = narration
        if bgm_file is not None:
            try:
                bgm_raw = io.BytesIO(bgm_file.getvalue())
                bgm = AudioSegment.from_file(bgm_raw)
                bgm = bgm.set_frame_rate(narration.frame_rate).set_channels(narration.channels) + bgm_db
                if len(bgm) < len(narration):
                    bgm = bgm * ((len(narration) // len(bgm)) + 1)
                bgm = bgm[:len(narration)].fade_in(1200).fade_out(2500)
                master = bgm.overlay(narration)
            except Exception as exc:
                st.warning(f"BGM could not be mixed; narration is still available. {exc}")

        master_mp3 = io.BytesIO()
        master.export(master_mp3, format="mp3", bitrate="192k")

        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("project_state.json", state_bytes(state))
            zf.writestr("run_log.json", json.dumps(run_log, ensure_ascii=False, indent=2))
            zf.writestr("story_exact.txt", story.encode("utf-8"))
            zf.writestr("narrator_profile.txt", (
                f"VOICE={fixed_voice}\nPRIMARY={PRIMARY_MODEL}\nFALLBACK={FALLBACK_MODEL}\n\n{style_text}"
            ).encode("utf-8"))
            zf.writestr("audio/full_story_master.mp3", master_mp3.getvalue())

            for part_no, wav_bytes, _, model, account in audio_parts:
                zf.writestr(f"audio/part_{part_no:03d}.wav", wav_bytes)
                zf.writestr(
                    f"audio/part_{part_no:03d}_source.txt",
                    f"model={model}\naccount={account}\nvoice={fixed_voice}\n".encode("utf-8"),
                )

        status_box.empty()
        if state["status"] == "COMPLETE":
            st.success("Narration complete. The same narrator voice was used throughout all successful parts.")
        else:
            st.info("Partial narration package is ready. It includes the exact checkpoint and all completed audio parts.")

        st.audio(master_mp3.getvalue(), format="audio/mp3")
        st.download_button(
            "⬇️ Download narration package ZIP",
            data=zip_buffer.getvalue(),
            file_name="Hanuman_Ansh_Gemini38_Narration.zip",
            mime="application/zip",
            use_container_width=True,
        )

    st.download_button(
        "⬇️ Download project checkpoint JSON",
        data=state_bytes(state),
        file_name="project_state.json",
        mime="application/json",
        use_container_width=True,
    )

    with st.expander("Technical run log"):
        st.json(run_log)

st.divider()
st.caption(
    "Visual generation is intentionally not included in this build. Pollinations was removed. "
    "After the narrator voice is approved, the next build can add a separate reference-image/video pipeline without changing the locked audio system."
)
