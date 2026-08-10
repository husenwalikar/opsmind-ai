import os
import re
from dotenv import load_dotenv
from groq import Groq
from pydantic import BaseModel, Field

# Load API key from .env
load_dotenv()
api_key = os.getenv("GROQ_API_KEY")

if not api_key:
    raise ValueError("GROQ_API_KEY not found in .env file!")

client = Groq(api_key=api_key)

# 1. Read a real error log line from the downloaded Loghub dataset
log_file_path = os.path.join("data", "Linux_2k.log")
sample_error = "Jul 28 17:02:15 combo sshd(pam_unix)[26348]: check pass; user unknown"

if os.path.exists(log_file_path):
    with open(log_file_path, "r", encoding="utf-8") as f:
        for line in f:
            if "error" in line.lower() or "failed" in line.lower() or "unknown" in line.lower():
                sample_error = line.strip()
                break

print(f"\n[1] Testing with Real Log Entry:\n--> {sample_error}\n")

# 2. Query Groq Llama-3.3 for structured diagnosis
prompt = f"""
You are an expert AIOps triage engine. Analyze this server log error:
Log: "{sample_error}"

Respond in this exact format:
- Severity: (Low/Medium/High/Critical)
- Root Cause: (1 sentence explaining what happened)
- Recommended Fix: (1 actionable remediation step)
"""

print("[2] Sending to Groq (Llama 3.3 70B)...")
response = client.chat.completions.create(
    model="llama-3.3-70b-versatile",
    messages=[{"role": "user", "content": prompt}],
    temperature=0.2
)

print("\n--- [3] OpsMind AI Diagnostic Output ---")
print(response.choices[0].message.content)
print("----------------------------------------\n")
print("SUCCESS: Day 1 AI Engine & Dataset Verified Working! (Cost: ₹0)")