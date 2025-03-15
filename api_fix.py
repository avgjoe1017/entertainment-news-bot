"""
This is a standalone Python file to replace specific sections of your app.py file.
Copy these functions into your app.py to fix the API responses.
"""

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
