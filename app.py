import streamlit as st
import os
import json
import io
import time
from PIL import Image
from pydub import AudioSegment
from google.cloud import texttospeech
from google.api_core.client_options import ClientOptions
from google import genai

st.set_page_config(page_title="AI Story Studio - Dual Engine Production", page_icon="🎬", layout="wide")

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
st.write("Powered by Google AI Studio (Gemini 3.8 Flash) for story intelligence and Google Cloud for natural voice narration.")

# 1. Dual Key Management Box
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
                st.success("Both API keys saved successfully in config.json!")
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
    "Paste Raw Continuous Story (Gemini will automatically understand and direct the scenes):", 
    height=230, 
    placeholder="Paste your raw story here. Gemini will analyze the narrative emotion, split into coherent cinematic scenes, identify characters, and prepare visual camera prompts..."
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

# Gemini AI દ્વારા સ્માર્ટ સીન વિશ્લેષણ (Gemini 3.8 Flash)
def gemini_segment_story(gemini_api_key, raw_story):
    ai_client = genai.Client(api_key=gemini_api_key)
    prompt = f"""
    You are an expert mythological film director and cinematographer. 
    Analyze this raw story and segment it into coherent cinematic scenes.
    Ensure each scene represents a meaningful emotional beat or visual transition.
    Return ONLY a valid JSON list of objects.
    Each object must contain:
    - "scene_number": integer
    - "narration_text": the exact segment of text for voiceover in this scene (keep the original script language and flow intact)
    - "visual_description": a rich English prompt describing the visual action, camera angle, mood, and environment.

    Story:
    {raw_story}
    """
    response = ai_client.models.generate_content(
        model='gemini-3.8-flash',
        contents=prompt,
        config=dict(response_mime_type="application/json")
    )
    return json.loads(response.text)

def build_consistent_prompt(visual_desc, ratio):
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
    return f"Cinematic scene: {visual_desc}. Featured Characters: {dna_block}. Art Style: {ART_STYLE}, framed perfectly for {ratio} aspect ratio."

if st.button("🚀 Auto-Produce Story & Scenes (Gemini + Cloud TTS)", type="primary", use_container_width=True):
    if not final_gcloud_key or not final_gemini_key:
        st.error("Please enter and save BOTH Google Cloud and Gemini API Keys above.")
    elif not text_input.strip():
        st.warning("Please paste your story text.")
    else:
        try:
            status_text = st.empty()
            status_text.text("🧠 Gemini 3.8 Flash is analyzing the story and orchestrating scenes...")

            parsed_scenes = gemini_segment_story(final_gemini_key, text_input)
            total_scenes = len(parsed_scenes)
            st.info(f"Gemini successfully crafted {total_scenes} cinematic scenes!")

            tts_client = texttospeech.TextToSpeechClient(client_options=ClientOptions(api_key=final_gcloud_key))
            voice = texttospeech.VoiceSelectionParams(language_code="hi-IN", name=voice_name, ssml_gender=ssml_gender)
            audio_config = texttospeech.AudioConfig(audio_encoding=texttospeech.AudioEncoding.MP3, speaking_rate=speed_rate, pitch=-1.0)

            scene_results = []
            full_voice_track = AudioSegment.empty()
            progress_bar = st.progress(0)

            for idx, item in enumerate(parsed_scenes):
                s_num = item.get("scene_number", idx + 1)
                narration = item.get("narration_text", "")
                visual_desc = item.get("visual_description", "")

                status_text.text(f"Synthesizing Audio & Prompts for Scene {s_num} of {total_scenes}...")

                s_input = texttospeech.SynthesisInput(text=narration)
                res = tts_client.synthesize_speech(input=s_input, voice=voice, audio_config=audio_config)
                scene_audio = AudioSegment.from_file(io.BytesIO(res.audio_content), format="mp3")
                full_voice_track += scene_audio + AudioSegment.silent(duration=1000)

                full_prompt = build_consistent_prompt(visual_desc, selected_ratio)

                scene_results.append((s_num, narration, scene_audio, full_prompt))
                progress_bar.progress((idx + 1) / total_scenes)

            status_text.text("Blending background score and mastering audio...")

            master_final = full_voice_track
            if bgm_file is not None:
                bgm_audio = AudioSegment.from_file(io.BytesIO(bgm_file.getvalue()))
                bgm_audio = bgm_audio.set_frame_rate(full_voice_track.frame_rate).set_channels(full_voice_track.channels) + bgm_volume_reduction
                if len(bgm_audio) < len(full_voice_track):
                    bgm_audio = bgm_audio * ((len(full_voice_track) // len(bgm_audio)) + 1)
                bgm_audio = bgm_audio[:len(full_voice_track) + 2500].fade_out(2500)
                master_final = bgm_audio.overlay(full_voice_track)

            status_text.empty()
            st.success(f"🎉 Production Completed! Successfully generated {total_scenes} scenes.")

            st.subheader("🎵 1. Complete Master Narration (With BGM)")
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

            st.divider()
            st.subheader(f"🎬 2. Scene-by-Scene Breakdown ({selected_ratio})")

            for s_num, s_txt, s_aud, s_prompt in scene_results:
                with st.expander(f"📍 Scene {s_num}: {s_txt[:60]}...", expanded=True):
                    col_aud, col_prm = st.columns([1, 1])
                    
                    with col_aud:
                        st.markdown("**Narration Audio:**")
                        st.write(s_txt)
                        s_buf = io.BytesIO()
                        s_aud.export(s_buf, format="mp3")
                        st.audio(s_buf.getvalue(), format="audio/mp3")
                        st.download_button(
                            label=f"⬇️ Download Scene {s_num} Audio",
                            data=s_buf.getvalue(),
                            file_name=f"scene_{s_num}_audio.mp3",
                            mime="audio/mp3",
                            key=f"aud_btn_{s_num}"
                        )
                        
                    with col_prm:
                        st.markdown(f"**Visual Prompt ({selected_ratio}):**")
                        st.code(s_prompt, language="text")

        except Exception as e:
            st.error(f"Error during production: {e}")
