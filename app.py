import streamlit as st
import requests
import json
import gspread
from google.oauth2.service_account import Credentials
import networkx as nx
import matplotlib.pyplot as plt
from collections import defaultdict

# ── Connect to Google Sheets ──────────────────────────────────────────────────

def get_sheet():
    creds = Credentials.from_service_account_info(
        st.secrets["gcp_service_account"],
        scopes=["https://www.googleapis.com/auth/spreadsheets",
                "https://www.googleapis.com/auth/drive"]
    )
    client = gspread.authorize(creds)
    return client.open_by_key(st.secrets["SHEET_ID"]).sheet1

# ── Page selector ─────────────────────────────────────────────────────────────

page = st.sidebar.radio("Go to", ["Survey", "Value Map (HVM)"])

# ══════════════════════════════════════════════════════════════════════════════
# PAGE 1 — SURVEY
# ══════════════════════════════════════════════════════════════════════════════

if page == "Survey":
    st.title("AI Laddering Survey")

    context   = st.text_area("1. What were you trying to do when you used an AI tool?")
    tool      = st.text_input("2. Which AI tool did you use?")
    attribute = st.text_area("3. What specific feature or thing about it mattered to you?")
    why1      = st.text_area("4. Why did that matter? What did it help you do?")
    why2      = st.text_area("5. And why does that matter to you on a deeper level?")
    value     = st.text_area("6. What does that give you in life or work overall?")

    if st.button("Submit"):

        # Send to OpenRouter for coding
        prompt = f"""
You are a market research analyst using means-end theory.
Classify these answers. Return ONLY a JSON object, no extra text.

Context: {context}
Tool used: {tool}
Attribute: {attribute}
Functional consequence: {why1}
Deeper consequence: {why2}
Value: {value}

Return exactly:
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
                "Authorization": f"Bearer {st.secrets['OPENROUTER_API_KEY']}",
                "Content-Type": "application/json"
            },
            json={
                "model": "qwen/qwen-2.5-7b-instruct:free",
                "messages": [{"role": "user", "content": prompt}]
            }
        )

        result = response.json()
        # Temporary: show the raw API response so we can see what went wrong
        st.write("Raw API response:", result)

        if "choices" not in result:
            st.error("OpenRouter did not return a valid response. See raw response above.")
            st.stop()

        text = result["choices"][0]["message"]["content"]

        try:
            data = json.loads(text)

            # Show result to user
            st.subheader("Your Ladder")
            st.write("**Attribute:**",               data["coded_attribute"])
            st.write("**Functional Consequence:**",  data["coded_functional_consequence"])
            st.write("**Emotional Consequence:**",   data["coded_emotional_consequence"])
            st.write("**Value:**",                   data["coded_value"])
            st.write("**Summary:**",                 data["short_ladder_summary"])

            # Save to Google Sheets
            sheet = get_sheet()
            sheet.append_row([
                context, tool, attribute, why1, why2, value,
                data["coded_attribute"],
                data["coded_functional_consequence"],
                data["coded_emotional_consequence"],
                data["coded_value"],
                data["short_ladder_summary"]
            ])
            st.success("Response saved.")

        except:
            st.error("Something went wrong. Raw response:")
            st.write(text)

# ══════════════════════════════════════════════════════════════════════════════
# PAGE 2 — HVM
# ══════════════════════════════════════════════════════════════════════════════

elif page == "Value Map (HVM)":
    st.title("Hierarchical Value Map")

    # Minimum number of people who must share a connection for it to appear
    cutoff = st.slider("Minimum connections to show a link", 1, 10, 2)

    sheet = get_sheet()
    rows  = sheet.get_all_records()  # Each row = one survey response

    if len(rows) == 0:
        st.warning("No responses yet. Complete some surveys first.")
    else:
        # Count how often each connection appears
        edge_counts = defaultdict(int)

        for row in rows:
            a  = row.get("coded_attribute", "").strip()
            fc = row.get("coded_functional_consequence", "").strip()
            ec = row.get("coded_emotional_consequence", "").strip()
            v  = row.get("coded_value", "").strip()

            # Only count a connection if both ends have a label
            if a and fc:
                edge_counts[(a, fc)] += 1
            if fc and ec:
                edge_counts[(fc, ec)] += 1
            if ec and v:
                edge_counts[(ec, v)] += 1

        # Build the network
        G = nx.DiGraph()

        for (source, target), count in edge_counts.items():
            if count >= cutoff:
                G.add_edge(source, target, weight=count)

        if len(G.edges()) == 0:
            st.info(f"No connections appear {cutoff}+ times yet. Try lowering the slider or adding more responses.")
        else:
            # Draw the map
            fig, ax = plt.subplots(figsize=(12, 7))

            pos    = nx.spring_layout(G, seed=42, k=2)
            weights = [G[u][v]["weight"] for u, v in G.edges()]

            nx.draw_networkx_nodes(G, pos, node_size=2000,
                                   node_color="steelblue", alpha=0.9, ax=ax)
            nx.draw_networkx_labels(G, pos, font_size=8,
                                    font_color="white", ax=ax)
            nx.draw_networkx_edges(G, pos, width=[w * 1.5 for w in weights],
                                   edge_color="gray", arrows=True,
                                   arrowsize=20, ax=ax)
            edge_labels = {(u, v): G[u][v]["weight"] for u, v in G.edges()}
            nx.draw_networkx_edge_labels(G, pos, edge_labels=edge_labels,
                                         font_size=7, ax=ax)

            ax.set_title("Attribute → Consequence → Value Map", fontsize=14)
            ax.axis("off")
            st.pyplot(fig)

        st.write(f"Based on **{len(rows)} responses**")
