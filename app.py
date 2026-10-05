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

st.set_page_config(page_title="AI Story Studio - Mythological Production", page_icon="🎬", layout="wide")

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

st.title("🎬 AI પૌરાણિક વાર્તા & સિનેમેટિક સીન સ્ટુડિયો")
st.write("વાર્તામાંથી સીન મુજબના પાત્ર-સુસંગત ફોટા, અવાજ અને બેકગ્રાઉન્ડ સંગીત એક જ ક્લિકમાં તૈયાર કરો.")

# ૧. API Key મેનેજમેન્ટ
with st.expander("🔑 Google Cloud / Gemini API Key Settings", expanded=(not bool(current_saved_key))):
    input_key = st.text_input(
        "તમારી Google Cloud API Key દાખલ કરો:",
        value=current_saved_key,
        type="password",
        placeholder="AIzaSy...",
        help="આ કી વડે Google Text-to-Speech અને Imagen બંને એકસાથે ચાલશે."
    )
    col_k1, col_k2 = st.columns([1, 1])
    with col_k1:
        if st.button("💾 Save Key કાયમ માટે સેવ કરો"):
            if input_key.strip():
                save_key_to_file(input_key.strip())
                st.success("API Key સફળતાપૂર્વક સેવ થઈ ગઈ છે!")
                st.rerun()
            else:
                st.warning("કૃપા કરીને સાચી કી દાખલ કરો.")
    with col_k2:
        if current_saved_key and st.button("🗑️ Clear Key હટાવો"):
            if os.path.exists(CONFIG_FILE):
                os.remove(CONFIG_FILE)
            st.info("કી હટાવી દેવામાં આવી છે.")
            st.rerun()

api_key = input_key.strip() if input_key.strip() else current_saved_key

# ૨. પાત્રોનું ફિક્સ વિઝ્યુઅલ DNA (દરેક સીનમાં લૂક એકસરખો રાખવા માટે)
CHARACTER_DNA = {
    "RAMA": "Lord Rama depicted as a noble 25-year-old ancient Indian prince, serene gentle almond-shaped eyes, divine benevolent smile, dusky wheatish complexion, royal golden-yellow silk pitambara dhoti, traditional ornate Vedic gold mukut crown, gold armlets and necklaces, majestic calm posture.",
    "KAUSHALYA": "Queen Mata Kaushalya, graceful loving queen mother in her mid-40s, kind motherly face with gentle benevolent eyes, dressed in royal crimson-maroon silk saree with wide gold zari border, ornate Vedic gold jewelry, dignified royal demeanor.",
    "KAIKEYI": "Queen Kaikeyi, beautiful determined royal queen in her late 30s, sharp commanding facial features, expressive resolute eyes, adorned in royal emerald-green silk garments with intricate gold embroidery and heavy royal gold crown.",
    "BHARATA": "Prince Bharata, devoted humble prince in royal ochre-silk attire, tearful affectionate eyes, deeply resembling Rama in royal lineage with folded hands and devotional expression.",
    "LAKSHMANA": "Prince Lakshmana, spirited devoted youthful prince, fierce protective loving eyes, golden-yellow silk attire, holding sacred bow, looking steadfastly beside Rama."
}

ART_STYLE = "Raja Ravi Varma aesthetic blended with cinematic 8k, soft golden ambient lighting, authentic ancient Indian palace and forest architecture, oil-painting warmth, ultra-consistent character faces."

# ૩. સ્ક્રિપ્ટ ઇનપુટ
text_input = st.text_area(
    "વાર્તાનું સંપૂર્ણ લખાણ (દરેક સીન વચ્ચે ૧ લાઈન છોડો અથવા Scene 1, Scene 2 લખો):", 
    height=220, 
    placeholder="Scene 1:\nશ્રીરામ અયોધ્યાના ભવ્ય રાજમહેલમાં માતા કૌશલ્યાના ચરણ સ્પર્શ કરી આશીર્વાદ લઈ રહ્યા છે...\n\nScene 2:\nમાતા કૈકેયીના ભવનમાં શ્રીરામ હાથ જોડીને વનવાસની આજ્ઞા સ્વીકારે છે...\n\nScene 3:\nચિત્રકૂટના પવિત્ર વનમાં ભાઈ ભરત શ્રીરામના ચરણોમાં નતમસ્તક થાય છે..."
)

# ૪ સેટિંગ્સ લાઈન (રેશિયો સિલેક્ટર સાથે)
col1, col2, col3, col4 = st.columns(4)
with col1:
    voice_choice = st.selectbox(
        "વાચકનો અવાજ:",
        [
            "hi-IN-Journey-D (પુરુષ - Ultra Natural Storytelling)",
            "hi-IN-Journey-F (સ્ત્રી - Ultra Natural Narrative)",
            "hi-IN-Neural2-B (પુરુષ - Deep & Classical)",
            "hi-IN-Neural2-A (સ્ત્રી - Clear & Narrative)"
        ]
    )
    voice_name = voice_choice.split(" ")[0]
    ssml_gender = texttospeech.SsmlVoiceGender.MALE if ("-B" in voice_name or "Journey-D" in voice_name) else texttospeech.SsmlVoiceGender.FEMALE

with col2:
    speed_rate = st.slider(
        "વાંચવાની ઝડપ:", 
        min_value=0.75, 
        max_value=1.10, 
        value=0.88, 
        step=0.02
    )

with col3:
    # વિડિયો અને રિલ્સ મુજબ રેશિયો પસંદગી
    aspect_ratio_choice = st.selectbox(
        "ઈમેજ રેશિયો (સાઇઝ):",
        [
            "9:16 (ઇન્સ્ટાગ્રામ રિલ્સ / શોર્ટ્સ)",
            "16:9 (યુટ્યુબ આડો વિડિયો)",
            "1:1 (ચોરસ પોસ્ટ / વિડિયો)",
            "4:3 (ક્લાસિકલ ટીવી સાઇઝ)"
        ]
    )
    selected_ratio = aspect_ratio_choice.split(" ")[0]

with col4:
    generate_images = st.checkbox("સીન મુજબ AI ઈમેજીસ બનાવવા?", value=True)

bgm_file = st.file_uploader("બેકગ્રાઉન્ડ વાંસળી/સંગીત ઓડિયો અપલોડ કરો (MP3/WAV):", type=["mp3", "wav"])

bgm_volume_reduction = st.slider(
    "BGM કેટલું ધીમું રાખવું (dB):", 
    min_value=-30, 
    max_value=-10, 
    value=-18, 
    format="%d dB"
)

def parse_scenes(raw_text):
    pattern = r'(?:Scene\s*\d+|સીન\s*\d+|दृश्य\s*\d+)[:\-\s]*'
    parts = re.split(pattern, raw_text, flags=re.IGNORECASE)
    scenes = [p.strip() for p in parts if p.strip()]
    if len(scenes) <= 1:
        scenes = [p.strip() for p in raw_text.split("\n\n") if p.strip()]
    return scenes if scenes else [raw_text.strip()]

def build_consistent_prompt(scene_text, ratio):
    matched_dna = []
    text_lower = scene_text.lower()
    
    if any(k in text_lower for k in ["રામ", "શ્રીરામ", "राम", "shri ram", "rama"]):
        matched_dna.append(CHARACTER_DNA["RAMA"])
    if any(k in text_lower for k in ["કૌશલ્યા", "કૌશલ્યાજી", "कौशल्या", "kaushalya"]):
        matched_dna.append(CHARACTER_DNA["KAUSHALYA"])
    if any(k in text_lower for k in ["કૈકેયી", "કૈકેઈ", "कैकेयी", "kaikeyi"]):
        matched_dna.append(CHARACTER_DNA["KAIKEYI"])
    if any(k in text_lower for k in ["ભરત", "भरत", "bharat"]):
        matched_dna.append(CHARACTER_DNA["BHARATA"])
    if any(k in text_lower for k in ["લક્ષ્મણ", "लक्ष्मण", "lakshman"]):
        matched_dna.append(CHARACTER_DNA["LAKSHMANA"])
        
    dna_block = " | ".join(matched_dna) if matched_dna else "Noble Indian mythological royal figures in classical Vedic attire."
    return f"Cinematic scene description: {scene_text[:250]}. Featured Characters: {dna_block}. Art Style: {ART_STYLE}, framed perfectly for {ratio} format."

if st.button("🚀 સંપૂર્ણ વાર્તા પ્રોજેક્ટ તૈયાર કરો", type="primary", use_container_width=True):
    if not api_key:
        st.error("કૃપા કરીને પહેલા ઉપર Google API Key સેવ કરો.")
    elif not text_input.strip():
        st.warning("કૃપા કરીને વાર્તાનું લખાણ દાખલ કરો.")
    else:
        scenes = parse_scenes(text_input)
        total_scenes = len(scenes)
        st.info(f"કુલ {total_scenes} સીન મળ્યા છે. પસંદ કરેલ સાઈઝ: {selected_ratio}. પ્રોસેસિંગ ચાલુ છે...")
        
        try:
            tts_client = texttospeech.TextToSpeechClient(client_options=ClientOptions(api_key=api_key))
            voice = texttospeech.VoiceSelectionParams(language_code="hi-IN", name=voice_name, ssml_gender=ssml_gender)
            audio_config = texttospeech.AudioConfig(audio_encoding=texttospeech.AudioEncoding.MP3, speaking_rate=speed_rate, pitch=-1.0)
            
            ai_client = genai.Client(api_key=api_key) if generate_images else None

            scene_results = []
            full_voice_track = AudioSegment.empty()
            
            progress_bar = st.progress(0)
            status_text = st.empty()

            for idx, scene_text in enumerate(scenes):
                status_text.text(f"પ્રોસેસિંગ: Scene {idx + 1} of {total_scenes}...")

                # ૧. ઓડિયો જનરેટ કરવો
                s_input = texttospeech.SynthesisInput(text=scene_text)
                res = tts_client.synthesize_speech(input=s_input, voice=voice, audio_config=audio_config)
                scene_audio = AudioSegment.from_file(io.BytesIO(res.audio_content), format="mp3")
                full_voice_track += scene_audio + AudioSegment.silent(duration=1000)

                # ૨. ઈમેજ જનરેટ કરવી (પસંદ કરેલા Aspect Ratio સાથે)
                scene_img = None
                if generate_images:
                    final_prompt = build_consistent_prompt(scene_text, selected_ratio)
                    try:
                        img_response = ai_client.models.generate_images(
                            model='imagen-3.0-generate-002',
                            prompt=final_prompt,
                            config=dict(number_of_images=1, aspect_ratio=selected_ratio)
                        )
                        for generated_image in img_response.generated_images:
                            scene_img = Image.open(io.BytesIO(generated_image.image.image_bytes))
                    except Exception:
                        pass
                    
                    time.sleep(2)

                scene_results.append((idx + 1, scene_text, scene_audio, scene_img))
                progress_bar.progress((idx + 1) / total_scenes)

            status_text.text("સંગીત અને ઓડિયો મિક્સિંગ ચાલુ છે...")

            # ૩. BGM મિક્સિંગ
            master_final = full_voice_track
            if bgm_file is not None:
                bgm_audio = AudioSegment.from_file(io.BytesIO(bgm_file.getvalue()))
                bgm_audio = bgm_audio.set_frame_rate(full_voice_track.frame_rate).set_channels(full_voice_track.channels) + bgm_volume_reduction
                if len(bgm_audio) < len(full_voice_track):
                    bgm_audio = bgm_audio * ((len(full_voice_track) // len(bgm_audio)) + 1)
                bgm_audio = bgm_audio[:len(full_voice_track) + 2500].fade_out(2500)
                master_final = bgm_audio.overlay(full_voice_track)

            status_text.empty()
            st.success(f"🎉 તમામ {total_scenes} સીન, {selected_ratio} સાઈઝની ઈમેજીસ અને ઓડિયો તૈયાર!")

            # ૪. મુખ્ય માસ્ટર ઓડિયો
            st.subheader("🎵 ૧. સંપૂર્ણ વાર્તાનો ઓડિયો (BGM સાથે)")
            master_buf = io.BytesIO()
            master_final.export(master_buf, format="mp3", bitrate="192k")
            st.audio(master_buf.getvalue(), format="audio/mp3")
            st.download_button(
                label="⬇️ સંપૂર્ણ વાર્તા MP3 ડાઉનલોડ કરો",
                data=master_buf.getvalue(),
                file_name="full_story_master.mp3",
                mime="audio/mp3",
                use_container_width=True
            )

            # ૫. સીન-વાઇઝ વિઝ્યુઅલ અને ઓડિયો ડિસ્પ્લે
            st.divider()
            st.subheader(f"🎬 ૨. સીન વાઇઝ ઈમેજ ({selected_ratio}) અને ઓડિયો")

            for s_num, s_txt, s_aud, s_img in scene_results:
                st.markdown(f"#### 📍 Scene {s_num}")
                col_img, col_aud = st.columns([1, 1])
                
                with col_img:
                    if s_img:
                        st.image(s_img, caption=f"Scene {s_num} Visual ({selected_ratio})", use_container_width=True)
                        img_buf = io.BytesIO()
                        s_img.save(img_buf, format="PNG")
                        st.download_button(
                            label=f"⬇️ Scene {s_num} Image ડાઉનલોડ",
                            data=img_buf.getvalue(),
                            file_name=f"scene_{s_num}_{selected_ratio.replace(':', '_')}.png",
                            mime="image/png",
                            key=f"img_btn_{s_num}"
                        )
                    else:
                        st.info("આ સીન માટે ઈમેજ ઉપલબ્ધ નથી.")
                        
                with col_aud:
                    st.write(f"**સીન વર્ણન:** {s_txt}")
                    s_buf = io.BytesIO()
                    s_aud.export(s_buf, format="mp3")
                    st.audio(s_buf.getvalue(), format="audio/mp3")
                    st.download_button(
                        label=f"⬇️ Scene {s_num} Audio ડાઉનલોડ",
                        data=s_buf.getvalue(),
                        file_name=f"scene_{s_num}_audio.mp3",
                        mime="audio/mp3",
                        key=f"aud_btn_{s_num}"
                    )
                st.divider()

        except Exception as e:
            st.error(f"એરર આવી: {e}")
