import os
import time
import re
import logging
import threading
import requests
import feedparser
import hashlib
import json
import nltk
from nltk.sentiment import SentimentIntensityAnalyzer
from datetime import datetime, timedelta
from flask import Flask, jsonify, request, render_template, send_from_directory
from flask_cors import CORS
from requests.adapters import HTTPAdapter
from requests.packages.urllib3.util.retry import Retry
from collections import Counter

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

# Initialize Flask app
app = Flask(__name__, static_folder='static', template_folder='templates')
CORS(app)  # Enable CORS for all routes

# Download NLTK resources
try:
    nltk.download('vader_lexicon', quiet=True)
except Exception as e:
    logging.error(f"Error downloading NLTK resources: {str(e)}")

# Initialize Redis if available
redis_client = None
try:
    redis_url = os.environ.get('REDIS_URL')
    if redis_url:
        from redis import Redis
        redis_client = Redis.from_url(redis_url, decode_responses=True)
        logging.info("Redis connection established")
    else:
        logging.info("No Redis URL provided, using in-memory cache")
except Exception as e:
    logging.warning(f"Could not connect to Redis: {str(e)}")

# Initialize sentiment analyzer
sia = SentimentIntensityAnalyzer()

# RSS feed sources
RSS_FEEDS = {
    "New York Times Entertainment": "https://rss.nytimes.com/services/xml/rss/nyt/Movies.xml",
    "BBC Entertainment": "http://feeds.bbci.co.uk/news/entertainment_and_arts/rss.xml",
    "Hollywood Reporter": "https://www.hollywoodreporter.com/t/entertainment/feed/",
    "Variety": "https://variety.com/feed/",
    "TMZ Celebrity News": "https://www.tmz.com/rss.xml",
    "Deadline Hollywood": "https://deadline.com/feed/",
    "People Magazine Entertainment": "https://people.com/feed/",
    "E! Online News": "https://www.eonline.com/news/rss",
    "Entertainment Weekly": "https://ew.com/feed/",
    "IGN Movies & TV": "https://www.ign.com/articles?format=rss",
    "CNET Entertainment": "https://www.cnet.com/rss/news/"
}

# Cache to store the latest results
feed_cache = []
trending_cache = []
source_stats = {}
category_cache = {}
health_status = {"last_successful_update": None, "failed_sources": {}}
duplicate_count = 0
cache_lock = threading.Lock()

# Constants for article categorization and processing
CATEGORIES = {
    "Movies": ["movie", "film", "cinema", "box office", "hollywood", "director", "actor", "actress", "oscars", "academy awards"],
    "TV": ["tv", "television", "show", "series", "episode", "streaming", "netflix", "hulu", "disney+", "hbo", "amazon prime"],
    "Music": ["music", "song", "album", "artist", "concert", "tour", "singer", "band", "grammy", "billboard"],
    "Celebrity": ["celebrity", "star", "famous", "gossip", "divorce", "wedding", "relationship", "red carpet"],
    "Gaming": ["game", "gaming", "playstation", "xbox", "nintendo", "console", "pc gaming", "esports"],
    "Tech": ["tech", "technology", "gadget", "apple", "iphone", "android", "samsung", "device"]
}

# Breaking news keywords
BREAKING_KEYWORDS = [
    "breaking", "urgent", "just in", "alert", "developing story", "breaking news", 
    "exclusive", "update", "emergency", "crisis", "just announced", "happening now"
]

# Custom HTTP headers to avoid being blocked
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
    'Accept-Language': 'en-US,en;q=0.5',
    'Connection': 'keep-alive',
    'Upgrade-Insecure-Requests': '1',
    'Cache-Control': 'max-age=0'
}

def get_session():
    """Create a requests session with retry strategy"""
    session = requests.Session()
    retry = Retry(
        total=3,
        backoff_factor=0.5,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["GET"]
    )
    adapter = HTTPAdapter(max_retries=retry)
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    session.headers.update(HEADERS)
    return session

def detect_categories(text):
    """Categorize an article based on its content"""
    text = text.lower()
    categories = []
    
    for category, keywords in CATEGORIES.items():
        for keyword in keywords:
            if keyword.lower() in text:
                categories.append(category)
                break
    
    return list(set(categories)) or ["General"]

def calculate_sentiment(text):
    """Calculate sentiment score for text"""
    try:
        sentiment = sia.polarity_scores(text)
        if sentiment['compound'] >= 0.05:
            return "positive"
        elif sentiment['compound'] <= -0.05:
            return "negative"
        else:
            return "neutral"
    except Exception as e:
        logger.error(f"Error calculating sentiment: {str(e)}")
        return "neutral"

def is_breaking_news(title, summary):
    """Detect if an article is breaking news"""
    combined_text = (title + " " + summary).lower()
    for keyword in BREAKING_KEYWORDS:
        if keyword.lower() in combined_text:
            return True
    return False

def generate_article_hash(title, link):
    """Generate a unique hash for article deduplication"""
    content = (title + link).encode('utf-8')
    return hashlib.md5(content).hexdigest()

def extract_image_url(entry):
    """Extract image URL from an RSS entry"""
    try:
        # Try to get media content
        if hasattr(entry, 'media_content') and entry.media_content:
            for media in entry.media_content:
                if 'url' in media:
                    return media['url']
        
        # Try to get enclosures
        if hasattr(entry, 'enclosures') and entry.enclosures:
            for enclosure in entry.enclosures:
                if 'href' in enclosure and (enclosure.get('type', '').startswith('image/') or 
                                           enclosure.get('type', '').startswith('image')):
                    return enclosure.href
        
        # Try to find image in content
        if hasattr(entry, 'content') and entry.content:
            content = entry.content[0].value
            img_match = re.search(r'<img[^>]+src="([^">]+)"', content)
            if img_match:
                return img_match.group(1)
        
        # Try to find image in summary/description
        for attr in ['summary', 'description']:
            if hasattr(entry, attr):
                content = getattr(entry, attr)
                img_match = re.search(r'<img[^>]+src="([^">]+)"', content)
                if img_match:
                    return img_match.group(1)
    
    except Exception as e:
        logger.error(f"Error extracting image URL: {str(e)}")
    
    return None

def fetch_rss_feed(source_name, feed_url, session):
    """Fetch and parse an RSS feed with enhanced processing"""
    global health_status
    
    try:
        response = session.get(feed_url, timeout=10)
        response.raise_for_status()
        
        feed = feedparser.parse(response.content)
        
        # Check if the feed was successfully parsed
        if not feed.entries:
            logger.warning(f"No entries found in feed: {source_name}")
            health_status["failed_sources"][source_name] = "No entries found"
            return []
            
        articles = []
        for entry in feed.entries[:15]:  # Get top 15 articles per feed for better coverage
            # Extract the published date with fallback options
            published = None
            if hasattr(entry, 'published_parsed') and entry.published_parsed:
                published = time.strftime('%Y-%m-%d %H:%M:%S', entry.published_parsed)
            elif hasattr(entry, 'updated_parsed') and entry.updated_parsed:
                published = time.strftime('%Y-%m-%d %H:%M:%S', entry.updated_parsed)
            else:
                published = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            
            # Extract summary with fallback to description or content
            summary = ""
            if hasattr(entry, 'summary'):
                summary = entry.summary
            elif hasattr(entry, 'description'):
                summary = entry.description
            elif hasattr(entry, 'content') and entry.content:
                summary = entry.content[0].value
                
            # Clean up HTML from summary (simplified approach)
            summary_text = re.sub(r'<.*?>', '', summary)
            summary_text = summary_text[:250] + '...' if len(summary_text) > 250 else summary_text
            
            # Get full text for analysis
            full_text = entry.title + " " + summary_text
            
            # Generate unique hash for deduplication
            article_hash = generate_article_hash(entry.title, entry.link)
            
            # Extract image URL if available
            image_url = extract_image_url(entry)
            
            # Check if it's breaking news
            breaking = is_breaking_news(entry.title, summary_text)
            
            # Calculate sentiment
            sentiment = calculate_sentiment(full_text)
            
            # Categorize the article
            categories = detect_categories(full_text)
            
            article = {
                'id': article_hash,
                'title': entry.title,
                'link': entry.link,
                'source': source_name,
                'published_date': published,
                'summary': summary_text,
                'sentiment': sentiment,
                'categories': categories,
                'breaking_news': breaking,
                'image_url': image_url,
                'popularity': 0  # Initial popularity score
            }
            articles.append(article)
            
        # Remove source from failed sources if successful
        if source_name in health_status["failed_sources"]:
            del health_status["failed_sources"][source_name]
            
        logger.info(f"Successfully fetched {len(articles)} articles from {source_name}")
        return articles
        
    except Exception as e:
        error_msg = str(e)
        logger.error(f"Error fetching feed {source_name}: {error_msg}")
        health_status["failed_sources"][source_name] = error_msg
        return []

def process_article_for_api(article):
    """Ensure an article has all required fields for the frontend"""
    # Create a copy to avoid modifying the original
    processed = article.copy()
    
    # Ensure required fields exist
    if 'id' not in processed:
        processed['id'] = generate_article_hash(processed.get('title', ''), processed.get('link', ''))
    
    if 'categories' not in processed:
        processed['categories'] = ["General"]
    elif not isinstance(processed['categories'], list):
        processed['categories'] = [processed['categories']]
    
    if 'breaking_news' not in processed:
        processed['breaking_news'] = False
    
    if 'sentiment' not in processed:
        processed['sentiment'] = 'neutral'
    
    if 'image_url' not in processed:
        processed['image_url'] = None
    
    # Ensure title, summary, and other text fields are strings
    for field in ['title', 'summary', 'source']:
        if field not in processed:
            processed[field] = ""
        elif processed[field] is None:
            processed[field] = ""
    
    # Ensure link is valid
    if 'link' not in processed or not processed['link']:
        processed['link'] = "#"
    
    # Validate dates
    if 'published_date' not in processed or not processed['published_date']:
        processed['published_date'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    
    return processed

def deduplicate_articles(articles):
    """Remove duplicate articles based on content similarity"""
    global duplicate_count
    
    unique_articles = {}
    duplicates = 0
    
    for article in articles:
        article_id = article['id']
        
        if article_id not in unique_articles:
            unique_articles[article_id] = article
        else:
            # If this is a breaking news but the original isn't, prioritize this one
            if article['breaking_news'] and not unique_articles[article_id]['breaking_news']:
                unique_articles[article_id] = article
            # Or if this is from a more reputable source (simple implementation)
            elif "New York Times" in article['source'] or "BBC" in article['source']:
                unique_articles[article_id] = article
            
            duplicates += 1
    
    duplicate_count += duplicates
    logger.info(f"Removed {duplicates} duplicate articles")
    return list(unique_articles.values())

def update_trending_score(articles):
    """Calculate trending score for articles based on recency and source"""
    trending_articles = []
    current_time = datetime.now()
    
    for article in articles:
        # Parse published date
        try:
            pub_date = datetime.strptime(article['published_date'], '%Y-%m-%d %H:%M:%S')
            # Calculate hours since publication
            hours_ago = (current_time - pub_date).total_seconds() / 3600
            
            # Base score calculation (recency-based)
            if hours_ago < 1:
                time_score = 10
            elif hours_ago < 3:
                time_score = 8
            elif hours_ago < 6:
                time_score = 6
            elif hours_ago < 12:
                time_score = 4
            elif hours_ago < 24:
                time_score = 2
            else:
                time_score = 1
                
            # Adjust score based on source reputation (simple implementation)
            source_bonus = 1.0
            if "New York Times" in article['source'] or "BBC" in article['source']:
                source_bonus = 1.5
            
            # Breaking news bonus
            breaking_bonus = 3.0 if article['breaking_news'] else 1.0
            
            # Calculate final score
            article['trending_score'] = time_score * source_bonus * breaking_bonus
            trending_articles.append(article)
            
        except Exception as e:
            logger.error(f"Error calculating trending score: {str(e)}")
            article['trending_score'] = 0
            trending_articles.append(article)
    
    # Sort by trending score
    trending_articles.sort(key=lambda x: x['trending_score'], reverse=True)
    return trending_articles[:20]  # Return top 20 trending

def update_source_stats(articles):
    """Update statistics about sources"""
    global source_stats
    
    # Count articles per source
    source_counts = Counter([article['source'] for article in articles])
    
    # Count breaking news per source
    breaking_counts = Counter([article['source'] for article in articles if article['breaking_news']])
    
    # Count sentiment per source
    sentiment_counts = {}
    for article in articles:
        source = article['source']
        sentiment = article['sentiment']
        
        if source not in sentiment_counts:
            sentiment_counts[source] = {'positive': 0, 'negative': 0, 'neutral': 0}
        
        sentiment_counts[source][sentiment] += 1
    
    # Update the global stats
    with cache_lock:
        for source in source_counts:
            if source not in source_stats:
                source_stats[source] = {
                    'total_articles': 0,
                    'breaking_news': 0,
                    'sentiment': {'positive': 0, 'negative': 0, 'neutral': 0}
                }
            
            source_stats[source]['total_articles'] += source_counts[source]
            source_stats[source]['breaking_news'] += breaking_counts.get(source, 0)
            
            if source in sentiment_counts:
                for sentiment_type in ['positive', 'negative', 'neutral']:
                    source_stats[source]['sentiment'][sentiment_type] += sentiment_counts[source].get(sentiment_type, 0)

def update_category_cache(articles):
    """Update the category cache with articles by category"""
    global category_cache
    
    # Initialize category dictionary
    categories_dict = {category: [] for category in CATEGORIES.keys()}
    categories_dict["General"] = []  # Add General category
    
    # Add articles to their categories
    for article in articles:
        if 'categories' in article:
            for category in article['categories']:
                # Add to specific category
                if category in categories_dict:
                    categories_dict[category].append(article)
                else:
                    categories_dict["General"].append(article)
    
    # Sort articles in each category by published date
    for category in categories_dict:
        categories_dict[category].sort(key=lambda x: x.get('published_date', ''), reverse=True)
        # Limit to top 50 articles per category
        categories_dict[category] = categories_dict[category][:50]
    
    # Update the global cache thread-safely
    with cache_lock:
        category_cache = categories_dict

def store_in_redis(key, data, expiry=3600):
    """Store data in Redis if available"""
    if redis_client:
        try:
            redis_client.setex(key, expiry, json.dumps(data))
            return True
        except Exception as e:
            logger.error(f"Redis error: {str(e)}")
    return False

def get_from_redis(key):
    """Retrieve data from Redis if available"""
    if redis_client:
        try:
            data = redis_client.get(key)
            if data:
                return json.loads(data)
        except Exception as e:
            logger.error(f"Redis error: {str(e)}")
    return None

def update_feeds():
    """Fetch all RSS feeds and update the cache with enhanced processing"""
    global feed_cache, trending_cache, health_status
    
    while True:
        try:
            logger.info("Starting RSS feed update cycle")
            start_time = time.time()
            
            session = get_session()
            all_articles = []
            
            # Fetch all feeds
            for source_name, feed_url in RSS_FEEDS.items():
                articles = fetch_rss_feed(source_name, feed_url, session)
                all_articles.extend(articles)
            
            # Process only if we have articles
            if all_articles:
                # Deduplicate articles
                unique_articles = deduplicate_articles(all_articles)
                
                # Sort by published date (newest first)
                unique_articles.sort(key=lambda x: x.get('published_date', ''), reverse=True)
                
                # Prioritize breaking news
                breaking_news = [a for a in unique_articles if a['breaking_news']]
                non_breaking = [a for a in unique_articles if not a['breaking_news']]
                prioritized_articles = breaking_news + non_breaking
                
                # Process articles for API consistency
                prioritized_articles = [process_article_for_api(a) for a in prioritized_articles]
                
                # Update trending articles
                trending_articles = update_trending_score(unique_articles.copy())
                trending_articles = [process_article_for_api(a) for a in trending_articles]
                
                # Update source statistics
                update_source_stats(unique_articles)
                
                # Update category cache
                update_category_cache(unique_articles)
                
                # Update the cache thread-safely
                with cache_lock:
                    feed_cache = prioritized_articles
                    trending_cache = trending_articles
                    health_status["last_successful_update"] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                
                # Store in Redis if available
                store_in_redis("feed_cache", prioritized_articles)
                store_in_redis("trending_cache", trending_articles)
                store_in_redis("source_stats", source_stats)
                store_in_redis("category_cache", category_cache)
            
            elapsed_time = time.time() - start_time
            logger.info(f"Feed update completed in {elapsed_time:.2f} seconds, fetched {len(all_articles)} articles, {len(feed_cache)} after deduplication")
            
            # Sleep for 15 seconds before the next update
            time.sleep(15)
            
        except Exception as e:
            logger.error(f"Error in update thread: {str(e)}")
            time.sleep(15)  # Sleep and try again even if there's an error

@app.route('/rss', methods=['GET'])
def get_rss():
    """API endpoint to get the latest RSS feed data with filtering options"""
    logger.info("API request received for /rss endpoint")
    
    # Get query parameters
    source = request.args.get('source')
    category = request.args.get('category')
    sentiment = request.args.get('sentiment')
    breaking_only = request.args.get('breaking', 'false').lower() == 'true'
    search_query = request.args.get('q')
    
    # Default sorting is by date, but can be changed to trending
    sort_by = request.args.get('sort', 'date').lower()
    
    # Pagination parameters
    page = int(request.args.get('page', 1))
    page_size = min(int(request.args.get('size', 25)), 100)  # Limit max size to 100
    
    # Copy the current cache
    with cache_lock:
        if sort_by == 'trending':
            current_cache = trending_cache.copy()
        else:
            current_cache = feed_cache.copy()
    
    # Debug: Log cache size
    logger.info(f"Cache size: {len(current_cache)} articles before filtering")
    
    # Apply filters
    filtered_articles = current_cache
    
    if source:
        filtered_articles = [a for a in filtered_articles if source.lower() in a['source'].lower()]
    
    if category:
        filtered_articles = [a for a in filtered_articles if category in a.get('categories', [])]
    
    if sentiment:
        filtered_articles = [a for a in filtered_articles if a.get('sentiment') == sentiment]
    
    if breaking_only:
        filtered_articles = [a for a in filtered_articles if a.get('breaking_news', False)]
    
    if search_query:
        query = search_query.lower()
        filtered_articles = [a for a in filtered_articles if 
                            query in a.get('title', '').lower() or 
                            query in a.get('summary', '').lower()]
    
    # Calculate total results and pages
    total_results = len(filtered_articles)
    total_pages = max(1, (total_results + page_size - 1) // page_size) if total_results > 0 else 1
    
    # Apply pagination
    start_idx = min((page - 1) * page_size, total_results) if total_results > 0 else 0
    end_idx = min(start_idx + page_size, total_results)
    paginated_articles = filtered_articles[start_idx:end_idx] if total_results > 0 else []
    
    # Make sure articles are fully populated
    for article in paginated_articles:
        # Ensure categories is always a list
        if 'categories' not in article:
            article['categories'] = ["General"]
        elif not isinstance(article['categories'], list):
            article['categories'] = [article['categories']]
            
        # Ensure breaking_news is always present
        if 'breaking_news' not in article:
            article['breaking_news'] = False
            
        # Ensure other required fields are present
        if 'sentiment' not in article:
            article['sentiment'] = 'neutral'
        if 'image_url' not in article:
            article['image_url'] = None
    
    # Debug: Log how many articles are being returned
    logger.info(f"Returning {len(paginated_articles)} articles after filtering and pagination")
    
    return jsonify({
        'status': 'success',
        'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'total_results': total_results,
        'page': page,
        'total_pages': total_pages,
        'page_size': page_size,
        'articles': paginated_articles
    })

@app.route('/trending', methods=['GET'])
def get_trending():
    """API endpoint to get trending articles"""
    logger.info("API request received for /trending endpoint")
    
    with cache_lock:
        current_trending = trending_cache.copy()
    
    # Make sure articles are fully populated
    for article in current_trending:
        # Ensure categories is always a list
        if 'categories' not in article:
            article['categories'] = ["General"]
        elif not isinstance(article['categories'], list):
            article['categories'] = [article['categories']]
            
        # Ensure breaking_news is always present
        if 'breaking_news' not in article:
            article['breaking_news'] = False
            
        # Ensure other required fields are present
        if 'sentiment' not in article:
            article['sentiment'] = 'neutral'
        if 'image_url' not in article:
            article['image_url'] = None
    
    logger.info(f"Returning {len(current_trending)} trending articles")
    
    return jsonify({
        'status': 'success',
        'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'count': len(current_trending),
        'articles': current_trending
    })

@app.route('/categories', methods=['GET'])
def get_categories():
    """API endpoint to get available categories"""
    logger.info("API request received for /categories endpoint")
    
    return jsonify({
        'status': 'success',
        'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'categories': list(CATEGORIES.keys()) + ["General"]
    })

@app.route('/category/<category>', methods=['GET'])
def get_category(category):
    """API endpoint to get articles by category"""
    logger.info(f"API request received for category: {category}")
    
    with cache_lock:
        if category in category_cache:
            articles = category_cache[category].copy()
        else:
            articles = []
    
    # Make sure articles are fully populated
    for article in articles:
        # Ensure categories is always a list
        if 'categories' not in article:
            article['categories'] = [category]
        elif not isinstance(article['categories'], list):
            article['categories'] = [article['categories']]
            
        # Ensure breaking_news is always present
        if 'breaking_news' not in article:
            article['breaking_news'] = False
            
        # Ensure other required fields are present
        if 'sentiment' not in article:
            article['sentiment'] = 'neutral'
        if 'image_url' not in article:
            article['image_url'] = None
    
    logger.info(f"Returning {len(articles)} articles for category: {category}")
    
    return jsonify({
        'status': 'success',
        'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'category': category,
        'count': len(articles),
        'articles': articles
    })

@app.route('/breaking', methods=['GET'])
def get_breaking():
    """API endpoint to get breaking news articles"""
    logger.info("API request received for breaking news")
    
    with cache_lock:
        breaking_articles = [a for a in feed_cache if a.get('breaking_news', False)]
    
    # Make sure articles are fully populated
    for article in breaking_articles:
        # Ensure categories is always a list
        if 'categories' not in article:
            article['categories'] = ["General"]
        elif not isinstance(article['categories'], list):
            article['categories'] = [article['categories']]
            
        # Ensure other required fields are present
        if 'sentiment' not in article:
            article['sentiment'] = 'neutral'
        if 'image_url' not in article:
            article['image_url'] = None
    
    logger.info(f"Returning {len(breaking_articles)} breaking news articles")
    
    return jsonify({
        'status': 'success',
        'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'count': len(breaking_articles),
        'articles': breaking_articles
    })

@app.route('/sources', methods=['GET'])
def get_sources():
    """API endpoint to get information about sources"""
    logger.info("API request received for sources information")
    
    with cache_lock:
        stats = source_stats.copy()
    
    return jsonify({
        'status': 'success',
        'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'sources': RSS_FEEDS,
        'stats': stats
    })

@app.route('/health', methods=['GET'])
def get_health():
    """API endpoint to get system health status"""
    logger.info("API request received for health status")
    
    with cache_lock:
        status = {
            'status': 'healthy' if health_status["last_successful_update"] else 'initializing',
            'last_update': health_status["last_successful_update"],
            'cache_size': len(feed_cache),
            'uptime': str(datetime.now() - app.start_time),
            'failed_sources': health_status["failed_sources"],
            'duplicate_count': duplicate_count
        }
    
    return jsonify(status)

@app.route('/', methods=['GET'])
def index():
    """Root endpoint now serves the web interface"""
    return render_template('index.html')

@app.route('/api', methods=['GET'])
def api_docs():
    """API documentation endpoint"""
    return jsonify({
        'service': 'Entertainment RSS Feed Aggregator API',
        'version': '2.0',
        'updated_every': '15 seconds',
        'endpoints': {
            '/rss': {
                'description': 'Get the latest entertainment news with filtering options',
                'parameters': {
                    ''/rss': {
                'description': 'Get the latest entertainment news with filtering options',
                'parameters': {
                    'source': 'Filter by news source',
                    'category': 'Filter by category',
                    'sentiment': 'Filter by sentiment (positive, negative, neutral)',
                    'breaking': 'Show only breaking news (true/false)',
                    'q': 'Search in title and summary',
                    'sort': 'Sort by date or trending',
                    'page': 'Page number for pagination',
                    'size': 'Number of results per page (max 100)'
                }
            },
            '/trending': 'Get trending entertainment news',
            '/categories': 'Get list of available categories',
            '/category/{name}': 'Get articles by category',
            '/breaking': 'Get breaking news only',
            '/sources': 'Get information about news sources',
            '/health': 'Get system health status'
        }
    })

def start_background_thread():
    """Start the background thread for feed updates"""
    thread = threading.Thread(target=update_feeds, daemon=True)
    thread.start()
    logger.info("Background update thread started")

def initialize_app():
    """Initialize the application"""
    # Set start time for uptime tracking
    app.start_time = datetime.now()
    
    # Create the static directory if it doesn't exist
    os.makedirs('static', exist_ok=True)
    
    # Create the templates directory if it doesn't exist
    os.makedirs('templates', exist_ok=True)
    
    # Start the feed updater in a background thread
    start_background_thread()

# Initialize the app when the module is loaded
initialize_app()

if __name__ == '__main__':
    # Determine the port to use (for Render.com compatibility)
    port = int(os.environ.get('PORT', 5000))
    
    # Start the Flask server
    logger.info(f"Starting Flask application on port {port}")
    app.run(host='0.0.0.0', port=port)
