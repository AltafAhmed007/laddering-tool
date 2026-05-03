import streamlit as st
import requests
import json
import gspread
from google.oauth2.service_account import Credentials
import networkx as nx
import matplotlib.pyplot as plt
from collections import defaultdict

def get_sheet():
    creds = Credentials.from_service_account_info(
        st.secrets["gcp_service_account"],
        scopes=["https://www.googleapis.com/auth/spreadsheets",
                "https://www.googleapis.com/auth/drive"]
    )
    client = gspread.authorize(creds)
    return client.open_by_key(st.secrets["SHEET_ID"]).sheet1

page = st.sidebar.radio("Go to", ["Survey", "Value Map (HVM)"])

if page == "Survey":
    st.title("Eating Out Survey")
    st.write("Think about the last time you ate outside of home.")

    attribute = st.text_area("1. Think of the most recent time you ate outside of home. What specifically made you choose that meal?")
    why1      = st.text_area("2. Why did that matter — what did it do for you?")
    value     = st.text_area("3. What did that give you — in that moment or that day?")

    if st.button("Submit"):

        prompt = f"""
You are a market research analyst using means-end theory.
Classify these answers about eating outside of home. Return ONLY a JSON object, no extra text, no markdown.

Attribute (what they chose): {attribute}
Consequence (why it mattered): {why1}
Value (what it gives them in life): {value}

Return exactly this format:
{{
  "coded_attribute": "",
  "coded_functional_consequence": "",
  "coded_emotional_consequence": "",
  "coded_value": "",
  "short_ladder_summary": ""
}}
"""

        response = requests.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {st.secrets['GROQ_API_KEY']}",
                "Content-Type": "application/json"
            },
            json={
                "model": "llama-3.3-70b-versatile",
                "messages": [{"role": "user", "content": prompt}]
            }
        )

        result = response.json()

        if "choices" not in result:
            st.error("API did not return a valid response.")
            st.write(result)
            st.stop()

        text = result["choices"][0]["message"]["content"]
        text = text.strip()
        if text.startswith("```"):
            text = text.split("```")[1]
            if text.startswith("json"):
                text = text[4:]
        text = text.strip()

        try:
            data = json.loads(text)
        except:
            st.error("Could not read the AI response as JSON.")
            st.write(text)
            st.stop()

        st.subheader("Your Ladder")
        st.write("**Attribute:**",              data["coded_attribute"])
        st.write("**Functional Consequence:**", data["coded_functional_consequence"])
        st.write("**Emotional Consequence:**",  data["coded_emotional_consequence"])
        st.write("**Value:**",                  data["coded_value"])
        st.write("**Summary:**",                data["short_ladder_summary"])

        try:
            sheet = get_sheet()
            sheet.append_row([
                attribute, why1, value,
                data["coded_attribute"],
                data["coded_functional_consequence"],
                data["coded_emotional_consequence"],
                data["coded_value"],
                data["short_ladder_summary"]
            ])
            st.success("Response saved.")
        except Exception as e:
            st.warning(f"Ladder displayed but could not save to Google Sheets: {e}")

elif page == "Value Map (HVM)":
    st.title("Hierarchical Value Map")

    cutoff = st.slider("Minimum connections to show a link", 1, 10, 1)

    try:
        sheet = get_sheet()
        rows  = sheet.get_all_records()
    except Exception as e:
        st.error(f"Could not load data: {e}")
        st.stop()

    if len(rows) == 0:
        st.warning("No responses yet. Complete some surveys first.")
    else:
        edge_counts  = defaultdict(int)
        node_layer   = {}  # track which layer each node belongs to

        for row in rows:
            a  = row.get("coded_attribute", "").strip()
            fc = row.get("coded_functional_consequence", "").strip()
            ec = row.get("coded_emotional_consequence", "").strip()
            v  = row.get("coded_value", "").strip()

            if a:  node_layer[a]  = 0  # bottom
            if fc: node_layer[fc] = 1
            if ec: node_layer[ec] = 2
            if v:  node_layer[v]  = 3  # top

            if a and fc:  edge_counts[(a, fc)]  += 1
            if fc and ec: edge_counts[(fc, ec)] += 1
            if ec and v:  edge_counts[(ec, v)]  += 1

        # Filter by cutoff
        filtered_edges = {(s, t): c for (s, t), c in edge_counts.items() if c >= cutoff}

        # Only keep nodes that appear in filtered edges
        active_nodes = set()
        for s, t in filtered_edges:
            active_nodes.add(s)
            active_nodes.add(t)

        if len(active_nodes) == 0:
            st.info(f"No connections appear {cutoff}+ times. Lower the slider.")
        else:
            # Group nodes by layer
            layers = {0: [], 1: [], 2: [], 3: []}
            for node in active_nodes:
                layer = node_layer.get(node, 1)
                layers[layer].append(node)

            # Build positions — pyramid layout
            pos = {}
            layer_labels = {0: "ATTRIBUTES", 1: "FUNCTIONAL CONSEQUENCES",
                            2: "EMOTIONAL CONSEQUENCES", 3: "VALUES"}
            y_positions = {0: 0, 1: 1.5, 2: 3, 3: 4.5}

            for layer_num, nodes in layers.items():
                nodes = sorted(nodes)
                n = len(nodes)
                for i, node in enumerate(nodes):
                    x = (i - (n - 1) / 2) * 2.5
                    y = y_positions[layer_num]
                    pos[node] = (x, y)

            # Build graph
            G = nx.DiGraph()
            for (s, t), c in filtered_edges.items():
                G.add_edge(s, t, weight=c)

            # Draw
            fig, ax = plt.subplots(figsize=(16, 10))
            fig.patch.set_facecolor("#f9f9f9")
            ax.set_facecolor("#f9f9f9")

            # Color by layer
            node_colors = []
            for node in G.nodes():
                layer = node_layer.get(node, 1)
                if layer == 0:   node_colors.append("#4A90D9")   # blue — attributes
                elif layer == 1: node_colors.append("#5BA85A")   # green — functional
                elif layer == 2: node_colors.append("#E8A838")   # orange — emotional
                else:            node_colors.append("#C0392B")   # red — values

            weights = [G[u][v]["weight"] for u, v in G.edges()]
            max_w   = max(weights) if weights else 1

            nx.draw_networkx_nodes(G, pos, node_size=3000,
                                   node_color=node_colors, alpha=0.95, ax=ax)
            nx.draw_networkx_edges(G, pos,
                                   width=[1 + (w / max_w) * 6 for w in weights],
                                   edge_color="#888888", arrows=True,
                                   arrowsize=25, ax=ax,
                                   connectionstyle="arc3,rad=0.05")
            # Full labels with word wrap
            labels = {node: "\n".join([node[i:i+15] for i in range(0, len(node), 15)])
                      for node in G.nodes()}
            nx.draw_networkx_labels(G, pos, labels=labels,
                                    font_size=7, font_color="white",
                                    font_weight="bold", ax=ax)
            edge_labels = {(u, v): G[u][v]["weight"] for u, v in G.edges()}
            nx.draw_networkx_edge_labels(G, pos, edge_labels=edge_labels,
                                         font_size=8, ax=ax)

            # Layer labels on left side
            for layer_num, label in layer_labels.items():
                if layers[layer_num]:
                    ax.text(-0.02, y_positions[layer_num], label,
                            transform=ax.get_yaxis_transform(),
                            fontsize=8, color="#555555",
                            verticalalignment="center", fontstyle="italic")

            ax.set_title("Hierarchical Value Map — Eating Outside Home",
                         fontsize=14, fontweight="bold", pad=20)
            ax.axis("off")
            plt.tight_layout()
            st.pyplot(fig)

            # Legend
            st.markdown("""
            🔵 **Attribute** → 🟢 **Functional Consequence** → 🟠 **Emotional Consequence** → 🔴 **Value**  
            *Line thickness = how many people share that connection*
            """)

        st.write(f"Based on **{len(rows)} responses** | Showing links appearing **{cutoff}+** times")
