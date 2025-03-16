# 🎬 Entertainment News Aggregator API

A Flask-based API that aggregates and categorizes entertainment news from reputable RSS feeds, analyzing sentiment, trending scores, and highlighting breaking news.

## 🚀 Key Features
- **Multi-source aggregation:** Fetches latest entertainment news from top sources (e.g., BBC, Variety, TMZ).
- **Categorization:** Automatically categorizes articles into Movies, TV, Music, Celebrity, Gaming, Tech, and more.
- **Sentiment Analysis:** Uses NLTK sentiment analysis to categorize articles as positive, negative, or neutral.
- **Trending and Breaking News:** Identifies breaking stories and calculates trending scores to highlight important news.

## 📡 API Endpoints

| Endpoint                  | Description                                             |
|---------------------------|---------------------------------------------------------|
| `/rss`                    | Fetch articles with filters (source, category, sentiment, etc.) |
| `/trending`               | Retrieve top trending articles                          |
| `/breaking`               | Access latest breaking news articles                    |
| `/categories`             | List available news categories                          |
| `/category/<category>`    | Fetch news articles by specific category                |
| `/sources`                | View available news sources and statistics              |
| `/health`                 | Check the health and status of the aggregator           |

## 📦 Dependencies
- `Flask`
- `feedparser`
- `requests`
- `nltk`
- `flask-cors`
- `redis` (optional caching)

## 🗃 Optional Redis Caching
To enable caching, set the environment variable:


## 🌟 Future Roadmap
- Improved frontend integration
- User-customizable news feeds
- Advanced analytics dashboards

## 🤝 Contributing
Pull requests are welcome. Feel free to fork, enhance, and submit improvements.

## 📌 Deployed on Cloud (Render.com, Heroku, etc.)
This application runs on cloud services, so no local setup is required for end users.

