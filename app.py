import os
import streamlit as st
from openai import OpenAI

def get_secret(name):
    try:
        return st.secrets[name]
    except Exception:
        from dotenv import load_dotenv
        load_dotenv()
        return os.getenv(name)

st.title("ShipCheck: deploy test")

client = OpenAI(base_url="https://api.tokenfactory.nebius.com/v1/",
                api_key=get_secret("NEBIUS_API_KEY"))

if st.button("Ping Nemotron Nano"):
    r = client.chat.completions.create(
        model=get_secret("MODEL_NANO"), max_tokens=200,
        messages=[{"role": "user", "content": "Reply with exactly: deployed OK"}])
    st.success(r.choices[0].message.content)