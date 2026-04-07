import arxiv
import datetime
import os
import requests
import json
import feedparser
import re
from openai import OpenAI

# --- Configuration ---
# Exclude computer vision (CV) and image generation (IG)
NEG_KEYWORDS = " -vision -image -video -diffusion -generative-art -cv"
ARXIV_QUERY = f'(cat:cs.CL OR cat:cs.LG OR cat:cs.AI){NEG_KEYWORDS}'
# Specific GitHub query for LLMs, Agents, and NLP
GITHUB_QUERY = f'topic:llm OR topic:agents OR topic:nlp OR topic:rag{NEG_KEYWORDS}'
NEWS_RSS = f"https://news.google.com/rss/search?q=AI+LLM+OR+Agents+OR+NLP+-vision+-image+-video+-diffusion&hl=en-US&gl=US&ceid=US:en"
LLM_MODEL = "gpt-4.1-mini"

client_ai = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

def detect_code_link(text):
    match = re.search(r'github\.com/[\w\-/]+', text)
    return f"https://{match.group(0)}" if match else None

# --- Source Fetchers ---
def get_arxiv_papers():
    print("Fetching ArXiv (NLP/LLM focus)...")
    client = arxiv.Client(page_size=25, delay_seconds=3.0, num_retries=5)
    search = arxiv.Search(query=ARXIV_QUERY, max_results=25, sort_by=arxiv.SortCriterion.SubmittedDate)
    return [{"title": r.title, "desc": r.summary[:500], "url": r.entry_id, "code_url": detect_code_link(r.summary)} for r in client.results(search)]

def get_hf_papers():
    print("Fetching Hugging Face...")
    try:
        response = requests.get("https://huggingface.co/api/papers", timeout=10)
        # HF doesn't support negative keywords in API, so we filter manually
        ignore = ['vision', 'image', 'video', 'diffusion', 'depth', 'segmentation']
        return [{"title": x['title'], "desc": "Trending on HF.", "url": f"https://huggingface.co/papers/{x['id']}", "code_url": None} 
                for x in response.json() if not any(word in x['title'].lower() for word in ignore)][:15]
    except Exception as e: print(f"HF Error: {e}"); return []

def get_github_trending():
    print("Fetching GitHub (Authenticated)...")
    token = os.getenv("GITHUB_TOKEN")
    headers = {"Authorization": f"token {token}"} if token else {}
    
    yesterday = (datetime.datetime.now() - datetime.timedelta(days=2)).strftime('%Y-%m-%d')
    url = f"https://api.github.com/search/repositories?q={GITHUB_QUERY}+pushed:>{yesterday}&sort=stars&order=desc"
    
    try:
        response = requests.get(url, headers=headers, timeout=10)
        if response.status_code == 403:
            print("GitHub Rate Limited. Try again later.")
            return []
        items = response.json().get('items', [])
        return [{"title": x['full_name'], "desc": x.get('description', ''), "url": x['html_url'], "code_url": x['html_url']} for x in items[:15]]
    except Exception as e: print(f"GitHub Error: {e}"); return []

def get_ai_news():
    print("Fetching News (No images/video)...")
    try:
        feed = feedparser.parse(NEWS_RSS)
        return [{"title": x.title, "desc": "NLP/LLM industry news.", "url": x.link, "code_url": None} for x in feed.entries[:15]]
    except Exception as e: print(f"News Error: {e}"); return []

# --- THE BRAIN ---
def process_source(source_name, items):
    if not items: return []
    print(f"Brain is filtering and ranking {source_name}...")
    
    input_data = [{"id": i, "title": item['title'], "desc": item['desc'][:300]} for i, item in enumerate(items)]

    prompt = f"""
    You are an AI Research Scout focusing EXCLUSIVELY on NLP, LLMs, Multi-Agent Systems, and RAG.
    
    STRICT RULE: Ignore any item related to:
    - Computer Vision
    - Image Generation (Stable Diffusion, Midjourney, etc.)
    - Video Generation (Sora, etc.)
    - Medical Imaging
    
    Pick the top 5 relevant items from this {source_name} list.
    Return JSON only: {{"selections": [{{"id": 0, "summary": "...", "hype": 1-10, "cat": "tag"}}, ...]}}
    """

    try:
        response = client_ai.chat.completions.create(
            model=LLM_MODEL,
            messages=[{"role": "system", "content": "Professional NLP researcher. JSON only."},
                      {"role": "user", "content": f"{prompt}\n\nData: {json.dumps(input_data)}"}],
            response_format={ "type": "json_object" }
        )
        
        raw_data = json.loads(response.choices[0].message.content)
        selections = raw_data.get('selections', [])
        
        blocks = [{"type": "section", "text": {"type": "mrkdwn", "text": f"*--- TOP 5 {source_name.upper()} ---*"}}]
        for sel in selections:
            item = items[int(sel['id'])]
            score = int(sel['hype'])
            hype_emoji = "🚀" if score >= 8 else "📈"
            code_text = f" | 💻 <{item['code_url']}|*Code*>" if item['code_url'] else ""
            blocks.append({
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"`{sel['cat']}` {hype_emoji} *Hype: {score}/10*{code_text}\n*<{item['url']}|{item['title']}>*\n{sel['summary']}"
                }
            })
        return blocks
    except Exception: return []

def send_to_slack(all_blocks):
    url = os.getenv("SLACK_WEBHOOK")
    if url: 
        # Send in chunks of 30 blocks to stay under Slack's limit
        for i in range(0, len(all_blocks), 30):
            requests.post(url, json={"blocks": all_blocks[i:i+30]})

if __name__ == "__main__":
    final_blocks = [{"type": "header", "text": {"type": "plain_text", "text": "🧠 NLP & LLM Scout: Top 20"}}]
    sources = {
        "ArXiv Papers": get_arxiv_papers(),
        "Hugging Face": get_hf_papers(),
        "GitHub Repos": get_github_trending(),
        "Industry News": get_ai_news()
    }
    for name, data in sources.items():
        res = process_source(name, data)
        if res:
            final_blocks.extend(res)
            final_blocks.append({"type": "divider"})
    if len(final_blocks) > 1: send_to_slack(final_blocks)
