import feedparser
import requests
import hashlib
import logging
from datetime import datetime
from .sentiment_analysis import calculate_sentiment
from .categorization import detect_categories, is_breaking_news, generate_article_hash, extract_image_url

logger = logging.getLogger(__name__)

def fetch_rss_feed(source_name, feed_url, session):
    try:
        response = session.get(feed_url, timeout=10)
        response.raise_for_status()
        feed = feedparser.parse(response.content)
        
        articles = []
        for entry in feed.entries[:15]:
            published = entry.get('published', datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
            summary = entry.get('summary', entry.get('description', ''))
            summary_text = summary[:250] + '...' if len(summary) > 250 else summary

            full_text = entry.title + " " + summary_text
            article_hash = generate_article_hash(entry.title, entry.link)
            image_url = extract_image_url(entry)
            breaking = is_breaking_news(entry.title, summary_text)
            sentiment = calculate_sentiment(full_text)
            categories = detect_categories(full_text)

            article = {
                'id': article_hash,
                'title': entry.title,
                'link': entry.link,
                'source': source_name,
                'published_date': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'summary': summary_text,
                'sentiment': sentiment,
                'categories': categories,
                'breaking_news': breaking,
                'image_url': image_url,
                'popularity': 0
            }
            return article
    except Exception as e:
        logger.error(f"Error fetching {source_name}: {str(e)}")
        return None
