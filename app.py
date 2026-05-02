import streamlit as st
import requests
import json

st.title("AI Laddering Survey")

# The 6 survey questions
context = st.text_area("1. What were you trying to do when you used an AI tool?")
tool = st.text_input("2. Which AI tool did you use?")
attribute = st.text_area("3. What specific feature or thing about it mattered to you?")
why1 = st.text_area("4. Why did that matter? What did it help you do?")
why2 = st.text_area("5. And why does that matter to you on a deeper level?")
value = st.text_area("6. What does that give you in life or work overall?")

if st.button("Submit"):
    api_key = st.secrets["OPENROUTER_API_KEY"]

    prompt = f"""
You are a market research analyst using means-end theory.
Classify these answers into the correct category.
Return ONLY a JSON object, no extra text.

Context: {context}
Tool used: {tool}
Attribute: {attribute}
Functional consequence: {why1}
Deeper consequence: {why2}
Value: {value}

Return this exact format:
{{
  "coded_attribute": "",
  "coded_functional_consequence": "",
  "coded_emotional_consequence": "",
  "coded_value": "",
  "short_ladder_summary": ""
}}
"""

    response = requests.post(
        "https://openrouter.ai/api/v1/chat/completions",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        },
        json={
            "model": "openrouter/auto",
            "messages": [{"role": "user", "content": prompt}]
        }
    )

    result = response.json()
    text = result["choices"][0]["message"]["content"]
    
    try:
        data = json.loads(text)
        st.subheader("Your Ladder")
        st.write("**Attribute:**", data["coded_attribute"])
        st.write("**Functional Consequence:**", data["coded_functional_consequence"])
        st.write("**Emotional Consequence:**", data["coded_emotional_consequence"])
        st.write("**Value:**", data["coded_value"])
        st.write("**Summary:**", data["short_ladder_summary"])
    except:
        st.error("Something went wrong. Raw response:")
        st.write(text)
