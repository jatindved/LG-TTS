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
from google import genai
from streamlit_local_storage import LocalStorage

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

storage = LocalStorage()
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
        st.session_state[state_name] = read_device_value(storage_key, f"load_{short}")

# ---------------------------
# HELPERS
# ---------------------------
def clean_keys(values):
    return [x.strip() for x in values if isinstance(x, str) and x.strip()]

def story_hash(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]
