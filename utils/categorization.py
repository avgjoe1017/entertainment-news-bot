import hashlib
import re

CATEGORIES = {
    "Movies": ["movie", "film", "cinema", "box office", "hollywood", "director", "actor", "actress", "oscars", "academy awards"],
    "TV": ["tv", "television", "show", "series", "episode", "streaming", "netflix", "hulu", "disney+", "hbo", "amazon prime"],
    "Music": ["music", "song", "album", "artist", "concert", "tour", "singer", "band", "grammy", "billboard"],
    "Celebrity": ["celebrity", "star", "famous", "gossip", "divorce", "wedding", "relationship", "red carpet"],
    "Gaming": ["game", "gaming", "playstation", "xbox", "nintendo", "console", "pc gaming", "esports"],
    "Tech": ["tech", "technology", "gadget", "apple", "iphone", "android", "samsung", "device"]
}

BREAKING_KEYWORDS = [
    "breaking", "urgent", "just in", "alert", "exclusive", "update"
]

def detect_categories(text):
    text = text.lower()
    categories = []
    for category, keywords in CATEGORIES.items():
        if any(keyword in text for keyword in keywords):
            categories.append(category)
    return categories or ["General"]

def is_breaking_news(title, summary):
    combined_text = (title + " " + summary).lower()
    return any(keyword in combined_text for keyword in BREAKING_KEYWORDS)

def generate_article_hash(title, link):
    content = (title + link).encode('utf-8')
    return hashlib.md5(content).hexdigest()

def extract_image_url(entry):
    try:
        if hasattr(entry, 'media_content') and entry.media_content:
            return entry.media_content[0].get('url')
        if hasattr(entry, 'enclosures') and entry.enclosures:
            return entry.enclosures[0].get('href')
        return None
    except:
        return None
