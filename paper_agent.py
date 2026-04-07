import arxiv
import datetime
import os
import requests
import json
import feedparser
import re
from openai import OpenAI

# --- Configuration ---
ARXIV_KEYWORDS = '(cat:cs.CL OR cat:cs.LG OR cat:cs.AI)'
GITHUB_QUERY = 'topic:machine-learning OR topic:llm OR topic:ai'
NEWS_RSS = "https://news.google.com/rss/search?q=Artificial+Intelligence+when:24h&hl=en-US&gl=US&ceid=US:en"
LLM_MODEL = "gpt-4.1-mini"

client_ai = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# --- Helper: Code Detector ---
def detect_code_link(text):
    """Simple regex to find github links in abstracts/descriptions"""
    match = re.search(r'github\.com/[\w\-/]+', text)
    return f"https://{match.group(0)}" if match else None

# --- Source 1: ArXiv ---
def get_arxiv_papers():
    print("Fetching ArXiv...")
    client = arxiv.Client(page_size=15, delay_seconds=3.0, num_retries=5)
    search = arxiv.Search(query=ARXIV_KEYWORDS, max_results=15, sort_by=arxiv.SortCriterion.SubmittedDate)
    
    today = datetime.datetime.now(datetime.timezone.utc).date()
    papers = []
    try:
        for result in client.results(search):
            if result.published.date() >= (today - datetime.timedelta(days=2)):
                code_url = detect_code_link(result.summary)
                papers.append({
                    "source": "ArXiv",
                    "title": result.title,
                    "desc": result.summary[:500],
                    "url": result.entry_id,
                    "code_url": code_url
                })
    except Exception as e: print(f"ArXiv Error: {e}")
    return papers

# --- Source 2: Hugging Face ---
def get_hf_papers():
    print("Fetching Hugging Face...")
    try:
        response = requests.get("https://huggingface.co/api/papers", timeout=10)
        data = response.json()
        hf_papers = []
        for entry in data[:8]:
            hf_papers.append({
                "source": "Hugging Face",
                "title": entry.get('title', 'Untitled'),
                "desc": "Trending on HF community.",
                "url": f"https://huggingface.co/papers/{entry.get('id')}",
                "code_url": None # HF usually links code on the landing page
            })
        return hf_papers
    except Exception as e: print(f"HF Error: {e}"); return []

# --- Source 3: GitHub ---
def get_github_trending():
    print("Fetching GitHub...")
    yesterday = (datetime.datetime.now() - datetime.timedelta(days=2)).strftime('%Y-%m-%d')
    url = f"https://api.github.com/search/repositories?q={GITHUB_QUERY}+pushed:>{yesterday}&sort=stars&order=desc"
    try:
        response = requests.get(url, timeout=10)
        data = response.json()
        return [{
            "source": "GitHub",
            "title": item['full_name'],
            "desc": item.get('description') or "AI Repo",
            "url": item['html_url'],
            "code_url": item['html_url'] # It's already code
        } for item in data.get('items', [])[:8]]
    except Exception as e: print(f"GitHub Error: {e}"); return []

# --- Source 4: AI News ---
def get_ai_news():
    print("Fetching AI News...")
    try:
        feed = feedparser.parse(NEWS_RSS)
        news_items = []
        for entry in feed.entries[:8]:
            news_items.append({
                "source": "News",
                "title": entry.title,
                "desc": "Daily news update.",
                "url": entry.link,
                "code_url": None
            })
        return news_items
    except Exception as e: print(f"News Error: {e}"); return []

# --- THE BRAIN: Rank, Hype, & Summarize ---
def summarize_and_rank(all_items):
    if not all_items: return None

    print(f"Brain is analyzing {len(all_items)} items...")
    
    input_data = [{"id": i, "title": item['title'], "source": item['source'], "desc": item['desc'][:300]} 
                  for i, item in enumerate(all_items)]

    prompt = """
    Rank these AI items. Return a JSON object with a 'selections' key containing the top 6 items.
    For each selection:
    1. 'id': original ID
    2. 'summary': 1-sentence punchy summary.
    3. 'hype_score': 1 to 10 rating of how 'game-changing' this is.
    4. 'category': Short tag (e.g., 'LLM', 'Vision', 'News', 'Tool').
    """

    try:
        response = client_ai.chat.completions.create(
            model=LLM_MODEL,
            messages=[{"role": "system", "content": "You are a senior AI researcher. Output JSON only."},
                      {"role": "user", "content": f"{prompt}\n\nData: {json.dumps(input_data)}"}],
            response_format={ "type": "json_object" }
        )
        
        raw_data = json.loads(response.choices[0].message.content)
        selections = raw_data.get('selections', [])

        blocks = [
            {"type": "header", "text": {"type": "plain_text", "text": "🔥 Elite AI Scout Report"}},
            {"type": "divider"}
        ]

        for sel in selections:
            item = all_items[int(sel['id'])]
            
            # Hype Emoji Logic
            score = int(sel['hype_score'])
            hype_emoji = "🚀" if score >= 8 else "📈" if score >= 5 else "☕"
            
            code_text = f" | 💻 <{item['code_url']}|*Code Available*>" if item['code_url'] else ""
            
            blocks.append({
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*{item['source']}* | `{sel['category']}` | {hype_emoji} *Hype: {score}/10*{code_text}\n*<{item['url']}|{item['title']}>*\n{sel['summary']}"
                }
            })
        
        return blocks
    except Exception as e: print(f"Brain Error: {e}"); return None

def send_to_slack(blocks):
    webhook_url = os.getenv("SLACK_WEBHOOK")
    if webhook_url: requests.post(webhook_url, json={"blocks": blocks})

if __name__ == "__main__":
    findings = []
    findings.extend(get_arxiv_papers())
    findings.extend(get_hf_papers())
    findings.extend(get_github_trending())
    findings.extend(get_ai_news())

    if findings:
        report = summarize_and_rank(findings)
        if report: send_to_slack(report)
    print("Scout mission complete.")
