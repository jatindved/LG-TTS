import streamlit as st
import os
from pydub import AudioSegment
from google.cloud import texttospeech
from google.api_core.client_options import ClientOptions

st.set_page_config(page_title="AI Voice & BGM Studio", page_icon="🎙️", layout="centered")

st.title("🎙️ Google Journey & Neural2 Voice Studio")
st.write("Generate ultra-realistic Google voices and blend them with background music.")

# 1. API Key Input
api_key = st.text_input("Enter your Google Cloud API Key:", type="password", placeholder="AIzaSy...")

# 2. Script Text Input
text_input = st.text_area(
    "Script Text (Hindi):", 
    height=200, 
    placeholder="Paste your story or script here..."
)

# 3. Voice Selection
col1, col2 = st.columns(2)
with col1:
    voice_choice = st.selectbox(
        "Select Narrator Voice:",
        [
            "hi-IN-Neural2-B (Male - Deep & Classical)",
            "hi-IN-Neural2-C (Male - Calm & Serious)",
            "hi-IN-Neural2-A (Female - Clear & Narrative)",
            "hi-IN-Neural2-D (Female - Soft & Emotional)",
            "hi-IN-Journey-D (Male - Ultra Natural Storytelling)",
            "hi-IN-Journey-F (Female - Ultra Natural Narrative)"
        ]
    )
    voice_name = voice_choice.split(" ")[0]
    ssml_gender = texttospeech.SsmlVoiceGender.MALE if ("-B" in voice_name or "-C" in voice_name or "Journey-D" in voice_name) else texttospeech.SsmlVoiceGender.FEMALE

with col2:
    speed_rate = st.slider(
        "Speaking Rate:", 
        min_value=0.75, 
        max_value=1.10, 
        value=0.88, 
        step=0.02, 
        help="0.85 to 0.90 is ideal for devotional and storytelling narration."
    )

# 4. Background Music Upload
bgm_file = st.file_uploader("Upload Background Music (MP3/WAV):", type=["mp3", "wav"])

bgm_volume_reduction = st.slider(
    "BGM Volume Reduction (dB):", 
    min_value=-30, 
    max_value=-10, 
    value=-18, 
    format="%d dB",
    help="-18 dB ensures background music is soft and speech is clear."
)

if st.button("🎧 Generate Master Audio", type="primary", use_container_width=True):
    if not api_key.strip():
        st.error("Please enter your Google Cloud API Key.")
    elif not text_input.strip():
        st.warning("Please enter your script text.")
    else:
        with st.spinner("Synthesizing voice via Google Neural Engine and mixing audio..."):
            try:
                # Setup Google TTS Client with API Key
                client_options = ClientOptions(api_key=api_key.strip())
                client = texttospeech.TextToSpeechClient(client_options=client_options)

                synthesis_input = texttospeech.SynthesisInput(text=text_input)

                voice = texttospeech.VoiceSelectionParams(
                    language_code="hi-IN",
                    name=voice_name,
                    ssml_gender=ssml_gender
                )

                audio_config = texttospeech.AudioConfig(
                    audio_encoding=texttospeech.AudioEncoding.MP3,
                    speaking_rate=speed_rate,
                    pitch=-1.0
                )

                response = client.synthesize_speech(
                    input=synthesis_input, 
                    voice=voice, 
                    audio_config=audio_config
                )

                temp_voice = "google_temp_voice.mp3"
                temp_bgm = "google_temp_bgm.mp3"
                final_output = "google_final_master.mp3"

                with open(temp_voice, "wb") as out:
                    out.write(response.audio_content)

                voice_audio = AudioSegment.from_file(temp_voice)

                # Mix BGM if provided
                if bgm_file is not None:
                    with open(temp_bgm, "wb") as f:
                        f.write(bgm_file.getbuffer())

                    bgm_audio = AudioSegment.from_file(temp_bgm)
                    bgm_audio = bgm_audio.set_frame_rate(voice_audio.frame_rate).set_channels(voice_audio.channels)
                    bgm_audio = bgm_audio + bgm_volume_reduction

                    if len(bgm_audio) < len(voice_audio):
                        repeats = (len(voice_audio) // len(bgm_audio)) + 1
                        bgm_audio = bgm_audio * repeats

                    bgm_audio = bgm_audio[:len(voice_audio) + 2500]
                    bgm_audio = bgm_audio.fade_out(2500)

                    final_audio = bgm_audio.overlay(voice_audio)
                    final_audio.export(final_output, format="mp3", bitrate="192k")

                    if os.path.exists(temp_bgm):
                        os.remove(temp_bgm)
                else:
                    voice_audio.export(final_output, format="mp3", bitrate="192k")

                if os.path.exists(temp_voice):
                    os.remove(temp_voice)

                st.success("Master Audio with BGM generated successfully!")

                with open(final_output, "rb") as f:
                    audio_bytes = f.read()
                    st.audio(audio_bytes, format="audio/mp3")
                    st.download_button(
                        label="⬇️ Download Final MP3",
                        data=audio_bytes,
                        file_name="story_master_audio.mp3",
                        mime="audio/mp3",
                        use_container_width=True
                    )

            except Exception as e:
                st.error(f"Error occurred: {e}")
