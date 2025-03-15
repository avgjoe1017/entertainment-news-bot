from flask import Flask, jsonify
import feedparser
import threading
import time
import logging

app = Flask(__name__)

# Entertainment news sources
RSS_FEEDS = {
    "New York Times": "https://rss.nytimes.com/services/xml/rss/nyt/Movies.xml",
    "BBC": "http://feeds.bbci.co.uk/news/entertainment_and_arts/rss.xml",
    "Hollywood Reporter": "https://www.hollywoodreporter.com/t/entertainment/feed/",
    "Variety": "https://variety.com/feed/",
    "TMZ": "https://www.tmz.com/rss.xml",
    "Deadline": "https://deadline.com/feed/",
    "People": "https://people.com/feed/",
    "E! Online": "https://www.eonline.com/news/rss",
    "Entertainment Weekly": "https://ew.com/feed/",
    "IGN": "https://www.ign.com/articles?format=rss",
    "CNET": "https://www.cnet.com/rss/news/"
}

# Store latest articles
latest_articles = []

def fetch_news():
    global latest_articles
    while True:
        articles = []
        for source, url in RSS_FEEDS.items():
            try:
                feed = feedparser.parse(url)
                for entry in feed.entries[:5]:
                    articles.append({
                        "title": entry.title,
                        "link": entry.link,
                        "source": source,
                        "published": entry.get("published", "Unknown"),
                        "summary": entry.get("summary", "No summary available.")
                    })
            except Exception as e:
                logging.error(f"Error fetching {source}: {e}")

        latest_articles = articles
        logging.info("News updated.")
        time.sleep(15)  # Fetch every 15 seconds

@app.route('/rss', methods=['GET'])
def get_news():
    return jsonify({
        "status": "success",
        "updated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "articles": latest_articles
    })

if __name__ == '__main__':
    threading.Thread(target=fetch_news, daemon=True).start()
    app.run(host="0.0.0.0", port=10000)
