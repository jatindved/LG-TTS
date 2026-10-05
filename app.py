import streamlit as st
import os
import json
import io
import re
import time
import zipfile
from PIL import Image
from pydub import AudioSegment
from google.cloud import texttospeech
from google.api_core.client_options import ClientOptions
from google import genai

st.set_page_config(page_title="AI Story Studio - Audience Presets Edition", page_icon="🎬", layout="wide")

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

st.title("🎬 AI Story Studio - Audience Preset Production")
st.write("Target-audience presets (Children, Devotional, Katha, Epic) with authentic Sulafat & Neural voiceover models.")

# 1. API Key Settings
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

# 2. Audience-Based Presets
PRESETS = {
    "💖 Children & Devotional (Loving Mother / Sulafat Style)": {
        "voice": "hi-IN-SulafatNeural",
        "fallback_voice": "hi-IN-Neural2-D",
        "gender": texttospeech.SsmlVoiceGender.FEMALE,
        "speed": 0.81,
        "pitch": -0.8,
        "pause_ms": 1300,
        "bgm_db": -22,
        "prompt_context": "Gentle, heartwarming picture-book story for children and spiritual seekers. Soft, tender atmosphere."
    },
    "📖 Classical Katha & Spiritual (Deep, Respectful & Calm)": {
        "voice": "hi-IN-Neural2-B",
        "fallback_voice": "hi-IN-Wavenet-B",
        "gender": texttospeech.SsmlVoiceGender.MALE,
        "speed": 0.86,
        "pitch": -1.0,
        "pause_ms": 1100,
        "bgm_db": -18,
        "prompt_context": "Vedic, philosophical, serene scriptural narration with deep spiritual gravity."
    },
    "⚔️ Mythological Epic & Drama (Valor & Action)": {
        "voice": "hi-IN-Neural2-B",
        "fallback_voice": "hi-IN-Wavenet-B",
        "gender": texttospeech.SsmlVoiceGender.MALE,
        "speed": 0.92,
        "pitch": 0.0,
        "pause_ms": 800,
        "bgm_db": -15,
        "prompt_context": "Dramatic, heroic, dynamic cinematic narration with strong emotional tension."
    },
    "🎙️ Standard Narrative (Clear & Modern)": {
        "voice": "hi-IN-Neural2-A",
        "fallback_voice": "hi-IN-Wavenet-A",
        "gender": texttospeech.SsmlVoiceGender.FEMALE,
        "speed": 0.95,
        "pitch": 0.0,
        "pause_ms": 900,
        "bgm_db": -18,
        "prompt_context": "Clear, modern, balanced narrative flow."
    }
}

# 3. Master Character DNA
CHARACTER_DNA = {
    "RAMA": "Lord Rama depicted as a noble 25-year-old ancient Indian prince, serene gentle almond-shaped eyes, divine benevolent smile, dusky wheatish complexion, royal golden-yellow silk pitambara dhoti, traditional ornate Vedic gold mukut crown, gold armlets and necklaces, majestic calm posture.",
    "SHABARI": "Mata Shabari, elderly revered ascetic woman in simple rustic bark/cotton garments, silver-white hair, deeply wrinkly gentle grandmotherly face radiating pure devotion, humble folded hands and tears of spiritual joy.",
    "KAUSHALYA": "Queen Mata Kaushalya, graceful loving queen mother in her mid-40s, kind motherly face with gentle benevolent eyes, dressed in royal crimson-maroon silk saree with wide gold zari border, ornate Vedic gold jewelry, dignified royal demeanor.",
    "KAIKEYI": "Queen Kaikeyi, beautiful determined royal queen in her late 30s, sharp commanding facial features, expressive resolute eyes, adorned in royal emerald-green silk garments with intricate gold embroidery and heavy royal gold crown.",
    "BHARATA": "Prince Bharata, devoted humble prince in royal ochre-silk attire, tearful affectionate eyes, deeply resembling Rama in royal lineage with folded hands and devotional expression.",
    "LAKSHMANA": "Prince Lakshmana, spirited devoted youthful prince, fierce protective loving eyes, golden-yellow silk attire, holding sacred bow, looking steadfastly beside Rama."
}

ART_STYLE = "Traditional Indian devotional illustration, warm golden ambient light, peaceful spiritual environment, expressive emotional faces, authentic ancient Vedic hermitage details."

# 4. Raw Script Input
text_input = st.text_area(
    "Paste Continuous Story Text:", 
    height=200, 
    placeholder="Paste your story here. Select the target audience preset below to automatically format voice, tone, pacing, and visual style..."
)

col1, col2 = st.columns([1.5, 1])
with col1:
    selected_preset_name = st.selectbox(
        "🎯 વાર્તા કોના માટે છે? (Target Audience Preset):",
        list(PRESETS.keys())
    )
    current_preset = PRESETS[selected_preset_name]

with col2:
    aspect_ratio_choice = st.selectbox(
        "Target Aspect Ratio:",
        [
            "16:9 (YouTube Landscape / Picture Book)",
            "9:16 (Instagram Reels / Shorts)",
            "1:1 (Square Post / Feed)",
            "4:3 (Classic Book Format)"
        ]
    )
    selected_ratio = aspect_ratio_choice.split(" ")[0]

bgm_file = st.file_uploader("Upload Background Score / Soft Flute (MP3/WAV):", type=["mp3", "wav"])

def python_fallback_segment(raw_text):
    sentences = [s.strip() for s in re.split(r'[।\.\n]+', raw_text) if s.strip()]
    scenes = []
    chunk = []
    chunk_len = 0
    s_idx = 1
    for s in sentences:
        chunk.append(s)
        chunk_len += len(s)
        if len(chunk) >= 2 or chunk_len >= 130:
            scenes.append({
                "scene_id": f"Scene_{s_idx:02d}",
                "narration_text": "। ".join(chunk) + "।",
                "visual_description": f"Touching scene highlighting key characters: {chunk[0][:120]}"
            })
            chunk = []
            chunk_len = 0
            s_idx += 1
    if chunk:
        scenes.append({
            "scene_id": f"Scene_{s_idx:02d}",
            "narration_text": "। ".join(chunk) + "।",
            "visual_description": f"Touching conclusion scene: {chunk[0][:120]}"
        })
    return scenes

def gemini_segment_dynamic(gemini_api_key, raw_story, preset_context):
    ai_client = genai.Client(api_key=gemini_api_key)
    prompt = f"""
    You are an expert story director. Tone guidance: {preset_context}.
    Analyze this story and segment it into coherent, beautifully paced cinematic scenes.
    Ensure each scene represents a meaningful emotional beat or visual moment.
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
    return fallback_data, "Generated with Smart Local Engine (API Fallback)"

def build_consistent_prompt(scene_id, visual_desc, ratio):
    matched_dna = []
    text_lower = visual_desc.lower()
    
    if any(k in text_lower for k in ["rama", "shri ram", "lord rama", "ram"]):
        matched_dna.append(CHARACTER_DNA["RAMA"])
    if any(k in text_lower for k in ["shabari", "shramana"]):
        matched_dna.append(CHARACTER_DNA["SHABARI"])
    if any(k in text_lower for k in ["kaushalya", "queen kaushalya"]):
        matched_dna.append(CHARACTER_DNA["KAUSHALYA"])
    if any(k in text_lower for k in ["kaikeyi", "queen kaikeyi"]):
        matched_dna.append(CHARACTER_DNA["KAIKEYI"])
    if any(k in text_lower for k in ["bharata", "bharat"]):
        matched_dna.append(CHARACTER_DNA["BHARATA"])
    if any(k in text_lower for k in ["lakshmana", "lakshman"]):
        matched_dna.append(CHARACTER_DNA["LAKSHMANA"])
        
    dna_block = " | ".join(matched_dna) if matched_dna else "Indian devotional spiritual figures in classical attire."
    return f"[Ref: img_{scene_id}] Picture-book style scene: {visual_desc}. Core Figures: {dna_block}. Art Style: {ART_STYLE}, framed for {ratio} format."

# વોઇસ સિન્થેસિસ ફંક્શન (Sulafat અને Fallback સાથે)
def synthesize_with_fallback(tts_client, text, preset):
    audio_config = texttospeech.AudioConfig(
        audio_encoding=texttospeech.AudioEncoding.MP3,
        speaking_rate=preset["speed"],
        pitch=preset["pitch"]
    )
    s_input = texttospeech.SynthesisInput(text=text)

    # ૧. પ્રાથમિક વોઇસ (દા.ત. Sulafat)
    try:
        voice = texttospeech.VoiceSelectionParams(
            language_code="hi-IN",
            name=preset["voice"],
            ssml_gender=preset["gender"]
        )
        res = tts_client.synthesize_speech(input=s_input, voice=voice, audio_config=audio_config)
        return res.audio_content
    except Exception:
        # ૨. જો Sulafat ઉપલબ્ધ ન હોય તો સમાન પ્રેમાળ Neural2-D વોઇસ
        fallback_voice = texttospeech.VoiceSelectionParams(
            language_code="hi-IN",
            name=preset["fallback_voice"],
            ssml_gender=preset["gender"]
        )
        res = tts_client.synthesize_speech(input=s_input, voice=fallback_voice, audio_config=audio_config)
        return res.audio_content

if st.button("🚀 Produce Story Pack with Preset", type="primary", use_container_width=True):
    if not final_gcloud_key or not final_gemini_key:
        st.error("Please enter and save BOTH Google Cloud and Gemini API Keys above.")
    elif not text_input.strip():
        st.warning("Please paste your story text.")
    else:
        try:
            status_text = st.empty()
            status_text.text(f"🧠 Directing story scenes for '{selected_preset_name}'...")

            parsed_scenes, engine_info = gemini_segment_dynamic(final_gemini_key, text_input, current_preset["prompt_context"])
            total_scenes = len(parsed_scenes)
            st.info(f"{engine_info} — Successfully produced {total_scenes} scenes.")

            tts_client = texttospeech.TextToSpeechClient(client_options=ClientOptions(api_key=final_gcloud_key))

            scene_results = []
            full_voice_track = AudioSegment.empty()
            progress_bar = st.progress(0)

            for idx, item in enumerate(parsed_scenes):
                scene_id = item.get("scene_id", f"Scene_{idx+1:02d}")
                narration = item.get("narration_text", "")
                visual_desc = item.get("visual_description", "")
                image_tag = f"img_{scene_id}"

                status_text.text(f"Synthesizing {scene_id} ({idx+1}/{total_scenes}) with preset voice...")

                raw_audio_bytes = synthesize_with_fallback(tts_client, narration, current_preset)
                scene_audio = AudioSegment.from_file(io.BytesIO(raw_audio_bytes), format="mp3")
                full_voice_track += scene_audio + AudioSegment.silent(duration=current_preset["pause_ms"])

                full_prompt = build_consistent_prompt(scene_id, visual_desc, selected_ratio)

                scene_results.append((scene_id, image_tag, narration, scene_audio, full_prompt))
                progress_bar.progress((idx + 1) / total_scenes)

            status_text.text("Mastering audio score and compiling ZIP package...")

            # BGM મિક્સિંગ (પ્રી-સેટ વોલ્યુમ મુજબ)
            master_final = full_voice_track
            if bgm_file is not None:
                bgm_audio = AudioSegment.from_file(io.BytesIO(bgm_file.getvalue()))
                bgm_audio = bgm_audio.set_frame_rate(full_voice_track.frame_rate).set_channels(full_voice_track.channels) + current_preset["bgm_db"]
                if len(bgm_audio) < len(full_voice_track):
                    bgm_audio = bgm_audio * ((len(full_voice_track) // len(bgm_audio)) + 1)
                bgm_audio = bgm_audio[:len(full_voice_track) + 3000].fade_out(3000)
                master_final = bgm_audio.overlay(full_voice_track)

            # ZIP ફાઈલ તૈયાર કરવી
            zip_buffer = io.BytesIO()
            with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
                master_audio_bytes = io.BytesIO()
                master_final.export(master_audio_bytes, format="mp3", bitrate="192k")
                zip_file.writestr("full_story_master.mp3", master_audio_bytes.getvalue())

                full_script_content = ""
                full_prompts_content = ""

                for s_id, img_tag, s_txt, s_aud, s_prompt in scene_results:
                    aud_bytes = io.BytesIO()
                    s_aud.export(aud_bytes, format="mp3")
                    zip_file.writestr(f"audio/{s_id}_audio.mp3", aud_bytes.getvalue())

                    full_script_content += f"[{s_id}]\n{s_txt}\n\n"
                    full_prompts_content += f"[{img_tag} - Matched with {s_id}_audio.mp3]\n{s_prompt}\n\n"

                zip_file.writestr("script.txt", full_script_content)
                zip_file.writestr("image_prompts.txt", full_prompts_content)

            status_text.empty()
            st.success(f"🎉 Production Finished using '{selected_preset_name}'!")

            # ૧. All-in-One ZIP ડાઉનલોડ બટન
            st.subheader("📦 ૧. સંપૂર્ણ પ્રોડક્શન ZIP પેકેજ")
            st.write("આ ઝિપમાં દરેક સીનનો ઓડિયો, સ્ક્રિપ્ટ, પ્રોમ્પ્ટ્સ અને માસ્ટર ટ્રેક સમાવિષ્ટ છે.")
            st.download_button(
                label="⬇️ Download Complete Production Package (ZIP)",
                data=zip_buffer.getvalue(),
                file_name="story_production_package.zip",
                mime="application/zip",
                type="primary",
                use_container_width=True
            )

            # ૨. માસ્ટર ઓડિયો
            st.divider()
            st.subheader("🎵 ૨. સંપૂર્ણ વાર્તાનો માસ્ટર ઓડિયો (BGM સાથે)")
            st.audio(master_audio_bytes.getvalue(), format="audio/mp3")

            # ૩. સીન-બાય-સીન ડેસ્ક
            st.divider()
            st.subheader(f"🎬 ૩. સીન-બાય-સીન પ્રોડક્શન ડેસ્ક ({selected_ratio})")

            for s_id, img_tag, s_txt, s_aud, s_prompt in scene_results:
                with st.expander(f"📌 {s_id} | Paired Visual: {img_tag}", expanded=True):
                    col_left, col_right = st.columns([1.2, 1])
                    
                    with col_left:
                        st.markdown(f"**📖 Narration Script ({s_id}):**")
                        st.code(s_txt, language="text")
                        aud_b = io.BytesIO()
                        s_aud.export(aud_b, format="mp3")
                        st.audio(aud_b.getvalue(), format="audio/mp3")
                        st.download_button(
                            label=f"⬇️ Download {s_id} Audio",
                            data=s_aud.export(io.BytesIO(), format="mp3").getvalue(),
                            file_name=f"{s_id}_audio.mp3",
                            mime="audio/mp3",
                            key=f"btn_{s_id}"
                        )
                        
                    with col_right:
                        st.markdown(f"**🎨 Image Prompt (`{img_tag}`):**")
                        st.code(s_prompt, language="text")
                        st.caption(f"💡 Visual matched with: `{s_id}_audio.mp3`")

        except Exception as e:
            st.error(f"Error during production: {e}")
