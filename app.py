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

st.set_page_config(page_title="AI Story Studio - Auto Scene Production", page_icon="🎬", layout="wide")

CONFIG_FILE = "config.json"

def load_saved_key():
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r") as f:
                return json.load(f).get("api_key", "")
        except Exception:
            return ""
    return ""

def save_key_to_file(key):
    with open(CONFIG_FILE, "w") as f:
        json.dump({"api_key": key}, f)

current_saved_key = load_saved_key()

st.title("🎬 AI Mythological Story & Cinematic Scene Studio")
st.write("Automatically segment raw stories into scenes, generate consistent visual frames, neural narration, and blended background music.")

# 1. API Key Management
with st.expander("🔑 Google Cloud / Gemini API Key Settings", expanded=(not bool(current_saved_key))):
    input_key = st.text_input(
        "Enter Google Cloud API Key:",
        value=current_saved_key,
        type="password",
        placeholder="AIzaSy...",
        help="This single key powers Gemini Analysis, Text-to-Speech, and Imagen Visuals."
    )
    col_k1, col_k2 = st.columns([1, 1])
    with col_k1:
        if st.button("💾 Save Key Permanently"):
            if input_key.strip():
                save_key_to_file(input_key.strip())
                st.success("API Key successfully saved!")
                st.rerun()
            else:
                st.warning("Please enter a valid API key.")
    with col_k2:
        if current_saved_key and st.button("🗑️ Clear Saved Key"):
            if os.path.exists(CONFIG_FILE):
                os.remove(CONFIG_FILE)
            st.info("API Key removed.")
            st.rerun()

api_key = input_key.strip() if input_key.strip() else current_saved_key

# 2. Character DNA & Art Style Definition
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
    "Paste Raw Story (No formatting or scene tags needed):", 
    height=230, 
    placeholder="Paste your continuous story text here. The AI will automatically read, understand, and segment it into coherent cinematic scenes..."
)

col1, col2, col3, col4 = st.columns(4)
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
        "Aspect Ratio:",
        [
            "9:16 (Instagram Reels / Shorts)",
            "16:9 (YouTube Landscape)",
            "1:1 (Square Post / Feed)",
            "4:3 (Classic Television)"
        ]
    )
    selected_ratio = aspect_ratio_choice.split(" ")[0]

with col4:
    generate_images = st.checkbox("Generate Visuals with Imagen?", value=True)

bgm_file = st.file_uploader("Upload Background Music (MP3/WAV):", type=["mp3", "wav"])

bgm_volume_reduction = st.slider(
    "BGM Volume Reduction (dB):", 
    min_value=-30, 
    max_value=-10, 
    value=-18, 
    format="%d dB"
)

# AI દ્વારા આપોઆપ વાર્તાનું વિશ્લેષણ અને સીન વિભાજન
def ai_segment_story(client, raw_story):
    prompt = f"""
    You are a professional mythological film director. Analyze the following story and break it down into sequential visual scenes.
    Return ONLY a valid JSON array of objects. Do not wrap in markdown quotes if possible, or use standard json formatting.
    Each object must have:
    - "scene_number": integer
    - "narration_text": the exact segment of text for voiceover in this scene (keep the original language)
    - "visual_description": a rich English prompt describing the visual action, environment, and characters present.

    Story:
    {raw_story}
    """
    response = client.models.generate_content(
        model='gemini-2.5-flash',
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
    return f"Scene Visual: {visual_desc}. Featured Characters: {dna_block}. Art Style: {ART_STYLE}, framed perfectly for {ratio} format."

if st.button("🚀 Auto-Produce Story & Scenes", type="primary", use_container_width=True):
    if not api_key:
        st.error("Please enter and save your Google API Key above.")
    elif not text_input.strip():
        st.warning("Please paste your story text.")
    else:
        try:
            ai_client = genai.Client(api_key=api_key)
            tts_client = texttospeech.TextToSpeechClient(client_options=ClientOptions(api_key=api_key))
            voice = texttospeech.VoiceSelectionParams(language_code="hi-IN", name=voice_name, ssml_gender=ssml_gender)
            audio_config = texttospeech.AudioConfig(audio_encoding=texttospeech.AudioEncoding.MP3, speaking_rate=speed_rate, pitch=-1.0)

            status_text = st.empty()
            status_text.text("AI is analyzing the narrative and automatically dividing it into scenes...")

            # ૧. વાર્તા આપોઆપ સીનમાં વહેંચાઈ જશે
            parsed_scenes = ai_segment_story(ai_client, text_input)
            total_scenes = len(parsed_scenes)
            st.info(f"AI identified and generated {total_scenes} cinematic scenes.")

            scene_results = []
            full_voice_track = AudioSegment.empty()
            progress_bar = st.progress(0)

            for idx, item in enumerate(parsed_scenes):
                s_num = item.get("scene_number", idx + 1)
                narration = item.get("narration_text", "")
                visual_desc = item.get("visual_description", "")

                status_text.text(f"Synthesizing Audio & Visuals for Scene {s_num} of {total_scenes}...")

                # ૨. ઓડિયો નિર્માણ
                s_input = texttospeech.SynthesisInput(text=narration)
                res = tts_client.synthesize_speech(input=s_input, voice=voice, audio_config=audio_config)
                scene_audio = AudioSegment.from_file(io.BytesIO(res.audio_content), format="mp3")
                full_voice_track += scene_audio + AudioSegment.silent(duration=1000)

                # ૩. ઈમેજ નિર્માણ (કેરેક્ટર DNA સાથે)
                scene_img = None
                if generate_images:
                    prompt = build_consistent_prompt(visual_desc, selected_ratio)
                    try:
                        img_response = ai_client.models.generate_images(
                            model='imagen-3.0-generate-002',
                            prompt=prompt,
                            config=dict(number_of_images=1, aspect_ratio=selected_ratio)
                        )
                        for generated_image in img_response.generated_images:
                            scene_img = Image.open(io.BytesIO(generated_image.image.image_bytes))
                    except Exception:
                        pass
                    
                    time.sleep(2)

                scene_results.append((s_num, narration, scene_audio, scene_img))
                progress_bar.progress((idx + 1) / total_scenes)

            status_text.text("Blending background score and mastering audio...")

            # ૪. માસ્ટર મ્યુઝિક ઓવરલે
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

            # Full Story Audio
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

            # Individual Scene Breakdowns
            st.divider()
            st.subheader(f"🎬 2. Scene-by-Scene Visuals ({selected_ratio}) & Isolated Audio")

            for s_num, s_txt, s_aud, s_img in scene_results:
                st.markdown(f"#### 📍 Scene {s_num}")
                col_img, col_aud = st.columns([1, 1])
                
                with col_img:
                    if s_img:
                        st.image(s_img, caption=f"Scene {s_num} Visual ({selected_ratio})", use_container_width=True)
                        img_buf = io.BytesIO()
                        s_img.save(img_buf, format="PNG")
                        st.download_button(
                            label=f"⬇️ Download Scene {s_num} Image",
                            data=img_buf.getvalue(),
                            file_name=f"scene_{s_num}_{selected_ratio.replace(':', '_')}.png",
                            mime="image/png",
                            key=f"img_btn_{s_num}"
                        )
                    else:
                        st.info("Visual generation skipped or unavailable.")
                        
                with col_aud:
                    st.write(f"**Narration Script:** {s_txt}")
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
                st.divider()

        except Exception as e:
            st.error(f"Error during production: {e}")
