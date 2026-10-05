import streamlit as st
import asyncio
import os
import edge_tts
from pydub import AudioSegment

st.set_page_config(page_title="AI Voice & BGM Studio", page_icon="🎙️", layout="centered")

st.title("🎙️ AI Voice-Over & BGM Studio")
st.write("Generate clean natural speech from text and mix it with background music.")

# 1. Text Input
text_input = st.text_area(
    "Enter Script Text:", 
    height=200, 
    placeholder="Paste your story or narration script here..."
)

# 2. Voice and Speed Settings
col1, col2 = st.columns(2)
with col1:
    voice_choice = st.selectbox(
        "Select Narrator Voice:",
        ["Swara (Female - Natural & Soft)", "Madhur (Male - Deep & Clear)"]
    )
    voice_id = "hi-IN-SwaraNeural" if "Swara" in voice_choice else "hi-IN-MadhurNeural"

with col2:
    speed_rate = st.slider(
        "Speech Speed Adjustment:", 
        min_value=-25, 
        max_value=10, 
        value=-8, 
        step=1, 
        format="%d%%"
    )

# 3. BGM Upload & Volume Control
bgm_file = st.file_uploader("Upload Background Music (MP3/WAV):", type=["mp3", "wav"])

bgm_volume_reduction = st.slider(
    "BGM Volume Reduction (dB):", 
    min_value=-30, 
    max_value=-5, 
    value=-18, 
    help="Recommended: -18 dB to -20 dB to keep voice clear and prominent."
)

async def generate_speech(text, voice, rate_str, output_path):
    communicate = edge_tts.Communicate(text, voice, rate=rate_str)
    await communicate.save(output_path)

if st.button("🎧 Generate Audio", type="primary", use_container_width=True):
    if not text_input.strip():
        st.warning("Please enter some text before generating.")
    else:
        with st.spinner("Processing audio, please wait..."):
            temp_voice = "temp_voice.mp3"
            final_output = "final_output.mp3"
            
            rate_param = f"{speed_rate:+d}%"
            asyncio.run(generate_speech(text_input, voice_id, rate_param, temp_voice))
            
            voice_audio = AudioSegment.from_file(temp_voice)
            
            if bgm_file is not None:
                with open("temp_bgm.mp3", "wb") as f:
                    f.write(bgm_file.getbuffer())
                    
                bgm_audio = AudioSegment.from_file("temp_bgm.mp3")
                bgm_audio = bgm_audio + bgm_volume_reduction
                
                # Loop BGM if it is shorter than voice track
                if len(bgm_audio) < len(voice_audio):
                    bgm_audio = bgm_audio * (len(voice_audio) // len(bgm_audio) + 1)
                
                # Trim and fade out after voice ends
                bgm_audio = bgm_audio[:len(voice_audio) + 2500]
                bgm_audio = bgm_audio.fade_out(2500)
                
                final_audio = bgm_audio.overlay(voice_audio)
                final_audio.export(final_output, format="mp3")
                
                if os.path.exists("temp_bgm.mp3"):
                    os.remove("temp_bgm.mp3")
            else:
                voice_audio.export(final_output, format="mp3")
                
            if os.path.exists(temp_voice):
                os.remove(temp_voice)
                
            st.success("Audio generated successfully!")
            
            # Player and Download
            with open(final_output, "rb") as audio_file:
                audio_bytes = audio_file.read()
                st.audio(audio_bytes, format="audio/mp3")
                st.download_button(
                    label="⬇️ Download MP3",
                    data=audio_bytes,
                    file_name="narrated_audio.mp3",
                    mime="audio/mp3",
                    use_container_width=True
                )
