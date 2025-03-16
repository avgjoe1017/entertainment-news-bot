import nltk
from nltk.sentiment import SentimentIntensityAnalyzer
import logging

logger = logging.getLogger(__name__)

sia = SentimentIntensityAnalyzer()

def calculate_sentiment(text):
    try:
        sentiment = sia.polarity_scores(text)
        if sentiment['compound'] >= 0.05:
            return "positive"
        elif sentiment['compound'] <= -0.05:
            return "negative"
        else:
            return "neutral"
    except Exception as e:
        logger.error(f"Sentiment calculation error: {str(e)}")
        return "neutral"
