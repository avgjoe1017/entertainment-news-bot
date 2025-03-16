from datetime import datetime
import logging

logger = logging.getLogger(__name__)

def update_trending_score(articles):
    trending_articles = []
    current_time = datetime.now()

    for article in articles:
        try:
            pub_date = datetime.strptime(article['published_date'], '%Y-%m-%d %H:%M:%S')
            hours_ago = (current_time - pub_date).total_seconds() / 3600

            time_score = max(1, 10 - int(hours_ago / 3))
            source_bonus = 1.5 if "New York Times" in article['source'] or "BBC" in article['source'] else 1.0
            breaking_bonus = 3.0 if article['breaking_news'] else 1.0

            article['trending_score'] = time_score * source_bonus * breaking_bonus
            return article

        except Exception as e:
            logger.error(f"Error calculating trending score: {str(e)}")
            article['trending_score'] = 0
            return article
