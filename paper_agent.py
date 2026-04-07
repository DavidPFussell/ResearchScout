import arxiv
import datetime
import os
import requests
from openai import OpenAI

# Configuration - Change your keywords here
KEYWORDS = '(cat:cs.CL OR cat:cs.LG OR cat:cs.AI OR cat:cs.MA)'
LLM_MODEL = "gpt-4.1-mini" # Fast and cheap

# Initialize OpenAI
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

def get_latest_papers():
    search = arxiv.Search(
        query=KEYWORDS,
        max_results=10,
        sort_by=arxiv.SortCriterion.SubmittedDate
    )
    
    today = datetime.datetime.now(datetime.timezone.utc).date()
    papers = []
    
    for result in search.results():
        # Check if the paper was published in the last 24-48 hours
        if result.published.date() >= (today - datetime.timedelta(days=1)):
            papers.append({
                "title": result.title,
                "summary": result.summary,
                "url": result.entry_id,
                "author": result.authors[0].name
            })
    return papers

def summarize_papers(papers):
    if not papers:
        return "No new papers found today."

    report = "### 🤖 Daily AI Research Report\n\n"
    
    for paper in papers:
        prompt = f"Summarize this AI research paper abstract in two sentences. Focus on the 'why it matters' and the 'key result'. \n\nAbstract: {paper['summary']}"
        
        response = client.chat.completions.create(
            model=LLM_MODEL,
            messages=[{"role": "user", "content": prompt}]
        )
        summary = response.choices[0].message.content
        
        report += f"**[{paper['title']}]({paper['url']})**\n"
        report += f"By: {paper['author']}\n"
        report += f"Summary: {summary}\n\n"
    
    return report

def send_to_slack(blocks):
    webhook_url = os.getenv("SLACK_WEBHOOK")
    if webhook_url and blocks:
        payload = {
            "username": "scout", # The name shown in the channel
            "icon_emoji": ":robot_face:",  # The avatar
            "blocks": blocks
        }
        response = requests.post(webhook_url, json=payload)
        if response.status_code != 200:
            print(f"Error: {response.text}")
            
if __name__ == "__main__":
    new_papers = get_latest_papers()
    if new_papers:
        final_report = summarize_papers(new_papers)
        send_to_slack(final_report)
    else:
        print("No new papers to report.")
