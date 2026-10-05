import streamlit as st
import os
import json
import io
import re
import time
from PIL import Image
from pydub import AudioSegment
from google.cloud import texttospeech
from google.api_core.client_options import ClientOptions
from google import genai

st.set_page_config(page_title="AI Story Studio - Auto Model Production", page_icon="🎬", layout="wide")

CONFIG_FILE = "config.json"

def load_saved_keys():
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r") as f:
                data = json.load(f)
                return data.get("gcloud_key", ""), data.get("gemini_key", "")
        except Exception:
            return "", ""
    return "", ""

def save_keys_to_file(gcloud_k, gemini_k):
    with open(CONFIG_FILE, "w") as f:
        json.dump({"gcloud_key": gcloud_k, "gemini_key": gemini_k}, f)

saved_gcloud, saved_gemini = load_saved_keys()

st.title("🎬 AI Mythological Story & Cinematic Scene Studio")
st.write("Dynamic Model Auto-Discovery, Consistent Character DNA, Isolated Scene Audios, and One-Click Copyable Prompts.")

# 1. Dual Key Settings
with st.expander("🔑 API Key Settings (Google Cloud + Gemini AI Studio)", expanded=(not bool(saved_gcloud and saved_gemini))):
    col_k_in1, col_k_in2 = st.columns(2)
    with col_k_in1:
        gcloud_input = st.text_input(
            "1. Google Cloud API Key (For TTS Audio):",
            value=saved_gcloud,
            type="password",
            placeholder="AIzaSy... (Cloud TTS Key)"
        )
    with col_k_in2:
        gemini_input = st.text_input(
            "2. Google AI Studio API Key (For Gemini AI):",
            value=saved_gemini,
            type="password",
            placeholder="AIzaSy... (AI Studio Key)"
        )

    col_btn1, col_btn2 = st.columns([1, 1])
    with col_btn1:
        if st.button("💾 Save Both Keys Permanently"):
            if gcloud_input.strip() and gemini_input.strip():
                save_keys_to_file(gcloud_input.strip(), gemini_input.strip())
                st.success("Both API keys saved successfully!")
                st.rerun()
            else:
                st.warning("Please enter both API keys to proceed.")
    with col_btn2:
        if (saved_gcloud or saved_gemini) and st.button("🗑️ Clear Saved Keys"):
            if os.path.exists(CONFIG_FILE):
                os.remove(CONFIG_FILE)
            st.info("Keys removed.")
            st.rerun()

final_gcloud_key = gcloud_input.strip() if gcloud_input.strip() else saved_gcloud
final_gemini_key = gemini_input.strip() if gemini_input.strip() else saved_gemini

# 2. Master Character DNA
CHARACTER_DNA = {
    "RAMA": "Lord Rama depicted as a noble 25-year-old ancient Indian prince, serene gentle almond-shaped eyes, divine benevolent smile, dusky wheatish complexion, royal golden-yellow silk pitambara dhoti, traditional ornate Vedic gold mukut crown, gold armlets and necklaces, majestic calm posture.",
    "KAUSHALYA": "Queen Mata Kaushalya, graceful loving queen mother in her mid-40s, kind motherly face with gentle benevolent eyes, dressed in royal crimson-maroon silk saree with wide gold zari border, ornate Vedic gold jewelry, dignified royal demeanor.",
    "KAIKEYI": "Queen Kaikeyi, beautiful determined royal queen in her late 30s, sharp commanding facial features, expressive resolute eyes, adorned in royal emerald-green silk garments with intricate gold embroidery and heavy royal gold crown.",
    "BHARATA": "Prince Bharata, devoted humble prince in royal ochre-silk attire, tearful affectionate eyes, deeply resembling Rama in royal lineage with folded hands and devotional expression.",
    "LAKSHMANA": "Prince Lakshmana, spirited devoted youthful prince, fierce protective loving eyes, golden-yellow silk attire, holding sacred bow, looking steadfastly beside Rama."
}

ART_STYLE = "Raja Ravi Varma aesthetic blended with cinematic 8k, soft golden ambient lighting, authentic ancient Indian palace and forest architecture, oil-painting warmth, ultra-consistent character faces."

# 3. Raw Script Input
text_input = st.text_area(
    "Paste Raw Continuous Story:", 
    height=220, 
    placeholder="Paste your continuous story text here. The system dynamically queries active models to segment into Scene_01, Scene_02..."
)

col1, col2, col3 = st.columns(3)
with col1:
    voice_choice = st.selectbox(
        "Narrator Voice:",
        [
            "hi-IN-Journey-D (Male - Ultra Natural Storytelling)",
            "hi-IN-Journey-F (Female - Ultra Natural Narrative)",
            "hi-IN-Neural2-B (Male - Deep & Classical)",
            "hi-IN-Neural2-A (Female - Clear & Narrative)"
        ]
    )
    voice_name = voice_choice.split(" ")[0]
    ssml_gender = texttospeech.SsmlVoiceGender.MALE if ("-B" in voice_name or "Journey-D" in voice_name) else texttospeech.SsmlVoiceGender.FEMALE

with col2:
    speed_rate = st.slider("Narration Speed:", min_value=0.75, max_value=1.10, value=0.88, step=0.02)

with col3:
    aspect_ratio_choice = st.selectbox(
        "Target Aspect Ratio:",
        [
            "9:16 (Instagram Reels / Shorts)",
            "16:9 (YouTube Landscape)",
            "1:1 (Square Post / Feed)",
            "4:3 (Classic Television)"
        ]
    )
    selected_ratio = aspect_ratio_choice.split(" ")[0]

bgm_file = st.file_uploader("Upload Background Score (MP3/WAV):", type=["mp3", "wav"])

bgm_volume_reduction = st.slider(
    "BGM Volume Reduction (dB):", 
    min_value=-30, 
    max_value=-10, 
    value=-18, 
    format="%d dB"
)

# લોકલ ફોલબેક જો API ન ચાલે તો
def python_fallback_segment(raw_text):
    sentences = [s.strip() for s in re.split(r'[।\.\n]+', raw_text) if s.strip()]
    scenes = []
    chunk = []
    chunk_len = 0
    s_idx = 1
    for s in sentences:
        chunk.append(s)
        chunk_len += len(s)
        if len(chunk) >= 3 or chunk_len >= 180:
            scenes.append({
                "scene_id": f"Scene_{s_idx:02d}",
                "narration_text": "। ".join(chunk) + "।",
                "visual_description": f"Cinematic scene focusing on: {chunk[0][:120]}"
            })
            chunk = []
            chunk_len = 0
            s_idx += 1
    if chunk:
        scenes.append({
            "scene_id": f"Scene_{s_idx:02d}",
            "narration_text": "। ".join(chunk) + "।",
            "visual_description": f"Cinematic conclusion focusing on: {chunk[0][:120]}"
        })
    return scenes

# ડાયનેમિક મોડેલ ડિટેક્શન (કોઈ હાર્ડકોડ મોડેલ નામ વગર)
def gemini_segment_dynamic(gemini_api_key, raw_story):
    ai_client = genai.Client(api_key=gemini_api_key)
    prompt = f"""
    You are an expert mythological film director. 
    Analyze this raw story and segment it into sequential cinematic scenes.
    Return ONLY a valid JSON list of objects.
    Each object must contain:
    - "scene_id": unique identifier string like "Scene_01", "Scene_02", etc.
    - "narration_text": the exact segment of text for voiceover in this scene (keep the original script language and text unchanged)
    - "visual_description": a rich English prompt describing the visual action, camera angle, mood, and environment.

    Story:
    {raw_story}
    """

    try:
        available_models = []
        for m in ai_client.models.list():
            methods = getattr(m, 'supported_generation_methods', []) or getattr(m, 'supported_actions', [])
            if any("generateContent" in str(act) for act in methods):
                clean_name = m.name.replace("models/", "")
                available_models.append(clean_name)
        
        # ફ્લેશ મોડેલ્સને પ્રાથમિકતા
        sorted_models = sorted(available_models, key=lambda x: (not ("flash" in x.lower()), x))

        for model_name in sorted_models:
            try:
                response = ai_client.models.generate_content(
                    model=model_name,
                    contents=prompt,
                    config=dict(response_mime_type="application/json")
                )
                data = json.loads(response.text)
                if isinstance(data, list) and len(data) > 0:
                    for i, item in enumerate(data):
                        item["scene_id"] = f"Scene_{i+1:02d}"
                    return data, f"Generated with Active Model: {model_name}"
            except Exception:
                time.sleep(1)
                continue
    except Exception:
        pass

    fallback_data = python_fallback_segment(raw_story)
    return fallback_data, "Generated with Smart Local Engine (API Unavailable)"

def build_consistent_prompt(scene_id, visual_desc, ratio):
    matched_dna = []
    text_lower = visual_desc.lower()
    
    if any(k in text_lower for k in ["rama", "shri ram", "lord rama", "ram"]):
        matched_dna.append(CHARACTER_DNA["RAMA"])
    if any(k in text_lower for k in ["kaushalya", "queen kaushalya"]):
        matched_dna.append(CHARACTER_DNA["KAUSHALYA"])
    if any(k in text_lower for k in ["kaikeyi", "queen kaikeyi"]):
        matched_dna.append(CHARACTER_DNA["KAIKEYI"])
    if any(k in text_lower for k in ["bharata", "bharat"]):
        matched_dna.append(CHARACTER_DNA["BHARATA"])
    if any(k in text_lower for k in ["lakshmana", "lakshman"]):
        matched_dna.append(CHARACTER_DNA["LAKSHMANA"])
        
    dna_block = " | ".join(matched_dna) if matched_dna else "Noble Indian mythological royal figures in classical Vedic attire."
    return f"[Ref: img_{scene_id}] Cinematic shot: {visual_desc}. Main Figures: {dna_block}. Art Style: {ART_STYLE}, composition optimized for {ratio} format."

if st.button("🚀 Auto-Produce Story & Scenes (Live Auto-Model)", type="primary", use_container_width=True):
    if not final_gcloud_key or not final_gemini_key:
        st.error("Please enter and save BOTH Google Cloud and Gemini API Keys above.")
    elif not text_input.strip():
        st.warning("Please paste your story text.")
    else:
        try:
            status_text = st.empty()
            status_text.text("🧠 Auto-detecting active model in your AI Studio account and segmenting scenes...")

            parsed_scenes, engine_info = gemini_segment_dynamic(final_gemini_key, text_input)
            total_scenes = len(parsed_scenes)
            st.info(f"{engine_info} — Successfully produced {total_scenes} structured scenes.")

            tts_client = texttospeech.TextToSpeechClient(client_options=ClientOptions(api_key=final_gcloud_key))
            voice = texttospeech.VoiceSelectionParams(language_code="hi-IN", name=voice_name, ssml_gender=ssml_gender)
            audio_config = texttospeech.AudioConfig(audio_encoding=texttospeech.AudioEncoding.MP3, speaking_rate=speed_rate, pitch=-1.0)

            scene_results = []
            full_voice_track = AudioSegment.empty()
            progress_bar = st.progress(0)

            for idx, item in enumerate(parsed_scenes):
                scene_id = item.get("scene_id", f"Scene_{idx+1:02d}")
                narration = item.get("narration_text", "")
                visual_desc = item.get("visual_description", "")
                image_tag = f"img_{scene_id}"

                status_text.text(f"Synthesizing Audio for {scene_id} ({idx+1}/{total_scenes})...")

                s_input = texttospeech.SynthesisInput(text=narration)
                res = tts_client.synthesize_speech(input=s_input, voice=voice, audio_config=audio_config)
                scene_audio = AudioSegment.from_file(io.BytesIO(res.audio_content), format="mp3")
                full_voice_track += scene_audio + AudioSegment.silent(duration=1000)

                full_prompt = build_consistent_prompt(scene_id, visual_desc, selected_ratio)

                scene_results.append((scene_id, image_tag, narration, scene_audio, full_prompt))
                progress_bar.progress((idx + 1) / total_scenes)

            status_text.text("Mastering audio score and blending background music...")

            master_final = full_voice_track
            if bgm_file is not None:
                bgm_audio = AudioSegment.from_file(io.BytesIO(bgm_file.getvalue()))
                bgm_audio = bgm_audio.set_frame_rate(full_voice_track.frame_rate).set_channels(full_voice_track.channels) + bgm_volume_reduction
                if len(bgm_audio) < len(full_voice_track):
                    bgm_audio = bgm_audio * ((len(full_voice_track) // len(bgm_audio)) + 1)
                bgm_audio = bgm_audio[:len(full_voice_track) + 2500].fade_out(2500)
                master_final = bgm_audio.overlay(full_voice_track)

            status_text.empty()
            st.success(f"🎉 Production Finished! {total_scenes} scenes ready with paired image tags.")

            # Full Story Master Audio
            st.subheader("🎵 1. Complete Master Story Audio (With BGM)")
            master_buf = io.BytesIO()
            master_final.export(master_buf, format="mp3", bitrate="192k")
            st.audio(master_buf.getvalue(), format="audio/mp3")
            st.download_button(
                label="⬇️ Download Full Story Master MP3",
                data=master_buf.getvalue(),
                file_name="full_story_master.mp3",
                mime="audio/mp3",
                use_container_width=True
            )

            # Scene-by-Scene Copy Blocks
            st.divider()
            st.subheader(f"🎬 2. Scene-by-Scene Production Desk ({selected_ratio})")

            for s_id, img_tag, s_txt, s_aud, s_prompt in scene_results:
                with st.expander(f"📌 {s_id} | Paired Visual: {img_tag}", expanded=True):
                    col_left, col_right = st.columns([1, 1])
                    
                    with col_left:
                        st.markdown(f"**📖 Narration Script ({s_id}):**")
                        st.code(s_txt, language="text")
                        
                        s_buf = io.BytesIO()
                        s_aud.export(s_buf, format="mp3")
                        st.audio(s_buf.getvalue(), format="audio/mp3")
                        st.download_button(
                            label=f"⬇️ Download {s_id} Audio",
                            data=s_buf.getvalue(),
                            file_name=f"{s_id}_audio.mp3",
                            mime="audio/mp3",
                            key=f"aud_{s_id}"
                        )
                        
                    with col_right:
                        st.markdown(f"**🎨 Image Prompt Identifier: `{img_tag}`**")
                        st.code(s_prompt, language="text")
                        st.caption(f"💡 Copy this prompt into your Image Generator. File naming match: `{img_tag}.png` matches `{s_id}_audio.mp3`")

        except Exception as e:
            st.error(f"Error during production: {e}")
